"""Transparent base scoring for quality findings."""

from typing import Any


def calculate_score(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Score starts at 100; high/medium/low penalties are 20/10/3 each, info 0."""
    penalties = {"high": 20, "medium": 10, "low": 3, "info": 0}
    counts = {severity: 0 for severity in penalties}
    breakdown = {severity: 0 for severity in penalties}
    for finding in findings:
        severity = finding.get("severity", "info")
        if severity in counts:
            counts[severity] += 1
            breakdown[severity] += penalties[severity]
    total_penalty = sum(breakdown.values())
    score = max(0, 100 - total_penalty)
    grade = "Sangat Baik" if score >= 90 else "Baik" if score >= 75 else "Perlu Perbaikan" if score >= 60 else "Bermasalah"
    return {"score": score, "grade": grade, "total_findings": len(findings), "findings_by_severity": counts, "penalty_breakdown": breakdown}
