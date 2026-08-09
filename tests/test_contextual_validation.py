"""Tests for deterministic metadata and cross-column contextual validation."""

from __future__ import annotations

import json

import pandas as pd

from core.contextual_validation import run_contextual_validation


def _metadata(**overrides: str) -> dict[str, str]:
    metadata = {"data_period": "2026", "geographic_scope": "Kabupaten Temanggung"}
    metadata.update(overrides)
    return metadata


def _findings(result: dict[str, object], check_id: str) -> list[dict[str, object]]:
    return [item for item in result["findings"] if item["check_id"] == check_id]


def test_period_match_is_consistent() -> None:
    dataframe = pd.DataFrame({"tanggal_pembaruan": ["2026-01-01", "2026-02-01", "2026-03-01"]})
    result = run_contextual_validation(dataframe, _metadata())
    assert result["status"] == "consistent"
    assert not _findings(result, "metadata_period_vs_dataset_dates")


def test_period_mismatch_is_potential_inconsistency() -> None:
    dataframe = pd.DataFrame({"tanggal": ["2026-01-01", "2026-02-01", "2026-03-01"]})
    result = run_contextual_validation(dataframe, _metadata(data_period="2025"))
    finding = _findings(result, "metadata_period_vs_dataset_dates")[0]
    assert result["status"] == "potential_inconsistency"
    assert finding["affected_rows"] == 3
    assert finding["observed_context"]["observed_years"] == [2026]


def test_period_requires_at_least_three_valid_dates_and_parsable_metadata() -> None:
    dataframe = pd.DataFrame({"tanggal": ["not-a-date", "2026-01-01"]})
    assert run_contextual_validation(dataframe, _metadata())["status"] == "not_evaluable"
    assert run_contextual_validation(
        pd.DataFrame({"tanggal": ["2026-01-01"] * 3}), _metadata(data_period="periode berjalan")
    )["status"] == "not_evaluable"


def test_period_threshold_is_deterministic() -> None:
    dataframe = pd.DataFrame({"tanggal": ["2026-01-01"] * 8 + ["2025-01-01"] * 2})
    assert not _findings(run_contextual_validation(dataframe, _metadata()), "metadata_period_vs_dataset_dates")
    dataframe.loc[7:, "tanggal"] = "2025-01-01"
    assert _findings(run_contextual_validation(dataframe, _metadata()), "metadata_period_vs_dataset_dates")


def test_geographic_scope_normalizes_case_whitespace_and_prefix() -> None:
    dataframe = pd.DataFrame({"nama_kabupaten": [" temanggung ", "Kabupaten Temanggung"]})
    result = run_contextual_validation(dataframe, _metadata())
    assert result["status"] == "consistent"


def test_geographic_scope_detects_multiple_regions() -> None:
    dataframe = pd.DataFrame({"kabupaten": ["Temanggung", "Wonosobo", "Temanggung"]})
    result = run_contextual_validation(dataframe, _metadata())
    finding = _findings(result, "metadata_geographic_scope_vs_dataset")[0]
    assert finding["affected_rows"] == 1
    assert finding["percentage"] == 33.33


def test_geographic_administrative_levels_are_not_collapsed() -> None:
    cases = (
        ("Kota Semarang", "kota", ["Semarang"], False),
        ("Kabupaten Semarang", "kabupaten", ["Semarang"], False),
        ("Kota Semarang", "kabupaten", ["Semarang"], False),
        ("Kabupaten Temanggung", "kecamatan", ["Temanggung"], False),
    )
    for scope, column, values, expects_finding in cases:
        result = run_contextual_validation(
            pd.DataFrame({column: values}),
            _metadata(data_period="", geographic_scope=scope),
        )
        geographic_findings = _findings(result, "metadata_geographic_scope_vs_dataset")
        assert bool(geographic_findings) is expects_finding


def test_geographic_scope_skips_lower_level_names_and_codes() -> None:
    metadata = _metadata(data_period="", geographic_scope="Kabupaten Temanggung")
    for dataframe in (
        pd.DataFrame({"kecamatan": ["Kedu", "Parakan"]}),
        pd.DataFrame({"kode_kecamatan": ["KC001", "KC002"]}),
    ):
        result = run_contextual_validation(dataframe, metadata)
        assert not _findings(result, "metadata_geographic_scope_vs_dataset")
        assert result["status"] == "not_evaluable"


def test_geographic_scope_compares_same_level_columns_only() -> None:
    metadata = _metadata(data_period="", geographic_scope="Kabupaten Temanggung")

    matching = run_contextual_validation(
        pd.DataFrame({"kabupaten": [" Kabupaten Temanggung "]}),
        metadata,
    )
    different_regency = run_contextual_validation(
        pd.DataFrame({"kabupaten": ["Kabupaten Semarang"]}),
        metadata,
    )
    different_level = run_contextual_validation(
        pd.DataFrame({"kabupaten": ["Kota Semarang"]}),
        metadata,
    )

    assert not _findings(matching, "metadata_geographic_scope_vs_dataset")
    assert _findings(different_regency, "metadata_geographic_scope_vs_dataset")
    assert _findings(different_level, "metadata_geographic_scope_vs_dataset")


def test_geographic_structured_normalization_keeps_level_and_handles_whitespace() -> None:
    result = run_contextual_validation(
        pd.DataFrame({"wilayah": ["  KOTA   Semarang  "]}),
        _metadata(data_period="", geographic_scope=" kota semarang "),
    )
    assert result["status"] == "consistent"


def test_geographic_unknown_level_is_not_evaluable() -> None:
    result = run_contextual_validation(
        pd.DataFrame({"wilayah": ["Semarang"]}),
        _metadata(data_period="", geographic_scope="Semarang"),
    )
    assert result["status"] == "not_evaluable"


def test_missing_geographic_column_is_safe_skip() -> None:
    result = run_contextual_validation(pd.DataFrame({"nama": ["a"]}), _metadata())
    assert result["status"] == "not_evaluable"


def test_beds_rule_handles_numeric_text_invalid_and_missing_without_mutation() -> None:
    dataframe = pd.DataFrame({
        "tempat_tidur_terisi": ["11", "10", None, "invalid"],
        "kapasitas_rawat_inap": ["10", "10", "8", "9"],
    })
    original = dataframe.copy(deep=True)
    result = run_contextual_validation(dataframe, _metadata(data_period=""))
    finding = _findings(result, "occupied_beds_exceed_capacity")[0]
    assert finding["affected_rows"] == 1
    assert finding["percentage"] == 50.0
    pd.testing.assert_frame_equal(dataframe, original)


def test_beds_equal_values_have_no_finding() -> None:
    dataframe = pd.DataFrame({"tempat_tidur_terisi": [10], "kapasitas_rawat_inap": [10]})
    assert not _findings(run_contextual_validation(dataframe, _metadata(data_period="")), "occupied_beds_exceed_capacity")


def test_internet_rule_uses_explicit_status_allowlist() -> None:
    dataframe = pd.DataFrame({"status_internet": ["Tidak ada", "online", "mungkin"], "bandwidth_mbps": [5, 5, 5]})
    result = run_contextual_validation(dataframe, _metadata(data_period=""))
    finding = _findings(result, "internet_status_vs_bandwidth")[0]
    assert finding["affected_rows"] == 1
    assert finding["percentage"] == 50.0


def test_contextual_result_is_json_safe_and_evidence_is_bounded() -> None:
    dataframe = pd.DataFrame({
        "tempat_tidur_terisi": [20] * 7,
        "kapasitas_rawat_inap": [10] * 7,
    })
    result = run_contextual_validation(dataframe, _metadata(data_period=""))
    finding = _findings(result, "occupied_beds_exceed_capacity")[0]
    assert len(finding["evidence"]) == 5
    json.dumps(result, ensure_ascii=False)


def test_period_uses_only_valid_dates_as_denominator() -> None:
    dataframe = pd.DataFrame({"tanggal": ["2026-01-01"] * 9 + ["2025-01-01", None, "invalid"]})
    result = run_contextual_validation(dataframe, _metadata(geographic_scope=""))
    assert not _findings(result, "metadata_period_vs_dataset_dates")


def test_period_threshold_accepts_exactly_eighty_percent_and_rejects_lower() -> None:
    exact_threshold = pd.DataFrame({"tanggal": ["2026-01-01"] * 8 + ["2025-01-01"] * 2})
    below_threshold = pd.DataFrame({"tanggal": ["2026-01-01"] * 7 + ["2025-01-01"] * 3})
    assert not _findings(run_contextual_validation(exact_threshold, _metadata(geographic_scope="")), "metadata_period_vs_dataset_dates")
    assert _findings(run_contextual_validation(below_threshold, _metadata(geographic_scope="")), "metadata_period_vs_dataset_dates")


def test_multi_year_period_accepts_explicit_year_ranges() -> None:
    dataframe = pd.DataFrame({"tanggal": ["2025-01-01", "2026-06-01", "2025-12-01"]})
    for period in ("2025-2026", "Januari 2025 - Desember 2026"):
        result = run_contextual_validation(dataframe, _metadata(data_period=period, geographic_scope=""))
        assert not _findings(result, "metadata_period_vs_dataset_dates")


def test_contextual_summary_uses_effective_ingestion_scope_without_scaling_findings() -> None:
    dataframe = pd.DataFrame({"tempat_tidur_terisi": [2] * 3, "kapasitas_rawat_inap": [1] * 3})
    sampled_dataframe = pd.DataFrame({"tempat_tidur_terisi": [2] * 2_000, "kapasitas_rawat_inap": [1] * 2_000})
    exact = run_contextual_validation(dataframe, _metadata(data_period="", geographic_scope=""), ingestion={"analysis_scope": "full", "total_rows": 3})
    chunked = run_contextual_validation(dataframe, _metadata(data_period="", geographic_scope=""), ingestion={"mode": "chunked", "analysis_scope": "full", "total_rows": 3})
    sampled = run_contextual_validation(sampled_dataframe, _metadata(data_period="", geographic_scope=""), ingestion={"analysis_scope": "sampled", "rows_loaded": 2_000, "total_rows": 12_000})
    full_sampled = run_contextual_validation(dataframe, _metadata(data_period="", geographic_scope=""), ingestion={"mode": "sampled", "analysis_scope": "full", "rows_loaded": 3, "total_rows": 3})
    assert exact["analysis_scope"] == chunked["analysis_scope"] == full_sampled["analysis_scope"] == "full"
    assert sampled["analysis_scope"] == "sampled"
    assert sampled["rows_evaluated"] == 2_000
    assert sampled["total_rows"] == 12_000
    assert _findings(sampled, "occupied_beds_exceed_capacity")[0]["affected_rows"] == 2_000
