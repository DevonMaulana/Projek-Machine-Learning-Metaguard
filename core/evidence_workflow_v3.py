"""Isolated, bounded deterministic policy-evidence workflow for v0.3."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from core.domain_models import DomainId, GovernanceContext, validate_domain_id, validate_governance_context
from core.evidence_assessment import EvidenceAssessment, assess_v3_evidence, combine_evidence_attempts
from core.evidence_sufficiency import MAX_RETRIEVAL_ATTEMPTS
from core.policy_router import ApplicabilityState, EvidenceNeed, PolicyRoutingResult, route_policy_evidence, validate_evidence_need
from rag.policy_corpus_v3 import needs_corpus_rebuild
from rag.policy_retrieval_v3 import RetrievalState, V3RetrievalResult, retrieve_policy_chunks_v3


class EvidenceWorkflowState(str, Enum):
    """Explicit terminal state for one bounded evidence-need invocation."""

    READY = "READY"
    NOT_READY = "NOT_READY"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CORPUS_STALE = "CORPUS_STALE"
    NO_ELIGIBLE_POLICY = "NO_ELIGIBLE_POLICY"
    ERROR = "ERROR"


@dataclass(frozen=True)
class PolicyEvidenceWorkflowRequest:
    """Validated public input for one evidence need; no raw filters or callables."""

    selected_domain: DomainId
    governance_context: GovernanceContext
    evidence_need: EvidenceNeed
    query_text: str
    topic: str | None = None
    top_k: int = 3
    max_attempts: int = MAX_RETRIEVAL_ATTEMPTS

    @classmethod
    def create(
        cls,
        *,
        selected_domain: DomainId | str,
        governance_context: GovernanceContext | str,
        evidence_need: EvidenceNeed | str,
        query_text: str,
        topic: str | None = None,
        top_k: int = 3,
        max_attempts: int = MAX_RETRIEVAL_ATTEMPTS,
    ) -> "PolicyEvidenceWorkflowRequest":
        """Validate external scalar inputs and enforce the hard retry bound."""
        if not isinstance(query_text, str) or not query_text.strip():
            raise ValueError("query_text tidak boleh kosong.")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k harus berupa integer minimal 1.")
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or not 1 <= max_attempts <= MAX_RETRIEVAL_ATTEMPTS:
            raise ValueError(f"max_attempts harus antara 1 dan {MAX_RETRIEVAL_ATTEMPTS}.")
        clean_topic = topic.strip() if isinstance(topic, str) else None
        return cls(
            selected_domain=validate_domain_id(selected_domain),
            governance_context=validate_governance_context(governance_context),
            evidence_need=validate_evidence_need(evidence_need),
            query_text=query_text.strip(),
            topic=clean_topic or None,
            top_k=top_k,
            max_attempts=max_attempts,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return primitive-only request metadata."""
        return {
            "selected_domain": self.selected_domain.value,
            "governance_context": self.governance_context.value,
            "evidence_need": self.evidence_need.value,
            "query_text": self.query_text,
            "topic": self.topic,
            "top_k": self.top_k,
            "max_attempts": self.max_attempts,
        }


@dataclass(frozen=True)
class EvidenceWorkflowAttempt:
    """Compact attempt trace; evidence text remains only in cumulative evidence."""

    attempt_number: int
    query: str
    routing_state: ApplicabilityState
    retrieval_state: RetrievalState
    retrieved_chunk_ids: tuple[str, ...]
    sufficiency_state: str
    sufficiency_score: float | None
    readiness: str
    retry_recommended: bool

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe attempt telemetry."""
        return {
            "attempt_number": self.attempt_number,
            "query": self.query,
            "routing_state": self.routing_state.value,
            "retrieval_state": self.retrieval_state.value,
            "retrieved_chunk_ids": list(self.retrieved_chunk_ids),
            "sufficiency_state": self.sufficiency_state,
            "sufficiency_score": self.sufficiency_score,
            "readiness": self.readiness,
            "retry_recommended": self.retry_recommended,
        }


@dataclass(frozen=True)
class PolicyEvidenceWorkflowResult:
    """Complete bounded workflow result, ready only for later human review."""

    request: PolicyEvidenceWorkflowRequest
    routing_result: PolicyRoutingResult
    attempts: tuple[EvidenceWorkflowAttempt, ...]
    cumulative_evidence: tuple[dict[str, Any], ...]
    final_assessment: EvidenceAssessment
    workflow_state: EvidenceWorkflowState
    max_attempts: int
    stop_reason: str

    @property
    def attempt_count(self) -> int:
        """Return actual retrieval calls made by this workflow."""
        return len(self.attempts)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe workflow output; does not authorize Gemini."""
        return {
            "request": self.request.to_dict(),
            "routing_result": self.routing_result.to_dict(),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "cumulative_evidence": [dict(item) for item in self.cumulative_evidence],
            "final_assessment": self.final_assessment.to_dict(),
            "workflow_state": self.workflow_state.value,
            "max_attempts": self.max_attempts,
            "attempt_count": self.attempt_count,
            "stop_reason": self.stop_reason,
        }


def build_retry_query(request: PolicyEvidenceWorkflowRequest) -> str:
    """Return the one deterministic refinement query allowed for attempt two."""
    templates = {
        EvidenceNeed.METADATA_GOVERNANCE: "standar metadata statistik tata kelola produsen data walidata evidence tambahan",
        EvidenceNeed.DATA_QUALITY: "standar kualitas data nilai kosong duplikasi konsistensi evidence tambahan",
        EvidenceNeed.ACCOUNTABILITY: "peran produsen data walidata tanggung jawab perbaikan data evidence tambahan",
        EvidenceNeed.DOMAIN_SEMANTIC_SUPPORT: f"{request.selected_domain.value} satu data sektor informasi semantik evidence tambahan",
        EvidenceNeed.TECHNICAL_STANDARD_SUPPORT: "standar teknis data klasifikasi definisi satuan evidence tambahan",
    }
    return templates[request.evidence_need]


def _assessment_for(
    retrieval: V3RetrievalResult,
    cumulative_evidence: tuple[dict[str, Any], ...],
    assessor: Callable[[V3RetrievalResult], EvidenceAssessment],
) -> EvidenceAssessment:
    state = RetrievalState.SUCCESS if cumulative_evidence else retrieval.state
    cumulative_result = V3RetrievalResult(state, retrieval.routing, cumulative_evidence, retrieval.where, retrieval.message)
    return assessor(cumulative_result)


def _workflow_state(routing: PolicyRoutingResult, assessment: EvidenceAssessment) -> EvidenceWorkflowState:
    if routing.applicability_state is ApplicabilityState.NOT_APPLICABLE:
        return EvidenceWorkflowState.NOT_APPLICABLE
    if routing.applicability_state is ApplicabilityState.NO_ELIGIBLE_POLICY:
        return EvidenceWorkflowState.NO_ELIGIBLE_POLICY
    if assessment.readiness.value == "CORPUS_STALE":
        return EvidenceWorkflowState.CORPUS_STALE
    if assessment.evidence_ready_for_review:
        return EvidenceWorkflowState.READY
    return EvidenceWorkflowState.NOT_READY


def _terminal_result(
    request: PolicyEvidenceWorkflowRequest,
    routing: PolicyRoutingResult,
    retrieval: V3RetrievalResult,
    assessment: EvidenceAssessment,
    state: EvidenceWorkflowState,
    stop_reason: str,
) -> PolicyEvidenceWorkflowResult:
    return PolicyEvidenceWorkflowResult(request, routing, (), (), assessment, state, request.max_attempts, stop_reason)


def run_policy_evidence_workflow_v3(
    request: PolicyEvidenceWorkflowRequest,
    *,
    router: Callable[..., PolicyRoutingResult] = route_policy_evidence,
    retriever: Callable[..., V3RetrievalResult] = retrieve_policy_chunks_v3,
    assessor: Callable[[V3RetrievalResult], EvidenceAssessment] = assess_v3_evidence,
    corpus_is_stale: Callable[[], bool] = needs_corpus_rebuild,
) -> PolicyEvidenceWorkflowResult:
    """Route, retrieve, assess, and retry at most once without calling Gemini."""
    if not isinstance(request, PolicyEvidenceWorkflowRequest):
        raise TypeError("request harus berupa PolicyEvidenceWorkflowRequest.")
    routing = router(
        governance_context=request.governance_context,
        selected_domain=request.selected_domain,
        evidence_need=request.evidence_need,
        topic=request.topic,
    )
    if routing.applicability_state is not ApplicabilityState.APPLICABLE:
        retrieval = V3RetrievalResult(RetrievalState.NOT_APPLICABLE, routing, (), None)
        assessment = assessor(retrieval)
        state = _workflow_state(routing, assessment)
        return _terminal_result(request, routing, retrieval, assessment, state, state.value)
    if corpus_is_stale():
        retrieval = V3RetrievalResult(RetrievalState.CORPUS_STALE, routing, (), None, "Corpus policy v3 belum current.")
        assessment = assessor(retrieval)
        return _terminal_result(request, routing, retrieval, assessment, EvidenceWorkflowState.CORPUS_STALE, "CORPUS_STALE")

    attempts: list[EvidenceWorkflowAttempt] = []
    cumulative: tuple[dict[str, Any], ...] = ()
    query = request.query_text
    final_assessment: EvidenceAssessment | None = None
    for attempt_number in range(1, request.max_attempts + 1):
        retrieval = retriever(query, routing=routing, top_k=request.top_k)
        cumulative = combine_evidence_attempts([cumulative, retrieval.evidence])
        final_assessment = _assessment_for(retrieval, cumulative, assessor)
        attempts.append(EvidenceWorkflowAttempt(
            attempt_number, query, routing.applicability_state, retrieval.state,
            tuple(str(item.get("chunk_id", "")).strip() for item in retrieval.evidence),
            final_assessment.sufficiency.state.value, final_assessment.sufficiency.score,
            final_assessment.readiness.value, final_assessment.retry_recommended,
        ))
        state = _workflow_state(routing, final_assessment)
        if state is EvidenceWorkflowState.READY:
            return PolicyEvidenceWorkflowResult(request, routing, tuple(attempts), cumulative, final_assessment, state, request.max_attempts, "READY")
        if retrieval.state is RetrievalState.CORPUS_STALE:
            return PolicyEvidenceWorkflowResult(request, routing, tuple(attempts), cumulative, final_assessment, EvidenceWorkflowState.CORPUS_STALE, request.max_attempts, "CORPUS_STALE")
        if not final_assessment.retry_recommended:
            return PolicyEvidenceWorkflowResult(request, routing, tuple(attempts), cumulative, final_assessment, state, request.max_attempts, "NO_RETRY_RECOMMENDED")
        if attempt_number == request.max_attempts:
            return PolicyEvidenceWorkflowResult(request, routing, tuple(attempts), cumulative, final_assessment, state, request.max_attempts, "MAX_ATTEMPTS_REACHED")
        query = build_retry_query(request)

    raise RuntimeError("Workflow bounded loop tidak menghasilkan hasil terminal.")
