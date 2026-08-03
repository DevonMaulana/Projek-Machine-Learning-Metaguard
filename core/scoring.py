"""Transparent and proportional quality scoring for MetaGuard findings."""

from __future__ import annotations

import math
from typing import Any

SEVERITY_WEIGHTS: dict[str, float] = {
    "high": 12.0,
    "medium": 6.0,
    "low": 2.0,
    "info": 0.0,
}
MINIMUM_IMPACT_FACTOR = 0.15
GRADE_THRESHOLDS = (
    (90, "Sangat Baik"),
    (75, "Baik"),
    (60, "Perlu Perbaikan"),
    (0, "Bermasalah"),
)


def _impact_factor(percentage: Any) -> float:
    """Scale row impact from 15% to 100% of the severity weight."""
    try:
        normalized = float(percentage)
    except (TypeError, ValueError):
        normalized = 0.0
    normalized = min(100.0, max(0.0, normalized)) / 100.0
    return MINIMUM_IMPACT_FACTOR + (1.0 - MINIMUM_IMPACT_FACTOR) * math.sqrt(normalized)


def _grade_for_score(score: float) -> str:
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "Bermasalah"


def calculate_score(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate a deterministic quality score in the range 0–100.

    Each finding penalty is ``severity_weight * impact_factor``. The impact
    factor equals ``0.15 + 0.85 * sqrt(affected_percentage / 100)`` after the
    percentage is clamped to 0–100. This preserves a small penalty when the
    percentage is zero or unavailable while making broad findings materially
    more costly than localized findings. Total penalties are capped at 100.
    """
    counts = {severity: 0 for severity in SEVERITY_WEIGHTS}
    breakdown = {severity: 0.0 for severity in SEVERITY_WEIGHTS}

    for finding in findings:
        severity = str(finding.get("severity", "info")).lower()
        if severity not in SEVERITY_WEIGHTS:
            severity = "info"
        counts[severity] += 1
        penalty = SEVERITY_WEIGHTS[severity] * _impact_factor(
            finding.get("percentage", 0.0)
        )
        breakdown[severity] += penalty

    rounded_breakdown = {
        severity: round(value, 2)
        for severity, value in breakdown.items()
    }
    total_penalty = min(100.0, sum(breakdown.values()))
    score = round(max(0.0, 100.0 - total_penalty), 2)

    return {
        "score": score,
        "grade": _grade_for_score(score),
        "total_findings": len(findings),
        "findings_by_severity": counts,
        "penalty_breakdown": rounded_breakdown,
    }
