import json

from core.agent_models import AgentAction, AgentAuditEvent, AgentDecision, AgentStage, AgentState


def test_agent_stage_and_action_values_are_stable() -> None:
    assert AgentStage.INGESTION_REQUIRED.value == "INGESTION_REQUIRED"
    assert AgentStage.COMPLETE.value == "COMPLETE"
    assert AgentAction.RUN_GEMINI_ANALYSIS.value == "RUN_GEMINI_ANALYSIS"
    assert AgentAction.NONE.value == "NONE"


def test_state_and_decision_are_json_safe_without_payloads() -> None:
    state = AgentState(
        fingerprint="abc",
        quality_check_completed=True,
        quality_finding_count=0,
        blocking_conditions=("metadata",),
    )
    decision = AgentDecision(
        AgentStage.METADATA_REQUIRED,
        AgentAction.VALIDATE_METADATA,
        "Metadata belum divalidasi.",
    )
    assert state.to_dict()["blocking_conditions"] == ["metadata"]
    assert decision.to_dict()["current_stage"] == "METADATA_REQUIRED"
    json.dumps({"state": state.to_dict(), "decision": decision.to_dict()})


def test_audit_event_is_small_and_json_safe() -> None:
    event = AgentAuditEvent.create(
        step=2,
        fingerprint="fingerprint",
        stage=AgentStage.ANALYSIS_READY,
        action=AgentAction.RUN_GEMINI_ANALYSIS,
        reason="Evidence tersedia.",
        outcome="success",
    )
    output = event.to_dict()
    assert output["step"] == 2
    assert output["stage"] == "ANALYSIS_READY"
    assert "T" in output["timestamp"]
    json.dumps(output)
