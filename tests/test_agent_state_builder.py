from core.agent_models import AgentAction, AgentStage
from core.agent_state_builder import (
    append_audit_event,
    append_decision_event,
    build_agent_state,
    count_policy_evidence,
    refresh_agent_review,
)
from core.agent_orchestrator import plan_next_action


def test_no_csv_builds_ingestion_required_state() -> None:
    state = build_agent_state(fingerprint=None)
    decision = plan_next_action(state)
    assert state.ingestion_completed is False
    assert decision.current_stage is AgentStage.INGESTION_REQUIRED


def test_ingestion_success_and_failure_are_mapped_explicitly() -> None:
    success = build_agent_state(
        fingerprint="x",
        ingestion={"status": "success_with_warnings", "analysis_scope": "sampled"},
    )
    failure = build_agent_state(fingerprint="x", ingestion={"status": "failed"})
    assert success.ingestion_completed is True
    assert success.ingestion_success is True
    assert success.analysis_scope == "sampled"
    assert failure.ingestion_completed is True
    assert failure.ingestion_success is False


def test_quality_completion_is_separate_from_zero_findings() -> None:
    state = build_agent_state(
        fingerprint="x",
        ingestion={"status": "success", "analysis_scope": "full"},
        profile={"row_count": 1},
        findings=[],
        score={"score": 100},
    )
    assert state.quality_check_completed is True
    assert state.quality_finding_count == 0
    assert plan_next_action(state).current_stage is AgentStage.METADATA_REQUIRED


def test_metadata_and_retrieval_state_distinguish_not_run_and_empty() -> None:
    common = {
        "fingerprint": "x",
        "ingestion": {"status": "success"},
        "profile": {},
        "findings": [],
        "score": {},
        "metadata_validation": {"status": "Lengkap"},
        "metadata_validation_completed": True,
        "contextual_validation": {"finding_count": 0},
        "contextual_validation_completed": True,
    }
    never = build_agent_state(**common)
    empty = build_agent_state(**common, policy_evidence_retrieval_completed=True)
    available = build_agent_state(
        **common,
        policy_evidence_retrieval_completed=True,
        policy_evidence=[{"query": "q", "results": [{"chunk_id": "one"}]}],
    )
    assert never.evidence_retrieval_completed is False
    assert empty.evidence_retrieval_completed is True
    assert empty.evidence_count == 0
    assert available.evidence_count == 1


def test_contextual_state_is_separate_from_metadata_completeness() -> None:
    pending = build_agent_state(
        fingerprint="x", ingestion={"status": "success"}, profile={}, findings=[], score={},
        metadata_validation={"status": "Lengkap"}, metadata_validation_completed=True,
    )
    reviewed = build_agent_state(
        fingerprint="x", ingestion={"status": "success"}, profile={}, findings=[], score={},
        metadata_validation={"status": "Lengkap"}, metadata_validation_completed=True,
        contextual_validation={"finding_count": 2}, contextual_validation_completed=True,
    )
    assert plan_next_action(pending).current_stage is AgentStage.CONTEXTUAL_VALIDATION_REQUIRED
    assert reviewed.contextual_finding_count == 2
    assert reviewed.contextual_requires_human_review is True


def test_gemini_traceability_report_and_scope_modes_are_mapped() -> None:
    for scope in ("full", "sampled"):
        state = build_agent_state(
            fingerprint="x",
            ingestion={"status": "success", "analysis_scope": scope},
            profile={}, findings=[], score={},
            metadata_validation={"status": "Lengkap"},
            metadata_validation_completed=True,
            contextual_validation={"finding_count": 1},
            contextual_validation_completed=True,
            policy_evidence_retrieval_completed=True,
            policy_evidence=[{"results": [{"chunk_id": "one"}]}],
            gemini_analysis={"summary": "Ada"},
            evidence_review={"status": "partially_valid"},
            report_payload={"schema_version": "1.0"},
        )
        assert state.analysis_scope == scope
        assert state.gemini_analysis_completed is True
        assert state.traceability_review_completed is True
        assert state.traceability_status == "partially_valid"
        assert state.contextual_requires_human_review is True
        assert state.report_completed is True


def test_exact_chunked_and_sampled_diagnostics_build_valid_states() -> None:
    modes = (("exact", "full"), ("chunked", "full"), ("sampled", "sampled"))
    for mode, scope in modes:
        state = build_agent_state(
            fingerprint=mode,
            ingestion={"status": "success", "mode": mode, "analysis_scope": scope},
        )
        assert state.ingestion_success is True
        assert state.analysis_scope == scope


def test_evidence_counter_ignores_non_list_results() -> None:
    assert count_policy_evidence([{"results": []}, {"results": "invalid"}]) == 0


def test_sufficiency_and_attempts_are_mapped_without_full_log_in_state() -> None:
    state = build_agent_state(
        fingerprint="x",
        ingestion={"status": "success"}, profile={}, findings=[], score={},
        metadata_validation={"status": "Lengkap"}, metadata_validation_completed=True,
        contextual_validation_completed=True,
        policy_evidence_retrieval_completed=True,
        policy_evidence=[{"results": [{"chunk_id": "one"}]}],
        evidence_sufficiency={"status": "partial", "score": 50.0, "missing_coverage": ["data_quality"]},
        retrieval_attempts=[{"attempt_number": 1, "queries": ["not retained by state"]}],
    )
    assert state.evidence_sufficiency_evaluated is True
    assert state.evidence_sufficiency_status == "partial"
    assert state.retrieval_attempt_count == 1
    assert state.retrieval_retry_available is True
    assert "queries" not in state.to_dict()


def test_partial_sufficiency_without_missing_coverage_does_not_offer_empty_retry() -> None:
    state = build_agent_state(
        fingerprint="x",
        ingestion={"status": "success"}, profile={}, findings=[], score={},
        metadata_validation={"status": "Lengkap"}, metadata_validation_completed=True,
        contextual_validation_completed=True,
        policy_evidence_retrieval_completed=True,
        policy_evidence=[{"results": [{"chunk_id": "one"}]}],
        evidence_sufficiency={"status": "partial", "score": 70.0, "missing_coverage": []},
        retrieval_attempts=[{"attempt_number": 1}],
    )
    assert state.retrieval_retry_available is False
    assert plan_next_action(state).next_action is AgentAction.NONE


def test_decision_events_do_not_duplicate_on_rerun_equivalent_state() -> None:
    state = build_agent_state(fingerprint=None)
    decision = plan_next_action(state)
    first = append_decision_event([], fingerprint=None, decision=decision)
    second = append_decision_event(first, fingerprint=None, decision=decision)
    assert len(first) == 1
    assert second == first


def test_action_events_do_not_duplicate_but_transition_is_recorded() -> None:
    first = append_audit_event(
        [], fingerprint="x", stage=AgentStage.EVIDENCE_REQUIRED,
        action=AgentAction.RETRIEVE_POLICY_EVIDENCE,
        reason="Retrieval selesai.", outcome="success",
    )
    duplicate = append_audit_event(
        first, fingerprint="x", stage=AgentStage.EVIDENCE_REQUIRED,
        action=AgentAction.RETRIEVE_POLICY_EVIDENCE,
        reason="Retrieval selesai.", outcome="success",
    )
    transition = append_audit_event(
        duplicate, fingerprint="x", stage=AgentStage.ANALYSIS_READY,
        action=AgentAction.RUN_GEMINI_ANALYSIS,
        reason="Evidence tersedia.", outcome="recommended",
    )
    assert len(duplicate) == 1
    assert len(transition) == 2


def test_refresh_persists_state_and_creates_transition_event() -> None:
    session: dict[str, object] = {"agent_audit": []}
    _, first = refresh_agent_review(session, fingerprint=None)
    _, second = refresh_agent_review(
        session,
        fingerprint="x",
        ingestion={"status": "success"},
        profile={}, findings=[], score={},
    )
    assert first.current_stage is AgentStage.INGESTION_REQUIRED
    assert second.current_stage is AgentStage.METADATA_REQUIRED
    assert second.next_action is AgentAction.VALIDATE_METADATA
    assert len(session["agent_audit"]) == 2


def test_refresh_same_fingerprint_preserves_agent_audit() -> None:
    session: dict[str, object] = {"agent_audit": []}
    inputs = {"fingerprint": "x", "ingestion": {"status": "success"}, "profile": {}, "findings": [], "score": {}}
    first_state, _ = refresh_agent_review(session, **inputs)
    second_state, _ = refresh_agent_review(session, **inputs)
    assert first_state == second_state
    assert len(session["agent_audit"]) == 1
