"""Tests for exact metadata alignment in isolated v0.3 evidence assessment."""

from __future__ import annotations

import json

import pytest

from core.evidence_alignment import AlignmentState, assess_evidence_alignment, deduplicate_evidence_chunks
from core.policy_router import route_policy_evidence


def _evidence(chunk_id: str, policy_id: str, pack: str, domain: str, source: str = "policy.pdf") -> dict[str, object]:
    return {"chunk_id": chunk_id, "policy_id": policy_id, "policy_pack": pack, "domain_id": domain, "source": source, "page": 1, "text": "ringkas"}


@pytest.mark.parametrize(
    ("domain", "policy_id", "pack"),
    [
        ("healthcare", "HEALTH-SATU-DATA-18-2022", "healthcare"),
        ("education", "EDU-SATU-DATA-31-2022", "education"),
        ("environment", "ENV-SATU-DATA-25-2021", "environment"),
    ],
)
def test_domain_evidence_is_aligned_only_with_its_exact_route(domain: str, policy_id: str, pack: str) -> None:
    routing = route_policy_evidence(governance_context="government_public", selected_domain=domain, evidence_need="domain_semantic_support")
    result = assess_evidence_alignment(routing, [_evidence("one", policy_id, pack, domain)])
    assert result.policy_pack_alignment is AlignmentState.ALIGNED
    assert result.domain_alignment is AlignmentState.ALIGNED
    json.dumps(result.to_dict())


def test_government_generic_evidence_aligns_for_governance_need() -> None:
    routing = route_policy_evidence(governance_context="government_public", selected_domain="healthcare", evidence_need="metadata_governance")
    result = assess_evidence_alignment(routing, [_evidence("one", "BPS-METADATA-5-2020", "government_generic", "generic")])
    assert result.policy_pack_alignment is AlignmentState.ALIGNED
    assert result.domain_alignment is AlignmentState.ALIGNED


def test_ineligible_evidence_is_rejected_and_cannot_align() -> None:
    routing = route_policy_evidence(governance_context="government_public", selected_domain="healthcare", evidence_need="domain_semantic_support")
    result = assess_evidence_alignment(routing, [_evidence("bad", "EDU-SATU-DATA-31-2022", "education", "education")])
    assert result.policy_pack_alignment is AlignmentState.MISALIGNED
    assert result.domain_alignment is AlignmentState.MISALIGNED
    assert result.rejected_chunk_ids == ("bad",)
    assert not result.eligible_evidence


def test_duplicate_chunks_preserve_first_occurrence_without_inflating_inputs() -> None:
    original = _evidence("same", "HEALTH-SATU-DATA-18-2022", "healthcare", "healthcare")
    output = deduplicate_evidence_chunks([original, {**original, "text": "berbeda"}])
    assert output == (original,)
    assert original["text"] == "ringkas"
