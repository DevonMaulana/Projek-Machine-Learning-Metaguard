"""Tests for the layered, isolated v0.3 evidence assessment API."""

from __future__ import annotations

import json

from core.evidence_assessment import EvidenceReadinessState, SufficiencyState, assess_v3_evidence, combine_evidence_attempts
from core.evidence_sufficiency import evaluate_evidence_sufficiency
from core.policy_router import route_policy_evidence
from rag.policy_retrieval_v3 import RetrievalState, V3RetrievalResult


def _item(chunk_id: str, *, policy_id: str = "HEALTH-SATU-DATA-18-2022", pack: str = "healthcare", domain: str = "healthcare", source: str = "health.pdf") -> dict[str, object]:
    return {"chunk_id": chunk_id, "policy_id": policy_id, "policy_pack": pack, "domain_id": domain, "source": source, "page": 1, "text": "Evidence."}


def _result(state: RetrievalState, routing, evidence=()) -> V3RetrievalResult:
    return V3RetrievalResult(state, routing, tuple(evidence), None)


def test_not_applicable_is_not_scored_or_retried() -> None:
    routing = route_policy_evidence(governance_context="generic_non_government", selected_domain="generic", evidence_need="metadata_governance")
    assessment = assess_v3_evidence(_result(RetrievalState.NOT_APPLICABLE, routing))
    assert assessment.sufficiency.state is SufficiencyState.NOT_ASSESSED
    assert assessment.readiness is EvidenceReadinessState.NOT_APPLICABLE
    assert not assessment.retry_recommended


def test_empty_applicable_retrieval_is_insufficient_and_retryable() -> None:
    routing = route_policy_evidence(governance_context="government_public", selected_domain="healthcare", evidence_need="domain_semantic_support")
    assessment = assess_v3_evidence(_result(RetrievalState.EMPTY, routing))
    assert assessment.sufficiency.state is SufficiencyState.INSUFFICIENT
    assert assessment.readiness is EvidenceReadinessState.NOT_READY
    assert assessment.retry_recommended


def test_stale_corpus_is_not_a_retry_condition() -> None:
    routing = route_policy_evidence(governance_context="government_public", selected_domain="healthcare", evidence_need="domain_semantic_support")
    assessment = assess_v3_evidence(_result(RetrievalState.CORPUS_STALE, routing))
    assert assessment.readiness is EvidenceReadinessState.CORPUS_STALE
    assert assessment.sufficiency.state is SufficiencyState.NOT_ASSESSED
    assert not assessment.retry_recommended


def test_no_eligible_policy_is_not_misrepresented_as_insufficient() -> None:
    routing = route_policy_evidence(governance_context="government_public", selected_domain="generic", evidence_need="domain_semantic_support")
    assessment = assess_v3_evidence(_result(RetrievalState.NOT_APPLICABLE, routing))
    assert assessment.sufficiency.state is SufficiencyState.NOT_ASSESSED
    assert assessment.readiness is EvidenceReadinessState.NOT_READY
    assert not assessment.retry_recommended


def test_legacy_sufficiency_formula_is_preserved_for_eligible_v3_evidence() -> None:
    routing = route_policy_evidence(governance_context="government_public", selected_domain="healthcare", evidence_need="domain_semantic_support")
    evidence = [_item("one", source="a.pdf"), _item("two", source="b.pdf")]
    assessment = assess_v3_evidence(_result(RetrievalState.SUCCESS, routing, evidence))
    legacy = evaluate_evidence_sufficiency([{"need": "domain_semantic_support", "results": evidence}], ["domain_semantic_support"])
    assert assessment.sufficiency.score == legacy["score"] == 100.0
    assert assessment.sufficiency.state is SufficiencyState.SUFFICIENT
    assert assessment.readiness is EvidenceReadinessState.READY
    assert assessment.evidence_ready_for_review
    json.dumps(assessment.to_dict())


def test_ineligible_or_duplicate_evidence_cannot_improve_readiness() -> None:
    routing = route_policy_evidence(governance_context="government_public", selected_domain="healthcare", evidence_need="domain_semantic_support")
    bad = _item("bad", policy_id="EDU-SATU-DATA-31-2022", pack="education", domain="education", source="edu.pdf")
    assessment = assess_v3_evidence(_result(RetrievalState.SUCCESS, routing, [_item("same"), _item("same"), bad]))
    assert assessment.sufficiency.unique_chunk_count == 1
    assert assessment.sufficiency.state is SufficiencyState.PARTIAL
    assert assessment.readiness is EvidenceReadinessState.NOT_READY
    assert assessment.retry_recommended
    assert assessment.alignment.rejected_chunk_ids == ("bad",)


def test_one_source_does_not_receive_legacy_diversity_points_and_is_deterministic() -> None:
    routing = route_policy_evidence(governance_context="government_public", selected_domain="healthcare", evidence_need="domain_semantic_support")
    evidence = [_item("one"), _item("two")]
    first = assess_v3_evidence(_result(RetrievalState.SUCCESS, routing, evidence))
    second = assess_v3_evidence(_result(RetrievalState.SUCCESS, routing, list(reversed(evidence))))
    assert first.sufficiency.score == second.sufficiency.score == 90.0
    assert first.sufficiency.source_count == second.sufficiency.source_count == 1
    assert first.sufficiency.state is SufficiencyState.SUFFICIENT


def test_cumulative_helper_preserves_attempt_order_and_removes_duplicates() -> None:
    first = [_item("a"), _item("shared")]
    second = [_item("shared"), _item("c")]
    combined = combine_evidence_attempts([first, second])
    assert [item["chunk_id"] for item in combined] == ["a", "shared", "c"]
