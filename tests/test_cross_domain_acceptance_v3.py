"""Release-candidate acceptance checks across explicit v0.3 domains."""

from __future__ import annotations

import pandas as pd

from core.analysis_context import build_analysis_context
from core.contextual_validation import run_contextual_validation
from core.policy_router import route_policy_evidence
from core.report_builder import build_report


def _metadata() -> dict[str, str]:
    return {"data_period": "", "geographic_scope": ""}


def test_sector_rule_packs_are_strictly_isolated() -> None:
    cases = {
        "healthcare": ("healthcare_core", {"tempat_tidur_terisi": [2], "kapasitas_rawat_inap": [1]}),
        "education": ("education_core", {"jumlah_siswa": [2], "jumlah_guru": [0], "jumlah_kelas": [1]}),
        "environment": ("environment_core", {"status_sensor": ["offline"], "pm25": [7]}),
    }
    for domain, (pack, data) in cases.items():
        result = run_contextual_validation(pd.DataFrame(data), _metadata(), selected_domain=domain)
        assert result["domain_rule_execution"]["active_rule_packs"] == [pack]
        for finding in result["findings"]:
            if "rule_pack_id" in finding:
                assert finding["rule_pack_id"] == pack
    for domain in ("generic", "other"):
        result = run_contextual_validation(pd.DataFrame({"nama": ["x"]}), _metadata(), selected_domain=domain)
        assert result["domain_rule_execution"]["active_rule_packs"] == []


def test_non_government_governance_need_is_not_applicable_without_retrieval() -> None:
    routed = route_policy_evidence(
        selected_domain="generic", governance_context="generic_non_government", evidence_need="metadata_governance"
    )
    assert routed.applicability_state.value == "NOT_APPLICABLE"
    assert routed.eligible_policy_ids == ()
    assert routed.eligible_policy_packs == ()


def test_context_fingerprint_and_report_provenance_change_with_domain() -> None:
    health = build_analysis_context(selected_domain="healthcare", governance_context="government_public")
    education = build_analysis_context(selected_domain="education", governance_context="government_public")
    assert health.fingerprint() != education.fingerprint()
    report = build_report({}, [], {"score": 100, "findings_by_severity": {}}, analysis_context={**education.to_dict(), "analysis_context_fingerprint": education.fingerprint()})
    assert report["schema_version"] == "1.1"
    assert report["v3_metadata"]["analysis_context"]["selected_domain"] == "education"
