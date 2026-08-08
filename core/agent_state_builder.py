"""Build lightweight orchestration state from existing MetaGuard outputs."""

from __future__ import annotations

from typing import Any, Iterable, MutableMapping

from core.agent_models import AgentAction, AgentAuditEvent, AgentDecision, AgentStage, AgentState

SUCCESSFUL_INGESTION_STATUSES = {"success", "success_with_warnings"}


def build_agent_state(
    *,
    fingerprint: str | None,
    ingestion: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    findings: list[dict[str, Any]] | None = None,
    score: dict[str, Any] | None = None,
    metadata_validation: dict[str, Any] | None = None,
    metadata_validation_completed: bool = False,
    policy_evidence: list[dict[str, Any]] | None = None,
    policy_evidence_retrieval_completed: bool = False,
    gemini_analysis: dict[str, Any] | None = None,
    evidence_review: dict[str, Any] | None = None,
    report_payload: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> AgentState:
    """Map v0.1 source-of-truth outputs to compact deterministic state."""
    diagnostics = ingestion or {}
    status = diagnostics.get("status")
    evidence = policy_evidence or []
    return AgentState(
        fingerprint=fingerprint,
        ingestion_completed=ingestion is not None,
        ingestion_success=status in SUCCESSFUL_INGESTION_STATUSES,
        ingestion_status=str(status) if status is not None else None,
        analysis_scope=diagnostics.get("analysis_scope"),
        profile_completed=profile is not None,
        quality_check_completed=findings is not None,
        quality_finding_count=len(findings or []),
        score_completed=score is not None,
        metadata_validation_completed=metadata_validation_completed,
        metadata_status=(metadata_validation or {}).get("status"),
        evidence_retrieval_completed=policy_evidence_retrieval_completed,
        evidence_count=count_policy_evidence(evidence),
        gemini_analysis_completed=bool(gemini_analysis),
        traceability_review_completed=bool(evidence_review),
        traceability_status=(evidence_review or {}).get("status"),
        report_completed=bool(report_payload),
        error_message=error_message,
    )


def count_policy_evidence(policy_evidence: Iterable[dict[str, Any]]) -> int:
    """Count retrieved result items without retaining their text in AgentState."""
    count = 0
    for group in policy_evidence:
        results = group.get("results", []) if isinstance(group, dict) else []
        if isinstance(results, list):
            count += len(results)
    return count


def append_audit_event(
    audit: list[AgentAuditEvent],
    *,
    fingerprint: str | None,
    stage: AgentStage,
    action: AgentAction,
    reason: str,
    outcome: str,
    error: str | None = None,
) -> list[AgentAuditEvent]:
    """Append one semantic event, avoiding duplicates caused by Streamlit reruns."""
    signature = (fingerprint, stage, action, reason, outcome, error)
    for previous in audit:
        previous_signature = (
            previous.fingerprint,
            previous.stage,
            previous.action,
            previous.reason,
            previous.outcome,
            previous.error,
        )
        if previous_signature == signature:
            return list(audit)
    event = AgentAuditEvent.create(
        step=(audit[-1].step + 1) if audit else 1,
        fingerprint=fingerprint,
        stage=stage,
        action=action,
        reason=reason,
        outcome=outcome,
        error=error,
    )
    return [*audit, event]


def append_decision_event(
    audit: list[AgentAuditEvent],
    *,
    fingerprint: str | None,
    decision: AgentDecision,
) -> list[AgentAuditEvent]:
    """Record a planner recommendation only when it meaningfully changes."""
    return append_audit_event(
        audit,
        fingerprint=fingerprint,
        stage=decision.current_stage,
        action=decision.next_action,
        reason=decision.decision_reason,
        outcome="recommended",
        error=decision.blocking_condition,
    )


def refresh_agent_review(
    session_state: MutableMapping[str, Any],
    **state_inputs: Any,
) -> tuple[AgentState, AgentDecision]:
    """Build, plan, and persist the current agent review without duplicate logs."""
    from core.agent_orchestrator import plan_next_action

    state = build_agent_state(**state_inputs)
    decision = plan_next_action(state)
    current_audit = session_state.get("agent_audit", [])
    audit = [item for item in current_audit if isinstance(item, AgentAuditEvent)]
    session_state["agent_state"] = state
    session_state["agent_decision"] = decision
    session_state["agent_audit"] = append_decision_event(
        audit,
        fingerprint=state.fingerprint,
        decision=decision,
    )
    return state, decision
