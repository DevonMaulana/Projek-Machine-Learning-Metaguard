"""Tests for deterministic, non-LLM policy routing and Chroma filters."""

from __future__ import annotations

import json

import pytest

from core.policy_router import (
    ApplicabilityState,
    EvidenceNeed,
    PolicyRoutingError,
    build_chroma_where,
    route_policy_evidence,
)


def test_government_generic_governance_need_routes_only_government_pack() -> None:
    result = route_policy_evidence(
        governance_context="government_public", selected_domain="healthcare", evidence_need="metadata_governance"
    )
    assert result.applicability_state is ApplicabilityState.APPLICABLE
    assert result.eligible_policy_packs == ("government_generic",)
    assert set(result.eligible_policy_ids) == {
        "GOV-SDI-PERPRES-39-2019", "BPS-STANDARD-DATA-4-2020", "BPS-METADATA-5-2020"
    }
    assert "government_public" in result.routing_reasons[0]
    json.dumps(result.to_dict(), ensure_ascii=False)


@pytest.mark.parametrize(
    ("domain", "expected_pack", "expected_id"),
    [
        ("healthcare", "healthcare", "HEALTH-SATU-DATA-18-2022"),
        ("education", "education", "EDU-SATU-DATA-31-2022"),
        ("environment", "environment", "ENV-SATU-DATA-25-2021"),
    ],
)
def test_domain_semantic_support_is_strictly_domain_scoped(domain: str, expected_pack: str, expected_id: str) -> None:
    result = route_policy_evidence(
        governance_context="government_public", selected_domain=domain, evidence_need=EvidenceNeed.DOMAIN_SEMANTIC_SUPPORT
    )
    assert result.applicability_state is ApplicabilityState.APPLICABLE
    assert result.eligible_policy_packs == (expected_pack,)
    assert result.eligible_policy_ids == (expected_id,)


def test_non_government_is_not_applicable_and_generic_other_have_no_domain_pack() -> None:
    non_government = route_policy_evidence(
        governance_context="generic_non_government", selected_domain="healthcare", evidence_need="metadata_governance"
    )
    assert non_government.applicability_state is ApplicabilityState.NOT_APPLICABLE
    assert not non_government.eligible_policy_ids
    assert build_chroma_where(non_government) is None

    for domain in ("generic", "other"):
        result = route_policy_evidence(
            governance_context="government_public", selected_domain=domain, evidence_need="domain_semantic_support"
        )
        assert result.applicability_state is ApplicabilityState.NO_ELIGIBLE_POLICY


def test_filter_builder_uses_only_validated_scalar_policy_conditions() -> None:
    routing = route_policy_evidence(
        governance_context="government_public", selected_domain="education", evidence_need="domain_semantic_support"
    )
    where = build_chroma_where(routing)
    assert where == {
        "$and": [
            {"policy_id": {"$in": ["EDU-SATU-DATA-31-2022"]}},
            {"effective_status": {"$eq": "current"}},
            {"verification_state": {"$eq": "verified"}},
        ]
    }
    assert "topics" not in json.dumps(where)
    with pytest.raises(PolicyRoutingError):
        build_chroma_where({})  # type: ignore[arg-type]


def test_unknown_need_and_topic_fail_deterministically() -> None:
    with pytest.raises(PolicyRoutingError, match="Evidence need"):
        route_policy_evidence(governance_context="government_public", selected_domain="generic", evidence_need="arbitrary")
    with pytest.raises(PolicyRoutingError, match="Topic"):
        route_policy_evidence(
            governance_context="government_public", selected_domain="generic", evidence_need="metadata_governance", topic="not-present"
        )
