import json

import pytest

from core.policy_evidence import build_policy_evidence, build_policy_queries


def test_build_queries_for_complete_metadata() -> None:
    metadata_validation = {
        "missing_fields": [],
        "findings": [],
    }

    queries = build_policy_queries(metadata_validation, [])

    assert len(queries) <= 3
    assert any("metadata statistik" in query for query in queries)


def test_build_queries_for_incomplete_metadata() -> None:
    metadata_validation = {
        "missing_fields": ["description", "producer_opd"],
        "findings": [],
    }

    queries = build_policy_queries(metadata_validation, [])

    assert any("kelengkapan metadata" in query for query in queries)


def test_build_queries_from_quality_findings() -> None:
    metadata_validation = {
        "missing_fields": [],
        "findings": [],
    }

    quality_findings = [
        {
            "check_id": "missing_values",
            "severity": "medium",
        }
    ]

    queries = build_policy_queries(
        metadata_validation,
        quality_findings,
    )

    assert any("pemeriksaan kualitas data" in query for query in queries)


def test_queries_limited_to_three() -> None:
    metadata_validation = {
        "missing_fields": ["title"],
        "findings": [{"field": "title"}],
    }

    queries = build_policy_queries(
        metadata_validation,
        [{"check_id": "duplicate_rows"}],
    )

    assert len(queries) <= 3


def test_build_policy_evidence_is_json_safe() -> None:
    def fake_retriever(query: str, top_k: int) -> list[dict]:
        return [
            {
                "chunk_id": "policy-p1-c1",
                "source": "policy.pdf",
                "page": 1,
                "text": f"Evidence untuk {query}",
                "distance": 0.25,
            }
        ][:top_k]

    evidence = build_policy_evidence(
        ["metadata statistik"],
        fake_retriever,
        top_k=1,
    )

    encoded = json.dumps(evidence, ensure_ascii=False)

    assert "policy.pdf" in encoded
    assert evidence[0]["query"] == "metadata statistik"


def test_invalid_top_k_rejected() -> None:
    with pytest.raises(ValueError):
        build_policy_evidence(
            ["metadata"],
            lambda query, top_k: [],
            top_k=0,
        )