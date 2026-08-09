"""Deterministic policy and domain alignment for v0.3 evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from core.policy_router import ApplicabilityState, PolicyRoutingResult


class AlignmentState(str, Enum):
    """Explicit alignment outcome; it is not a compliance conclusion."""

    ALIGNED = "ALIGNED"
    PARTIAL = "PARTIAL"
    MISALIGNED = "MISALIGNED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_ASSESSED = "NOT_ASSESSED"


@dataclass(frozen=True)
class EvidenceAlignmentResult:
    """JSON-safe metadata alignment summary without evidence text."""

    policy_pack_alignment: AlignmentState
    domain_alignment: AlignmentState
    eligible_policy_ids: tuple[str, ...]
    observed_policy_ids: tuple[str, ...]
    eligible_policy_packs: tuple[str, ...]
    observed_policy_packs: tuple[str, ...]
    eligible_domains: tuple[str, ...]
    observed_domains: tuple[str, ...]
    eligible_evidence: tuple[dict[str, Any], ...]
    rejected_chunk_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a compact JSON-safe alignment summary."""
        return {
            "policy_pack_alignment": self.policy_pack_alignment.value,
            "domain_alignment": self.domain_alignment.value,
            "eligible_policy_ids": list(self.eligible_policy_ids),
            "observed_policy_ids": list(self.observed_policy_ids),
            "eligible_policy_packs": list(self.eligible_policy_packs),
            "observed_policy_packs": list(self.observed_policy_packs),
            "eligible_domains": list(self.eligible_domains),
            "observed_domains": list(self.observed_domains),
            "eligible_evidence_count": len(self.eligible_evidence),
            "rejected_chunk_ids": list(self.rejected_chunk_ids),
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


def deduplicate_evidence_chunks(evidence: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Keep the first stable chunk occurrence, without mutating input evidence."""
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for item in evidence:
        if not isinstance(item, dict):
            continue
        chunk_id = str(item.get("chunk_id", "")).strip()
        if chunk_id:
            key = ("chunk_id", chunk_id)
        else:
            key = (
                "fallback",
                str(item.get("source", "")).strip(),
                str(item.get("page", "")).strip(),
                str(item.get("text", "")).strip(),
            )
        if key in seen:
            continue
        seen.add(key)
        output.append(dict(item))
    return tuple(output)


def _expected_domains(routing: PolicyRoutingResult) -> tuple[str, ...]:
    domains: set[str] = set()
    if "government_generic" in routing.eligible_policy_packs:
        domains.add("generic")
    for pack in routing.eligible_policy_packs:
        if pack in {"healthcare", "education", "environment"}:
            domains.add(pack)
    return tuple(sorted(domains))


def _alignment_state(*, values: list[str], allowed: set[str]) -> AlignmentState:
    if not values:
        return AlignmentState.NOT_ASSESSED
    matching = sum(value in allowed for value in values)
    if matching == len(values):
        return AlignmentState.ALIGNED
    if matching == 0:
        return AlignmentState.MISALIGNED
    return AlignmentState.PARTIAL


def assess_evidence_alignment(
    routing: PolicyRoutingResult,
    evidence: Iterable[dict[str, Any]],
) -> EvidenceAlignmentResult:
    """Assess only exact registry-routing metadata; never infer semantic truth."""
    if not isinstance(routing, PolicyRoutingResult):
        raise TypeError("routing harus berupa PolicyRoutingResult tervalidasi.")
    if routing.applicability_state is ApplicabilityState.NOT_APPLICABLE:
        return EvidenceAlignmentResult(
            AlignmentState.NOT_APPLICABLE, AlignmentState.NOT_APPLICABLE,
            (), (), (), (), (), (), (), (),
            ("Evidence alignment tidak dinilai karena routing NOT_APPLICABLE.",), (),
        )
    if routing.applicability_state is not ApplicabilityState.APPLICABLE:
        return EvidenceAlignmentResult(
            AlignmentState.NOT_ASSESSED, AlignmentState.NOT_ASSESSED,
            tuple(routing.eligible_policy_ids), (), tuple(routing.eligible_policy_packs), (), (), (), (), (),
            ("Evidence alignment belum dapat dinilai karena tidak ada policy eligible.",), (),
        )

    deduplicated = deduplicate_evidence_chunks(evidence)
    eligible_ids = set(routing.eligible_policy_ids)
    eligible_packs = set(routing.eligible_policy_packs)
    expected_domains = _expected_domains(routing)
    accepted: list[dict[str, Any]] = []
    rejected: list[str] = []
    observed_ids: list[str] = []
    observed_packs: list[str] = []
    observed_domains: list[str] = []
    warnings: list[str] = []

    for item in deduplicated:
        policy_id = str(item.get("policy_id", "")).strip()
        policy_pack = str(item.get("policy_pack", "")).strip()
        domain_id = str(item.get("domain_id", "")).strip()
        if policy_id:
            observed_ids.append(policy_id)
        if policy_pack:
            observed_packs.append(policy_pack)
        if domain_id:
            observed_domains.append(domain_id)
        if policy_id not in eligible_ids:
            rejected.append(str(item.get("chunk_id", "")).strip())
            warnings.append(f"Evidence policy_id tidak eligible: {policy_id or '(kosong)'}.")
            continue
        accepted.append(item)

    accepted_packs = [str(item.get("policy_pack", "")).strip() for item in accepted]
    accepted_domains = [str(item.get("domain_id", "")).strip() for item in accepted]
    pack_state = _alignment_state(values=accepted_packs, allowed=eligible_packs)
    domain_state = _alignment_state(values=accepted_domains, allowed=set(expected_domains))
    if rejected:
        pack_state = AlignmentState.MISALIGNED
        domain_state = AlignmentState.MISALIGNED
    reasons: list[str] = []
    if accepted:
        reasons.append("Evidence dinilai menggunakan policy_id, policy_pack, dan domain_id yang dirutekan secara deterministik.")
    else:
        reasons.append("Tidak ada evidence eligible yang dapat dipakai untuk assessment.")
    if not expected_domains:
        warnings.append("Routing tidak mendefinisikan domain metadata yang dapat diverifikasi.")

    return EvidenceAlignmentResult(
        pack_state,
        domain_state,
        tuple(routing.eligible_policy_ids),
        tuple(sorted(set(observed_ids))),
        tuple(routing.eligible_policy_packs),
        tuple(sorted(set(observed_packs))),
        expected_domains,
        tuple(sorted(set(observed_domains))),
        tuple(accepted),
        tuple(rejected),
        tuple(reasons),
        tuple(dict.fromkeys(warnings)),
    )
