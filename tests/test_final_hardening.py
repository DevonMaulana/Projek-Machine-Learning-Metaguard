from core.agent_models import AgentAction, AgentStage
from core.agent_orchestrator import execute_decision, plan_next_action
from core.agent_state_builder import build_agent_state
from core.agent_tools import AgentExecutionContext, ToolDefinition
from core.domain_models import DomainId, GovernanceContext
from core.product_evidence_v3 import (
    plan_product_evidence_needs,
    run_product_evidence_workflows,
)
from core.report_builder import build_report

def _v3_inputs(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "fingerprint": "x",
        "ingestion": {"status": "success"},
        "profile": {},
        "findings": [],
        "score": {},
        "metadata_validation": {"status": "Lengkap"},
        "metadata_validation_completed": True,
        "contextual_validation_completed": True,
        "policy_evidence_retrieval_completed": True,
        "evidence_sufficiency": {"status": "insufficient", "score": 0},
        "evidence_workflow_v3_completed": True,
        "evidence_ready_v3": False,
        "evidence_workflow_v3_state": "NOT_APPLICABLE",
    }
    values.update(changes)
    return values


def test_all_not_applicable_v3_is_terminal_not_review_required() -> None:
    state = build_agent_state(**_v3_inputs())
    decision = plan_next_action(state)

    assert decision.current_stage is AgentStage.COMPLETE
    assert decision.next_action is AgentAction.NONE
    assert not decision.requires_human_action
    assert decision.blocking_condition is None


def test_generic_non_government_plans_only_not_applicable_evidence_needs() -> None:
    needs = plan_product_evidence_needs(
        selected_domain=DomainId.GENERIC,
        metadata_validation={},
        findings=[],
        contextual_validation={},
    )
    aggregate = run_product_evidence_workflows(
        selected_domain=DomainId.GENERIC,
        governance_context=GovernanceContext.GENERIC_NON_GOVERNMENT,
        evidence_needs=needs,
    )

    assert [item.workflow_state.value for item in aggregate.workflows] == [
        "NOT_APPLICABLE",
        "NOT_APPLICABLE",
    ]
    assert not aggregate.evidence_ready
    assert aggregate.evidence_pool == ()


def test_all_not_applicable_v3_cannot_execute_gemini_and_keeps_report_available() -> None:
    calls = 0

    def fake_gemini(_: AgentExecutionContext) -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"summary": "must not run"}

    state = build_agent_state(**_v3_inputs())
    decision = plan_next_action(state)
    registry = {
        AgentAction.RUN_GEMINI_ANALYSIS: ToolDefinition(
            "gemini",
            "test only",
            AgentAction.RUN_GEMINI_ANALYSIS,
            (AgentStage.ANALYSIS_READY,),
            True,
            fake_gemini,
        )
    }
    result = execute_decision(
        decision,
        state,
        AgentExecutionContext(),
        approved=True,
        registry=registry,
    )
    report = build_report(profile={}, findings=[], score={})

    assert not result.success
    assert calls == 0
    assert report["schema_version"] == "1.1"


def test_applicable_not_ready_or_ready_awaiting_approval_is_not_terminal() -> None:
    not_ready = plan_next_action(
        build_agent_state(**_v3_inputs(evidence_workflow_v3_state="NOT_READY"))
    )
    ready = plan_next_action(
        build_agent_state(
            **_v3_inputs(
                evidence_sufficiency={"status": "sufficient", "score": 90},
                evidence_workflow_v3_state="READY",
                evidence_ready_v3=True,
            )
        )
    )

    assert not_ready.current_stage is AgentStage.EVIDENCE_REVIEW_REQUIRED
    assert not_ready.next_action is AgentAction.NONE
    assert ready.current_stage is AgentStage.ANALYSIS_READY
    assert ready.next_action is AgentAction.RUN_GEMINI_ANALYSIS
    assert ready.requires_human_action


def test_applicable_failure_or_stale_workflow_is_not_terminal() -> None:
    for workflow_state in ("ERROR", "CORPUS_STALE"):
        decision = plan_next_action(
            build_agent_state(**_v3_inputs(evidence_workflow_v3_state=workflow_state))
        )

        assert decision.current_stage is AgentStage.EVIDENCE_REVIEW_REQUIRED
        assert decision.next_action is AgentAction.NONE
        assert decision.requires_human_action
