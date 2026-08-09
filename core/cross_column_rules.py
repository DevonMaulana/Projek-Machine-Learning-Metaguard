"""Deterministic, preliminary cross-column validation rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from core.evidence_sanitizer import sanitize_evidence

CrossRuleEvaluator = Callable[[pd.DataFrame], tuple[list[dict[str, Any]], bool]]


@dataclass(frozen=True)
class CrossColumnRule:
    """One fixed rule with required columns and a deterministic evaluator."""

    rule_id: str
    name: str
    required_columns: tuple[str, ...]
    severity: str
    evaluator: CrossRuleEvaluator
    description: str
    recommendation: str


def _normalize_column(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")


def _column_positions(dataframe: pd.DataFrame, required: tuple[str, ...]) -> list[int] | None:
    positions = {_normalize_column(name): index for index, name in enumerate(dataframe.columns)}
    try:
        return [positions[_normalize_column(name)] for name in required]
    except KeyError:
        return None


def _finding(
    *,
    check_id: str,
    severity: str,
    title: str,
    description: str,
    columns: tuple[str, ...],
    affected_rows: int,
    rows_analyzed: int,
    evidence: list[Any],
    recommendation: str,
    confidence: str,
) -> dict[str, Any]:
    """Return bounded JSON-safe contextual finding data."""
    percentage = round(affected_rows / rows_analyzed * 100, 2) if rows_analyzed else 0.0
    return {
        "check_id": check_id,
        "category": "cross_column",
        "severity": severity,
        "title": title,
        "description": description,
        "metadata_field": None,
        "columns": list(columns),
        "observed_context": {"rows_analyzed": rows_analyzed},
        "affected_rows": affected_rows,
        "percentage": percentage,
        "evidence": sanitize_evidence(evidence),
        "recommendation": recommendation,
        "deterministic": True,
        "confidence": confidence,
    }


def _beds_rule(dataframe: pd.DataFrame) -> tuple[list[dict[str, Any]], bool]:
    required = ("tempat_tidur_terisi", "kapasitas_rawat_inap")
    positions = _column_positions(dataframe, required)
    if positions is None:
        return [], False
    occupied = pd.to_numeric(dataframe.iloc[:, positions[0]], errors="coerce")
    capacity = pd.to_numeric(dataframe.iloc[:, positions[1]], errors="coerce")
    valid = occupied.notna() & capacity.notna()
    analyzed = int(valid.sum())
    if not analyzed:
        return [], False
    mismatch = valid & (occupied > capacity)
    affected = int(mismatch.sum())
    if not affected:
        return [], True
    evidence = []
    for row_position, is_mismatched in enumerate(mismatch.tolist()):
        if not is_mismatched:
            continue
        evidence.append(
            "baris "
            f"{dataframe.index[row_position]}: tempat_tidur_terisi={occupied.iloc[row_position]}, "
            f"kapasitas_rawat_inap={capacity.iloc[row_position]}"
        )
        if len(evidence) == 5:
            break
    return [
        _finding(
            check_id="occupied_beds_exceed_capacity",
            severity="high",
            title="Tempat tidur terisi melebihi kapasitas rawat inap",
            description=(
                "Nilai tempat_tidur_terisi lebih besar daripada kapasitas_rawat_inap "
                "pada baris yang dapat dianalisis."
            ),
            columns=required,
            affected_rows=affected,
            rows_analyzed=analyzed,
            evidence=evidence,
            recommendation="Verifikasi kapasitas dan jumlah tempat tidur terisi pada baris terkait.",
            confidence="high",
        )
    ], True


NO_INTERNET_VALUES = {"tidak", "tidak ada", "offline", "none"}
KNOWN_ACTIVE_INTERNET_VALUES = {"ada", "online", "aktif"}


def _internet_rule(dataframe: pd.DataFrame) -> tuple[list[dict[str, Any]], bool]:
    required = ("status_internet", "bandwidth_mbps")
    positions = _column_positions(dataframe, required)
    if positions is None:
        return [], False
    status = dataframe.iloc[:, positions[0]].astype("string").str.strip().str.casefold()
    bandwidth = pd.to_numeric(dataframe.iloc[:, positions[1]], errors="coerce")
    known_status = status.isin(NO_INTERNET_VALUES | KNOWN_ACTIVE_INTERNET_VALUES)
    valid = bandwidth.notna() & known_status
    analyzed = int(valid.sum())
    if not analyzed:
        return [], False
    mismatch = valid & status.isin(NO_INTERNET_VALUES) & (bandwidth > 0)
    affected = int(mismatch.sum())
    if not affected:
        return [], True
    evidence = []
    for row_position, is_mismatched in enumerate(mismatch.tolist()):
        if not is_mismatched:
            continue
        evidence.append(
            "baris "
            f"{dataframe.index[row_position]}: status_internet={status.iloc[row_position]}, "
            f"bandwidth_mbps={bandwidth.iloc[row_position]}"
        )
        if len(evidence) == 5:
            break
    return [
        _finding(
            check_id="internet_status_vs_bandwidth",
            severity="medium",
            title="Status internet berpotensi tidak konsisten dengan bandwidth",
            description=(
                "Status internet menyatakan tidak ada koneksi, tetapi bandwidth_mbps bernilai lebih dari nol. "
                "Ini merupakan potential inconsistency yang perlu diverifikasi."
            ),
            columns=required,
            affected_rows=affected,
            rows_analyzed=analyzed,
            evidence=evidence,
            recommendation="Verifikasi status konektivitas dan nilai bandwidth pada baris terkait.",
            confidence="high",
        )
    ], True


HEALTHCARE_RULES = (
    CrossColumnRule(
        "occupied_beds_exceed_capacity", "Kapasitas tempat tidur", ("tempat_tidur_terisi", "kapasitas_rawat_inap"), "high", _beds_rule,
        "Tempat tidur terisi tidak boleh melebihi kapasitas rawat inap.", "Verifikasi data kapasitas.",
    ),
    CrossColumnRule(
        "internet_status_vs_bandwidth", "Konsistensi internet", ("status_internet", "bandwidth_mbps"), "medium", _internet_rule,
        "Status tanpa internet tidak konsisten dengan bandwidth positif.", "Verifikasi konektivitas.",
    ),
)


def run_cross_column_validation(
    dataframe: pd.DataFrame,
    *,
    profile: str = "healthcare",
) -> dict[str, Any]:
    """Run fixed preliminary relationship rules without mutating the DataFrame."""
    rules = HEALTHCARE_RULES if profile == "healthcare" else ()
    findings: list[dict[str, Any]] = []
    evaluated_rules = 0
    for rule in rules:
        rule_findings, evaluated = rule.evaluator(dataframe)
        findings.extend(rule_findings)
        evaluated_rules += int(evaluated)
    return {
        "profile": profile,
        "evaluated_rules": evaluated_rules,
        "findings": findings,
    }
