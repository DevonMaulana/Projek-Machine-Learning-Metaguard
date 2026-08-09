"""Compact, JSON-safe v0.3 provenance metadata for MetaGuard reports."""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from core.evidence_sanitizer import MAX_EVIDENCE_ITEMS, MAX_EVIDENCE_STRING_LENGTH, TRUNCATION_MARKER


REPORT_LIMITATIONS = (
    "MetaGuard adalah prototipe review kualitas data; hasilnya memerlukan penilaian manusia.",
    "Temuan domain berprovenance HEURISTIC adalah sinyal pemeriksaan MetaGuard, bukan pelanggaran otomatis.",
    "Evidence kebijakan adalah konteks pendukung; sufficiency evidence merupakan heuristic MetaGuard.",
    "Laporan ini bukan sertifikasi hukum atau compliance dan tidak melakukan perbaikan dataset otomatis.",
)


def _json_safe(value: Any) -> Any:
    """Convert report metadata to JSON primitives without retaining runtime objects."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "value"):
        return _json_safe(value.value)
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)


def _bounded_text(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) > MAX_EVIDENCE_STRING_LENGTH:
        return text[:MAX_EVIDENCE_STRING_LENGTH] + TRUNCATION_MARKER
    return text


def _as_mappings(items: Iterable[Any]) -> list[Mapping[str, Any]]:
    return [item for item in items if isinstance(item, Mapping)]


def _context_snapshot(analysis_context: Mapping[str, Any] | None, contextual_validation: Mapping[str, Any]) -> dict[str, Any]:
    context = analysis_context or {}
    profile = context.get("domain_profile") if isinstance(context.get("domain_profile"), Mapping) else {}
    execution = contextual_validation.get("domain_rule_execution")
    active_packs = execution.get("active_rule_packs", []) if isinstance(execution, Mapping) else []
    return {
        "selected_domain": context.get("selected_domain"),
        "governance_context": context.get("governance_context"),
        "analysis_context_fingerprint": context.get("analysis_context_fingerprint"),
        "concept_registry_fingerprint": context.get("concept_registry_fingerprint"),
        "rule_registry_fingerprint": context.get("rule_registry_fingerprint"),
        "policy_registry_fingerprint": context.get("policy_registry_fingerprint"),
        "domain": {
            "domain_id": profile.get("domain_id", context.get("selected_domain")),
            "display_name": profile.get("display_name"),
            "active_rule_packs": list(active_packs) if isinstance(active_packs, list) else [],
        },
    }


def _rule_provenance(contextual_validation: Mapping[str, Any]) -> list[dict[str, Any]]:
    findings = contextual_validation.get("findings", [])
    result: list[dict[str, Any]] = []
    for finding in _as_mappings(findings if isinstance(findings, list) else []):
        if not finding.get("rule_id"):
            continue
        result.append(
            {
                key: _json_safe(finding.get(key))
                for key in (
                    "rule_id",
                    "rule_pack_id",
                    "domain_id",
                    "provenance_type",
                    "required_concepts",
                    "resolved_columns",
                    "human_review_required",
                    "interpretation_note",
                    "policy_requirement",
                )
            }
        )
    return result


def _workflow_summaries(workflows: Iterable[Any]) -> tuple[list[dict[str, Any]], set[str]]:
    summaries: list[dict[str, Any]] = []
    eligible_policy_ids: set[str] = set()
    for workflow in _as_mappings(workflows):
        request = workflow.get("request") if isinstance(workflow.get("request"), Mapping) else {}
        routing = workflow.get("routing_result") if isinstance(workflow.get("routing_result"), Mapping) else {}
        assessment = workflow.get("final_assessment") if isinstance(workflow.get("final_assessment"), Mapping) else {}
        sufficiency = assessment.get("sufficiency") if isinstance(assessment.get("sufficiency"), Mapping) else {}
        alignment = assessment.get("alignment") if isinstance(assessment.get("alignment"), Mapping) else {}
        policy_ids = routing.get("eligible_policy_ids", [])
        if isinstance(policy_ids, list):
            eligible_policy_ids.update(str(item) for item in policy_ids if str(item).strip())
        summaries.append(
            _json_safe(
                {
                    "evidence_need": request.get("evidence_need"),
                    "applicability_state": routing.get("applicability_state"),
                    "attempt_count": workflow.get("attempt_count", 0),
                    "stop_reason": workflow.get("stop_reason"),
                    "sufficiency_state": sufficiency.get("state"),
                    "sufficiency_score": sufficiency.get("score"),
                    "policy_pack_alignment": alignment.get("policy_pack_alignment"),
                    "domain_alignment": alignment.get("domain_alignment"),
                    "readiness": assessment.get("readiness"),
                }
            )
        )
    return summaries, eligible_policy_ids


def _flatten_evidence(evidence_pool: Iterable[Any]) -> list[Mapping[str, Any]]:
    flattened: list[Mapping[str, Any]] = []
    for item in _as_mappings(evidence_pool):
        results = item.get("results")
        if isinstance(results, list):
            flattened.extend(_as_mappings(results))
        else:
            flattened.append(item)
    return flattened


def _policy_evidence_summary(evidence_pool: Iterable[Any], eligible_policy_ids: set[str]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    summary: list[dict[str, Any]] = []
    for item in _flatten_evidence(evidence_pool):
        chunk_id = str(item.get("chunk_id", "")).strip()
        policy_id = str(item.get("policy_id", "")).strip()
        if not chunk_id or chunk_id in seen:
            continue
        if eligible_policy_ids and policy_id not in eligible_policy_ids:
            continue
        seen.add(chunk_id)
        summary.append(
            {
                "chunk_id": chunk_id,
                "source": str(item.get("source", "")).strip(),
                "page": _json_safe(item.get("page")),
                "policy_id": policy_id,
                "policy_pack": str(item.get("policy_pack", "")).strip(),
                "domain_id": str(item.get("domain_id", "")).strip(),
                "document_type": str(item.get("document_type", "")).strip(),
                "excerpt": _bounded_text(item.get("text", "")),
            }
        )
        if len(summary) == MAX_EVIDENCE_ITEMS:
            break
    return summary


def _traceability_snapshot(evidence_review: Mapping[str, Any]) -> dict[str, Any]:
    citations: list[dict[str, Any]] = []
    for reference in _as_mappings(evidence_review.get("valid_references", [])):
        citations.append({"chunk_id": reference.get("chunk_id"), "source": reference.get("source"), "page": _json_safe(reference.get("page")), "valid": True, "reason": None})
    for reference in _as_mappings(evidence_review.get("invalid_references", [])):
        citations.append({"chunk_id": reference.get("chunk_id"), "source": reference.get("source"), "page": _json_safe(reference.get("page")), "valid": False, "reason": reference.get("reason")})
    return _json_safe(
        {
            "citations_total": evidence_review.get("total_references", 0),
            "citations_valid": evidence_review.get("valid_reference_count", 0),
            "citations_invalid": evidence_review.get("invalid_reference_count", 0),
            "traceability_percentage": evidence_review.get("traceability_score", 0),
            "status": evidence_review.get("status"),
            "citations": citations,
        }
    )


def build_v3_report_metadata(
    *,
    analysis_context: Mapping[str, Any] | None = None,
    contextual_validation: Mapping[str, Any] | None = None,
    evidence_workflows: Iterable[Any] = (),
    evidence_pool: Iterable[Any] = (),
    evidence_ready: bool = False,
    human_approval: bool = False,
    gemini_analysis: Mapping[str, Any] | None = None,
    evidence_review: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the bounded additive v0.3 report layer without legal conclusions."""
    contextual = contextual_validation or {}
    workflows, eligible_policy_ids = _workflow_summaries(evidence_workflows)
    review = evidence_review or {}
    return {
        "analysis_context": _json_safe(_context_snapshot(analysis_context, contextual)),
        "domain_rule_execution": _json_safe(contextual.get("domain_rule_execution", {})),
        "rule_provenance": _rule_provenance(contextual),
        "policy_evidence": _policy_evidence_summary(evidence_pool, eligible_policy_ids),
        "evidence_needs": workflows,
        "evidence_ready_for_review": bool(evidence_ready),
        "human_approval": {"approved": bool(human_approval)},
        "gemini": {"executed": bool(gemini_analysis)},
        "traceability": _traceability_snapshot(review),
        "limitations": list(REPORT_LIMITATIONS),
    }
