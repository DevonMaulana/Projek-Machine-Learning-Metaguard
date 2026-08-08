"""Deterministic evidence sufficiency checks before Gemini analysis.

This module evaluates retrieval coverage before analysis. It is distinct from
the post-analysis traceability reviewer, which verifies Gemini references.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

MAX_RETRIEVAL_ATTEMPTS = 2
SUFFICIENT_THRESHOLD = 85.0
PARTIAL_THRESHOLD = 40.0
MIN_UNIQUE_EVIDENCE_FOR_SUFFICIENT = 2


def build_evidence_needs(
    metadata_validation: dict[str, Any],
    quality_findings: list[dict[str, Any]],
    contextual_validation: dict[str, Any] | None = None,
) -> list[str]:
    """Derive compact policy-evidence needs from deterministic outputs."""
    needs: list[str] = []
    if metadata_validation.get("missing_fields") or metadata_validation.get("findings"):
        needs.append("metadata_governance")
    else:
        needs.append("metadata_governance")
    if quality_findings or (contextual_validation or {}).get("finding_count", 0):
        needs.append("data_quality")
    needs.append("accountability")
    return needs


def classify_policy_query(query: str) -> str | None:
    """Classify only known deterministic policy-query concepts."""
    normalized = query.casefold()
    if "produsen data" in normalized or "walidata" in normalized:
        return "accountability"
    if "kualitas data" in normalized or "nilai kosong" in normalized or "duplikasi" in normalized:
        return "data_quality"
    if "metadata" in normalized:
        return "metadata_governance"
    return None


def _chunk_key(chunk: dict[str, Any]) -> tuple[str, ...] | None:
    chunk_id = str(chunk.get("chunk_id", "")).strip()
    if chunk_id:
        return ("chunk_id", chunk_id)
    source = str(chunk.get("source", "")).strip()
    page = str(chunk.get("page", "")).strip()
    text = re.sub(r"\s+", " ", str(chunk.get("text", "")).strip())
    if source or page or text:
        return ("source_page_text", source, page, text)
    return None


def _iter_results(policy_evidence: Iterable[dict[str, Any]]) -> Iterable[tuple[str | None, dict[str, Any]]]:
    for group in policy_evidence:
        if not isinstance(group, dict):
            continue
        need = group.get("need") or classify_policy_query(str(group.get("query", "")))
        results = group.get("results", [])
        if not isinstance(results, list):
            continue
        for result in results:
            if isinstance(result, dict):
                yield str(need) if need else None, result


def evaluate_evidence_sufficiency(
    policy_evidence: list[dict[str, Any]],
    evidence_needs: list[str],
) -> dict[str, Any]:
    """Score deterministic coverage without using embeddings, distance, or an LLM.

    Score = coverage (60) + unique-evidence adequacy (30) + source diversity
    (10). Thresholds are MetaGuard heuristics, not policy standards.
    """
    needs = list(dict.fromkeys(item for item in evidence_needs if item))
    unique_chunks: dict[tuple[str, ...], dict[str, Any]] = {}
    covered_needs: set[str] = set()
    total_retrieved = 0
    for need, chunk in _iter_results(policy_evidence):
        total_retrieved += 1
        key = _chunk_key(chunk)
        if key is None:
            continue
        is_unique = key not in unique_chunks
        unique_chunks.setdefault(key, chunk)
        if is_unique and need in needs:
            covered_needs.add(need)

    unique_evidence_count = len(unique_chunks)
    duplicate_count = max(0, total_retrieved - unique_evidence_count)
    unique_sources = {
        str(chunk.get("source", "")).strip()
        for chunk in unique_chunks.values()
        if str(chunk.get("source", "")).strip()
    }
    coverage_ratio = len(covered_needs) / len(needs) if needs else 0.0
    adequacy_ratio = min(unique_evidence_count / MIN_UNIQUE_EVIDENCE_FOR_SUFFICIENT, 1.0)
    diversity_score = 10.0 if len(unique_sources) >= 2 else 0.0
    score = round(coverage_ratio * 60.0 + adequacy_ratio * 30.0 + diversity_score, 2)
    missing_coverage = [need for need in needs if need not in covered_needs]

    if (
        coverage_ratio == 1.0
        and unique_evidence_count >= MIN_UNIQUE_EVIDENCE_FOR_SUFFICIENT
        and score >= SUFFICIENT_THRESHOLD
    ):
        status = "sufficient"
        recommended_action = "proceed_to_analysis"
    elif unique_evidence_count and score >= PARTIAL_THRESHOLD:
        status = "partial"
        recommended_action = "retry_retrieval" if missing_coverage else "requires_human_review"
    else:
        status = "insufficient"
        recommended_action = "retry_retrieval" if missing_coverage else "requires_human_review"

    reasons: list[str] = []
    if not unique_evidence_count:
        reasons.append("Tidak ada evidence policy yang dapat digunakan.")
    if missing_coverage:
        reasons.append("Coverage belum tersedia untuk: " + ", ".join(missing_coverage) + ".")
    if unique_evidence_count < MIN_UNIQUE_EVIDENCE_FOR_SUFFICIENT:
        reasons.append("Jumlah evidence unik belum memenuhi heuristic minimum MetaGuard.")
    if duplicate_count:
        reasons.append(f"{duplicate_count} hasil duplikat tidak dihitung sebagai evidence tambahan.")

    return {
        "status": status,
        "score": score,
        "total_retrieved": total_retrieved,
        "evidence_count": total_retrieved,
        "unique_evidence_count": unique_evidence_count,
        "unique_source_count": len(unique_sources),
        "duplicate_count": duplicate_count,
        "coverage": {need: need in covered_needs for need in needs},
        "missing_coverage": missing_coverage,
        "reasons": reasons,
        "recommended_action": recommended_action,
    }


def refine_policy_queries(
    missing_coverage: list[str],
) -> list[str]:
    """Return stable, template-based queries for uncovered policy concepts."""
    templates = {
        "metadata_governance": "standar metadata statistik produsen data walidata Satu Data Indonesia",
        "data_quality": "standar pemeriksaan kualitas data nilai kosong duplikasi konsistensi format Satu Data Indonesia",
        "accountability": "peran produsen data walidata tanggung jawab perbaikan data Satu Data Indonesia",
    }
    return [templates[need] for need in dict.fromkeys(missing_coverage) if need in templates]


def deduplicate_policy_evidence(
    policy_evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep the first exact chunk occurrence while preserving group order."""
    seen: set[tuple[str, ...]] = set()
    deduplicated: list[dict[str, Any]] = []
    for group in policy_evidence:
        if not isinstance(group, dict):
            continue
        results = group.get("results", [])
        unique_results: list[dict[str, Any]] = []
        if isinstance(results, list):
            for result in results:
                if not isinstance(result, dict):
                    continue
                key = _chunk_key(result)
                if key is not None and key in seen:
                    continue
                if key is not None:
                    seen.add(key)
                unique_results.append(result)
        clean_group = dict(group)
        clean_group["results"] = unique_results
        deduplicated.append(clean_group)
    return deduplicated
