import json

import pandas as pd

from core.evidence_sanitizer import (
    MAX_EVIDENCE_STRING_LENGTH,
    TRUNCATION_MARKER,
    sanitize_evidence,
    sanitize_policy_evidence_for_gemini,
)


def test_gemini_policy_evidence_keeps_identity_but_bounds_text() -> None:
    result = sanitize_policy_evidence_for_gemini([
        {"chunk_id": "a", "source": "policy.pdf", "page": 3, "text": "x" * 400, "policy_id": "P", "policy_pack": "healthcare", "domain_id": "healthcare", "document_type": "regulation"},
        {"chunk_id": "b", "source": "policy.pdf", "page": 4, "text": "ok"},
    ])
    assert result[0]["chunk_id"] == "a"
    assert result[0]["source"] == "policy.pdf"
    assert result[0]["page"] == 3
    assert result[0]["text"].endswith(TRUNCATION_MARKER)
    assert len(result[0]["text"]) == MAX_EVIDENCE_STRING_LENGTH + len(TRUNCATION_MARKER)
    assert result[1]["chunk_id"] == "b"
from core.quality_checker import run_quality_checks


def test_sanitize_evidence_limits_items_and_long_unicode_strings() -> None:
    long_text = "é" * 301
    output = sanitize_evidence([long_text, 12, True, None, "aman", "keenam"])
    assert len(output) == 5
    assert output[0] == long_text[:MAX_EVIDENCE_STRING_LENGTH] + TRUNCATION_MARKER
    assert output[1:] == [12, True, None, "aman"]
    json.dumps(output, ensure_ascii=False)


def test_quality_findings_sanitize_evidence_without_mutating_dataframe() -> None:
    dataframe = pd.DataFrame({"nama": [" " + ("x" * 350), "normal"]})
    original = dataframe.copy(deep=True)
    findings = run_quality_checks(dataframe)
    whitespace = next(item for item in findings if item["check_id"] == "whitespace")
    assert len(whitespace["evidence"]) <= 5
    assert whitespace["evidence"][0].endswith(TRUNCATION_MARKER)
    assert whitespace["count"] == 1
    pd.testing.assert_frame_equal(dataframe, original)
