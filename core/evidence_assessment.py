"""Deterministic, layered evidence assessment for the isolated v0.3 path."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from core.evidence_alignment import AlignmentState, EvidenceAlignmentResult, assess_evidence_alignment, deduplicate_evidence_chunks
from core.evidence_sufficiency import evaluate_evidence_sufficiency
from core.policy_router import ApplicabilityState, PolicyRoutingResult
from rag.policy_retrieval_v3 import RetrievalState, V3RetrievalResult


class SufficiencyState(str, Enum):
    """Retrieval-evidence heuristic state, distinct from applicability."""

    SUFFICIENT = "SUFFICIENT"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    NOT_ASSESSED = "NOT_ASSESSED"


class EvidenceReadinessState(str, Enum):
    """Future Gemini-review readiness; this does not grant human approval."""

    READY = "READY"
    NOT_READY = "NOT_READY"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CORPUS_STALE = "CORPUS_STALE"


@dataclass(frozen=True)
class EvidenceSufficiencyResult:
    """JSON-safe v0.3 wrapper around the retained v0.2 heuristic."""

    state: SufficiencyState
    score: float | None
    coverage: dict[str, bool]
    unique_chunk_count: int
    source_count: int
    duplicate_count: int
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return primitive-only representation."""
        return {
            "state": self.state.value,
            "score": self.score,
            "coverage": dict(self.coverage),
            "unique_chunk_count": self.unique_chunk_count,
            "source_count": self.source_count,
            "duplicate_count": self.duplicate_count,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class EvidenceAssessment:
    """Layered deterministic assessment. It does not authorize Gemini execution."""

    routing: PolicyRoutingResult
    retrieval_state: RetrievalState
    sufficiency: EvidenceSufficiencyResult
    alignment: EvidenceAlignmentResult
    readiness: EvidenceReadinessState
    retry_recommended: bool
    evidence_ready_for_review: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return compact JSON-safe assessment data."""
        return {
            "applicability_state": self.routing.applicability_state.value,
            "routing": self.routing.to_dict(),
            "retrieval_state": self.retrieval_state.value,
            "sufficiency": self.sufficiency.to_dict(),
            "alignment": self.alignment.to_dict(),
            "readiness": self.readiness.value,
            "retry_recommended": self.retry_recommended,
            "evidence_ready_for_review": self.evidence_ready_for_review,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


def combine_evidence_attempts(attempts: Iterable[Iterable[dict[str, Any]]]) -> tuple[dict[str, Any], ...]:
    """Combine attempt outputs cumulatively, retaining the first chunk occurrence."""
    flattened: list[dict[str, Any]] = []
    for attempt in attempts:
        flattened.extend(item for item in attempt if isinstance(item, dict))
    return deduplicate_evidence_chunks(flattened)


def _not_assessed(reason: str) -> EvidenceSufficiencyResult:
    return EvidenceSufficiencyResult(SufficiencyState.NOT_ASSESSED, None, {}, 0, 0, 0, (reason,), ())


def _evaluate_sufficiency(evidence: tuple[dict[str, Any], ...], need: str) -> EvidenceSufficiencyResult:
    legacy = evaluate_evidence_sufficiency(
        [{"need": need, "results": list(evidence)}], [need]
    )
    state = SufficiencyState(str(legacy["status"]).upper())
    return EvidenceSufficiencyResult(
        state,
        float(legacy["score"]),
        dict(legacy["coverage"]),
        int(legacy["unique_evidence_count"]),
        int(legacy["unique_source_count"]),
        int(legacy["duplicate_count"]),
        tuple(str(item) for item in legacy["reasons"]),
        (),
    )


def assess_v3_evidence(retrieval: V3RetrievalResult) -> EvidenceAssessment:
    """Assess validated v3 retrieval result without querying Chroma or an LLM."""
    if not isinstance(retrieval, V3RetrievalResult):
        raise TypeError("retrieval harus berupa V3RetrievalResult.")
    routing = retrieval.routing
    alignment = assess_evidence_alignment(routing, retrieval.evidence)
    if routing.applicability_state is ApplicabilityState.NOT_APPLICABLE:
        return EvidenceAssessment(
            routing, retrieval.state, _not_assessed("Evidence tidak applicable untuk konteks routing ini."), alignment,
            EvidenceReadinessState.NOT_APPLICABLE, False, False,
            ("NOT_APPLICABLE berbeda dari evidence insufficient.",), (),
        )
    if routing.applicability_state is not ApplicabilityState.APPLICABLE:
        return EvidenceAssessment(
            routing, retrieval.state, _not_assessed("Tidak ada policy eligible untuk evidence need ini."), alignment,
            EvidenceReadinessState.NOT_READY, False, False,
            ("Tidak ada evidence route yang dapat dinilai.",), (),
        )
    if retrieval.state is RetrievalState.CORPUS_STALE:
        return EvidenceAssessment(
            routing, retrieval.state, _not_assessed("Corpus policy v3 stale dan harus dibangun ulang secara eksplisit."), alignment,
            EvidenceReadinessState.CORPUS_STALE, False, False,
            ("Corpus stale bukan kondisi untuk retry retrieval.",), (),
        )

    sufficiency = _evaluate_sufficiency(alignment.eligible_evidence, routing.evidence_need.value)
    aligned = (
        alignment.policy_pack_alignment is AlignmentState.ALIGNED
        and alignment.domain_alignment is AlignmentState.ALIGNED
        and bool(alignment.eligible_evidence)
    )
    ready = retrieval.state is RetrievalState.SUCCESS and sufficiency.state is SufficiencyState.SUFFICIENT and aligned
    readiness = EvidenceReadinessState.READY if ready else EvidenceReadinessState.NOT_READY
    retry = not ready and retrieval.state in {RetrievalState.SUCCESS, RetrievalState.EMPTY}
    warnings = list(alignment.warnings)
    if retrieval.state is RetrievalState.EMPTY:
        warnings.append("Retrieval applicable tetapi tidak mengembalikan evidence.")
    if alignment.rejected_chunk_ids:
        warnings.append("Evidence ineligible tidak dihitung untuk sufficiency atau readiness.")
    return EvidenceAssessment(
        routing, retrieval.state, sufficiency, alignment, readiness, retry, ready,
        ("Readiness evidence adalah heuristic MetaGuard dan bukan otorisasi Gemini atau kesimpulan kepatuhan.",),
        tuple(dict.fromkeys(warnings)),
    )
