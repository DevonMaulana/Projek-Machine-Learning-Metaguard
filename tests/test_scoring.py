import copy
import json

import pandas as pd
import pytest

from core.quality_checker import run_quality_checks
from core.scoring import calculate_score


def finding(severity: str, percentage: float) -> dict[str, object]:
    return {"severity": severity, "percentage": percentage}


def test_empty_findings_score_100():
    result = calculate_score([])
    assert result["score"] == 100
    assert result["grade"] == "Sangat Baik"


def test_severity_order_and_percentage_impact():
    high = calculate_score([finding("high", 20)])["score"]
    medium = calculate_score([finding("medium", 20)])["score"]
    low = calculate_score([finding("low", 20)])["score"]
    broad = calculate_score([finding("medium", 80)])["score"]
    narrow = calculate_score([finding("medium", 5)])["score"]
    assert high < medium < low
    assert broad < narrow


def test_zero_percentage_still_has_minimum_penalty():
    assert calculate_score([finding("high", 0)])["score"] < 100


def test_many_small_low_findings_do_not_force_zero():
    result = calculate_score([finding("low", 2) for _ in range(30)])
    assert 0 < result["score"] < 100


def test_many_broad_high_findings_can_be_very_low():
    assert calculate_score([finding("high", 100) for _ in range(10)])["score"] == 0


@pytest.mark.parametrize(
    ("findings", "grade"),
    [
        ([], "Sangat Baik"),
        ([finding("high", 100), finding("medium", 100)], "Baik"),
        ([finding("high", 100), finding("high", 100), finding("medium", 100)], "Perlu Perbaikan"),
        ([finding("high", 100) for _ in range(4)], "Bermasalah"),
    ],
)
def test_grade_thresholds(findings, grade):
    assert calculate_score(findings)["grade"] == grade


def test_output_is_bounded_json_safe_and_input_unchanged():
    findings = [finding("high", 250), finding("medium", -10), finding("low", "5")]
    original = copy.deepcopy(findings)
    result = calculate_score(findings)
    assert 0 <= result["score"] <= 100
    assert result["findings_by_severity"] == {"high": 1, "medium": 1, "low": 1, "info": 0}
    json.dumps(result)
    assert findings == original


def test_representative_small_impact_fixture_is_low_but_not_zero():
    findings = (
        [finding("high", 4.55) for _ in range(4)]
        + [finding("medium", 2.27) for _ in range(18)]
        + [finding("low", 2.27) for _ in range(6)]
    )
    result = calculate_score(findings)
    assert 0 < result["score"] < 60
    assert result["total_findings"] == 28


def test_valid_negative_coordinates_do_not_reduce_quality_score():
    findings = run_quality_checks(
        pd.DataFrame(
            {
                "latitude": [-7.3, -7.4, -7.5, -7.6, -7.7],
                "longitude": [-110.1, -110.2, -110.3, -110.4, -110.5],
            }
        )
    )

    assert not [
        finding
        for finding in findings
        if finding["check_id"] == "negative_numeric"
    ]
    assert calculate_score(findings)["score"] == calculate_score([])["score"]
