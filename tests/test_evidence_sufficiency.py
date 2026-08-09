"""Tests for deterministic pre-Gemini evidence sufficiency and retry bounds."""

from __future__ import annotations

import json

from core.evidence_sufficiency import (
    MAX_RETRIEVAL_ATTEMPTS,
    evaluate_evidence_sufficiency,
    refine_policy_queries,
)
from core.policy_evidence import retrieve_with_bounded_retry


NEEDS = ["metadata_governance", "data_quality"]


def _chunk(chunk_id: str, source: str = "policy.pdf") -> dict[str, object]:
    return {"chunk_id": chunk_id, "source": source, "page": 1, "text": "Evidence kebijakan."}


def test_zero_evidence_is_insufficient_and_json_safe() -> None:
    result = evaluate_evidence_sufficiency([], NEEDS)
    assert result["status"] == "insufficient"
    assert result["missing_coverage"] == NEEDS
    json.dumps(result)


def test_one_evidence_is_not_sufficient_even_with_coverage() -> None:
    result = evaluate_evidence_sufficiency(
        [{"need": "metadata_governance", "query": "metadata", "results": [_chunk("one")]}],
        ["metadata_governance"],
    )
    assert result["status"] == "partial"
    assert result["unique_evidence_count"] == 1


def test_full_coverage_with_two_unique_chunks_is_sufficient() -> None:
    evidence = [
        {"need": "metadata_governance", "query": "metadata", "results": [_chunk("m1")]},
        {"need": "data_quality", "query": "kualitas data", "results": [_chunk("q1", "other.pdf")]},
    ]
    result = evaluate_evidence_sufficiency(evidence, NEEDS)
    assert result["status"] == "sufficient"
    assert result["coverage"] == {"metadata_governance": True, "data_quality": True}
    assert result["unique_source_count"] == 2


def test_partial_coverage_and_repeated_evaluation_are_deterministic() -> None:
    evidence = [{"need": "metadata_governance", "query": "metadata", "results": [_chunk("m1")]}]
    first = evaluate_evidence_sufficiency(evidence, NEEDS)
    second = evaluate_evidence_sufficiency(evidence, NEEDS)
    assert first == second
    assert first["status"] == "partial"
    assert first["missing_coverage"] == ["data_quality"]


def test_duplicate_chunk_does_not_inflate_sufficiency() -> None:
    evidence = [
        {"need": "metadata_governance", "query": "metadata", "results": [_chunk("same"), _chunk("same")]},
        {"need": "data_quality", "query": "kualitas data", "results": [_chunk("same")]},
    ]
    result = evaluate_evidence_sufficiency(evidence, NEEDS)
    assert result["unique_evidence_count"] == 1
    assert result["duplicate_count"] == 2
    assert result["status"] != "sufficient"


def test_refined_queries_are_stable_and_different_from_original() -> None:
    refined = refine_policy_queries(["metadata_governance", "data_quality"])
    assert refined == refine_policy_queries(["metadata_governance", "data_quality"])
    assert all("Satu Data Indonesia" in query for query in refined)


def test_bounded_retry_stops_after_sufficient_second_attempt() -> None:
    calls: list[str] = []

    def retriever(query: str, *, top_k: int) -> list[dict[str, object]]:
        calls.append(query)
        if "Satu Data Indonesia" in query:
            return [_chunk(f"refined-{len(calls)}", "refined.pdf")]
        return [_chunk("initial")]

    result = retrieve_with_bounded_retry(
        initial_queries=["metadata statistik"],
        evidence_needs=["metadata_governance", "data_quality"],
        retriever=retriever,
    )
    assert len(result["retrieval_attempts"]) == 2
    assert result["retrieval_attempts"][0]["attempt_number"] == 1
    assert result["retrieval_attempts"][1]["attempt_number"] == 2
    assert result["evidence_sufficiency"]["status"] == "sufficient"
    assert len(calls) <= 1 + 2


def test_retry_keeps_cumulative_evidence_and_deduplicates_final_order() -> None:
    def retriever(query: str, *, top_k: int) -> list[dict[str, object]]:
        if "metadata statistik" in query:
            return [_chunk("metadata-a"), _chunk("shared")]
        return [_chunk("shared"), _chunk("accountability-c", "accountability.pdf")]

    result = retrieve_with_bounded_retry(
        initial_queries=["metadata statistik"],
        evidence_needs=["metadata_governance", "accountability"],
        retriever=retriever,
    )
    final_ids = [
        chunk["chunk_id"]
        for group in result["policy_evidence"]
        for chunk in group["results"]
    ]
    assert final_ids == ["metadata-a", "shared", "accountability-c"]
    assert result["evidence_sufficiency"]["coverage"] == {
        "metadata_governance": True,
        "accountability": True,
    }
    assert result["evidence_sufficiency"]["duplicate_count"] == 1
    assert [attempt["attempt_number"] for attempt in result["retrieval_attempts"]] == [1, 2]
    assert [attempt["evidence_count"] for attempt in result["retrieval_attempts"]] == [2, 2]
    assert result["retrieval_attempts"][0]["missing_coverage"] == ["accountability"]


def test_duplicate_cannot_claim_complete_coverage_and_empty_refinement_is_safe() -> None:
    result = evaluate_evidence_sufficiency(
        [
            {"need": "metadata_governance", "query": "metadata", "results": [_chunk("one")]},
            {"need": "data_quality", "query": "quality", "results": [_chunk("one")]},
        ],
        NEEDS,
    )
    assert result["missing_coverage"] == ["data_quality"]
    assert refine_policy_queries([]) == []


def test_sufficient_first_attempt_does_not_retry() -> None:
    calls: list[str] = []

    def retriever(query: str, *, top_k: int) -> list[dict[str, object]]:
        calls.append(query)
        return [_chunk(f"chunk-{len(calls)}")]

    result = retrieve_with_bounded_retry(
        initial_queries=["metadata statistik", "pemeriksaan kualitas data"],
        evidence_needs=NEEDS,
        retriever=retriever,
    )
    assert result["evidence_sufficiency"]["status"] == "sufficient"
    assert len(result["retrieval_attempts"]) == 1
    assert len(calls) == 2


def test_bounded_retry_never_exceeds_limit_when_still_insufficient() -> None:
    def empty_retriever(query: str, *, top_k: int) -> list[dict[str, object]]:
        return []

    result = retrieve_with_bounded_retry(
        initial_queries=["metadata statistik"],
        evidence_needs=NEEDS,
        retriever=empty_retriever,
    )
    assert len(result["retrieval_attempts"]) == MAX_RETRIEVAL_ATTEMPTS
    assert result["evidence_sufficiency"]["status"] == "insufficient"
