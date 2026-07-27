"""Deterministic validation for dataset metadata completeness."""

from __future__ import annotations

import math
from typing import Any

METADATA_FIELDS = (
    "title", "description", "producer_opd", "data_period", "geographic_scope",
    "measurement_unit", "update_frequency", "responsible_unit", "publication_purpose",
)
METADATA_SEVERITIES = {"low", "medium", "high"}


def validate_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Validate required metadata fields and return a JSON-safe result.

    Completeness is the proportion of required fields containing non-whitespace
    values, multiplied by 100. Status thresholds are 90 (Lengkap), 70 (Cukup
    Lengkap), and below 70 (Belum Lengkap).
    """
    missing_fields = [field for field in METADATA_FIELDS if not str(metadata.get(field, "") or "").strip()]
    filled_fields = len(METADATA_FIELDS) - len(missing_fields)
    findings: list[dict[str, str]] = []

    for field in missing_fields:
        findings.append({"field": field, "issue": "Field wajib belum diisi.", "severity": "high", "recommendation": "Isi field metadata ini."})
    title = str(metadata.get("title", "") or "").strip()
    if title and len(title) < 5:
        findings.append({"field": "title", "issue": "Judul terlalu pendek.", "severity": "medium", "recommendation": "Gunakan judul minimal 5 karakter."})
    description = str(metadata.get("description", "") or "").strip()
    if description and len(description) < 20:
        findings.append({"field": "description", "issue": "Deskripsi terlalu pendek.", "severity": "medium", "recommendation": "Gunakan deskripsi minimal 20 karakter."})

    score = round(filled_fields / len(METADATA_FIELDS) * 100, 2)
    status = "Lengkap" if score >= 90 else "Cukup Lengkap" if score >= 70 else "Belum Lengkap"
    return {"completeness_score": score, "status": status, "filled_fields": filled_fields,
            "total_fields": len(METADATA_FIELDS), "missing_fields": missing_fields,
            "findings": findings}
