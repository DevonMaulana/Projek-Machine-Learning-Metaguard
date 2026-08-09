import json
from dataclasses import FrozenInstanceError

import pytest

from core.domain_models import (
    DOMAIN_PROFILES,
    DomainId,
    GovernanceContext,
    get_domain_profile,
    validate_domain_id,
    validate_governance_context,
)


def test_governance_contexts_are_stable_and_independent_from_domain() -> None:
    assert [context.value for context in GovernanceContext] == [
        "government_public",
        "generic_non_government",
    ]
    assert validate_governance_context("government_public") is (
        GovernanceContext.GOVERNMENT_PUBLIC
    )
    assert validate_governance_context("generic_non_government") is (
        GovernanceContext.GENERIC_NON_GOVERNMENT
    )

    education = get_domain_profile(DomainId.EDUCATION)
    assert education.domain_id is DomainId.EDUCATION
    assert education.eligible_governance_contexts == tuple(GovernanceContext)


def test_invalid_governance_context_is_rejected() -> None:
    with pytest.raises(ValueError, match="Governance context"):
        validate_governance_context("government_guess")


def test_domain_ids_are_stable_and_validated() -> None:
    assert [domain.value for domain in DomainId] == [
        "generic",
        "healthcare",
        "education",
        "environment",
        "other",
    ]
    assert validate_domain_id("environment") is DomainId.ENVIRONMENT

    with pytest.raises(ValueError, match="Domain"):
        validate_domain_id("unknown_domain")


def test_profiles_expose_only_future_pack_declarations() -> None:
    healthcare = get_domain_profile("healthcare")
    education = get_domain_profile("education")
    environment = get_domain_profile("environment")

    assert healthcare.future_rule_pack_ids == ("healthcare_contextual",)
    assert healthcare.future_policy_pack_ids == (
        "government_generic",
        "healthcare",
    )
    assert education.future_rule_pack_ids == ("education_contextual",)
    assert environment.future_rule_pack_ids == ("environment_contextual",)
    assert environment.future_policy_pack_ids == (
        "government_generic",
        "environment",
    )
    assert all(profile.generic_quality_enabled for profile in DOMAIN_PROFILES.values())


def test_generic_and_other_profiles_have_safe_fallback_and_json_safe_snapshot() -> None:
    generic = get_domain_profile("generic")
    other = get_domain_profile("other")

    assert generic.fallback_message
    assert other.fallback_message == "No domain-specific validation profile is active."
    assert generic.future_rule_pack_ids == ()
    assert other.future_policy_pack_ids == ()
    assert json.loads(json.dumps(other.to_dict()))["domain_id"] == "other"

    with pytest.raises(FrozenInstanceError):
        other.display_name = "Mutated"  # type: ignore[misc]
