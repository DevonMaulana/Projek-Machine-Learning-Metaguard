"""Temporary local Chroma integration tests for the isolated v3 corpus build."""

from __future__ import annotations

import gc
from pathlib import Path
from typing import Sequence

import chromadb
from chromadb.config import Settings

from core.policy_registry import parse_policy_registry
from rag.policy_corpus_v3 import (
    V3_COLLECTION_NAME,
    needs_corpus_rebuild,
    read_corpus_manifest,
    rebuild_policy_corpus_v3,
    verify_persisted_corpus,
    compute_expected_corpus_state,
)


def _test_registry(tmp_path: Path):
    policy_path = tmp_path / "data" / "policies" / "policy.txt"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text("Kebijakan metadata dan kualitas data yang dapat diverifikasi. " * 35, encoding="utf-8")
    return parse_policy_registry(
        {
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
    )


def _fake_encoder(texts: Sequence[str]) -> list[list[float]]:
    return [[float(index + 1), float(len(text))] for index, text in enumerate(texts)]


def test_v3_rebuild_uses_scalar_metadata_persists_and_preserves_other_collection(tmp_path: Path) -> None:
    registry = _test_registry(tmp_path)
    database = tmp_path / "vector_db"
    client = chromadb.PersistentClient(path=str(database), settings=Settings(anonymized_telemetry=False))
    legacy = client.get_or_create_collection("metaguard_policies")
    legacy.add(
        ids=["legacy"],
        embeddings=[[1.0, 0.0]],
        documents=["legacy corpus"],
        metadatas=[{"source": "legacy.pdf", "page": 1}],
    )

    summary = rebuild_policy_corpus_v3(
        vector_db_path=database,
        registry=registry,
        repository_root=tmp_path,
        encoder=_fake_encoder,
        require_initial_six=False,
    )
    assert summary["collection_name"] == V3_COLLECTION_NAME
    assert summary["total_documents"] == 1
    assert summary["total_chunks"] > 0
    assert summary["verification"]["persistent_reopen_verified"] is True
    assert legacy.count() == 1
    assert not needs_corpus_rebuild(
        vector_db_path=database,
        registry=registry,
        repository_root=tmp_path,
        require_initial_six=False,
    )

    reopened = chromadb.PersistentClient(path=str(database), settings=Settings(anonymized_telemetry=False))
    collection = reopened.get_collection(V3_COLLECTION_NAME)
    stored = collection.get(include=["documents", "metadatas"])
    assert stored["ids"]
    metadata = stored["metadatas"][0]
    assert metadata["policy_id"] == "TEST-POLICY-001"
    assert metadata["source"] == "policy.txt"
    assert metadata["page"] == 1
    assert metadata["domain_id"] == "generic"
    assert metadata["policy_pack"] == "government_generic"
    assert metadata["document_type"] == "governance_policy"
    assert "topics" not in metadata
    assert all(type(value) in {str, int, float, bool} for value in metadata.values())

    manifest = read_corpus_manifest(database)
    assert manifest is not None
    assert manifest["total_chunks"] == collection.count()
    plan = compute_expected_corpus_state(registry=registry, repository_root=tmp_path, require_initial_six=False)
    assert verify_persisted_corpus(plan=plan, vector_db_path=database)["chunk_count"] == collection.count()

    del collection
    del reopened
    del legacy
    del client
    gc.collect()
