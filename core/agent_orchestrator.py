"""Deterministic planner and controlled executor for MetaGuard v0.2."""

from __future__ import annotations

from typing import Mapping

from core.agent_models import (
    AgentAction,
    AgentAuditEvent,
    AgentDecision,
    AgentExecutionResult,
    AgentStage,
    AgentState,
)
from core.agent_tools import AgentExecutionContext, ToolDefinition, build_tool_registry

COMPLETE_METADATA_STATUS = "Lengkap"


def plan_next_action(state: AgentState) -> AgentDecision:
    """Choose the next permitted workflow step without using an LLM."""
    if state.error_message:
        return AgentDecision(
            AgentStage.ERROR,
            AgentAction.NONE,
            "Orchestrator menerima status error dari eksekusi sebelumnya.",
            state.error_message,
            True,
        )
    if not state.ingestion_completed:
        return AgentDecision(
            AgentStage.INGESTION_REQUIRED,
            AgentAction.NONE,
            "Dataset belum melalui ingestion.",
            "Pengguna perlu mengunggah dan membaca CSV terlebih dahulu.",
            True,
        )
    if not state.ingestion_success:
        return AgentDecision(
            AgentStage.ERROR,
            AgentAction.NONE,
            "Ingestion telah selesai tetapi tidak berhasil.",
            state.ingestion_status or "CSV tidak dapat diproses.",
            True,
        )
    if not (state.profile_completed and state.quality_check_completed and state.score_completed):
        return AgentDecision(
            AgentStage.QUALITY_REQUIRED,
            AgentAction.RUN_QUALITY_PIPELINE,
            "Profil, quality check, atau score deterministik belum lengkap.",
        )
    if not state.metadata_validation_completed:
        return AgentDecision(
            AgentStage.METADATA_REQUIRED,
            AgentAction.VALIDATE_METADATA,
            "Metadata belum divalidasi.",
        )
    if state.metadata_status != COMPLETE_METADATA_STATUS:
        return AgentDecision(
            AgentStage.METADATA_REQUIRED,
            AgentAction.NONE,
            "Validasi metadata selesai tetapi metadata belum lengkap.",
            "Pengguna perlu melengkapi metadata sebelum retrieval evidence.",
            True,
        )
    if not state.contextual_validation_completed:
        return AgentDecision(
            AgentStage.CONTEXTUAL_VALIDATION_REQUIRED,
            AgentAction.RUN_CONTEXTUAL_VALIDATION,
            "Metadata lengkap, tetapi validasi kontekstual deterministik belum dijalankan.",
        )
    if not state.evidence_retrieval_completed:
        return AgentDecision(
            AgentStage.EVIDENCE_REQUIRED,
            AgentAction.RETRIEVE_POLICY_EVIDENCE,
            "Metadata lengkap, tetapi retrieval policy evidence belum dijalankan.",
        )
    if not state.evidence_sufficiency_evaluated:
        return AgentDecision(
            AgentStage.EVIDENCE_REVIEW_REQUIRED,
            AgentAction.EVALUATE_EVIDENCE,
            "Retrieval selesai tetapi sufficiency evidence belum dievaluasi.",
        )
    if state.evidence_sufficiency_status != "sufficient":
        if state.retrieval_retry_available:
            return AgentDecision(
                AgentStage.EVIDENCE_REQUIRED,
                AgentAction.RETRY_POLICY_RETRIEVAL,
                "Evidence belum memadai dan satu retry retrieval deterministik masih tersedia.",
            )
        return AgentDecision(
            AgentStage.EVIDENCE_REVIEW_REQUIRED,
            AgentAction.NONE,
            "Evidence telah dievaluasi tetapi belum memadai untuk analisis Gemini.",
            "Evidence belum memadai untuk analisis AI. Perbaiki metadata atau input lalu jalankan ulang.",
            True,
        )
    if not state.gemini_analysis_completed:
        return AgentDecision(
            AgentStage.ANALYSIS_READY,
            AgentAction.RUN_GEMINI_ANALYSIS,
            "Quality checking, metadata validation, dan policy evidence telah tersedia.",
            requires_human_action=True,
        )
    if not state.traceability_review_completed:
        return AgentDecision(
            AgentStage.TRACEABILITY_REQUIRED,
            AgentAction.REVIEW_TRACEABILITY,
            "Analisis Gemini tersedia tetapi traceability belum diperiksa.",
        )
    if not state.report_completed:
        return AgentDecision(
            AgentStage.REPORT_REQUIRED,
            AgentAction.BUILD_REPORT,
            "Traceability selesai tetapi laporan JSON belum dibangun.",
        )
    return AgentDecision(
        AgentStage.COMPLETE,
        AgentAction.NONE,
        "Seluruh tahap workflow telah selesai.",
    )


def execute_decision(
    decision: AgentDecision,
    state: AgentState,
    context: AgentExecutionContext,
    *,
    approved: bool = False,
    step: int = 1,
    registry: Mapping[AgentAction, ToolDefinition] | None = None,
) -> AgentExecutionResult:
    """Execute only the allowlisted action selected by a valid decision."""
    active_registry = registry or build_tool_registry()
    definition = active_registry.get(decision.next_action)
    if decision.next_action is AgentAction.NONE:
        return _failure(decision, state, step, "Decision tidak memiliki action yang dapat dieksekusi.")
    if definition is None:
        return _failure(decision, state, step, "Action tidak terdaftar pada tool registry.")
    if definition.action is not decision.next_action:
        return _failure(decision, state, step, "Tool registry tidak cocok dengan action keputusan.")
    if decision.current_stage not in definition.allowed_stages:
        return _failure(decision, state, step, "Action tidak diizinkan pada stage keputusan saat ini.")
    if definition.requires_human_approval:
        if not decision.requires_human_action:
            return _failure(decision, state, step, "Decision Gemini wajib menandai kebutuhan approval manusia.")
        if not approved:
            return _failure(decision, state, step, "Approval manusia eksplisit diperlukan sebelum Gemini dijalankan.")
        if state.evidence_count <= 0:
            return _failure(decision, state, step, "Gemini tidak dapat dijalankan tanpa policy evidence.")
        if not state.evidence_sufficiency_evaluated or state.evidence_sufficiency_status != "sufficient":
            return _failure(decision, state, step, "Gemini hanya dapat dijalankan setelah evidence berstatus sufficient.")
    try:
        output = definition.handler(context)
    except Exception as error:  # Tool failures must become structured results.
        return _failure(decision, state, step, str(error))
    audit_event = AgentAuditEvent.create(
        step=step,
        fingerprint=state.fingerprint,
        stage=decision.current_stage,
        action=decision.next_action,
        reason=decision.decision_reason,
        outcome="success",
    )
    return AgentExecutionResult(
        success=True,
        action=decision.next_action,
        output=output,
        audit_event=audit_event,
    )


def _failure(
    decision: AgentDecision,
    state: AgentState,
    step: int,
    error: str,
) -> AgentExecutionResult:
    """Build an error result without exposing a full execution payload."""
    safe_error = error[:300]
    audit_event = AgentAuditEvent.create(
        step=step,
        fingerprint=state.fingerprint,
        stage=decision.current_stage,
        action=decision.next_action,
        reason=decision.decision_reason,
        outcome="failed",
        error=safe_error,
    )
    return AgentExecutionResult(
        success=False,
        action=decision.next_action,
        error=safe_error,
        audit_event=audit_event,
    )
