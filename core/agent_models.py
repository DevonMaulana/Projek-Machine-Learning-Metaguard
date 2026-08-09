"""Small JSON-safe models for the deterministic MetaGuard orchestrator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AgentStage(str, Enum):
    """One unambiguous lifecycle state for an analysis run."""

    INGESTION_REQUIRED = "INGESTION_REQUIRED"
    QUALITY_REQUIRED = "QUALITY_REQUIRED"
    METADATA_REQUIRED = "METADATA_REQUIRED"
    CONTEXTUAL_VALIDATION_REQUIRED = "CONTEXTUAL_VALIDATION_REQUIRED"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    EVIDENCE_REVIEW_REQUIRED = "EVIDENCE_REVIEW_REQUIRED"
    ANALYSIS_READY = "ANALYSIS_READY"
    TRACEABILITY_REQUIRED = "TRACEABILITY_REQUIRED"
    REPORT_REQUIRED = "REPORT_REQUIRED"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


class AgentAction(str, Enum):
    """Allowed actions for the orchestrator's static tool allowlist."""

    RUN_QUALITY_PIPELINE = "RUN_QUALITY_PIPELINE"
    VALIDATE_METADATA = "VALIDATE_METADATA"
    RUN_CONTEXTUAL_VALIDATION = "RUN_CONTEXTUAL_VALIDATION"
    RETRIEVE_POLICY_EVIDENCE = "RETRIEVE_POLICY_EVIDENCE"
    EVALUATE_EVIDENCE = "EVALUATE_EVIDENCE"
    RETRY_POLICY_RETRIEVAL = "RETRY_POLICY_RETRIEVAL"
    RUN_GEMINI_ANALYSIS = "RUN_GEMINI_ANALYSIS"
    REVIEW_TRACEABILITY = "REVIEW_TRACEABILITY"
    BUILD_REPORT = "BUILD_REPORT"
    NONE = "NONE"


@dataclass(frozen=True)
class AgentState:
    """Compact orchestration state without dataset or sensitive payloads."""

    fingerprint: str | None = None
    ingestion_completed: bool = False
    ingestion_success: bool = False
    ingestion_status: str | None = None
    analysis_scope: str | None = None
    profile_completed: bool = False
    quality_check_completed: bool = False
    quality_finding_count: int = 0
    score_completed: bool = False
    metadata_validation_completed: bool = False
    metadata_status: str | None = None
    contextual_validation_completed: bool = False
    contextual_finding_count: int = 0
    contextual_requires_human_review: bool = False
    evidence_retrieval_completed: bool = False
    evidence_count: int = 0
    evidence_sufficiency_evaluated: bool = False
    evidence_sufficiency_status: str | None = None
    evidence_sufficiency_score: float | None = None
    evidence_workflow_v3_completed: bool = False
    evidence_ready_v3: bool = False
    evidence_workflow_v3_state: str | None = None
    retrieval_attempt_count: int = 0
    retrieval_retry_available: bool = False
    gemini_analysis_completed: bool = False
    traceability_review_completed: bool = False
    traceability_status: str | None = None
    report_completed: bool = False
    blocking_conditions: tuple[str, ...] = field(default_factory=tuple)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        data = asdict(self)
        data["blocking_conditions"] = list(self.blocking_conditions)
        return data


@dataclass(frozen=True)
class AgentDecision:
    """Deterministic next-step recommendation for one AgentState."""

    current_stage: AgentStage
    next_action: AgentAction
    decision_reason: str
    blocking_condition: str | None = None
    requires_human_action: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "current_stage": self.current_stage.value,
            "next_action": self.next_action.value,
            "decision_reason": self.decision_reason,
            "blocking_condition": self.blocking_condition,
            "requires_human_action": self.requires_human_action,
        }


@dataclass(frozen=True)
class AgentAuditEvent:
    """Small execution record that excludes data and sensitive payloads."""

    step: int
    timestamp: str
    fingerprint: str | None
    stage: AgentStage
    action: AgentAction
    reason: str
    outcome: str
    error: str | None = None

    @classmethod
    def create(
        cls,
        *,
        step: int,
        fingerprint: str | None,
        stage: AgentStage,
        action: AgentAction,
        reason: str,
        outcome: str,
        error: str | None = None,
    ) -> "AgentAuditEvent":
        """Create an event with an explicit UTC timestamp."""
        return cls(
            step=step,
            timestamp=datetime.now(timezone.utc).isoformat(),
            fingerprint=fingerprint,
            stage=stage,
            action=action,
            reason=reason,
            outcome=outcome,
            error=error,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "step": self.step,
            "timestamp": self.timestamp,
            "fingerprint": self.fingerprint,
            "stage": self.stage.value,
            "action": self.action.value,
            "reason": self.reason,
            "outcome": self.outcome,
            "error": self.error,
        }


@dataclass(frozen=True)
class AgentExecutionResult:
    """Safe result returned when the executor handles one decision."""

    success: bool
    action: AgentAction
    output: Any = None
    error: str | None = None
    audit_event: AgentAuditEvent | None = None
