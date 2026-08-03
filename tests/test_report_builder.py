import json

import pytest

from core.report_builder import build_report, save_report_json


def test_build_and_save_report(tmp_path) -> None:
    report = build_report(
        profile={
            "row_count": 1,
        },
        findings=[],
        score={
            "score": 100,
            "findings_by_severity": {},
        },
        source={
            "file_name": "x.csv",
        },
    )

    assert report["schema_version"]
    assert report["source"]["file_name"] == "x.csv"
    assert report["policy_evidence"] == []
    assert report["gemini_analysis"] == {}
    assert report["evidence_review"] == {}
    assert report["ingestion"] == {}

    json.dumps(report)

    target = tmp_path / "nested" / "report.json"

    assert save_report_json(
        report,
        target,
    ) == target

    saved_report = json.loads(
        target.read_text(
            encoding="utf-8",
        )
    )

    assert (
        saved_report["source"]["file_name"]
        == "x.csv"
    )

    with pytest.raises(FileExistsError):
        save_report_json(
            report,
            target,
        )

    save_report_json(
        report,
        target,
        overwrite=True,
    )


def test_report_contains_policy_evidence() -> None:
    policy_evidence = [
        {
            "query": "metadata statistik",
            "results": [
                {
                    "chunk_id": "policy-p1-c1",
                    "source": "policy.pdf",
                    "page": 1,
                    "text": "Evidence metadata statistik.",
                    "distance": 0.2,
                }
            ],
        }
    ]

    report = build_report(
        profile={
            "row_count": 1,
        },
        findings=[],
        score={
            "score": 100,
            "findings_by_severity": {},
        },
        policy_evidence=policy_evidence,
    )

    assert (
        report["policy_evidence"]
        == policy_evidence
    )
    assert (
        report["policy_evidence"][0]["query"]
        == "metadata statistik"
    )
    assert (
        report["policy_evidence"][0]["results"][0][
            "source"
        ]
        == "policy.pdf"
    )

    json.dumps(
        report,
        ensure_ascii=False,
    )


def test_report_uses_empty_policy_evidence_when_none() -> None:
    report = build_report(
        profile={
            "row_count": 0,
        },
        findings=[],
        score={
            "score": 100,
            "findings_by_severity": {},
        },
        policy_evidence=None,
    )

    assert report["policy_evidence"] == []


def test_report_contains_gemini_analysis() -> None:
    gemini_analysis = {
        "summary": "Dataset memerlukan perbaikan.",
        "metadata_assessment": [
            "Metadata lengkap.",
        ],
        "data_quality_assessment": [
            "Terdapat nilai kosong.",
        ],
        "priority_actions": [
            {
                "priority": "Tinggi",
                "action": "Perbaiki nilai kosong.",
                "reason": (
                    "Nilai kosong memengaruhi kualitas data."
                ),
            }
        ],
        "evidence_references": [
            {
                "chunk_id": "policy-p1-c1",
                "source": "policy.pdf",
                "page": 1,
                "relevance": (
                    "Membahas pemeriksaan data."
                ),
            }
        ],
        "limitations": [
            "Analisis hanya memakai evidence yang tersedia.",
        ],
    }

    report = build_report(
        profile={
            "row_count": 1,
        },
        findings=[],
        score={
            "score": 100,
            "findings_by_severity": {},
        },
        gemini_analysis=gemini_analysis,
    )

    assert (
        report["gemini_analysis"]
        == gemini_analysis
    )
    assert (
        report["gemini_analysis"][
            "priority_actions"
        ][0]["priority"]
        == "Tinggi"
    )

    json.dumps(
        report,
        ensure_ascii=False,
    )


def test_report_uses_empty_gemini_analysis_when_none() -> None:
    report = build_report(
        profile={
            "row_count": 0,
        },
        findings=[],
        score={
            "score": 100,
            "findings_by_severity": {},
        },
        gemini_analysis=None,
    )

    assert report["gemini_analysis"] == {}


def test_report_contains_evidence_review() -> None:
    evidence_review = {
        "status": "valid",
        "total_references": 2,
        "valid_references": [
            {
                "chunk_id": "policy-p1-c1",
                "source": "policy.pdf",
                "page": 1,
                "relevance": (
                    "Membahas pemeriksaan data."
                ),
            },
            {
                "chunk_id": "policy-p2-c1",
                "source": "policy.pdf",
                "page": 2,
                "relevance": (
                    "Membahas metadata statistik."
                ),
            },
        ],
        "valid_reference_count": 2,
        "invalid_references": [],
        "invalid_reference_count": 0,
        "unsupported_sections": [],
        "traceability_score": 100.0,
    }

    report = build_report(
        profile={
            "row_count": 1,
        },
        findings=[],
        score={
            "score": 100,
            "findings_by_severity": {},
        },
        evidence_review=evidence_review,
    )

    assert (
        report["evidence_review"]
        == evidence_review
    )
    assert (
        report["evidence_review"]["status"]
        == "valid"
    )
    assert (
        report["evidence_review"][
            "traceability_score"
        ]
        == 100.0
    )

    json.dumps(
        report,
        ensure_ascii=False,
    )


def test_report_uses_empty_evidence_review_when_none() -> None:
    report = build_report(
        profile={
            "row_count": 0,
        },
        findings=[],
        score={
            "score": 100,
            "findings_by_severity": {},
        },
        evidence_review=None,
    )

    assert report["evidence_review"] == {}


def test_complete_report_is_json_safe() -> None:
    policy_evidence = [
        {
            "query": "metadata statistik",
            "results": [
                {
                    "chunk_id": "policy-p1-c1",
                    "source": "policy.pdf",
                    "page": 1,
                    "text": "Metadata statistik.",
                    "distance": 0.2,
                }
            ],
        }
    ]

    gemini_analysis = {
        "summary": "Ringkasan analisis.",
        "metadata_assessment": [
            "Metadata lengkap.",
        ],
        "data_quality_assessment": [
            "Terdapat nilai kosong.",
        ],
        "priority_actions": [],
        "evidence_references": [
            {
                "chunk_id": "policy-p1-c1",
                "source": "policy.pdf",
                "page": 1,
                "relevance": "Evidence metadata.",
            }
        ],
        "limitations": [],
    }

    evidence_review = {
        "status": "valid",
        "total_references": 1,
        "valid_references": [
            {
                "chunk_id": "policy-p1-c1",
                "source": "policy.pdf",
                "page": 1,
                "relevance": "Evidence metadata.",
            }
        ],
        "valid_reference_count": 1,
        "invalid_references": [],
        "invalid_reference_count": 0,
        "unsupported_sections": [],
        "traceability_score": 100.0,
    }

    report = build_report(
        profile={
            "row_count": 10,
            "column_count": 6,
        },
        findings=[],
        score={
            "score": 100,
            "findings_by_severity": {},
        },
        metadata={
            "title": "Data Puskesmas",
        },
        metadata_validation={
            "status": "Lengkap",
            "completeness_score": 100.0,
        },
        policy_evidence=policy_evidence,
        gemini_analysis=gemini_analysis,
        evidence_review=evidence_review,
    )

    encoded = json.dumps(
        report,
        ensure_ascii=False,
    )

    assert "policy_evidence" in encoded
    assert "gemini_analysis" in encoded
    assert "evidence_review" in encoded


def test_report_contains_ingestion_diagnostics() -> None:
    ingestion = {
        "status": "success_with_warnings",
        "mode": "chunked",
        "analysis_scope": "full",
        "rows_loaded": 250000,
        "warnings": ["Satu baris malformed terdeteksi."],
    }
    report = build_report(
        profile={}, findings=[],
        score={"score": 100, "findings_by_severity": {}},
        ingestion=ingestion,
    )
    assert report["ingestion"] == ingestion
    json.dumps(report)


def test_report_preserves_chunked_and_sampled_configuration() -> None:
    sampled = {
        "mode": "sampled",
        "analysis_scope": "sampled",
        "memory_strategy": "reservoir_sample",
        "sampling_method": "reservoir_sampling",
        "sampling_applied": True,
        "sample_size_requested": 10_000,
        "sample_seed": 42,
        "sampled_rows": 10_000,
        "rows_loaded": 10_000,
        "total_rows": 12_000,
    }
    chunked = {
        "mode": "chunked",
        "analysis_scope": "full",
        "memory_strategy": "combined_dataframe",
        "chunk_size_requested": 2_000,
    }
    for ingestion in (sampled, chunked):
        report = build_report({}, [], {"score": 100, "findings_by_severity": {}}, ingestion=ingestion)
        assert report["ingestion"] == ingestion
        json.dumps(report)
