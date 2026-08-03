"""Configurable CSV preflight, parsing, and structured diagnostics."""

from __future__ import annotations

import csv
import io
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pandas.errors import EmptyDataError, ParserError

SUPPORTED_DELIMITERS = (",", ";", "\t", "|")
DEFAULT_MISSING_TOKENS = ("", "NA", "N/A", "NULL", "null", "None", "-")


class CsvIngestionError(ValueError):
    """Raised when CSV preflight or parsing cannot safely continue."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.diagnostics: dict[str, Any] = {
            "status": "failed",
            "warnings": [message],
        }


@dataclass(frozen=True)
class CsvReadConfig:
    """Explicit settings for deterministic CSV ingestion."""

    encoding: str | None = None
    delimiter: str | None = None
    quote_character: str = '"'
    header_row: int | None = 0
    missing_value_tokens: tuple[str, ...] = DEFAULT_MISSING_TOKENS
    parsing_mode: Literal["strict", "warn"] = "strict"
    analysis_mode: Literal["exact", "chunked", "sampled"] = "exact"
    preview_row_limit: int = 10
    chunk_size: int = 50_000
    sample_size: int = 10_000
    sample_seed: int = 42

    def __post_init__(self) -> None:
        if self.delimiter is not None and len(self.delimiter) != 1:
            raise ValueError("Delimiter harus tepat satu karakter.")
        if len(self.quote_character) != 1:
            raise ValueError("Quote character harus tepat satu karakter.")
        if self.preview_row_limit < 1 or self.chunk_size < 1 or self.sample_size < 1:
            raise ValueError("Batas preview, chunk, dan sample harus minimal 1.")


def build_csv_read_config(
    *,
    encoding: str | None = None,
    delimiter: str | None = None,
    quote_character: str | None = None,
    parsing_mode: Literal["strict", "warn"] | None = None,
    analysis_mode: Literal["exact", "chunked", "sampled"] | None = None,
    chunk_size: int | None = None,
    sample_size: int | None = None,
    sample_seed: int | None = None,
    base_config: CsvReadConfig | None = None,
) -> CsvReadConfig:
    """Build reader settings while retaining defaults from one base config."""
    defaults = base_config or CsvReadConfig()
    return CsvReadConfig(
        encoding=encoding,
        delimiter=delimiter,
        quote_character=quote_character or defaults.quote_character,
        header_row=defaults.header_row,
        missing_value_tokens=defaults.missing_value_tokens,
        parsing_mode=parsing_mode or defaults.parsing_mode,
        analysis_mode=analysis_mode or defaults.analysis_mode,
        preview_row_limit=defaults.preview_row_limit,
        chunk_size=int(chunk_size if chunk_size is not None else defaults.chunk_size),
        sample_size=int(sample_size if sample_size is not None else defaults.sample_size),
        sample_seed=int(sample_seed if sample_seed is not None else defaults.sample_seed),
    )


@dataclass
class CsvIngestionResult:
    """CSV data plus JSON-safe preflight and ingestion diagnostics."""

    dataframe: pd.DataFrame
    diagnostics: dict[str, Any]
    preflight: dict[str, Any]


def _decode_bytes(raw: bytes, requested_encoding: str | None) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    encodings = [requested_encoding] if requested_encoding else ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
    for index, encoding in enumerate(encodings):
        if encoding is None:
            continue
        try:
            text = raw.decode(encoding)
            if requested_encoding is None and index > 0:
                warnings.append(f"Encoding otomatis menggunakan fallback {encoding}.")
            return text, encoding, warnings
        except UnicodeDecodeError:
            continue
    selected = requested_encoding or "encoding yang didukung"
    raise CsvIngestionError(f"Encoding tidak sesuai untuk membaca file CSV: {selected}")


def _detect_delimiter(sample: str, override: str | None) -> tuple[str, list[str]]:
    if override is not None:
        return override, []
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(SUPPORTED_DELIMITERS))
        return dialect.delimiter, []
    except csv.Error:
        return ",", ["Delimiter tidak dapat dideteksi; fallback koma digunakan."]


def preflight_csv(file_path: str | Path, config: CsvReadConfig | None = None) -> dict[str, Any]:
    """Inspect raw CSV structure without modifying or fully loading the source."""
    path = Path(file_path)
    settings = config or CsvReadConfig()
    if not path.exists():
        raise CsvIngestionError(f"File CSV tidak ditemukan: {path}")
    if not path.is_file():
        raise CsvIngestionError(f"Path bukan file CSV: {path}")
    raw = path.read_bytes()
    if not raw:
        raise CsvIngestionError(f"File CSV kosong: {path}")
    text, encoding, warnings = _decode_bytes(raw, settings.encoding)
    delimiter, delimiter_warnings = _detect_delimiter(text[:65_536], settings.delimiter)
    warnings.extend(delimiter_warnings)
    header: list[str] = []
    expected = 0
    row_count = 0
    data_row_count = 0
    malformed: list[dict[str, int]] = []
    malformed_count = 0
    excessive_field_count = 0
    field_counts: set[int] = set()
    try:
        reader = csv.reader(
            io.StringIO(text, newline=""), delimiter=delimiter,
            quotechar=settings.quote_character, strict=True,
        )
        for row_index, row in enumerate(reader):
            row_count += 1
            field_counts.add(len(row))
            if settings.header_row is not None and row_index == settings.header_row:
                header = row
                expected = len(row)
                continue
            if settings.header_row is None and row_index == 0:
                expected = len(row)
            if settings.header_row is not None and row_index <= settings.header_row:
                continue
            data_row_count += 1
            if len(row) != expected:
                malformed_count += 1
                if len(row) > expected:
                    excessive_field_count += 1
                if len(malformed) < 10:
                    malformed.append({
                        "line": int(reader.line_num),
                        "field_count": len(row),
                        "expected_fields": expected,
                    })
    except csv.Error as error:
        raise CsvIngestionError(f"CSV gagal diparsing saat preflight: {error}") from error
    if row_count == 0 or not text.strip():
        raise CsvIngestionError(f"File CSV kosong: {path}")
    duplicates = sorted({name for name in header if name and header.count(name) > 1})
    unnamed = [index for index, name in enumerate(header) if not name.strip()]
    if len(field_counts) > 1:
        warnings.append("Jumlah field antarbaris tidak konsisten.")
    if duplicates:
        warnings.append("Nama header duplikat terdeteksi dan dipertahankan pada hasil parsing.")
    if unnamed:
        warnings.append("Kolom tanpa nama terdeteksi.")
    if expected == 1 and any(candidate in text[:65_536] for candidate in SUPPORTED_DELIMITERS if candidate != delimiter):
        warnings.append("Hanya satu kolom terdeteksi; periksa kembali delimiter yang dipilih.")
    return {
        "file_size_bytes": len(raw),
        "encoding": encoding,
        "delimiter": delimiter,
        "quote_character": settings.quote_character,
        "estimated_columns": expected,
        "has_header": settings.header_row is not None,
        "original_headers": header,
        "duplicate_headers": duplicates,
        "unnamed_columns": unnamed,
        "field_count_consistent": malformed_count == 0,
        "malformed_rows": malformed_count,
        "malformed_examples": malformed,
        "excessive_field_rows": excessive_field_count,
        "estimated_data_rows": data_row_count,
        "warnings": warnings,
    }


def _sample_chunks(chunks: Any, sample_size: int, seed: int) -> tuple[pd.DataFrame, int]:
    rng = random.Random(seed)
    reservoir: list[dict[str, Any]] = []
    columns: list[Any] = []
    seen = 0
    for chunk in chunks:
        columns = list(chunk.columns)
        for record in chunk.to_dict(orient="records"):
            seen += 1
            if len(reservoir) < sample_size:
                reservoir.append(record)
            else:
                index = rng.randrange(seen)
                if index < sample_size:
                    reservoir[index] = record
    return pd.DataFrame(reservoir, columns=columns), seen


def read_csv_with_diagnostics(
    file_path: str | Path, config: CsvReadConfig | None = None
) -> CsvIngestionResult:
    """Read CSV using explicit settings and return structured diagnostics."""
    path = Path(file_path)
    settings = config or CsvReadConfig()
    preflight = preflight_csv(path, settings)
    excessive_fields = [
        item for item in preflight["malformed_examples"]
        if item["field_count"] > item["expected_fields"]
    ]
    if settings.parsing_mode == "strict" and excessive_fields:
        lines = ", ".join(str(item["line"]) for item in excessive_fields)
        raise CsvIngestionError(
            f"CSV gagal diparsing: field berlebih pada baris {lines}."
        )
    bad_lines: Literal["error", "skip"] = "error" if settings.parsing_mode == "strict" else "skip"
    read_kwargs: dict[str, Any] = {
        "encoding": preflight["encoding"],
        "sep": preflight["delimiter"],
        "quotechar": settings.quote_character,
        "header": settings.header_row,
        "na_values": list(settings.missing_value_tokens),
        "keep_default_na": True,
        "on_bad_lines": bad_lines,
    }
    try:
        if settings.analysis_mode == "exact":
            dataframe = pd.read_csv(path, **read_kwargs)
            total_rows = len(dataframe)
        else:
            chunks = pd.read_csv(path, chunksize=settings.chunk_size, **read_kwargs)
            if settings.analysis_mode == "chunked":
                loaded = list(chunks)
                dataframe = pd.concat(loaded, ignore_index=True) if loaded else pd.DataFrame()
                total_rows = len(dataframe)
            else:
                dataframe, total_rows = _sample_chunks(chunks, settings.sample_size, settings.sample_seed)
    except EmptyDataError as error:
        raise CsvIngestionError(f"File CSV kosong: {path}") from error
    except (ParserError, UnicodeDecodeError) as error:
        raise CsvIngestionError(f"CSV gagal diparsing: {error}") from error

    parsed_headers = [str(column) for column in dataframe.columns]
    rows_skipped = preflight["excessive_field_rows"] if settings.parsing_mode == "warn" else 0
    warnings = list(preflight["warnings"])
    if rows_skipped:
        warnings.append(f"{rows_skipped} baris malformed dilewati sesuai parsing_mode='warn'.")
    sampling_applied = (
        settings.analysis_mode == "sampled"
        and settings.sample_size < total_rows
    )
    if sampling_applied:
        warnings.append("Analisis menggunakan sampel deterministik, bukan seluruh baris.")
    elif settings.analysis_mode == "sampled":
        warnings.append(
            "Mode sampled dipilih, tetapi ukuran sampel mencakup seluruh "
            "dataset; seluruh baris dianalisis."
        )
    if settings.analysis_mode == "chunked":
        warnings.append(
            "File dibaca bertahap, tetapi seluruh chunk masih digabung ke memori "
            "untuk pemeriksaan global."
        )
    status = "success_with_warnings" if warnings else "success"
    diagnostics = {
        "status": status,
        "mode": settings.analysis_mode,
        "analysis_scope": "sampled" if sampling_applied else "full",
        "memory_strategy": (
            "combined_dataframe"
            if settings.analysis_mode == "chunked"
            else "reservoir_sample"
            if settings.analysis_mode == "sampled"
            else "single_dataframe"
        ),
        "encoding": preflight["encoding"],
        "delimiter": preflight["delimiter"],
        "quote_character": settings.quote_character,
        "rows_loaded": len(dataframe),
        "total_rows": total_rows,
        "sampled_rows": len(dataframe) if settings.analysis_mode == "sampled" else 0,
        "sampling_applied": sampling_applied,
        "columns_loaded": dataframe.shape[1],
        "malformed_rows": preflight["malformed_rows"],
        "malformed_examples": preflight["malformed_examples"],
        "rows_skipped": rows_skipped,
        "duplicate_headers": preflight["duplicate_headers"],
        "unnamed_columns": preflight["unnamed_columns"],
        "original_headers": preflight["original_headers"],
        "parsed_headers": parsed_headers,
        "warnings": warnings,
    }
    if settings.analysis_mode == "chunked":
        diagnostics["chunk_size_requested"] = settings.chunk_size
    if settings.analysis_mode == "sampled":
        diagnostics.update(
            {
                "sampling_method": "reservoir_sampling",
                "sample_size_requested": settings.sample_size,
                "sample_seed": settings.sample_seed,
            }
        )
    return CsvIngestionResult(dataframe=dataframe, diagnostics=diagnostics, preflight=preflight)
