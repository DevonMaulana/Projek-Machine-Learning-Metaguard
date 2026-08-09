"""Deterministic policy routing over the validated MetaGuard v0.3 registry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.domain_models import DomainId, GovernanceContext, validate_domain_id, validate_governance_context
from core.policy_registry import PolicyRegistry, load_policy_registry


class EvidenceNeed(str, Enum):
    METADATA_GOVERNANCE = "metadata_governance"
    DATA_QUALITY = "data_quality"
    ACCOUNTABILITY = "accountability"
    DOMAIN_SEMANTIC_SUPPORT = "domain_semantic_support"
    TECHNICAL_STANDARD_SUPPORT = "technical_standard_support"


class ApplicabilityState(str, Enum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NO_ELIGIBLE_POLICY = "NO_ELIGIBLE_POLICY"


class PolicyRoutingError(ValueError):
    """Raised for invalid explicit routing inputs."""


@dataclass(frozen=True)
class PolicyRoutingResult:
    """JSON-safe routing output; never contains a raw Chroma filter."""

    evidence_need: EvidenceNeed
    selected_domain: DomainId
    governance_context: GovernanceContext
    eligible_policy_packs: tuple[str, ...]
    eligible_policy_ids: tuple[str, ...]
    eligible_document_types: tuple[str, ...]
    eligible_topics: tuple[str, ...]
    routing_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    applicability_state: ApplicabilityState

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_need": self.evidence_need.value,
            "selected_domain": self.selected_domain.value,
            "governance_context": self.governance_context.value,
            "eligible_policy_packs": list(self.eligible_policy_packs),
            "eligible_policy_ids": list(self.eligible_policy_ids),
            "eligible_document_types": list(self.eligible_document_types),
            "eligible_topics": list(self.eligible_topics),
            "routing_reasons": list(self.routing_reasons),
            "warnings": list(self.warnings),
            "applicability_state": self.applicability_state.value,
        }


def validate_evidence_need(value: EvidenceNeed | str) -> EvidenceNeed:
    """Return a supported stable evidence need or raise clearly."""
    try:
        return EvidenceNeed(value)
    except ValueError as error:
        raise PolicyRoutingError(f"Evidence need tidak didukung: {value!r}") from error


def route_policy_evidence(
    *,
    governance_context: GovernanceContext | str,
    selected_domain: DomainId | str,
    evidence_need: EvidenceNeed | str,
    topic: str | None = None,
    registry: PolicyRegistry | None = None,
) -> PolicyRoutingResult:
    """Route only explicit, validated context to current verified policy records."""
    context = validate_governance_context(governance_context)
    domain = validate_domain_id(selected_domain)
    need = validate_evidence_need(evidence_need)
    active_registry = registry or load_policy_registry()
    normalized_topic = topic.strip() if isinstance(topic, str) else None
    if normalized_topic == "":
        normalized_topic = None

    if context is GovernanceContext.GENERIC_NON_GOVERNMENT:
        return PolicyRoutingResult(
            need, domain, context, (), (), (), (),
            ("Policy pemerintah tidak dirutekan otomatis untuk generic_non_government.",),
            ("Evidence kebijakan pemerintah tidak berlaku otomatis pada konteks ini.",),
            ApplicabilityState.NOT_APPLICABLE,
        )

    governance_needs = {
        EvidenceNeed.METADATA_GOVERNANCE,
        EvidenceNeed.DATA_QUALITY,
        EvidenceNeed.ACCOUNTABILITY,
    }
    domain_packs = {
        DomainId.HEALTHCARE: "healthcare",
        DomainId.EDUCATION: "education",
        DomainId.ENVIRONMENT: "environment",
    }
    if need in governance_needs:
        packs = ("government_generic",)
        reasons = (
            f"government_generic selected because governance_context is government_public and evidence_need is {need.value}.",
        )
    elif need is EvidenceNeed.DOMAIN_SEMANTIC_SUPPORT and domain in domain_packs:
        packs = (domain_packs[domain],)
        reasons = (f"{packs[0]} selected for domain_semantic_support in domain {domain.value}.",)
    elif need is EvidenceNeed.DOMAIN_SEMANTIC_SUPPORT:
        return PolicyRoutingResult(
            need, domain, context, (), (), (), (),
            ("Tidak ada policy pack domain-specific untuk domain yang dipilih.",), (),
            ApplicabilityState.NO_ELIGIBLE_POLICY,
        )
    else:
        return PolicyRoutingResult(
            need, domain, context, (), (), (), (),
            ("Initial corpus tidak memiliki policy technical-standard yang dirutekan untuk need ini.",), (),
            ApplicabilityState.NO_ELIGIBLE_POLICY,
        )

    eligible = [
        policy for policy in active_registry.policies
        if policy.policy_pack in packs
        and policy.effective_status == "current"
        and policy.verification_state == "verified"
    ]
    if normalized_topic is not None:
        available_topics = {entry for policy in eligible for entry in policy.topics}
        if normalized_topic not in available_topics:
            raise PolicyRoutingError(f"Topic tidak tersedia pada policy yang eligible: {normalized_topic!r}")
        eligible = [policy for policy in eligible if normalized_topic in policy.topics]
    if not eligible:
        return PolicyRoutingResult(need, domain, context, packs, (), (), (), reasons, (), ApplicabilityState.NO_ELIGIBLE_POLICY)
    return PolicyRoutingResult(
        need,
        domain,
        context,
        tuple(sorted(packs)),
        tuple(sorted(policy.policy_id for policy in eligible)),
        tuple(sorted({policy.document_type for policy in eligible})),
        (normalized_topic,) if normalized_topic else (),
        reasons,
        (),
        ApplicabilityState.APPLICABLE,
    )


def build_chroma_where(routing: PolicyRoutingResult) -> dict[str, Any] | None:
    """Build a fixed scalar Chroma 0.6.3 filter from validated routing output."""
    if not isinstance(routing, PolicyRoutingResult):
        raise PolicyRoutingError("Filter hanya dapat dibangun dari PolicyRoutingResult tervalidasi.")
    if routing.applicability_state is not ApplicabilityState.APPLICABLE:
        return None
    if not routing.eligible_policy_ids:
        raise PolicyRoutingError("Routing APPLICABLE harus memiliki eligible_policy_ids.")
    conditions: list[dict[str, Any]] = [
        {"policy_id": {"$in": list(routing.eligible_policy_ids)}},
        {"effective_status": {"$eq": "current"}},
        {"verification_state": {"$eq": "verified"}},
    ]
    return {"$and": conditions}
