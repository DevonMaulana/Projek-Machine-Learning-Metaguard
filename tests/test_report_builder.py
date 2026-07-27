import json

import pytest

from core.report_builder import build_report, save_report_json


def test_build_and_save_report(tmp_path) -> None:
    report = build_report(
        profile={"row_count": 1},
        findings=[],
        score={
            "score": 100,
            "findings_by_severity": {},
        },
        source={"file_name": "x.csv"},
    )

    assert report["schema_version"]
    assert report["source"]["file_name"] == "x.csv"
    assert report["policy_evidence"] == []

    json.dumps(report)

    target = tmp_path / "nested" / "report.json"

    assert save_report_json(report, target) == target
    assert (
        json.loads(
            target.read_text(encoding="utf-8")
        )["source"]["file_name"]
        == "x.csv"
    )

    with pytest.raises(FileExistsError):
        save_report_json(report, target)

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
        profile={"row_count": 1},
        findings=[],
        score={
            "score": 100,
            "findings_by_severity": {},
        },
        policy_evidence=policy_evidence,
    )

    assert report["policy_evidence"] == policy_evidence
    assert report["policy_evidence"][0]["query"] == "metadata statistik"
    assert (
        report["policy_evidence"][0]["results"][0]["source"]
        == "policy.pdf"
    )

    json.dumps(
        report,
        ensure_ascii=False,
    )


def test_report_uses_empty_policy_evidence_when_none() -> None:
    report = build_report(
        profile={"row_count": 0},
        findings=[],
        score={
            "score": 100,
            "findings_by_severity": {},
        },
        policy_evidence=None,
    )

    assert report["policy_evidence"] == []