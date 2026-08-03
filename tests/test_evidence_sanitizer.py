import json

import pandas as pd

from core.evidence_sanitizer import (
    MAX_EVIDENCE_STRING_LENGTH,
    TRUNCATION_MARKER,
    sanitize_evidence,
)
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
