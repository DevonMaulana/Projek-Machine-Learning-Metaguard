from dataclasses import replace

import pandas as pd

from core.agent_models import AgentAction, AgentDecision, AgentStage, AgentState
from core.agent_orchestrator import execute_decision
from core.agent_tools import AgentExecutionContext, ToolDefinition, build_tool_registry


def _state(**changes: object) -> AgentState:
    values: dict[str, object] = {
        "fingerprint": "run-1",
        "ingestion_completed": True,
        "ingestion_success": True,
        "profile_completed": True,
        "quality_check_completed": True,
        "score_completed": True,
        "metadata_validation_completed": True,
        "metadata_status": "Lengkap",
        "evidence_retrieval_completed": True,
        "evidence_count": 1,
    }
    values.update(changes)
    return AgentState(**values)


def test_static_registry_has_expected_tools_and_no_unknown_tool() -> None:
    registry = build_tool_registry()
    assert set(registry) == {
            AgentAction.RUN_QUALITY_PIPELINE,
            AgentAction.VALIDATE_METADATA,
            AgentAction.RUN_CONTEXTUAL_VALIDATION,
        AgentAction.RETRIEVE_POLICY_EVIDENCE,
        AgentAction.RUN_GEMINI_ANALYSIS,
        AgentAction.REVIEW_TRACEABILITY,
        AgentAction.BUILD_REPORT,
    }
    assert registry.get(AgentAction.NONE) is None


def test_quality_execution_reuses_pipeline_and_creates_audit_event() -> None:
    decision = AgentDecision(AgentStage.QUALITY_REQUIRED, AgentAction.RUN_QUALITY_PIPELINE, "Quality belum selesai.")
    context = AgentExecutionContext(dataframe=pd.DataFrame({"id": [1, 1]}))
    result = execute_decision(decision, _state(), context, step=3)
    assert result.success is True
    assert result.output["score"]["total_findings"] >= 0
    assert result.audit_event is not None
    assert result.audit_event.step == 3


def test_contextual_execution_uses_registered_deterministic_tool() -> None:
    decision = AgentDecision(
        AgentStage.CONTEXTUAL_VALIDATION_REQUIRED,
        AgentAction.RUN_CONTEXTUAL_VALIDATION,
        "Konteks belum diperiksa.",
    )
    result = execute_decision(
        decision,
        _state(),
        AgentExecutionContext(
            dataframe=pd.DataFrame({"tempat_tidur_terisi": [2], "kapasitas_rawat_inap": [1]}),
            metadata={"data_period": "", "geographic_scope": ""},
        ),
    )
    assert result.success is True
    assert result.output["finding_count"] == 1


def test_wrong_stage_and_no_action_are_rejected() -> None:
    wrong_stage = AgentDecision(AgentStage.REPORT_REQUIRED, AgentAction.RUN_QUALITY_PIPELINE, "Salah stage.")
    no_action = AgentDecision(AgentStage.COMPLETE, AgentAction.NONE, "Selesai.")
    context = AgentExecutionContext(dataframe=pd.DataFrame({"a": [1]}))
    assert execute_decision(wrong_stage, _state(), context).success is False
    assert execute_decision(no_action, _state(), context).success is False


def test_registry_mismatch_is_rejected() -> None:
    definition = build_tool_registry()[AgentAction.RUN_QUALITY_PIPELINE]
    mismatched = replace(definition, action=AgentAction.BUILD_REPORT)
    decision = AgentDecision(AgentStage.QUALITY_REQUIRED, AgentAction.RUN_QUALITY_PIPELINE, "Quality.")
    result = execute_decision(
        decision,
        _state(),
        AgentExecutionContext(dataframe=pd.DataFrame({"a": [1]})),
        registry={AgentAction.RUN_QUALITY_PIPELINE: mismatched},
    )
    assert result.success is False


def test_gemini_requires_approval_and_evidence_before_single_mock_call() -> None:
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
    decision = AgentDecision(
        AgentStage.ANALYSIS_READY,
        AgentAction.RUN_GEMINI_ANALYSIS,
        "Evidence tersedia.",
        requires_human_action=True,
    )
    context = AgentExecutionContext()
    registry = {AgentAction.RUN_GEMINI_ANALYSIS: definition}
    assert execute_decision(decision, _state(), context, registry=registry).success is False
    assert execute_decision(decision, _state(evidence_count=0), context, approved=True, registry=registry).success is False
    result = execute_decision(decision, _state(), context, approved=True, registry=registry)
    assert result.success is True
    assert calls == 1


def test_tool_error_returns_structured_failure_and_audit_event() -> None:
    def failing_handler(context: AgentExecutionContext) -> dict[str, str]:
        raise RuntimeError("kegagalan tool yang disengaja")

    definition = ToolDefinition(
        name="failing",
        description="mock",
        action=AgentAction.VALIDATE_METADATA,
        allowed_stages=(AgentStage.METADATA_REQUIRED,),
        requires_human_approval=False,
        handler=failing_handler,
    )
    decision = AgentDecision(AgentStage.METADATA_REQUIRED, AgentAction.VALIDATE_METADATA, "Validasi.")
    result = execute_decision(decision, _state(), AgentExecutionContext(), registry={AgentAction.VALIDATE_METADATA: definition})
    assert result.success is False
    assert "kegagalan tool" in (result.error or "")
    assert result.audit_event is not None
    assert result.audit_event.outcome == "failed"
