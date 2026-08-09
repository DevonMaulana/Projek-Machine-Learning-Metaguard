"""Build and explicitly persist JSON reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.report_provenance import build_v3_report_metadata


def build_report(
    profile: dict[str, Any],
    findings: list[dict[str, Any]],
    score: dict[str, Any],
    source: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    metadata_validation: dict[str, Any] | None = None,
    contextual_validation: dict[str, Any] | None = None,
    policy_evidence: list[dict[str, Any]] | None = None,
    evidence_sufficiency: dict[str, Any] | None = None,
    retrieval_attempts: list[dict[str, Any]] | None = None,
    gemini_analysis: dict[str, Any] | None = None,
    evidence_review: dict[str, Any] | None = None,
    ingestion: dict[str, Any] | None = None,
    analysis_context: dict[str, Any] | None = None,
    evidence_workflows_v3: list[dict[str, Any]] | None = None,
    evidence_pool_v3: list[dict[str, Any]] | None = None,
    evidence_ready_v3: bool = False,
    human_approval: bool = False,
) -> dict[str, Any]:
    """Combine analysis outputs into a JSON-serializable report."""
    by_severity = score.get(
        "findings_by_severity",
        {},
    )

    return {
        "schema_version": "1.1",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "source": source or {},
        "profile": profile,
        "quality_summary": {
            "total_findings": len(findings),
            "findings_by_severity": by_severity,
        },
        "findings": findings,
        "score": score,
        "metadata": metadata or {},
        "metadata_validation": (
            metadata_validation or {}
        ),
        "contextual_validation": contextual_validation or {},
        "policy_evidence": policy_evidence or [],
        "evidence_sufficiency": evidence_sufficiency or {},
        "retrieval_attempts": retrieval_attempts or [],
        "gemini_analysis": gemini_analysis or {},
        "evidence_review": evidence_review or {},
        "ingestion": ingestion or {},
        "v3_metadata": build_v3_report_metadata(
            analysis_context=analysis_context,
            contextual_validation=contextual_validation,
            evidence_workflows=evidence_workflows_v3 or [],
            evidence_pool=evidence_pool_v3 or [],
            evidence_ready=evidence_ready_v3,
            human_approval=human_approval,
            gemini_analysis=gemini_analysis,
            evidence_review=evidence_review,
        ),
    }


def save_report_json(
    report: dict[str, Any],
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """
    Save a report as UTF-8 JSON.

    Existing files are preserved unless overwrite is explicitly enabled.
    """
    path = Path(output_path)

    if path.exists() and not overwrite:
        raise FileExistsError(
            f"File laporan sudah ada: {path}"
        )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return path
