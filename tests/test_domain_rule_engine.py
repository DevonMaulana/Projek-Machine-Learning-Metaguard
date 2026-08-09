"""Parity tests for the isolated v0.3 domain-rule execution foundation."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from core.cross_column_rules import run_cross_column_validation
from core.domain_rule_engine import (
    EVALUATOR_ALLOWLIST,
    RULE_STATE_EVALUATED,
    RULE_STATE_ERROR,
    RULE_STATE_SKIPPED_AMBIGUOUS_CONCEPT,
    RULE_STATE_SKIPPED_MISSING_CONCEPT,
    run_domain_rule_validation,
)


LEGACY_FIELDS = (
    "check_id",
    "category",
    "severity",
    "title",
    "description",
    "columns",
    "affected_rows",
    "percentage",
    "evidence",
    "recommendation",
    "deterministic",
    "confidence",
)


def _engine_findings(result: object) -> list[dict[str, object]]:
    return [finding for item in result.rule_results for finding in item.findings]  # type: ignore[attr-defined]


def _assert_legacy_parity(dataframe: pd.DataFrame) -> None:
    legacy = run_cross_column_validation(dataframe, profile="healthcare")
    engine = run_domain_rule_validation(dataframe, selected_domain="healthcare")
    legacy_by_id = {finding["check_id"]: finding for finding in legacy["findings"]}
    engine_by_id = {finding["check_id"]: finding for finding in _engine_findings(engine)}
    assert engine_by_id.keys() == legacy_by_id.keys()
    for check_id, legacy_finding in legacy_by_id.items():
        assert {field: engine_by_id[check_id][field] for field in LEGACY_FIELDS} == {
            field: legacy_finding[field] for field in LEGACY_FIELDS
        }


@pytest.mark.parametrize(
    "dataframe",
    [
        pd.DataFrame({"tempat_tidur_terisi": [9, 10], "kapasitas_rawat_inap": [10, 10]}),
        pd.DataFrame({"tempat_tidur_terisi": [11, "10", None, "invalid"], "kapasitas_rawat_inap": [10, "10", 8, 9]}),
        pd.DataFrame({"tempat_tidur_terisi": [2], "kapasitas_rawat_inap": [1]}),
    ],
)
def test_bed_capacity_engine_has_legacy_semantic_parity(dataframe: pd.DataFrame) -> None:
    original = dataframe.copy(deep=True)
    _assert_legacy_parity(dataframe)
    pd.testing.assert_frame_equal(dataframe, original)


@pytest.mark.parametrize(
    "status",
    ["tidak", "Tidak ada", "offline", "none", "online", "ada", "aktif", "mungkin"],
)
def test_internet_bandwidth_engine_has_legacy_status_parity(status: str) -> None:
    dataframe = pd.DataFrame({"status_internet": [status], "bandwidth_mbps": [5]})
    _assert_legacy_parity(dataframe)


def test_internet_zero_bandwidth_and_missing_values_have_legacy_parity() -> None:
    dataframe = pd.DataFrame(
        {
            "status_internet": ["offline", None, "mungkin", "online"],
            "bandwidth_mbps": [0, 4, 5, None],
        }
    )
    _assert_legacy_parity(dataframe)
    engine = run_domain_rule_validation(dataframe, selected_domain="healthcare")
    assert {result.state for result in engine.rule_results} == {
        RULE_STATE_SKIPPED_MISSING_CONCEPT,
        RULE_STATE_EVALUATED,
    }


def test_missing_required_concept_is_explicit_skip_not_zero_findings() -> None:
    dataframe = pd.DataFrame({"tempat_tidur_terisi": [11]})
    result = run_domain_rule_validation(dataframe, selected_domain="healthcare")
    bed_result = next(item for item in result.rule_results if item.rule_id == "HEALTH-BED-CAPACITY-001")
    assert bed_result.state == RULE_STATE_SKIPPED_MISSING_CONCEPT
    assert not bed_result.findings
    assert result.rules_evaluated == 0
    assert result.rules_skipped == 2


def test_duplicate_normalized_concept_columns_are_conservatively_skipped() -> None:
    dataframe = pd.DataFrame(
        [[20, 21, 10]],
        columns=["Tempat Tidur Terisi", "tempat_tidur_terisi", "kapasitas_rawat_inap"],
    )
    result = run_domain_rule_validation(dataframe, selected_domain="healthcare")
    bed_result = next(item for item in result.rule_results if item.rule_id == "HEALTH-BED-CAPACITY-001")
    assert bed_result.state == RULE_STATE_SKIPPED_AMBIGUOUS_CONCEPT
    assert not bed_result.findings


def test_engine_enriches_findings_with_rule_provenance() -> None:
    dataframe = pd.DataFrame({"tempat_tidur_terisi": [20], "kapasitas_rawat_inap": [10]})
    result = run_domain_rule_validation(dataframe, selected_domain="healthcare")
    finding = _engine_findings(result)[0]
    assert finding["rule_id"] == "HEALTH-BED-CAPACITY-001"
    assert finding["rule_pack_id"] == "healthcare_core"
    assert finding["domain_id"] == "healthcare"
    assert finding["provenance_type"] == "DETERMINISTIC_INVARIANT"
    assert finding["required_concepts"] == ["occupied_beds", "inpatient_capacity"]
    assert [column["source_column"] for column in finding["resolved_columns"]] == [  # type: ignore[index]
        "tempat_tidur_terisi",
        "kapasitas_rawat_inap",
    ]
    assert finding["human_review_required"] is True
    json.dumps(result.to_dict(), ensure_ascii=False)


def test_engine_uses_concepts_to_support_normalized_source_columns() -> None:
    dataframe = pd.DataFrame({"Tempat Tidur Terisi": [20], "Kapasitas Rawat Inap": [10]})
    result = run_domain_rule_validation(dataframe, selected_domain="healthcare")
    finding = _engine_findings(result)[0]
    assert finding["check_id"] == "occupied_beds_exceed_capacity"
    assert finding["columns"] == ["tempat_tidur_terisi", "kapasitas_rawat_inap"]
    assert finding["resolved_columns"][0]["source_column"] == "Tempat Tidur Terisi"  # type: ignore[index]


def test_engine_keeps_healthcare_rules_isolated_from_other_domains() -> None:
    dataframe = pd.DataFrame({"tempat_tidur_terisi": [20], "kapasitas_rawat_inap": [10]})
    for domain in ("generic", "education", "environment", "other"):
        result = run_domain_rule_validation(dataframe, selected_domain=domain)
        assert all(item.rule_id.startswith(("EDU-", "ENV-")) for item in result.rule_results)
        assert result.findings_count == 0


def test_education_rules_use_resolved_aliases_and_are_human_review_heuristics() -> None:
    dataframe = pd.DataFrame({"Jumlah Siswa": [10, 10], "jml_guru": [2, 0], "total_kelas": [1, 0]})
    original = dataframe.copy(deep=True)
    result = run_domain_rule_validation(dataframe, selected_domain="education")
    findings = {finding["check_id"]: finding for finding in _engine_findings(result)}
    assert findings.keys() == {"student_count_without_teacher", "student_count_without_classroom"}
    for finding in findings.values():
        assert finding["rule_pack_id"] == "education_core"
        assert finding["provenance_type"] == "HEURISTIC"
        assert finding["policy_requirement"] is False
        assert finding["human_review_required"] is True
        assert finding["severity"] == "medium"
    pd.testing.assert_frame_equal(dataframe, original)


def test_education_missing_concepts_are_explicit_skips() -> None:
    result = run_domain_rule_validation(pd.DataFrame({"jumlah_siswa": [10]}), selected_domain="education")
    assert {item.state for item in result.rule_results} == {RULE_STATE_SKIPPED_MISSING_CONCEPT}
    assert result.findings_count == 0


@pytest.mark.parametrize("status", ["offline", "nonaktif", "tidak aktif"])
def test_environment_sensor_measurement_rule_is_conservative_and_human_reviewed(status: str) -> None:
    dataframe = pd.DataFrame({"status_sensor": [status, "aktif"], "ph_air": [7.0, 6.5], "pm25": [None, 12]})
    original = dataframe.copy(deep=True)
    result = run_domain_rule_validation(dataframe, selected_domain="environment")
    rule_result = result.rule_results[0]
    assert rule_result.state == RULE_STATE_EVALUATED
    assert len(rule_result.findings) == 1
    finding = rule_result.findings[0]
    assert finding["check_id"] == "offline_sensor_with_measurement"
    assert finding["affected_rows"] == 1
    assert finding["severity"] == "low"
    assert finding["provenance_type"] == "HEURISTIC"
    assert finding["policy_requirement"] is False
    assert finding["human_review_required"] is True
    pd.testing.assert_frame_equal(dataframe, original)


def test_environment_missing_sensor_skips_and_missing_measurements_are_not_applicable() -> None:
    missing_sensor = run_domain_rule_validation(pd.DataFrame({"ph_air": [7]}), selected_domain="environment")
    assert missing_sensor.rule_results[0].state == RULE_STATE_SKIPPED_MISSING_CONCEPT
    missing_measurement = run_domain_rule_validation(
        pd.DataFrame({"status_sensor": ["offline"]}), selected_domain="environment"
    )
    assert missing_measurement.rule_results[0].state == "not_applicable"
    assert not missing_measurement.findings_count


@pytest.mark.parametrize("status", ["aktif", "online", "unknown", None])
def test_environment_only_flags_explicit_offline_statuses(status: str | None) -> None:
    result = run_domain_rule_validation(
        pd.DataFrame({"status_sensor": [status], "pm_25": [12]}), selected_domain="environment"
    )
    assert result.findings_count == 0


def test_engine_is_deterministic_and_summary_is_json_safe() -> None:
    dataframe = pd.DataFrame({"status_internet": ["offline"], "bandwidth_mbps": [5]})
    first = run_domain_rule_validation(dataframe, selected_domain="healthcare")
    second = run_domain_rule_validation(dataframe, selected_domain="healthcare")
    assert first.to_dict() == second.to_dict()
    assert first.rule_results[1].state == RULE_STATE_EVALUATED
    json.dumps(first.to_dict(), ensure_ascii=False)


def test_evaluator_failure_is_reported_as_a_rule_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_evaluator(*_args: object) -> object:
        raise RuntimeError("controlled evaluator failure")

    monkeypatch.setitem(EVALUATOR_ALLOWLIST, "health_bed_capacity_consistency", failing_evaluator)
    dataframe = pd.DataFrame({"tempat_tidur_terisi": [20], "kapasitas_rawat_inap": [10]})
    result = run_domain_rule_validation(dataframe, selected_domain="healthcare")
    bed_result = next(item for item in result.rule_results if item.rule_id == "HEALTH-BED-CAPACITY-001")
    assert bed_result.state == RULE_STATE_ERROR
    assert bed_result.error == "controlled evaluator failure"
