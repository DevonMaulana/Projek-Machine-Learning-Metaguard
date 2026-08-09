from core.agent_models import AgentAction, AgentStage, AgentState
from core.agent_orchestrator import plan_next_action


def _quality_ready_state(**changes: object) -> AgentState:
    values: dict[str, object] = {
        "fingerprint": "run-1",
        "ingestion_completed": True,
        "ingestion_success": True,
        "ingestion_status": "success",
        "analysis_scope": "full",
        "profile_completed": True,
        "quality_check_completed": True,
        "quality_finding_count": 2,
        "score_completed": True,
    }
    values.update(changes)
    return AgentState(**values)


def test_ingestion_required_when_not_completed() -> None:
    decision = plan_next_action(AgentState())
    assert decision.current_stage is AgentStage.INGESTION_REQUIRED
    assert decision.next_action is AgentAction.NONE
    assert decision.requires_human_action is True


def test_failed_ingestion_requires_human_action() -> None:
    decision = plan_next_action(AgentState(ingestion_completed=True, ingestion_status="failed"))
    assert decision.current_stage is AgentStage.ERROR
    assert decision.requires_human_action is True


def test_quality_pipeline_required_until_all_quality_steps_complete() -> None:
    decision = plan_next_action(AgentState(ingestion_completed=True, ingestion_success=True))
    assert decision.current_stage is AgentStage.QUALITY_REQUIRED
    assert decision.next_action is AgentAction.RUN_QUALITY_PIPELINE


def test_clean_dataset_with_zero_findings_is_quality_complete() -> None:
    decision = plan_next_action(_quality_ready_state(quality_finding_count=0))
    assert decision.current_stage is AgentStage.METADATA_REQUIRED
    assert decision.next_action is AgentAction.VALIDATE_METADATA


def test_metadata_not_validated_then_incomplete_then_complete() -> None:
    not_validated = plan_next_action(_quality_ready_state())
    incomplete = plan_next_action(
        _quality_ready_state(metadata_validation_completed=True, metadata_status="Belum Lengkap")
    )
    complete = plan_next_action(
        _quality_ready_state(
            metadata_validation_completed=True,
            metadata_status="Lengkap",
            contextual_validation_completed=True,
        )
    )
    assert not_validated.next_action is AgentAction.VALIDATE_METADATA
    assert incomplete.next_action is AgentAction.NONE
    assert incomplete.requires_human_action is True
    assert complete.current_stage is AgentStage.EVIDENCE_REQUIRED
    assert complete.next_action is AgentAction.RETRIEVE_POLICY_EVIDENCE


def test_evidence_empty_blocks_gemini_and_evidence_available_unlocks_it() -> None:
    base = _quality_ready_state(
        metadata_validation_completed=True,
        metadata_status="Lengkap",
        contextual_validation_completed=True,
    )
    empty = plan_next_action(AgentState(**{**base.to_dict(), "evidence_retrieval_completed": True}))
    ready = plan_next_action(
        AgentState(**{
            **base.to_dict(),
            "evidence_retrieval_completed": True,
            "evidence_count": 1,
            "evidence_sufficiency_evaluated": True,
            "evidence_sufficiency_status": "sufficient",
        })
    )
    assert empty.current_stage is AgentStage.EVIDENCE_REVIEW_REQUIRED
    assert empty.next_action is AgentAction.EVALUATE_EVIDENCE
    assert empty.requires_human_action is False
    assert ready.current_stage is AgentStage.ANALYSIS_READY
    assert ready.next_action is AgentAction.RUN_GEMINI_ANALYSIS
    assert ready.requires_human_action is True


def test_traceability_report_and_complete_transitions() -> None:
    base = _quality_ready_state(
        metadata_validation_completed=True,
        metadata_status="Lengkap",
        evidence_retrieval_completed=True,
        evidence_count=1,
        evidence_sufficiency_evaluated=True,
        evidence_sufficiency_status="sufficient",
        gemini_analysis_completed=True,
        contextual_validation_completed=True,
    )
    traceability = plan_next_action(base)
    report = plan_next_action(AgentState(**{**base.to_dict(), "traceability_review_completed": True, "traceability_status": "valid"}))
    complete = plan_next_action(AgentState(**{**base.to_dict(), "traceability_review_completed": True, "report_completed": True}))
    assert traceability.current_stage is AgentStage.TRACEABILITY_REQUIRED
    assert traceability.next_action is AgentAction.REVIEW_TRACEABILITY
    assert report.current_stage is AgentStage.REPORT_REQUIRED
    assert report.next_action is AgentAction.BUILD_REPORT
    assert complete.current_stage is AgentStage.COMPLETE
    assert complete.next_action is AgentAction.NONE


def test_explicit_error_state_has_priority() -> None:
    decision = plan_next_action(_quality_ready_state(error_message="Tool gagal."))
    assert decision.current_stage is AgentStage.ERROR
    assert decision.blocking_condition == "Tool gagal."
