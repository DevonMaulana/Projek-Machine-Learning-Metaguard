import json
from pathlib import Path

import pandas as pd
import pytest

from core.csv_ingestion import (
    CsvIngestionError,
    CsvReadConfig,
    build_csv_read_config,
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
    assert result.diagnostics["chunk_size_requested"] == 1000
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
    assert first.diagnostics["sampling_applied"] is True
    assert first.diagnostics["sampling_method"] == "reservoir_sampling"
    assert first.diagnostics["sample_size_requested"] == 50
    assert first.diagnostics["sample_seed"] == 7


def test_sampling_larger_than_dataset_loads_all_rows_with_warning(tmp_path: Path):
    path = tmp_path / "all_rows.csv"
    path.write_text("id\n1\n2\n3\n", encoding="utf-8")
    result = read_csv_with_diagnostics(
        path,
        CsvReadConfig(analysis_mode="sampled", sample_size=10, sample_seed=99),
    )
    assert result.diagnostics["sample_size_requested"] == 10
    assert result.diagnostics["sampled_rows"] == 3
    assert result.diagnostics["rows_loaded"] == 3
    assert result.diagnostics["total_rows"] == 3
    assert result.diagnostics["analysis_scope"] == "full"
    assert result.diagnostics["sampling_applied"] is False
    assert any("Mode sampled dipilih" in item for item in result.diagnostics["warnings"])
    assert not any("Analisis menggunakan sampel deterministik" in item for item in result.diagnostics["warnings"])


def test_sampling_size_equal_to_dataset_uses_full_scope(tmp_path: Path):
    path = tmp_path / "equal_rows.csv"
    path.write_text("id,value\n1,A\n2,B\n3,C\n", encoding="utf-8")
    sampled = read_csv_with_diagnostics(
        path, CsvReadConfig(analysis_mode="sampled", sample_size=3)
    )
    exact = read_csv_with_diagnostics(path, CsvReadConfig(analysis_mode="exact"))
    assert sampled.diagnostics["analysis_scope"] == "full"
    assert sampled.diagnostics["sampling_applied"] is False
    assert sampled.diagnostics["rows_loaded"] == sampled.diagnostics["total_rows"] == 3
    assert sampled.diagnostics["sampled_rows"] == 3
    pd.testing.assert_frame_equal(sampled.dataframe, exact.dataframe)
    assert run_quality_checks(sampled.dataframe) == run_quality_checks(exact.dataframe)


def test_sampling_with_different_seed_can_select_different_rows(tmp_path: Path):
    path = tmp_path / "seed.csv"
    path.write_text("id\n" + "".join(f"{value}\n" for value in range(100)), encoding="utf-8")
    first = read_csv_with_diagnostics(path, CsvReadConfig(analysis_mode="sampled", sample_size=10, sample_seed=1))
    second = read_csv_with_diagnostics(path, CsvReadConfig(analysis_mode="sampled", sample_size=10, sample_seed=2))
    assert first.dataframe["id"].tolist() != second.dataframe["id"].tolist()


def test_build_reader_config_preserves_defaults_and_accepts_ui_values():
    defaults = CsvReadConfig()
    config = build_csv_read_config(
        analysis_mode="chunked", chunk_size=2_000, base_config=defaults
    )
    assert config.chunk_size == 2_000
    assert config.sample_size == defaults.sample_size
    sampled = build_csv_read_config(
        analysis_mode="sampled", sample_size=500, sample_seed=5, base_config=defaults
    )
    assert sampled.sample_size == 500
    assert sampled.sample_seed == 5


def test_duplicate_identifier_across_parser_chunks_is_detected(tmp_path: Path):
    path = tmp_path / "identifiers.csv"
    path.write_text("id_record,value\nA,1\nB,2\nA,3\n", encoding="utf-8")
    ingestion = read_csv_with_diagnostics(
        path, CsvReadConfig(analysis_mode="chunked", chunk_size=2)
    )
    findings = run_quality_checks(ingestion.dataframe)
    assert any(item["check_id"] == "duplicate_identifier" for item in findings)


def test_chunked_result_matches_exact_result(tmp_path: Path):
    path = tmp_path / "equivalent.csv"
    path.write_text("id,value\n" + "".join(f"{value},{value % 3}\n" for value in range(20)), encoding="utf-8")
    exact = read_csv_with_diagnostics(path, CsvReadConfig(analysis_mode="exact"))
    chunked = read_csv_with_diagnostics(
        path, CsvReadConfig(analysis_mode="chunked", chunk_size=5)
    )
    pd.testing.assert_frame_equal(exact.dataframe, chunked.dataframe)


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
