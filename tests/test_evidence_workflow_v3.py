"""Tests for isolated bounded v0.3 policy-evidence orchestration."""

from __future__ import annotations

import json

from core.evidence_assessment import assess_v3_evidence
from core.evidence_workflow_v3 import (
    EvidenceWorkflowState,
    PolicyEvidenceWorkflowRequest,
    build_retry_query,
    run_policy_evidence_workflow_v3,
)
from core.policy_router import route_policy_evidence
from rag.policy_retrieval_v3 import RetrievalState, V3RetrievalResult


def _item(chunk_id: str, *, policy_id: str = "HEALTH-SATU-DATA-18-2022", pack: str = "healthcare", domain: str = "healthcare", source: str = "health.pdf") -> dict[str, object]:
    return {"chunk_id": chunk_id, "policy_id": policy_id, "policy_pack": pack, "domain_id": domain, "source": source, "page": 1, "text": "evidence"}


def _request(**overrides: object) -> PolicyEvidenceWorkflowRequest:
    values: dict[str, object] = {
        "selected_domain": "healthcare", "governance_context": "government_public",
        "evidence_need": "domain_semantic_support", "query_text": "data kesehatan satu data",
    }
    values.update(overrides)
    return PolicyEvidenceWorkflowRequest.create(**values)  # type: ignore[arg-type]


def _retriever_from(outputs: list[V3RetrievalResult], calls: list[str]):
    def retrieve(query: str, *, routing, top_k: int) -> V3RetrievalResult:
        calls.append(query)
        result = outputs[len(calls) - 1]
        return V3RetrievalResult(result.state, routing, result.evidence, result.where, result.message)
    return retrieve


def test_ready_first_attempt_stops_without_retry() -> None:
    request = _request()
    route = route_policy_evidence(governance_context="government_public", selected_domain="healthcare", evidence_need="domain_semantic_support")
    calls: list[str] = []
    result = run_policy_evidence_workflow_v3(request, retriever=_retriever_from([V3RetrievalResult(RetrievalState.SUCCESS, route, tuple([_item("a", source="a.pdf"), _item("b", source="b.pdf")]), None)], calls), corpus_is_stale=lambda: False)
    assert result.workflow_state is EvidenceWorkflowState.READY
    assert result.attempt_count == len(calls) == 1
    assert result.stop_reason == "READY"
    assert not result.final_assessment.retry_recommended
    json.dumps(result.to_dict())


def test_not_applicable_and_no_eligible_policy_make_zero_retrieval_calls() -> None:
    calls: list[str] = []
    not_applicable = run_policy_evidence_workflow_v3(
        _request(selected_domain="generic", governance_context="generic_non_government", evidence_need="metadata_governance"),
        retriever=lambda *args, **kwargs: calls.append("called"), corpus_is_stale=lambda: False,
    )
    assert not_applicable.workflow_state is EvidenceWorkflowState.NOT_APPLICABLE
    assert not_applicable.attempt_count == 0
    assert calls == []
    no_policy = run_policy_evidence_workflow_v3(
        _request(selected_domain="generic"), retriever=lambda *args, **kwargs: calls.append("called"), corpus_is_stale=lambda: False,
    )
    assert no_policy.workflow_state is EvidenceWorkflowState.NO_ELIGIBLE_POLICY
    assert no_policy.attempt_count == 0
    assert calls == []


def test_stale_corpus_stops_before_retriever() -> None:
    calls: list[str] = []
    result = run_policy_evidence_workflow_v3(_request(), retriever=lambda *args, **kwargs: calls.append("called"), corpus_is_stale=lambda: True)
    assert result.workflow_state is EvidenceWorkflowState.CORPUS_STALE
    assert result.stop_reason == "CORPUS_STALE"
    assert result.attempt_count == 0 and not calls


def test_empty_then_retry_stops_at_legacy_bound() -> None:
    request = _request()
    route = route_policy_evidence(governance_context="government_public", selected_domain="healthcare", evidence_need="domain_semantic_support")
    calls: list[str] = []
    empty = V3RetrievalResult(RetrievalState.EMPTY, route, (), None)
    result = run_policy_evidence_workflow_v3(request, retriever=_retriever_from([empty, empty], calls), corpus_is_stale=lambda: False)
    assert result.attempt_count == len(calls) == 2
    assert result.stop_reason == "MAX_ATTEMPTS_REACHED"
    assert calls[1] == build_retry_query(request)
    assert calls[0] != calls[1]


def test_second_attempt_uses_cumulative_unique_evidence_for_readiness() -> None:
    request = _request()
    route = route_policy_evidence(governance_context="government_public", selected_domain="healthcare", evidence_need="domain_semantic_support")
    calls: list[str] = []
    first = V3RetrievalResult(RetrievalState.SUCCESS, route, tuple([_item("a", source="a.pdf")]), None)
    second = V3RetrievalResult(RetrievalState.SUCCESS, route, tuple([_item("a", source="a.pdf"), _item("b", source="b.pdf")]), None)
    result = run_policy_evidence_workflow_v3(request, retriever=_retriever_from([first, second], calls), corpus_is_stale=lambda: False)
    assert result.workflow_state is EvidenceWorkflowState.READY
    assert result.attempt_count == 2
    assert [item["chunk_id"] for item in result.cumulative_evidence] == ["a", "b"]
    assert result.final_assessment.sufficiency.score == 100.0
    assert result.attempts[0].sufficiency_score == 75.0
    assert result.attempts[1].sufficiency_score == 100.0


def test_retry_query_is_stable_and_domain_does_not_broaden() -> None:
    healthcare = _request()
    education = _request(selected_domain="education", query_text="data pendidikan")
    assert build_retry_query(healthcare) == build_retry_query(healthcare)
    assert "healthcare" in build_retry_query(healthcare)
    assert "education" in build_retry_query(education)
    assert "education" not in build_retry_query(healthcare)
