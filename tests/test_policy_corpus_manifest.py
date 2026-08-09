"""Pure state and manifest tests for the isolated MetaGuard v3 corpus."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from core.policy_registry import load_policy_registry, parse_policy_registry
from rag.policy_corpus_v3 import (
    ChunkingConfig,
    EXPECTED_INITIAL_POLICY_IDS,
    build_stable_chunk_id,
    compute_expected_corpus_state,
    needs_corpus_rebuild,
    validate_initial_policy_registry,
)


def _test_registry(tmp_path: Path):
    policy_path = tmp_path / "data" / "policies" / "policy.txt"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text("Kebijakan data yang terstruktur dan dapat ditelusuri. " * 30, encoding="utf-8")
    raw = {
        "schema_version": "1.0",
        "policies": [
            {
                "policy_id": "TEST-POLICY-001",
                "title": "Test policy",
                "number": "1",
                "year": 2026,
                "authority": "Test authority",
                "domain_id": "generic",
                "policy_pack": "government_generic",
                "document_type": "governance_policy",
                "classification": "ESSENTIAL",
                "effective_status": "current",
                "topics": ["metadata"],
                "scope": "Test only",
                "local_file": "data/policies/policy.txt",
                "verification_state": "verified",
            }
        ],
    }
    return parse_policy_registry(raw), policy_path


def _plan(tmp_path: Path, **changes: object):
    registry, _ = _test_registry(tmp_path)
    return compute_expected_corpus_state(
        registry=registry,
        repository_root=tmp_path,
        require_initial_six=False,
        **changes,
    )


def test_production_registry_is_exactly_the_approved_initial_six() -> None:
    registry = load_policy_registry()
    validate_initial_policy_registry(registry)
    assert {policy.policy_id for policy in registry.policies} == EXPECTED_INITIAL_POLICY_IDS


def test_expected_corpus_state_is_stable_and_registry_order_independent(tmp_path: Path) -> None:
    registry, _ = _test_registry(tmp_path)
    first = compute_expected_corpus_state(registry=registry, repository_root=tmp_path, require_initial_six=False)
    raw = registry.to_dict()
    raw["policies"].reverse()
    reordered = parse_policy_registry(raw)
    second = compute_expected_corpus_state(registry=reordered, repository_root=tmp_path, require_initial_six=False)
    assert first.corpus_fingerprint == second.corpus_fingerprint
    assert first.registry_retrieval_fingerprint == second.registry_retrieval_fingerprint


def test_corpus_fingerprint_changes_for_file_registry_model_and_chunking_inputs(tmp_path: Path) -> None:
    registry, policy_path = _test_registry(tmp_path)
    baseline = compute_expected_corpus_state(registry=registry, repository_root=tmp_path, require_initial_six=False)

    policy_path.write_text("Kebijakan data berubah dan dapat ditelusuri. " * 30, encoding="utf-8")
    changed_file = compute_expected_corpus_state(registry=registry, repository_root=tmp_path, require_initial_six=False)
    assert changed_file.corpus_fingerprint != baseline.corpus_fingerprint

    raw = registry.to_dict()
    raw["policies"][0]["authority"] = "Changed authority"
    changed_registry = parse_policy_registry(raw)
    registry_plan = compute_expected_corpus_state(registry=changed_registry, repository_root=tmp_path, require_initial_six=False)
    assert registry_plan.corpus_fingerprint != changed_file.corpus_fingerprint

    assert compute_expected_corpus_state(
        registry=changed_registry,
        repository_root=tmp_path,
        embedding_model="other-local-model",
        require_initial_six=False,
    ).corpus_fingerprint != registry_plan.corpus_fingerprint
    assert compute_expected_corpus_state(
        registry=changed_registry,
        repository_root=tmp_path,
        chunking=ChunkingConfig(chunk_size=700),
        require_initial_six=False,
    ).corpus_fingerprint != registry_plan.corpus_fingerprint


def test_stable_chunk_ids_are_unique_and_depend_on_text_and_config() -> None:
    common = {"policy_id": "TEST-POLICY-001", "page": 2, "ordinal": 1, "text": "Evidence policy text."}
    first = build_stable_chunk_id(**common)
    assert first == build_stable_chunk_id(**common)
    assert first != build_stable_chunk_id(**(common | {"ordinal": 2}))
    assert first != build_stable_chunk_id(**(common | {"text": "Changed text."}))
    assert first != build_stable_chunk_id(**common, chunking=ChunkingConfig(chunk_size=700))


def test_absent_or_stale_manifest_requires_rebuild(tmp_path: Path) -> None:
    assert needs_corpus_rebuild(vector_db_path=tmp_path / "db", registry=_test_registry(tmp_path)[0], repository_root=tmp_path, require_initial_six=False)
    manifest_path = tmp_path / "db" / "metaguard_policies_v3_manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(json.dumps({"corpus_fingerprint": "stale"}), encoding="utf-8")
    assert needs_corpus_rebuild(vector_db_path=tmp_path / "db", registry=_test_registry(tmp_path)[0], repository_root=tmp_path, require_initial_six=False)
