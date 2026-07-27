from core.scoring import calculate_score


def test_empty_findings_score_100():
    result = calculate_score([])
    assert result["score"] == 100
    assert result["grade"] == "Sangat Baik"


def test_high_penalty_exceeds_medium_and_score_is_bounded():
    high = calculate_score([{"severity": "high"}])
    medium = calculate_score([{"severity": "medium"}])
    many = calculate_score([{"severity": "high"}] * 10)
    assert high["score"] < medium["score"]
    assert many["score"] == 0
    assert high["findings_by_severity"]["high"] == 1
