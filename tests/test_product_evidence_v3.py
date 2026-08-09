"""Tests for the product-facing v3 workflow aggregate and approval guard."""

from __future__ import annotations

from core.agent_models import AgentAction
from core.agent_orchestrator import execute_decision, plan_next_action
from core.agent_state_builder import build_agent_state
from core.agent_tools import AgentExecutionContext, ToolDefinition
from core.domain_models import DomainId
from core.evidence_assessment import assess_v3_evidence
from core.evidence_reviewer import review_evidence_traceability
from core.evidence_sanitizer import sanitize_policy_evidence_for_gemini
from core.evidence_workflow_v3 import EvidenceWorkflowState, PolicyEvidenceWorkflowRequest, PolicyEvidenceWorkflowResult
from core.policy_router import route_policy_evidence
from core.product_evidence_v3 import aggregate_evidence_workflows, evidence_pool_as_groups, plan_product_evidence_needs
from rag.policy_retrieval_v3 import RetrievalState, V3RetrievalResult


def _item(chunk_id: str) -> dict[str, object]:
    return {"chunk_id": chunk_id, "source": "health.pdf", "page": 1, "text": "x", "policy_id": "HEALTH-SATU-DATA-18-2022", "policy_pack": "healthcare", "domain_id": "healthcare", "document_type": "regulation"}


def _workflow(state: EvidenceWorkflowState, evidence=()) -> PolicyEvidenceWorkflowResult:
    request = PolicyEvidenceWorkflowRequest.create(selected_domain="healthcare", governance_context="government_public", evidence_need="domain_semantic_support", query_text="health")
    route = route_policy_evidence(governance_context="government_public", selected_domain="healthcare", evidence_need="domain_semantic_support")
    retrieval = V3RetrievalResult(RetrievalState.SUCCESS if evidence else RetrievalState.EMPTY, route, tuple(evidence), None)
    return PolicyEvidenceWorkflowResult(request, route, (), tuple(evidence), assess_v3_evidence(retrieval), state, 2, state.value)


def _ready_agent_inputs(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "fingerprint": "a", "ingestion": {"status": "success"}, "profile": {}, "findings": [], "score": {},
        "metadata_validation": {"status": "Lengkap"}, "metadata_validation_completed": True,
        "contextual_validation": {}, "contextual_validation_completed": True,
        "policy_evidence_retrieval_completed": True,
        "policy_evidence": [{"results": [_item("a"), _item("b")]}],
        "evidence_sufficiency": {"status": "sufficient", "score": 90},
        "evidence_workflow_v3_completed": True, "evidence_ready_v3": True, "evidence_workflow_v3_state": "READY",
    }
    values.update(changes)
    return values


def test_aggregate_requires_all_applicable_workflows_ready_and_deduplicates_pool() -> None:
    ready = _workflow(EvidenceWorkflowState.READY, [_item("a"), _item("a"), _item("b")])
    aggregate = aggregate_evidence_workflows([ready])
    assert aggregate.evidence_ready
    assert [item["chunk_id"] for item in aggregate.evidence_pool] == ["a", "b"]
    blocked = aggregate_evidence_workflows([ready, _workflow(EvidenceWorkflowState.NOT_READY)])
    assert not blocked.evidence_ready
    assert blocked.blocking_reasons
    assert evidence_pool_as_groups(aggregate.evidence_pool)[0]["results"][0]["chunk_id"] == "a"


def test_domain_planning_is_explicit_and_has_no_cross_domain_rule_inference() -> None:
    healthcare = plan_product_evidence_needs(selected_domain=DomainId.HEALTHCARE, metadata_validation={}, findings=[], contextual_validation={})
    generic = plan_product_evidence_needs(selected_domain=DomainId.GENERIC, metadata_validation={}, findings=[], contextual_validation={})
    assert healthcare[-1].value == "domain_semantic_support"
    assert "domain_semantic_support" not in [item.value for item in generic]


def test_v3_readiness_and_explicit_approval_gate_mock_gemini_once() -> None:
    calls = 0

    def fake_gemini(context: AgentExecutionContext) -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"summary": "mock"}

    state = build_agent_state(**_ready_agent_inputs())
    decision = plan_next_action(state)
    registry = {AgentAction.RUN_GEMINI_ANALYSIS: ToolDefinition("gemini", "mock", AgentAction.RUN_GEMINI_ANALYSIS, (decision.current_stage,), True, fake_gemini)}
    assert execute_decision(decision, state, AgentExecutionContext(), registry=registry).success is False
    assert execute_decision(decision, state, AgentExecutionContext(), approved=True, registry=registry).success is True
    assert calls == 1
    blocked = build_agent_state(**_ready_agent_inputs(evidence_ready_v3=False, evidence_workflow_v3_state="NOT_READY"))
    assert plan_next_action(blocked).next_action is AgentAction.NONE


def test_context_fingerprint_reset_clears_v3_evidence_and_approval() -> None:
    from core.analysis_state import reset_analysis_results

    session = {"evidence_workflow_results_v3": [{"x": 1}], "evidence_pool_v3": [_item("a")], "evidence_ready_v3": True, "gemini_policy_evidence": [{"results": [_item("a")]}], "gemini_approval_fingerprint": "old"}
    reset_analysis_results(session)
    assert session["evidence_workflow_results_v3"] == []
    assert session["evidence_pool_v3"] == []
    assert not session["evidence_ready_v3"]
    assert session["gemini_policy_evidence"] == []
    assert session["gemini_approval_fingerprint"] is None


def test_traceability_uses_only_the_sanitized_eligible_gemini_pool() -> None:
    supplied = evidence_pool_as_groups(sanitize_policy_evidence_for_gemini([_item("a")]))
    review = review_evidence_traceability(supplied, {"evidence_references": [
        {"chunk_id": "a", "source": "health.pdf", "page": 1, "relevance": "valid"},
        {"chunk_id": "not-supplied", "source": "health.pdf", "page": 1, "relevance": "invalid"},
    ]})
    assert review["valid_reference_count"] == 1
    assert review["invalid_reference_count"] == 1
