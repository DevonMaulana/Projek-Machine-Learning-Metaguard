import json
from pathlib import Path

import pandas as pd
import pytest

from core.csv_ingestion import (
    CsvIngestionError,
    CsvReadConfig,
    preflight_csv,
    read_csv_with_diagnostics,
)
from core.data_profiler import profile_dataframe
from core.quality_checker import run_quality_checks
from core.report_builder import build_report
from core.scoring import calculate_score


@pytest.mark.parametrize(("delimiter", "label"), [(";", "semicolon"), ("\t", "tab"), ("|", "pipe")])
def test_detects_supported_delimiters(tmp_path: Path, delimiter: str, label: str):
    path = tmp_path / f"{label}.csv"
    path.write_text(f"name{delimiter}value\nalpha{delimiter}1\n", encoding="utf-8")
    result = read_csv_with_diagnostics(path)
    assert result.diagnostics["delimiter"] == delimiter
    assert result.dataframe.to_dict("records") == [{"name": "alpha", "value": 1}]


def test_utf8_bom_and_fallback_encoding_are_recorded(tmp_path: Path):
    bom = tmp_path / "bom.csv"
    bom.write_text("nama,kota\nAndi,Bandung\n", encoding="utf-8-sig")
    assert read_csv_with_diagnostics(bom).diagnostics["encoding"] == "utf-8-sig"
    cp1252 = tmp_path / "cp1252.csv"
    cp1252.write_bytes("nama,kota\nAndré,Bandung\n".encode("cp1252"))
    result = read_csv_with_diagnostics(cp1252)
    assert result.diagnostics["encoding"] == "cp1252"
    assert result.diagnostics["status"] == "success_with_warnings"


def test_quoted_delimiter_quote_and_newline(tmp_path: Path):
    path = tmp_path / "quoted.csv"
    path.write_text('id,text\n1,"a,b"\n2,"kata ""kutip"""\n3,"dua\nbaris"\n', encoding="utf-8")
    frame = read_csv_with_diagnostics(path).dataframe
    assert frame.loc[0, "text"] == "a,b"
    assert frame.loc[1, "text"] == 'kata "kutip"'
    assert frame.loc[2, "text"].replace("\r\n", "\n") == "dua\nbaris"


def test_duplicate_and_unnamed_headers_are_not_hidden(tmp_path: Path):
    path = tmp_path / "headers.csv"
    path.write_text("id,id,,value\n1,2,x,3\n", encoding="utf-8")
    result = read_csv_with_diagnostics(path)
    assert list(result.dataframe.columns) == ["id", "id.1", "Unnamed: 2", "value"]
    assert result.diagnostics["duplicate_headers"] == ["id"]
    assert result.diagnostics["unnamed_columns"] == [2]
    assert result.diagnostics["original_headers"] == ["id", "id", "", "value"]
    assert result.diagnostics["parsed_headers"] == ["id", "id.1", "Unnamed: 2", "value"]


def test_duplicate_headers_keep_original_and_parsed_diagnostics(tmp_path: Path):
    path = tmp_path / "duplicate_names.csv"
    path.write_text("id,nama,nama\n1,A,B\n", encoding="utf-8")
    result = read_csv_with_diagnostics(path)
    assert result.diagnostics["original_headers"] == ["id", "nama", "nama"]
    assert result.diagnostics["parsed_headers"] == ["id", "nama", "nama.1"]
    assert result.diagnostics["duplicate_headers"] == ["nama"]


def test_short_row_is_diagnosed_and_extra_row_fails_strict(tmp_path: Path):
    short = tmp_path / "short.csv"
    short.write_text("a,b,c\n1,2\n", encoding="utf-8")
    result = read_csv_with_diagnostics(short)
    assert result.diagnostics["malformed_rows"] == 1
    assert result.diagnostics["malformed_examples"][0]["line"] == 2
    extra = tmp_path / "extra.csv"
    extra.write_text("a,b\n1,2,3\n", encoding="utf-8")
    with pytest.raises(CsvIngestionError, match="gagal diparsing") as error:
        read_csv_with_diagnostics(extra)
    assert error.value.diagnostics["status"] == "failed"
    json.dumps(error.value.diagnostics)


def test_warn_mode_records_skipped_malformed_rows(tmp_path: Path):
    path = tmp_path / "warn.csv"
    path.write_text("a,b\n1,2\n3,4,5\n", encoding="utf-8")
    result = read_csv_with_diagnostics(path, CsvReadConfig(parsing_mode="warn"))
    assert result.diagnostics["rows_skipped"] == 1
    assert result.diagnostics["status"] == "success_with_warnings"


def test_missing_tokens_mixed_types_long_text_and_many_columns(tmp_path: Path):
    path = tmp_path / "complex.csv"
    headers = [f"c{i}" for i in range(30)]
    row = ["NA", "NULL", "1", "text"] + ["x" * 200] * 26
    path.write_text(",".join(headers) + "\n" + ",".join(row) + "\n", encoding="utf-8")
    frame = read_csv_with_diagnostics(path).dataframe
    assert pd.isna(frame.iloc[0, 0]) and pd.isna(frame.iloc[0, 1])
    assert frame.shape == (1, 30)
    assert len(frame.iloc[0, 4]) == 200


def test_header_only_many_rows_and_source_unchanged(tmp_path: Path):
    header_only = tmp_path / "header.csv"
    header_only.write_text("a,b\n", encoding="utf-8")
    assert read_csv_with_diagnostics(header_only).dataframe.empty
    large = tmp_path / "large.csv"
    content = "id,value\n" + "".join(f"{i},{i % 10}\n" for i in range(20_000))
    large.write_text(content, encoding="utf-8")
    before = large.read_bytes()
    result = read_csv_with_diagnostics(large, CsvReadConfig(analysis_mode="chunked", chunk_size=1000))
    assert result.dataframe.shape == (20_000, 2)
    assert result.diagnostics["analysis_scope"] == "full"
    assert result.diagnostics["memory_strategy"] == "combined_dataframe"
    assert any("digabung ke memori" in warning for warning in result.diagnostics["warnings"])
    assert large.read_bytes() == before


def test_sampling_is_deterministic_and_disclosed(tmp_path: Path):
    path = tmp_path / "sample.csv"
    path.write_text("id,value\n" + "".join(f"{i},{i}\n" for i in range(1000)), encoding="utf-8")
    config = CsvReadConfig(analysis_mode="sampled", chunk_size=100, sample_size=50, sample_seed=7)
    first = read_csv_with_diagnostics(path, config)
    second = read_csv_with_diagnostics(path, config)
    pd.testing.assert_frame_equal(first.dataframe, second.dataframe)
    assert first.diagnostics["sampled_rows"] == 50
    assert first.diagnostics["total_rows"] == 1000
    assert first.diagnostics["analysis_scope"] == "sampled"


def test_duplicate_identifier_across_parser_chunks_is_detected(tmp_path: Path):
    path = tmp_path / "identifiers.csv"
    path.write_text("id_record,value\nA,1\nB,2\nA,3\n", encoding="utf-8")
    ingestion = read_csv_with_diagnostics(
        path, CsvReadConfig(analysis_mode="chunked", chunk_size=2)
    )
    findings = run_quality_checks(ingestion.dataframe)
    assert any(item["check_id"] == "duplicate_identifier" for item in findings)


def test_wrong_delimiter_warns_and_diagnostics_are_json_safe(tmp_path: Path):
    path = tmp_path / "wrong.csv"
    path.write_text("a;b\n1;2\n", encoding="utf-8")
    result = read_csv_with_diagnostics(path, CsvReadConfig(delimiter=","))
    assert any("satu kolom" in warning for warning in result.diagnostics["warnings"])
    json.dumps(result.diagnostics)
    json.dumps(result.preflight)


def test_complex_csv_to_report_integration(tmp_path: Path):
    path = tmp_path / "integration.csv"
    path.write_text("id;name;value\n1;Alpha;10\n1; Beta ;NA\n", encoding="utf-8")
    ingestion = read_csv_with_diagnostics(path)
    profile = profile_dataframe(ingestion.dataframe)
    findings = run_quality_checks(ingestion.dataframe)
    score = calculate_score(findings)
    report = build_report(profile, findings, score, ingestion=ingestion.diagnostics)
    assert report["ingestion"]["delimiter"] == ";"
    json.dumps(report)
