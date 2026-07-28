"""Deterministic traceability review for Gemini policy references."""

from __future__ import annotations

from typing import Any


def _build_evidence_index(
    policy_evidence: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build an index of retrieved evidence keyed by chunk_id."""
    evidence_index: dict[str, dict[str, Any]] = {}

    for evidence_group in policy_evidence:
        results = evidence_group.get("results", [])

        if not isinstance(results, list):
            continue

        for result in results:
            if not isinstance(result, dict):
                continue

            chunk_id = str(
                result.get("chunk_id", "")
            ).strip()

            if not chunk_id:
                continue

            evidence_index[chunk_id] = {
                "chunk_id": chunk_id,
                "source": str(
                    result.get("source", "")
                ).strip(),
                "page": result.get("page"),
                "text": str(
                    result.get("text", "")
                ).strip(),
            }

    return evidence_index


def _normalize_page(value: Any) -> int | None:
    """Convert a page value to int when possible."""
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    if isinstance(value, str):
        clean_value = value.strip()

        if clean_value.isdigit():
            return int(clean_value)

    return None


def review_evidence_traceability(
    policy_evidence: list[dict[str, Any]],
    gemini_analysis: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate Gemini evidence references against retrieved policy evidence.

    The review is deterministic and does not call an LLM.
    """
    evidence_index = _build_evidence_index(
        policy_evidence
    )

    raw_references = gemini_analysis.get(
        "evidence_references",
        [],
    )

    if not isinstance(raw_references, list):
        raw_references = []

    valid_references: list[dict[str, Any]] = []
    invalid_references: list[dict[str, Any]] = []

    for reference in raw_references:
        if not isinstance(reference, dict):
            invalid_references.append(
                {
                    "chunk_id": "",
                    "source": "",
                    "page": None,
                    "reason": (
                        "Format referensi bukan dictionary."
                    ),
                }
            )
            continue

        chunk_id = str(
            reference.get("chunk_id", "")
        ).strip()
        source = str(
            reference.get("source", "")
        ).strip()
        page = _normalize_page(
            reference.get("page")
        )

        matched_evidence = evidence_index.get(
            chunk_id
        )

        if matched_evidence is None:
            invalid_references.append(
                {
                    "chunk_id": chunk_id,
                    "source": source,
                    "page": page,
                    "reason": (
                        "chunk_id tidak ditemukan pada "
                        "policy_evidence."
                    ),
                }
            )
            continue

        expected_source = matched_evidence["source"]
        expected_page = _normalize_page(
            matched_evidence["page"]
        )

        mismatch_reasons: list[str] = []

        if source != expected_source:
            mismatch_reasons.append(
                "source tidak sesuai dengan evidence asli"
            )

        if page != expected_page:
            mismatch_reasons.append(
                "page tidak sesuai dengan evidence asli"
            )

        if mismatch_reasons:
            invalid_references.append(
                {
                    "chunk_id": chunk_id,
                    "source": source,
                    "page": page,
                    "expected_source": expected_source,
                    "expected_page": expected_page,
                    "reason": "; ".join(
                        mismatch_reasons
                    ),
                }
            )
            continue

        valid_references.append(
            {
                "chunk_id": chunk_id,
                "source": source,
                "page": page,
                "relevance": str(
                    reference.get(
                        "relevance",
                        "",
                    )
                ).strip(),
            }
        )

    total_references = len(raw_references)
    valid_count = len(valid_references)
    invalid_count = len(invalid_references)

    if total_references == 0:
        traceability_score = 0
    else:
        traceability_score = round(
            valid_count / total_references * 100,
            2,
        )

    unsupported_sections: list[str] = []

    sections_requiring_evidence = {
        "metadata_assessment": (
            "Penilaian metadata tidak memiliki "
            "referensi evidence yang tervalidasi."
        ),
        "data_quality_assessment": (
            "Penilaian kualitas data tidak memiliki "
            "referensi evidence yang tervalidasi."
        ),
        "priority_actions": (
            "Tindakan prioritas tidak memiliki "
            "referensi evidence yang tervalidasi."
        ),
    }

    for section_name, warning_message in (
        sections_requiring_evidence.items()
    ):
        section_value = gemini_analysis.get(
            section_name,
            [],
        )

        if section_value and valid_count == 0:
            unsupported_sections.append(
                warning_message
            )

    if total_references == 0:
        status = "no_references"
    elif invalid_count == 0:
        status = "valid"
    elif valid_count == 0:
        status = "invalid"
    else:
        status = "partially_valid"

    return {
        "status": status,
        "total_references": total_references,
        "valid_references": valid_references,
        "valid_reference_count": valid_count,
        "invalid_references": invalid_references,
        "invalid_reference_count": invalid_count,
        "unsupported_sections": unsupported_sections,
        "traceability_score": traceability_score,
    }