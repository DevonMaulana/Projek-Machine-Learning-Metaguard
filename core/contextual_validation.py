"""Deterministic preliminary consistency checks for metadata and dataset context."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from core.cross_column_rules import run_cross_column_validation
from core.evidence_sanitizer import sanitize_evidence

MINIMUM_VALID_DATE_VALUES = 3
YEAR_MATCH_THRESHOLD = 0.80
DATE_COLUMN_KEYWORDS = ("date", "tanggal", "tgl")
GEOGRAPHIC_COLUMN_KEYWORDS = ("kabupaten", "kota", "kecamatan", "wilayah")
ADMINISTRATIVE_LEVELS = ("kabupaten", "kota", "kecamatan")


def _normalized_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")


def _contextual_finding(
    *,
    check_id: str,
    title: str,
    description: str,
    metadata_field: str,
    columns: list[str],
    observed_context: dict[str, Any],
    affected_rows: int | None,
    percentage: float | None,
    evidence: list[Any],
    recommendation: str,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "category": "metadata_consistency",
        "severity": "medium",
        "title": title,
        "description": description,
        "metadata_field": metadata_field,
        "columns": columns,
        "observed_context": observed_context,
        "affected_rows": affected_rows,
        "percentage": percentage,
        "evidence": sanitize_evidence(evidence),
        "recommendation": recommendation,
        "deterministic": True,
        "confidence": "high",
    }


def _metadata_years(value: Any) -> set[int]:
    return {
        int(year)
        for year in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", str(value or ""))
    }


def _date_column_positions(dataframe: pd.DataFrame) -> list[int]:
    return [
        index for index, name in enumerate(dataframe.columns)
        if any(keyword in _normalized_name(name) for keyword in DATE_COLUMN_KEYWORDS)
    ]


def _period_consistency(
    dataframe: pd.DataFrame,
    metadata: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    metadata_value = metadata.get("data_period", "")
    expected_years = _metadata_years(metadata_value)
    if not expected_years:
        return [], 0
    findings: list[dict[str, Any]] = []
    evaluated = 0
    for position in _date_column_positions(dataframe):
        column = str(dataframe.columns[position])
        parsed = pd.to_datetime(
            dataframe.iloc[:, position],
            errors="coerce",
            dayfirst=True,
            format="mixed",
        )
        valid = parsed.dropna()
        if len(valid) < MINIMUM_VALID_DATE_VALUES:
            continue
        evaluated += 1
        matches = valid.dt.year.isin(expected_years)
        match_ratio = float(matches.mean())
        if match_ratio >= YEAR_MATCH_THRESHOLD:
            continue
        mismatched = valid[~matches]
        observed_years = sorted({int(year) for year in valid.dt.year})
        findings.append(_contextual_finding(
            check_id="metadata_period_vs_dataset_dates",
            title="Periode metadata berpotensi tidak konsisten",
            description=(
                "Tahun pada metadata data_period tidak mencakup sebagian besar tahun "
                "yang dapat dibaca dari kolom tanggal dataset."
            ),
            metadata_field="data_period",
            columns=[column],
            observed_context={
                "metadata_value": str(metadata_value),
                "expected_years": sorted(expected_years),
                "observed_years": observed_years,
                "valid_date_count": int(len(valid)),
                "match_ratio": round(match_ratio, 2),
            },
            affected_rows=int((~matches).sum()),
            percentage=round((~matches).mean() * 100, 2),
            evidence=[str(value.date()) for value in mismatched.iloc[:5]],
            recommendation="Verifikasi periode metadata dan nilai tanggal pada dataset.",
        ))
    return findings, evaluated


def _administrative_region(
    value: Any,
    *,
    inferred_level: str | None = None,
) -> dict[str, str] | None:
    """Parse only explicit or column-inferred Indonesian administrative levels."""
    normalized = re.sub(r"\s+", " ", str(value or "").strip().casefold())
    if not normalized:
        return None
    match = re.match(r"^(kabupaten|kota|kecamatan)\s+(.+)$", normalized)
    if match:
        return {"level": match.group(1), "name": match.group(2).strip()}
    if inferred_level in ADMINISTRATIVE_LEVELS:
        return {"level": inferred_level, "name": normalized}
    return None


def _column_administrative_level(column_name: object) -> str | None:
    normalized = _normalized_name(column_name)
    for level in ADMINISTRATIVE_LEVELS:
        if level in normalized:
            return level
    return None


def _geographic_column_positions(dataframe: pd.DataFrame) -> list[int]:
    """Return conservative geographic candidate columns without level filtering."""
    return [
        index
        for index, name in enumerate(dataframe.columns)
        if any(keyword in _normalized_name(name) for keyword in GEOGRAPHIC_COLUMN_KEYWORDS)
    ]


def _geographic_consistency(dataframe: pd.DataFrame, metadata: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    metadata_value = metadata.get("geographic_scope", "")
    expected = _administrative_region(metadata_value)
    if not expected:
        return [], 0
    findings: list[dict[str, Any]] = []
    evaluated = 0
    for position in _geographic_column_positions(dataframe):
        column = str(dataframe.columns[position])
        inferred_level = _column_administrative_level(column)
        regions = dataframe.iloc[:, position].map(
            lambda value: _administrative_region(value, inferred_level=inferred_level)
        )
        regions = regions[regions.notna()]
        if not len(regions):
            continue
        evaluated += 1
        matches = regions.map(lambda region: region == expected)
        mismatched = regions[~matches]
        if not len(mismatched):
            continue
        observed = sorted(
            {f"{region['level']} {region['name']}" for region in regions}
        )[:5]
        findings.append(_contextual_finding(
            check_id="metadata_geographic_scope_vs_dataset",
            title="Cakupan wilayah metadata berpotensi tidak konsisten",
            description=(
                "Nilai wilayah pada dataset tidak seluruhnya sesuai dengan cakupan "
                "wilayah metadata setelah normalisasi sederhana."
            ),
            metadata_field="geographic_scope",
            columns=[column],
            observed_context={
                "metadata_value": str(metadata_value),
                "expected_region": expected,
                "observed_regions": observed,
            },
            affected_rows=int(len(mismatched)),
            percentage=round(len(mismatched) / len(regions) * 100, 2),
            evidence=[
                f"{region['level']} {region['name']}"
                for region in mismatched.iloc[:5]
            ],
            recommendation="Verifikasi cakupan wilayah metadata dan nilai wilayah dataset.",
        ))
    return findings, evaluated


def run_contextual_validation(
    dataframe: pd.DataFrame,
    metadata: dict[str, Any],
    *,
    profile: str = "healthcare",
    ingestion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run deterministic preliminary consistency rules without mutating inputs.

    Findings indicate potential inconsistencies and require human/domain review.
    Period checks require at least three valid dates and use an 80% year-match
    threshold; values below that threshold are reported rather than corrected.
    """
    context = _analysis_context(dataframe, ingestion)
    period_findings, period_evaluated = _period_consistency(dataframe, metadata)
    geography_findings, geography_evaluated = _geographic_consistency(dataframe, metadata)
    cross = run_cross_column_validation(dataframe, profile=profile)
    findings = [*period_findings, *geography_findings, *cross["findings"]]
    evaluated = period_evaluated + geography_evaluated + int(cross["evaluated_rules"])
    if findings:
        status = "potential_inconsistency"
    elif evaluated:
        status = "consistent"
    else:
        status = "not_evaluable"
    return {
        "status": status,
        "finding_count": len(findings),
        "findings": findings,
        "metadata_rules_evaluated": period_evaluated + geography_evaluated,
        "cross_column_rules_evaluated": cross["evaluated_rules"],
        "profile": profile,
        **context,
    }


def _analysis_context(
    dataframe: pd.DataFrame,
    ingestion: dict[str, Any] | None,
) -> dict[str, int | str]:
    """Describe the effective rows examined without estimating a population."""
    diagnostics = ingestion or {}
    scope = diagnostics.get("analysis_scope")
    analysis_scope = scope if scope in {"full", "sampled"} else "full"
    rows_evaluated = int(len(dataframe))
    total_rows = diagnostics.get("total_rows", rows_evaluated)
    try:
        total_rows = int(total_rows)
    except (TypeError, ValueError):
        total_rows = rows_evaluated
    return {
        "analysis_scope": analysis_scope,
        "rows_evaluated": rows_evaluated,
        "total_rows": total_rows,
    }
