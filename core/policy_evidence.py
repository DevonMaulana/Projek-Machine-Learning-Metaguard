from __future__ import annotations

from typing import Any

from core.evidence_sufficiency import (
    MAX_RETRIEVAL_ATTEMPTS,
    deduplicate_policy_evidence,
    evaluate_evidence_sufficiency,
    refine_policy_queries,
)


MAX_POLICY_QUERIES = 3


def build_policy_queries(
    metadata_validation: dict[str, Any],
    quality_findings: list[dict[str, Any]],
) -> list[str]:
    """
    Build deterministic policy retrieval queries.

    The function does not use an LLM. Queries are selected from metadata
    completeness and local data-quality findings.
    """
    queries: list[str] = []

    missing_fields = metadata_validation.get("missing_fields", [])
    metadata_findings = metadata_validation.get("findings", [])

    if missing_fields or metadata_findings:
        queries.append(
            "ketentuan kelengkapan metadata statistik untuk dataset pemerintah"
        )
    else:
        queries.append(
            "metadata statistik yang harus disediakan dalam publikasi dataset"
        )

    if quality_findings:
        queries.append(
            "pemeriksaan kualitas data sebelum publikasi meliputi nilai kosong "
            "duplikasi konsistensi dan format data"
        )

    queries.append(
        "tugas produsen data dan walidata dalam pemeriksaan serta perbaikan data"
    )

    unique_queries: list[str] = []
    seen: set[str] = set()

    for query in queries:
        normalized = query.strip().casefold()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_queries.append(query.strip())

    return unique_queries[:MAX_POLICY_QUERIES]


def build_policy_evidence(
    queries: list[str],
    retriever: Any,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """
    Retrieve policy evidence for deterministic queries.

    The retriever must accept:
        retriever(query: str, top_k: int) -> list[dict[str, Any]]
    """
    if top_k < 1:
        raise ValueError("top_k minimal 1.")

    evidence: list[dict[str, Any]] = []

    for query in queries[:MAX_POLICY_QUERIES]:
        clean_query = query.strip()
        if not clean_query:
            continue

        results = retriever(clean_query, top_k=top_k)

        evidence.append(
            {
                "query": clean_query,
                "results": results,
            }
        )

    return evidence


def retrieve_with_bounded_retry(
    *,
    initial_queries: list[str],
    evidence_needs: list[str],
    retriever: Any,
    top_k: int = 3,
) -> dict[str, Any]:
    """Retrieve once, then perform at most one deterministic refinement retry.

    The returned attempts contain only lightweight query and sufficiency
    metadata. Full evidence remains in ``policy_evidence`` for the existing
    traceability and Gemini workflow.
    """
    all_evidence: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    queries = initial_queries

    for attempt_number in range(1, MAX_RETRIEVAL_ATTEMPTS + 1):
        retrieved = build_policy_evidence(queries, retriever, top_k=top_k)
        attempt_evaluation = evaluate_evidence_sufficiency(retrieved, evidence_needs)
        all_evidence.extend(retrieved)
        sufficiency = evaluate_evidence_sufficiency(all_evidence, evidence_needs)
        attempts.append(
            {
                "attempt_number": attempt_number,
                "queries": list(queries),
                "evidence_count": attempt_evaluation["evidence_count"],
                "unique_evidence_count": attempt_evaluation["unique_evidence_count"],
                "sufficiency_status": sufficiency["status"],
                "sufficiency_score": sufficiency["score"],
                "missing_coverage": list(sufficiency["missing_coverage"]),
                "reason": "; ".join(sufficiency["reasons"]),
            }
        )
        if sufficiency["status"] == "sufficient":
            break
        queries = refine_policy_queries(sufficiency["missing_coverage"])
        if not queries:
            break

    return {
        "policy_evidence": deduplicate_policy_evidence(all_evidence),
        "evidence_sufficiency": sufficiency,
        "retrieval_attempts": attempts,
    }
