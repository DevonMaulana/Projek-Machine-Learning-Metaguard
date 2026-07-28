import json

from core.evidence_reviewer import (
    review_evidence_traceability,
)


def _policy_evidence() -> list[dict]:
    return [
        {
            "query": "metadata statistik",
            "results": [
                {
                    "chunk_id": "policy-p8-c3",
                    "source": "policy.pdf",
                    "page": 8,
                    "text": "Metadata menjelaskan atribut data.",
                    "distance": 0.2,
                },
                {
                    "chunk_id": "policy-p24-c2",
                    "source": "policy.pdf",
                    "page": 24,
                    "text": "Walidata melakukan pemeriksaan.",
                    "distance": 0.3,
                },
            ],
        }
    ]


def test_all_references_valid() -> None:
    gemini_analysis = {
        "evidence_references": [
            {
                "chunk_id": "policy-p8-c3",
                "source": "policy.pdf",
                "page": 8,
                "relevance": "Membahas metadata.",
            }
        ]
    }

    result = review_evidence_traceability(
        policy_evidence=_policy_evidence(),
        gemini_analysis=gemini_analysis,
    )

    assert result["status"] == "valid"
    assert result["traceability_score"] == 100.0
    assert result["valid_reference_count"] == 1
    assert result["invalid_reference_count"] == 0


def test_unknown_chunk_id_is_invalid() -> None:
    gemini_analysis = {
        "evidence_references": [
            {
                "chunk_id": "unknown-p1-c1",
                "source": "unknown.pdf",
                "page": 1,
                "relevance": "Tidak tersedia.",
            }
        ]
    }

    result = review_evidence_traceability(
        policy_evidence=_policy_evidence(),
        gemini_analysis=gemini_analysis,
    )

    assert result["status"] == "invalid"
    assert result["traceability_score"] == 0.0
    assert result["invalid_reference_count"] == 1
    assert (
        "tidak ditemukan"
        in result["invalid_references"][0]["reason"]
    )


def test_source_mismatch_is_invalid() -> None:
    gemini_analysis = {
        "evidence_references": [
            {
                "chunk_id": "policy-p8-c3",
                "source": "wrong.pdf",
                "page": 8,
                "relevance": "Membahas metadata.",
            }
        ]
    }

    result = review_evidence_traceability(
        policy_evidence=_policy_evidence(),
        gemini_analysis=gemini_analysis,
    )

    assert result["status"] == "invalid"
    assert result["invalid_reference_count"] == 1
    assert (
        result["invalid_references"][0][
            "expected_source"
        ]
        == "policy.pdf"
    )


def test_page_mismatch_is_invalid() -> None:
    gemini_analysis = {
        "evidence_references": [
            {
                "chunk_id": "policy-p8-c3",
                "source": "policy.pdf",
                "page": 99,
                "relevance": "Membahas metadata.",
            }
        ]
    }

    result = review_evidence_traceability(
        policy_evidence=_policy_evidence(),
        gemini_analysis=gemini_analysis,
    )

    assert result["status"] == "invalid"
    assert result["invalid_reference_count"] == 1
    assert (
        result["invalid_references"][0][
            "expected_page"
        ]
        == 8
    )


def test_mixed_references_are_partially_valid() -> None:
    gemini_analysis = {
        "evidence_references": [
            {
                "chunk_id": "policy-p8-c3",
                "source": "policy.pdf",
                "page": 8,
                "relevance": "Valid.",
            },
            {
                "chunk_id": "unknown-p1-c1",
                "source": "unknown.pdf",
                "page": 1,
                "relevance": "Tidak valid.",
            },
        ]
    }

    result = review_evidence_traceability(
        policy_evidence=_policy_evidence(),
        gemini_analysis=gemini_analysis,
    )

    assert result["status"] == "partially_valid"
    assert result["traceability_score"] == 50.0
    assert result["valid_reference_count"] == 1
    assert result["invalid_reference_count"] == 1


def test_no_references_status() -> None:
    result = review_evidence_traceability(
        policy_evidence=_policy_evidence(),
        gemini_analysis={
            "evidence_references": [],
        },
    )

    assert result["status"] == "no_references"
    assert result["traceability_score"] == 0
    assert result["total_references"] == 0


def test_unsupported_sections_detected() -> None:
    result = review_evidence_traceability(
        policy_evidence=_policy_evidence(),
        gemini_analysis={
            "metadata_assessment": [
                "Metadata lengkap.",
            ],
            "data_quality_assessment": [
                "Ada nilai kosong.",
            ],
            "priority_actions": [
                {
                    "priority": "Tinggi",
                    "action": "Perbaiki data.",
                    "reason": "Ada masalah.",
                }
            ],
            "evidence_references": [],
        },
    )

    assert len(result["unsupported_sections"]) == 3


def test_output_is_json_safe() -> None:
    result = review_evidence_traceability(
        policy_evidence=_policy_evidence(),
        gemini_analysis={
            "evidence_references": [
                {
                    "chunk_id": "policy-p8-c3",
                    "source": "policy.pdf",
                    "page": "8",
                    "relevance": "Membahas metadata.",
                }
            ],
        },
    )

    encoded = json.dumps(
        result,
        ensure_ascii=False,
    )

    assert "traceability_score" in encoded
    assert result["valid_references"][0]["page"] == 8