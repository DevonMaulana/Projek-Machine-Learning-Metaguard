"""Real local Chroma contract tests required by planned v0.3 routing.

These tests use only explicit dummy vectors and pytest temporary directories.
They do not load the project embedder, policy PDFs, or repository vector store.
"""

from __future__ import annotations

import gc
from typing import Any

import chromadb
import pytest
from chromadb.config import Settings


TEST_COLLECTION_NAME = "metaguard_chroma_contract_test_only"


@pytest.fixture
def chroma_collection(tmp_path: Any) -> Any:
    """Return a temporary persistent collection populated with scalar metadata."""
    client = chromadb.PersistentClient(
        path=str(tmp_path),
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(TEST_COLLECTION_NAME)
    records = [
        (
            "generic-policy",
            [1.0, 0.0],
            {
                "policy_id": "GOV-SDI-PERPRES-39-2019",
                "policy_pack": "government_generic",
                "domain_id": "generic",
                "document_type": "governance_policy",
                "effective_status": "current",
                "rank": 1,
                "weight": 1.5,
                "verified": True,
            },
        ),
        (
            "health-policy",
            [0.9, 0.1],
            {
                "policy_id": "HEALTH-GOV-PERMENKES-18-2022",
                "policy_pack": "healthcare",
                "domain_id": "healthcare",
                "document_type": "sectoral_data_governance",
                "effective_status": "current",
                "rank": 2,
                "weight": 2.5,
                "verified": False,
            },
        ),
        (
            "education-policy",
            [0.8, 0.2],
            {
                "policy_id": "EDU-GOV-PERMENDIKBUDRISTEK-31-2022",
                "policy_pack": "education",
                "domain_id": "education",
                "document_type": "sectoral_data_governance",
                "effective_status": "current",
                "rank": 3,
                "weight": 3.5,
                "verified": True,
            },
        ),
        (
            "environment-policy",
            [0.7, 0.3],
            {
                "policy_id": "ENV-GOV-PERMENLHK-25-2021",
                "policy_pack": "environment",
                "domain_id": "environment",
                "document_type": "sectoral_data_governance",
                "effective_status": "current",
                "rank": 4,
                "weight": 4.5,
                "verified": True,
            },
        ),
    ]
    collection.add(
        ids=[record[0] for record in records],
        embeddings=[record[1] for record in records],
        documents=[record[0] for record in records],
        metadatas=[record[2] for record in records],
    )
    yield collection
    del collection
    del client
    gc.collect()


def _query_ids(collection: Any, where: dict[str, Any] | None = None) -> set[str]:
    result = collection.query(
        query_embeddings=[[1.0, 0.0]],
        n_results=4,
        where=where,
    )
    assert isinstance(result["ids"], list)
    assert len(result["ids"]) == 1
    assert isinstance(result["ids"][0], list)
    return set(result["ids"][0])


def test_scalar_metadata_and_result_shapes(chroma_collection: Any) -> None:
    """Scalar routing metadata persists; query and get retain distinct shapes."""
    metadata = chroma_collection.get(ids=["generic-policy"])["metadatas"][0]

    assert metadata["policy_id"] == "GOV-SDI-PERPRES-39-2019"
    assert metadata["policy_pack"] == "government_generic"
    assert metadata["domain_id"] == "generic"
    assert metadata["document_type"] == "governance_policy"
    assert metadata["effective_status"] == "current"
    assert metadata["rank"] == 1
    assert metadata["weight"] == 1.5
    assert metadata["verified"] is True

    query_result = chroma_collection.query(
        query_embeddings=[[1.0, 0.0]],
        n_results=1,
    )
    get_result = chroma_collection.get(ids=["generic-policy"])

    assert isinstance(query_result["ids"], list)
    assert isinstance(query_result["ids"][0], list)
    assert query_result["ids"] == [["generic-policy"]]
    assert isinstance(get_result["ids"], list)
    assert get_result["ids"] == ["generic-policy"]


def test_metadata_filter_contract(chroma_collection: Any) -> None:
    """Chroma 0.6 routing filters return only their eligible dummy records."""
    assert _query_ids(chroma_collection) == {
        "generic-policy",
        "health-policy",
        "education-policy",
        "environment-policy",
    }
    assert _query_ids(
        chroma_collection,
        {"policy_pack": {"$eq": "government_generic"}},
    ) == {"generic-policy"}
    assert _query_ids(chroma_collection, {"domain_id": "education"}) == {
        "education-policy"
    }
    assert _query_ids(
        chroma_collection,
        {"policy_pack": {"$in": ["government_generic", "environment"]}},
    ) == {"generic-policy", "environment-policy"}
    assert _query_ids(
        chroma_collection,
        {
            "$and": [
                {"effective_status": {"$eq": "current"}},
                {"domain_id": {"$eq": "healthcare"}},
            ]
        },
    ) == {"health-policy"}
    assert _query_ids(
        chroma_collection,
        {
            "$or": [
                {"domain_id": {"$eq": "healthcare"}},
                {"domain_id": {"$eq": "education"}},
            ]
        },
    ) == {"health-policy", "education-policy"}
    assert _query_ids(
        chroma_collection,
        {"domain_id": {"$ne": "generic"}},
    ) == {"health-policy", "education-policy", "environment-policy"}
    assert _query_ids(
        chroma_collection,
        {"domain_id": {"$nin": ["generic", "healthcare"]}},
    ) == {"education-policy", "environment-policy"}


def test_filtered_get_and_delete_contract(chroma_collection: Any) -> None:
    """Filtered reads and deletes isolate the selected policy records."""
    filtered = chroma_collection.get(where={"domain_id": {"$eq": "education"}})
    assert filtered["ids"] == ["education-policy"]

    chroma_collection.delete(where={"domain_id": {"$eq": "environment"}})

    assert chroma_collection.count() == 3
    assert chroma_collection.get(where={"domain_id": "environment"})["ids"] == []
    assert set(chroma_collection.get()["ids"]) == {
        "generic-policy",
        "health-policy",
        "education-policy",
    }


def test_persistent_collection_reopens_from_temporary_directory(tmp_path: Any) -> None:
    """A PersistentClient can reopen a test-only collection from pytest storage."""
    client = chromadb.PersistentClient(
        path=str(tmp_path),
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(TEST_COLLECTION_NAME)
    collection.add(
        ids=["persisted-policy"],
        embeddings=[[1.0, 0.0]],
        documents=["persisted policy"],
        metadatas=[
            {
                "policy_id": "PERSISTED-TEST-1",
                "policy_pack": "government_generic",
                "domain_id": "generic",
                "document_type": "governance_policy",
                "effective_status": "current",
            }
        ],
    )
    del collection
    del client
    gc.collect()

    reopened_client = chromadb.PersistentClient(
        path=str(tmp_path),
        settings=Settings(anonymized_telemetry=False),
    )
    reopened_collection = reopened_client.get_or_create_collection(
        TEST_COLLECTION_NAME
    )

    assert reopened_collection.count() == 1
    assert reopened_collection.get()["ids"] == ["persisted-policy"]

    del reopened_collection
    del reopened_client
    gc.collect()


def test_list_metadata_is_not_a_supported_routing_contract(tmp_path: Any) -> None:
    """Keep topics in the registry: Chroma metadata is deliberately scalar-only."""
    client = chromadb.PersistentClient(
        path=str(tmp_path),
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(TEST_COLLECTION_NAME)

    with pytest.raises(ValueError, match="list"):
        collection.add(
            ids=["invalid-list-metadata"],
            embeddings=[[1.0, 0.0]],
            documents=["list metadata must not be used"],
            metadatas=[{"topics": ["metadata", "governance"]}],
        )

    del collection
    del client
    gc.collect()
