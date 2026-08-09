"""Explicit, deterministic analysis semantics for MetaGuard v0.3.

The context is independent of a dataset fingerprint.  It records the selected
domain, governance context, and registry semantics that determine how a dataset
would be interpreted.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from core.concept_registry import ConceptRegistry, load_concept_registry
from core.domain_models import (
    DomainId,
    DomainProfile,
    GovernanceContext,
    get_domain_profile,
    validate_domain_id,
    validate_governance_context,
)
from core.policy_registry import PolicyRegistry, load_policy_registry
from core.rule_registry import RuleRegistry, load_rule_registry


@dataclass(frozen=True)
class AnalysisContext:
    """Immutable, JSON-safe semantic context for one analysis session."""

    selected_domain: DomainId
    governance_context: GovernanceContext
    domain_profile: DomainProfile
    concept_registry_fingerprint: str
    rule_registry_fingerprint: str
    policy_registry_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        """Return compact metadata suitable for future report and audit use."""
        return {
            "selected_domain": self.selected_domain.value,
            "governance_context": self.governance_context.value,
            "domain_profile": self.domain_profile.to_dict(),
            "concept_registry_fingerprint": self.concept_registry_fingerprint,
            "rule_registry_fingerprint": self.rule_registry_fingerprint,
            "policy_registry_fingerprint": self.policy_registry_fingerprint,
        }

    def canonical_snapshot(self) -> str:
        """Return a deterministic serialization of all semantic inputs."""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def fingerprint(self) -> str:
        """Return a stable SHA-256 semantic-context fingerprint."""
        return sha256(self.canonical_snapshot().encode("utf-8")).hexdigest()


def build_analysis_context(
    *,
    selected_domain: DomainId | str,
    governance_context: GovernanceContext | str,
    concept_registry: ConceptRegistry | None = None,
    rule_registry: RuleRegistry | None = None,
    policy_registry: PolicyRegistry | None = None,
) -> AnalysisContext:
    """Build explicit context; registry load failures are intentionally surfaced."""
    domain_id = validate_domain_id(selected_domain)
    governance_id = validate_governance_context(governance_context)
    active_concepts = concept_registry or load_concept_registry()
    active_rules = rule_registry or load_rule_registry(concept_registry=active_concepts)
    active_policies = policy_registry or load_policy_registry()
    return AnalysisContext(
        selected_domain=domain_id,
        governance_context=governance_id,
        domain_profile=get_domain_profile(domain_id),
        concept_registry_fingerprint=active_concepts.fingerprint(),
        rule_registry_fingerprint=active_rules.fingerprint(),
        policy_registry_fingerprint=active_policies.fingerprint(),
    )
