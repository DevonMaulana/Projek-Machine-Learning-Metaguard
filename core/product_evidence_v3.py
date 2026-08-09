"""Product-facing aggregation of isolated v3 evidence workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from core.domain_models import DomainId, GovernanceContext
from core.evidence_alignment import deduplicate_evidence_chunks
from core.evidence_workflow_v3 import (
    EvidenceWorkflowState,
    PolicyEvidenceWorkflowRequest,
    PolicyEvidenceWorkflowResult,
    run_policy_evidence_workflow_v3,
)
from core.policy_router import EvidenceNeed


_BASE_QUERIES = {
    EvidenceNeed.METADATA_GOVERNANCE: "ketentuan kelengkapan metadata statistik untuk dataset pemerintah",
    EvidenceNeed.DATA_QUALITY: "pemeriksaan kualitas data nilai kosong duplikasi konsistensi dan format data",
    EvidenceNeed.ACCOUNTABILITY: "tugas produsen data dan walidata dalam pemeriksaan serta perbaikan data",
    EvidenceNeed.TECHNICAL_STANDARD_SUPPORT: "standar teknis data klasifikasi definisi dan satuan",
}


@dataclass(frozen=True)
class V3EvidenceAggregate:
    """JSON-safe aggregate for a deterministic list of evidence needs."""

    workflows: tuple[PolicyEvidenceWorkflowResult, ...]
    evidence_pool: tuple[dict[str, Any], ...]
    evidence_ready: bool
    applicability_summary: tuple[str, ...]
    blocking_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return compact state suitable for session storage and future reporting."""
        return {
            "workflows": [item.to_dict() for item in self.workflows],
            "evidence_pool": [dict(item) for item in self.evidence_pool],
            "evidence_ready": self.evidence_ready,
            "applicability_summary": list(self.applicability_summary),
            "blocking_reasons": list(self.blocking_reasons),
        }


def plan_product_evidence_needs(
    *,
    selected_domain: DomainId,
    metadata_validation: dict[str, Any],
    findings: list[dict[str, Any]],
    contextual_validation: dict[str, Any],
) -> tuple[EvidenceNeed, ...]:
    """Preserve v0.2 needs, adding bounded sector support for selected pilot domains."""
    del metadata_validation, contextual_validation  # Metadata governance and accountability remain baseline needs.
    needs = [EvidenceNeed.METADATA_GOVERNANCE]
    if findings:
        needs.append(EvidenceNeed.DATA_QUALITY)
    needs.append(EvidenceNeed.ACCOUNTABILITY)
    if selected_domain in {DomainId.HEALTHCARE, DomainId.EDUCATION, DomainId.ENVIRONMENT}:
        needs.append(EvidenceNeed.DOMAIN_SEMANTIC_SUPPORT)
    return tuple(needs)


def build_product_query(need: EvidenceNeed, domain: DomainId) -> str:
    """Build one deterministic base query for a validated evidence need."""
    if need is EvidenceNeed.DOMAIN_SEMANTIC_SUPPORT:
        return f"Satu Data sektor {domain.value} dan penyelenggaraan informasi data"
    return _BASE_QUERIES[need]


def aggregate_evidence_workflows(workflows: Iterable[PolicyEvidenceWorkflowResult]) -> V3EvidenceAggregate:
    """Require every applicable workflow to be ready without scoring compliance."""
    items = tuple(workflows)
    applicable = [item for item in items if item.routing_result.applicability_state.value == "APPLICABLE"]
    ready_items = [item for item in applicable if item.workflow_state is EvidenceWorkflowState.READY]
    pool = deduplicate_evidence_chunks(
        evidence
        for item in ready_items
        for evidence in item.cumulative_evidence
    )
    reasons: list[str] = []
    for item in items:
        if item.workflow_state is EvidenceWorkflowState.CORPUS_STALE:
            reasons.append("Corpus policy v3 stale; rebuild eksplisit diperlukan.")
        elif item.workflow_state is EvidenceWorkflowState.NO_ELIGIBLE_POLICY:
            reasons.append(f"Tidak ada policy eligible untuk {item.request.evidence_need.value}.")
        elif item.routing_result.applicability_state.value == "APPLICABLE" and item.workflow_state is not EvidenceWorkflowState.READY:
            reasons.append(f"Evidence {item.request.evidence_need.value} belum ready untuk review AI.")
    evidence_ready = bool(applicable) and len(ready_items) == len(applicable) and bool(pool)
    if not applicable:
        reasons.append("Tidak ada evidence need yang applicable untuk konteks ini.")
    return V3EvidenceAggregate(
        workflows=items,
        evidence_pool=pool,
        evidence_ready=evidence_ready,
        applicability_summary=tuple(item.workflow_state.value for item in items),
        blocking_reasons=tuple(dict.fromkeys(reasons)),
    )


def run_product_evidence_workflows(
    *,
    selected_domain: DomainId,
    governance_context: GovernanceContext,
    evidence_needs: Iterable[EvidenceNeed],
    workflow_runner: Callable[[PolicyEvidenceWorkflowRequest], PolicyEvidenceWorkflowResult] = run_policy_evidence_workflow_v3,
) -> V3EvidenceAggregate:
    """Run exactly one bounded workflow per deterministic evidence need."""
    workflows = []
    for need in evidence_needs:
        request = PolicyEvidenceWorkflowRequest.create(
            selected_domain=selected_domain,
            governance_context=governance_context,
            evidence_need=need,
            query_text=build_product_query(need, selected_domain),
        )
        workflows.append(workflow_runner(request))
    return aggregate_evidence_workflows(workflows)


def evidence_pool_as_groups(evidence_pool: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Adapt the v3 eligible pool to the existing traceability group contract."""
    return [{"query": "evidence_workflow_v3", "results": [dict(item) for item in evidence_pool]}]
