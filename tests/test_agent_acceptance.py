"""Acceptance-level tests for the controlled MetaGuard agent workflow."""

from __future__ import annotations

import pytest

from core.agent_models import AgentAction, AgentDecision, AgentStage
from core.agent_orchestrator import execute_decision, plan_next_action
from core.agent_state_builder import append_audit_event, build_agent_state, refresh_agent_review
from core.agent_tools import AgentExecutionContext, ToolDefinition
from core.analysis_state import reset_analysis_results
from core.report_builder import build_report


def _quality_ready_inputs(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "fingerprint": "fingerprint-a",
        "ingestion": {"status": "success", "analysis_scope": "full"},
        "profile": {"row_count": 2},
        "findings": [],
        "score": {"score": 100},
    }
    values.update(changes)
    return values


def _metadata_complete_inputs(**changes: object) -> dict[str, object]:
    values = _quality_ready_inputs(
        metadata_validation={"status": "Lengkap"},
        metadata_validation_completed=True,
        contextual_validation={"finding_count": 0},
        contextual_validation_completed=True,
    )
    values.update(changes)
    return values


def _evidence_inputs(**changes: object) -> dict[str, object]:
    values = _metadata_complete_inputs(
        policy_evidence_retrieval_completed=True,
        policy_evidence=[{"query": "q", "results": [{"chunk_id": "p1"}]}],
    )
    values.update(changes)
    return values


def test_acceptance_no_dataset_to_metadata_required_for_clean_dataset() -> None:
    no_dataset = plan_next_action(build_agent_state(fingerprint=None))
    quality_ready = plan_next_action(build_agent_state(**_quality_ready_inputs()))
    assert no_dataset.current_stage is AgentStage.INGESTION_REQUIRED
    assert no_dataset.next_action is AgentAction.NONE
    assert no_dataset.requires_human_action is True
    assert quality_ready.current_stage is AgentStage.METADATA_REQUIRED
    assert quality_ready.next_action is AgentAction.VALIDATE_METADATA


def test_acceptance_metadata_and_retrieval_transitions() -> None:
    never_retrieved = plan_next_action(build_agent_state(**_metadata_complete_inputs()))
    empty_retrieval = plan_next_action(
        build_agent_state(**_metadata_complete_inputs(policy_evidence_retrieval_completed=True))
    )
    assert never_retrieved.current_stage is AgentStage.EVIDENCE_REQUIRED
    assert never_retrieved.next_action is AgentAction.RETRIEVE_POLICY_EVIDENCE
    assert empty_retrieval.current_stage is AgentStage.EVIDENCE_REQUIRED
    assert empty_retrieval.next_action is AgentAction.NONE
    assert empty_retrieval.requires_human_action is True


def test_contextual_validation_is_required_before_evidence_and_findings_do_not_block() -> None:
    pending = plan_next_action(
        build_agent_state(
            **_quality_ready_inputs(
                metadata_validation={"status": "Lengkap"},
                metadata_validation_completed=True,
            )
        )
    )
    completed = plan_next_action(
        build_agent_state(
            **_metadata_complete_inputs(
                contextual_validation={"finding_count": 2},
                contextual_validation_completed=True,
            )
        )
    )
    assert pending.current_stage is AgentStage.CONTEXTUAL_VALIDATION_REQUIRED
    assert pending.next_action is AgentAction.RUN_CONTEXTUAL_VALIDATION
    assert completed.current_stage is AgentStage.EVIDENCE_REQUIRED


def test_acceptance_evidence_to_gemini_traceability_and_report() -> None:
    analysis = plan_next_action(build_agent_state(**_evidence_inputs()))
    traceability = plan_next_action(
        build_agent_state(**_evidence_inputs(gemini_analysis={"summary": "mock"}))
    )
    report = plan_next_action(
        build_agent_state(
            **_evidence_inputs(
                gemini_analysis={"summary": "mock"},
                evidence_review={"status": "valid"},
            )
        )
    )
    assert analysis.current_stage is AgentStage.ANALYSIS_READY
    assert analysis.next_action is AgentAction.RUN_GEMINI_ANALYSIS
    assert analysis.requires_human_action is True
    assert traceability.current_stage is AgentStage.TRACEABILITY_REQUIRED
    assert traceability.next_action is AgentAction.REVIEW_TRACEABILITY
    assert report.current_stage is AgentStage.REPORT_REQUIRED
    assert report.next_action is AgentAction.BUILD_REPORT


def test_gemini_guard_requires_approval_and_calls_mock_once() -> None:
    calls = 0

    def fake_gemini(context: AgentExecutionContext) -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"summary": "mock"}

    definition = ToolDefinition(
        name="run_gemini_analysis",
        description="mock",
        action=AgentAction.RUN_GEMINI_ANALYSIS,
        allowed_stages=(AgentStage.ANALYSIS_READY,),
        requires_human_approval=True,
        handler=fake_gemini,
    )
    state = build_agent_state(**_evidence_inputs())
    decision = plan_next_action(state)
    registry = {AgentAction.RUN_GEMINI_ANALYSIS: definition}
    rejected = execute_decision(decision, state, AgentExecutionContext(), registry=registry)
    accepted = execute_decision(
        decision, state, AgentExecutionContext(), approved=True, registry=registry
    )
    assert rejected.success is False
    assert accepted.success is True
    assert calls == 1
    next_state = build_agent_state(**_evidence_inputs(gemini_analysis=accepted.output))
    assert plan_next_action(next_state).current_stage is AgentStage.TRACEABILITY_REQUIRED


@pytest.mark.parametrize("status", ["valid", "partially_valid", "invalid", "no_references"])
def test_traceability_status_is_preserved_and_report_remains_allowed(status: str) -> None:
    state = build_agent_state(
        **_evidence_inputs(
            gemini_analysis={"summary": "mock"},
            evidence_review={"status": status},
        )
    )
    decision = plan_next_action(state)
    assert state.traceability_review_completed is True
    assert state.traceability_status == status
    assert decision.current_stage is AgentStage.REPORT_REQUIRED
    assert decision.next_action is AgentAction.BUILD_REPORT
    assert "valid" not in decision.decision_reason.casefold()


def test_report_completion_depends_on_payload_not_download() -> None:
    before = build_agent_state(
        **_evidence_inputs(
            gemini_analysis={"summary": "mock"},
            evidence_review={"status": "valid"},
        )
    )
    report = build_report(
        profile={"row_count": 2}, findings=[], score={"score": 100},
        evidence_review={"status": "valid"},
    )
    after = build_agent_state(
        **_evidence_inputs(
            gemini_analysis={"summary": "mock"},
            evidence_review={"status": "valid"},
            report_payload=report,
        )
    )
    assert plan_next_action(before).current_stage is AgentStage.REPORT_REQUIRED
    assert after.report_completed is True
    assert plan_next_action(after).current_stage is AgentStage.COMPLETE


def test_fingerprint_change_resets_derived_agent_workflow() -> None:
    session = {
        "policy_evidence": [{"results": [{"chunk_id": "p1"}]}],
        "policy_evidence_retrieval_completed": True,
        "gemini_analysis": {"summary": "mock"},
        "evidence_review": {"status": "valid"},
        "report_payload": {"schema_version": "1.0"},
        "agent_state": {"old": True},
        "agent_decision": {"old": True},
        "agent_audit": [{"step": 1}],
    }
    reset_analysis_results(session)
    rebuilt = build_agent_state(
        fingerprint="fingerprint-b",
        ingestion={"status": "success"},
        profile={}, findings=[], score={},
    )
    assert session["policy_evidence"] == []
    assert session["policy_evidence_retrieval_completed"] is False
    assert session["gemini_analysis"] == {}
    assert session["evidence_review"] == {}
    assert session["report_payload"] == {}
    assert session["agent_state"] is None
    assert session["agent_decision"] is None
    assert session["agent_audit"] == []
    assert plan_next_action(rebuilt).current_stage is AgentStage.METADATA_REQUIRED


def test_same_fingerprint_rerun_preserves_state_and_deduplicates_audit() -> None:
    session: dict[str, object] = {"agent_audit": []}
    inputs = _metadata_complete_inputs(
        policy_evidence_retrieval_completed=True,
        policy_evidence=[{"results": [{"chunk_id": "p1"}]}],
    )
    first_state, first_decision = refresh_agent_review(session, **inputs)
    second_state, second_decision = refresh_agent_review(session, **inputs)
    assert first_state == second_state
    assert first_decision == second_decision
    assert len(session["agent_audit"]) == 1


def test_meaningful_transition_adds_audit_step() -> None:
    first = append_audit_event(
        [], fingerprint="a", stage=AgentStage.METADATA_REQUIRED,
        action=AgentAction.VALIDATE_METADATA, reason="Validasi.", outcome="success",
    )
    second = append_audit_event(
        first, fingerprint="a", stage=AgentStage.EVIDENCE_REQUIRED,
        action=AgentAction.RETRIEVE_POLICY_EVIDENCE, reason="Retrieval.", outcome="success",
    )
    assert [item.step for item in second] == [1, 2]


@pytest.mark.parametrize(
    ("mode", "scope"),
    [("exact", "full"), ("chunked", "full"), ("sampled", "sampled"), ("sampled", "full")],
)
def test_analysis_modes_share_the_same_agent_workflow(mode: str, scope: str) -> None:
    state = build_agent_state(
        **_quality_ready_inputs(
            ingestion={"status": "success", "mode": mode, "analysis_scope": scope}
        )
    )
    decision = plan_next_action(state)
    assert state.analysis_scope == scope
    assert decision.current_stage is AgentStage.METADATA_REQUIRED
