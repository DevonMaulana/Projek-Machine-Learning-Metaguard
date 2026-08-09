"""Temporary local Chroma tests for isolated v3 metadata-filtered retrieval."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Sequence

from core.policy_registry import parse_policy_registry
from core.policy_router import route_policy_evidence
from rag.policy_corpus_v3 import compute_expected_corpus_state, rebuild_policy_corpus_v3
from rag.policy_retrieval_v3 import RetrievalState, retrieve_policy_chunks_v3


def _registry(tmp_path: Path):
    directory = tmp_path / "data" / "policies"
    directory.mkdir(parents=True)
    records = []
    for policy_id, pack, domain in (
        ("TEST-GOV", "government_generic", "generic"),
        ("TEST-HEALTH", "healthcare", "healthcare"),
        ("TEST-EDU", "education", "education"),
    ):
        filename = f"{policy_id}.txt"
        (directory / filename).write_text((f"{policy_id} evidence kebijakan data terstruktur. " * 35), encoding="utf-8")
        records.append({"policy_id": policy_id, "title": policy_id, "number": "1", "year": 2026, "authority": "Test", "domain_id": domain, "policy_pack": pack, "document_type": "governance_policy" if pack == "government_generic" else "sectoral_data_governance", "classification": "ESSENTIAL", "effective_status": "current", "topics": ["metadata"], "scope": "test", "local_file": f"data/policies/{filename}", "verification_state": "verified"})
    return parse_policy_registry({"schema_version": "1.0", "policies": records})


def _encoder(texts: Sequence[str]) -> list[list[float]]:
    return [[float(index + 1), 1.0] for index, _ in enumerate(texts)]


def test_v3_retrieval_preserves_identity_and_respects_policy_filter(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    database = tmp_path / "db"
    rebuild_policy_corpus_v3(vector_db_path=database, registry=registry, repository_root=tmp_path, encoder=_encoder, require_initial_six=False)
    plan = compute_expected_corpus_state(registry=registry, repository_root=tmp_path, require_initial_six=False)

    education = route_policy_evidence(governance_context="government_public", selected_domain="education", evidence_need="domain_semantic_support", registry=registry)
    result = retrieve_policy_chunks_v3("education policy", routing=education, vector_db_path=database, corpus_plan=plan, encoder=_encoder)
    assert result.state is RetrievalState.SUCCESS
    assert result.evidence
    assert {item["policy_id"] for item in result.evidence} == {"TEST-EDU"}
    assert all({"chunk_id", "source", "page", "text", "policy_pack", "domain_id", "document_type"} <= set(item) for item in result.evidence)

    non_government = route_policy_evidence(governance_context="generic_non_government", selected_domain="education", evidence_need="metadata_governance", registry=registry)
    skipped = retrieve_policy_chunks_v3("must not query", routing=non_government, vector_db_path=database, corpus_plan=plan, encoder=_encoder)
    assert skipped.state is RetrievalState.NOT_APPLICABLE
    assert not skipped.evidence and skipped.where is None


def test_stale_corpus_is_explicit_and_not_empty(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    routing = route_policy_evidence(governance_context="government_public", selected_domain="education", evidence_need="domain_semantic_support", registry=registry)
    plan = compute_expected_corpus_state(registry=registry, repository_root=tmp_path, require_initial_six=False)
    result = retrieve_policy_chunks_v3("education", routing=routing, vector_db_path=tmp_path / "missing", corpus_plan=plan, encoder=_encoder)
    assert result.state is RetrievalState.CORPUS_STALE
    assert not result.evidence


def test_applicable_empty_result_is_not_not_applicable(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    database = tmp_path / "db"
    rebuild_policy_corpus_v3(vector_db_path=database, registry=registry, repository_root=tmp_path, encoder=_encoder, require_initial_six=False)
    plan = compute_expected_corpus_state(registry=registry, repository_root=tmp_path, require_initial_six=False)
    routed = route_policy_evidence(governance_context="government_public", selected_domain="education", evidence_need="domain_semantic_support", registry=registry)
    no_match = replace(routed, eligible_policy_ids=("MISSING-POLICY",))
    result = retrieve_policy_chunks_v3("education", routing=no_match, vector_db_path=database, corpus_plan=plan, encoder=_encoder)
    assert result.state is RetrievalState.EMPTY
    assert not result.evidence
