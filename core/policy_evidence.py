from __future__ import annotations

from typing import Any


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