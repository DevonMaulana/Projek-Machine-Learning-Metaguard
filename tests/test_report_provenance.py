"""Focused tests for additive v0.3 report provenance and traceability."""

from __future__ import annotations

import json

import pandas as pd

from core.analysis_context import build_analysis_context
from core.contextual_validation import run_contextual_validation
from core.evidence_reviewer import review_evidence_traceability
from core.report_builder import build_report


def _metadata() -> dict[str, str]:
    return {"data_period": "", "geographic_scope": ""}


def _context(domain: str, governance: str) -> dict[str, object]:
    context = build_analysis_context(selected_domain=domain, governance_context=governance)
    return {**context.to_dict(), "analysis_context_fingerprint": context.fingerprint()}


def _workflow(*, need: str, state: str, policy_id: str, pack: str, domain: str) -> dict[str, object]:
    return {
        "request": {"evidence_need": need},
        "routing_result": {"applicability_state": state, "eligible_policy_ids": [policy_id]},
        "attempt_count": 1 if state == "APPLICABLE" else 0,
        "stop_reason": "READY" if state == "APPLICABLE" else state,
        "final_assessment": {
            "sufficiency": {"state": "SUFFICIENT" if state == "APPLICABLE" else "NOT_ASSESSED", "score": 90.0 if state == "APPLICABLE" else None},
            "alignment": {"policy_pack_alignment": "ALIGNED", "domain_alignment": "ALIGNED"},
            "readiness": "READY" if state == "APPLICABLE" else "NOT_APPLICABLE",
        },
        "policy_pack": pack,
        "domain": domain,
    }


def _report(*, context: dict[str, object], contextual: dict[str, object], workflows: list[dict[str, object]] | None = None, pool: list[dict[str, object]] | None = None, ready: bool = False, approval: bool = False, gemini: dict[str, object] | None = None, review: dict[str, object] | None = None) -> dict[str, object]:
    return build_report(
        profile={}, findings=[{"check_id": "generic_check", "severity": "low"}],
        score={"score": 90, "findings_by_severity": {"low": 1}},
        analysis_context=context,
        contextual_validation=contextual,
        evidence_workflows_v3=workflows,
        evidence_pool_v3=pool,
        evidence_ready_v3=ready,
        human_approval=approval,
        gemini_analysis=gemini,
        evidence_review=review,
    )


def test_report_records_explicit_context_and_education_heuristic_without_policy_promotion() -> None:
    contextual = run_contextual_validation(
        pd.DataFrame({"jumlah_siswa": [12], "jumlah_guru": [0], "jumlah_kelas": [1]}),
        _metadata(), selected_domain="education",
    )
    report = _report(context=_context("education", "government_public"), contextual=contextual)
    metadata = report["v3_metadata"]
    assert metadata["analysis_context"]["selected_domain"] == "education"
    assert metadata["analysis_context"]["governance_context"] == "government_public"
    assert metadata["analysis_context"]["domain"]["active_rule_packs"] == ["education_core"]
    provenance = metadata["rule_provenance"]
    assert provenance[0]["rule_id"] == "EDU-STUDENT-TEACHER-001"
    assert provenance[0]["provenance_type"] == "HEURISTIC"
    assert provenance[0]["human_review_required"] is True
    assert provenance[0]["policy_requirement"] is False


def test_report_preserves_healthcare_and_environment_rule_provenance() -> None:
    healthcare = run_contextual_validation(
        pd.DataFrame({"tempat_tidur_terisi": [2], "kapasitas_rawat_inap": [1]}),
        _metadata(), selected_domain="healthcare",
    )
    health_report = _report(context=_context("healthcare", "government_public"), contextual=healthcare)
    assert health_report["v3_metadata"]["rule_provenance"][0]["provenance_type"] == "DETERMINISTIC_INVARIANT"

    environment = run_contextual_validation(
        pd.DataFrame({"status_sensor": ["offline"], "pm25": [12]}),
        _metadata(), selected_domain="environment",
    )
    environment_report = _report(context=_context("environment", "government_public"), contextual=environment)
    provenance = environment_report["v3_metadata"]["rule_provenance"][0]
    assert provenance["rule_id"] == "ENV-SENSOR-MEASUREMENT-001"
    assert provenance["provenance_type"] == "HEURISTIC"
    assert provenance["human_review_required"] is True


def test_report_includes_only_eligible_deduplicated_bounded_v3_evidence() -> None:
    workflow = _workflow(need="domain_semantic_support", state="APPLICABLE", policy_id="EDU-SATU-DATA-31-2022", pack="education", domain="education")
    eligible = {"chunk_id": "edu-1", "source": "education.pdf", "page": 3, "text": "x" * 400, "policy_id": "EDU-SATU-DATA-31-2022", "policy_pack": "education", "domain_id": "education", "document_type": "regulation"}
    ineligible = {**eligible, "chunk_id": "health-1", "policy_id": "HEALTH-SATU-DATA-18-2022", "policy_pack": "healthcare", "domain_id": "healthcare"}
    report = _report(
        context=_context("education", "government_public"), contextual={}, workflows=[workflow],
        pool=[{"query": "supplied", "results": [eligible, eligible, ineligible]}], ready=True,
    )
    evidence = report["v3_metadata"]["policy_evidence"]
    assert [item["chunk_id"] for item in evidence] == ["edu-1"]
    assert evidence[0]["excerpt"].endswith("...[dipotong]")
    need = report["v3_metadata"]["evidence_needs"][0]
    assert need["sufficiency_state"] == "SUFFICIENT"
    assert need["policy_pack_alignment"] == "ALIGNED"


def test_report_distinguishes_not_applicable_approval_gemini_and_traceability() -> None:
    workflow = _workflow(need="metadata_governance", state="NOT_APPLICABLE", policy_id="", pack="", domain="generic")
    supplied = [{"query": "supplied", "results": [{"chunk_id": "known", "source": "policy.pdf", "page": 2, "text": "excerpt", "policy_id": "GOV-SDI-PERPRES-39-2019"}]}]
    review = review_evidence_traceability(supplied, {"evidence_references": [
        {"chunk_id": "known", "source": "policy.pdf", "page": 2, "relevance": "valid"},
        {"chunk_id": "unknown", "source": "policy.pdf", "page": 2, "relevance": "invalid"},
    ]})
    report = _report(
        context=_context("generic", "generic_non_government"), contextual={}, workflows=[workflow],
        ready=False, approval=False, gemini={"summary": "Interpretasi"}, review=review,
    )
    metadata = report["v3_metadata"]
    assert metadata["evidence_needs"][0]["applicability_state"] == "NOT_APPLICABLE"
    assert metadata["evidence_needs"][0]["sufficiency_state"] == "NOT_ASSESSED"
    assert metadata["evidence_ready_for_review"] is False
    assert metadata["human_approval"]["approved"] is False
    assert metadata["gemini"]["executed"] is True
    assert metadata["traceability"]["citations_valid"] == 1
    assert metadata["traceability"]["citations_invalid"] == 1
    assert {citation["valid"] for citation in metadata["traceability"]["citations"]} == {True, False}


def test_report_is_valid_without_gemini_and_has_non_compliance_limitations() -> None:
    report = _report(context=_context("other", "generic_non_government"), contextual={})
    encoded = json.dumps(report, ensure_ascii=False, allow_nan=False)
    metadata = report["v3_metadata"]
    assert metadata["analysis_context"]["domain"]["active_rule_packs"] == []
    assert metadata["gemini"]["executed"] is False
    assert metadata["traceability"]["citations_total"] == 0
    assert "compliance" in encoded.lower()
    assert "dataset compliant" not in encoded.lower()
