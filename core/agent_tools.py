"""Static, controlled tool registry for MetaGuard orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import pandas as pd

from core.agent_models import AgentAction, AgentStage
from core.contextual_validation import run_contextual_validation
from core.data_profiler import profile_dataframe
from core.evidence_reviewer import review_evidence_traceability
from core.metadata_validator import validate_metadata
from core.policy_evidence import build_policy_evidence, build_policy_queries
from core.quality_checker import run_quality_checks
from core.report_builder import build_report
from core.scoring import calculate_score
from llm.gemini_client import analyze_with_gemini
from rag.retriever import retrieve_policy_chunks

ToolHandler = Callable[["AgentExecutionContext"], Any]


@dataclass
class AgentExecutionContext:
    """Ephemeral input values required by existing MetaGuard functions."""

    dataframe: pd.DataFrame | None = None
    ingestion: dict[str, Any] = field(default_factory=dict)
    profile: dict[str, Any] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    score: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    metadata_validation: dict[str, Any] = field(default_factory=dict)
    contextual_validation: dict[str, Any] = field(default_factory=dict)
    contextual_profile: str = "healthcare"
    policy_evidence: list[dict[str, Any]] = field(default_factory=list)
    gemini_analysis: dict[str, Any] = field(default_factory=dict)
    evidence_review: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    retriever: Callable[..., list[dict[str, Any]]] = retrieve_policy_chunks


@dataclass(frozen=True)
class ToolDefinition:
    """One allowlisted internal tool and its execution constraints."""

    name: str
    description: str
    action: AgentAction
    allowed_stages: tuple[AgentStage, ...]
    requires_human_approval: bool
    handler: ToolHandler


def _run_quality_pipeline(context: AgentExecutionContext) -> dict[str, Any]:
    """Reuse the existing deterministic profile, checker, and scorer."""
    if context.dataframe is None:
        raise ValueError("DataFrame belum tersedia untuk quality pipeline.")
    profile = profile_dataframe(context.dataframe)
    findings = run_quality_checks(context.dataframe)
    return {
        "profile": profile,
        "findings": findings,
        "score": calculate_score(findings),
    }


def _validate_metadata(context: AgentExecutionContext) -> dict[str, Any]:
    """Reuse deterministic metadata validation."""
    return validate_metadata(context.metadata)


def _run_contextual_validation(context: AgentExecutionContext) -> dict[str, Any]:
    """Run controlled local consistency validation without modifying data."""
    if context.dataframe is None:
        raise ValueError("DataFrame belum tersedia untuk validasi kontekstual.")
    return run_contextual_validation(
        context.dataframe,
        context.metadata,
        profile=context.contextual_profile,
        ingestion=context.ingestion,
    )


def _retrieve_policy_evidence(context: AgentExecutionContext) -> list[dict[str, Any]]:
    """Build deterministic policy queries and retrieve their evidence."""
    queries = build_policy_queries(context.metadata_validation, context.findings)
    return build_policy_evidence(queries, context.retriever, top_k=3)


def _run_gemini_analysis(context: AgentExecutionContext) -> dict[str, Any]:
    """Call the existing single-call Gemini client only through approval gate."""
    return analyze_with_gemini(
        profile=context.profile,
        findings=context.findings,
        metadata=context.metadata,
        metadata_validation=context.metadata_validation,
        policy_evidence=context.policy_evidence,
        ingestion=context.ingestion,
    )


def _review_traceability(context: AgentExecutionContext) -> dict[str, Any]:
    """Reuse deterministic evidence traceability review."""
    return review_evidence_traceability(
        policy_evidence=context.policy_evidence,
        gemini_analysis=context.gemini_analysis,
    )


def _build_report(context: AgentExecutionContext) -> dict[str, Any]:
    """Reuse the existing v0.1 report contract without schema changes."""
    return build_report(
        profile=context.profile,
        findings=context.findings,
        score=context.score,
        source=context.source,
        metadata=context.metadata,
        metadata_validation=context.metadata_validation,
        contextual_validation=context.contextual_validation,
        policy_evidence=context.policy_evidence,
        gemini_analysis=context.gemini_analysis,
        evidence_review=context.evidence_review,
        ingestion=context.ingestion,
    )


def build_tool_registry() -> Mapping[AgentAction, ToolDefinition]:
    """Return the fixed allowlist of internal MetaGuard tools."""
    definitions = (
        ToolDefinition(
            name="run_quality_pipeline",
            description="Build profile, deterministic findings, and quality score.",
            action=AgentAction.RUN_QUALITY_PIPELINE,
            allowed_stages=(AgentStage.QUALITY_REQUIRED,),
            requires_human_approval=False,
            handler=_run_quality_pipeline,
        ),
        ToolDefinition(
            name="validate_metadata",
            description="Validate deterministic metadata completeness.",
            action=AgentAction.VALIDATE_METADATA,
            allowed_stages=(AgentStage.METADATA_REQUIRED,),
            requires_human_approval=False,
            handler=_validate_metadata,
        ),
        ToolDefinition(
            name="run_contextual_validation",
            description="Validate metadata context and fixed cross-column relationships.",
            action=AgentAction.RUN_CONTEXTUAL_VALIDATION,
            allowed_stages=(AgentStage.CONTEXTUAL_VALIDATION_REQUIRED,),
            requires_human_approval=False,
            handler=_run_contextual_validation,
        ),
        ToolDefinition(
            name="retrieve_policy_evidence",
            description="Retrieve evidence for deterministic policy queries.",
            action=AgentAction.RETRIEVE_POLICY_EVIDENCE,
            allowed_stages=(AgentStage.EVIDENCE_REQUIRED,),
            requires_human_approval=False,
            handler=_retrieve_policy_evidence,
        ),
        ToolDefinition(
            name="run_gemini_analysis",
            description="Run one structured Gemini analysis using existing evidence.",
            action=AgentAction.RUN_GEMINI_ANALYSIS,
            allowed_stages=(AgentStage.ANALYSIS_READY,),
            requires_human_approval=True,
            handler=_run_gemini_analysis,
        ),
        ToolDefinition(
            name="review_traceability",
            description="Review Gemini references deterministically.",
            action=AgentAction.REVIEW_TRACEABILITY,
            allowed_stages=(AgentStage.TRACEABILITY_REQUIRED,),
            requires_human_approval=False,
            handler=_review_traceability,
        ),
        ToolDefinition(
            name="build_report",
            description="Build the existing JSON report.",
            action=AgentAction.BUILD_REPORT,
            allowed_stages=(AgentStage.REPORT_REQUIRED,),
            requires_human_approval=False,
            handler=_build_report,
        ),
    )
    return {definition.action: definition for definition in definitions}
