"""Deterministic domain and governance definitions for MetaGuard v0.3.

These models are registry foundations only. They do not activate rules, route
policy, or change the existing v0.2 application workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class GovernanceContext(str, Enum):
    """Explicit governance context selected independently from a domain."""

    GOVERNMENT_PUBLIC = "government_public"
    GENERIC_NON_GOVERNMENT = "generic_non_government"


class DomainId(str, Enum):
    """Stable, finite identifiers for supported analysis domains."""

    GENERIC = "generic"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    ENVIRONMENT = "environment"
    OTHER = "other"


@dataclass(frozen=True)
class DomainProfile:
    """Immutable declaration of future domain/profile capabilities."""

    domain_id: DomainId
    display_name: str
    description: str
    generic_quality_enabled: bool
    eligible_governance_contexts: tuple[GovernanceContext, ...]
    future_rule_pack_ids: tuple[str, ...]
    future_policy_pack_ids: tuple[str, ...]
    fallback_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe profile snapshot without executable behavior."""
        return {
            "domain_id": self.domain_id.value,
            "display_name": self.display_name,
            "description": self.description,
            "generic_quality_enabled": self.generic_quality_enabled,
            "eligible_governance_contexts": [
                context.value for context in self.eligible_governance_contexts
            ],
            "future_rule_pack_ids": list(self.future_rule_pack_ids),
            "future_policy_pack_ids": list(self.future_policy_pack_ids),
            "fallback_message": self.fallback_message,
        }


_ALL_GOVERNANCE_CONTEXTS = tuple(GovernanceContext)

DOMAIN_PROFILES: dict[DomainId, DomainProfile] = {
    DomainId.GENERIC: DomainProfile(
        domain_id=DomainId.GENERIC,
        display_name="Generic",
        description="Pemeriksaan kualitas generik tanpa validator domain khusus.",
        generic_quality_enabled=True,
        eligible_governance_contexts=_ALL_GOVERNANCE_CONTEXTS,
        future_rule_pack_ids=(),
        future_policy_pack_ids=("government_generic",),
        fallback_message=(
            "Profil generic aktif; tidak ada validator domain-specific yang aktif."
        ),
    ),
    DomainId.HEALTHCARE: DomainProfile(
        domain_id=DomainId.HEALTHCARE,
        display_name="Healthcare",
        description="Konteks kesehatan untuk rule pack dan policy pack masa depan.",
        generic_quality_enabled=True,
        eligible_governance_contexts=_ALL_GOVERNANCE_CONTEXTS,
        future_rule_pack_ids=("healthcare_contextual",),
        future_policy_pack_ids=("government_generic", "healthcare"),
    ),
    DomainId.EDUCATION: DomainProfile(
        domain_id=DomainId.EDUCATION,
        display_name="Education",
        description="Konteks pendidikan untuk rule pack dan policy pack masa depan.",
        generic_quality_enabled=True,
        eligible_governance_contexts=_ALL_GOVERNANCE_CONTEXTS,
        future_rule_pack_ids=("education_contextual",),
        future_policy_pack_ids=("government_generic", "education"),
    ),
    DomainId.ENVIRONMENT: DomainProfile(
        domain_id=DomainId.ENVIRONMENT,
        display_name="Environment",
        description="Konteks lingkungan untuk rule pack dan policy pack masa depan.",
        generic_quality_enabled=True,
        eligible_governance_contexts=_ALL_GOVERNANCE_CONTEXTS,
        future_rule_pack_ids=("environment_contextual",),
        future_policy_pack_ids=("government_generic", "environment"),
    ),
    DomainId.OTHER: DomainProfile(
        domain_id=DomainId.OTHER,
        display_name="Other",
        description="Konteks selain profil domain yang telah didefinisikan.",
        generic_quality_enabled=True,
        eligible_governance_contexts=_ALL_GOVERNANCE_CONTEXTS,
        future_rule_pack_ids=(),
        future_policy_pack_ids=(),
        fallback_message="No domain-specific validation profile is active.",
    ),
}


def validate_governance_context(
    value: GovernanceContext | str,
) -> GovernanceContext:
    """Return a supported governance context or raise a clear ValueError."""
    try:
        return GovernanceContext(value)
    except ValueError as error:
        raise ValueError(f"Governance context tidak didukung: {value!r}") from error


def validate_domain_id(value: DomainId | str) -> DomainId:
    """Return a supported domain identifier or raise a clear ValueError."""
    try:
        return DomainId(value)
    except ValueError as error:
        raise ValueError(f"Domain tidak didukung: {value!r}") from error


def get_domain_profile(value: DomainId | str) -> DomainProfile:
    """Return the immutable profile for a validated domain identifier."""
    return DOMAIN_PROFILES[validate_domain_id(value)]
