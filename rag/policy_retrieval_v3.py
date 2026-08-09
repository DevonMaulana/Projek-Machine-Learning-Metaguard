"""Isolated metadata-filtered retrieval for the persisted MetaGuard v3 corpus."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Sequence

from core.policy_router import ApplicabilityState, PolicyRoutingResult, build_chroma_where
from rag.policy_corpus_v3 import CorpusPlan, V3_COLLECTION_NAME, needs_corpus_rebuild, verify_persisted_corpus
from rag.vector_store import DEFAULT_VECTOR_DB, get_embedding_model


class RetrievalState(str, Enum):
    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CORPUS_STALE = "CORPUS_STALE"


@dataclass(frozen=True)
class V3RetrievalResult:
    """Compact result separating routing applicability from retrieval emptiness."""

    state: RetrievalState
    routing: PolicyRoutingResult
    evidence: tuple[dict[str, Any], ...]
    where: dict[str, Any] | None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "routing": self.routing.to_dict(),
            "evidence": list(self.evidence),
            "where": self.where,
            "message": self.message,
        }


def _default_encoder(texts: Sequence[str]) -> list[list[float]]:
    return get_embedding_model().encode(list(texts), normalize_embeddings=True).tolist()


def _open_v3_collection(vector_db_path: str | Path) -> Any:
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(path=str(vector_db_path), settings=Settings(anonymized_telemetry=False))
    return client.get_collection(V3_COLLECTION_NAME)


def retrieve_policy_chunks_v3(
    query: str,
    *,
    routing: PolicyRoutingResult,
    top_k: int = 4,
    vector_db_path: str | Path = DEFAULT_VECTOR_DB,
    corpus_plan: CorpusPlan | None = None,
    encoder: Callable[[Sequence[str]], list[list[float]]] | None = None,
) -> V3RetrievalResult:
    """Query only current v3 corpus with an allowlisted metadata filter."""
    if not isinstance(routing, PolicyRoutingResult):
        raise ValueError("routing harus berupa PolicyRoutingResult tervalidasi.")
    if not query.strip():
        raise ValueError("Query tidak boleh kosong.")
    if top_k < 1:
        raise ValueError("top_k harus minimal 1.")
    if routing.applicability_state is not ApplicabilityState.APPLICABLE:
        return V3RetrievalResult(RetrievalState.NOT_APPLICABLE, routing, (), None, "Policy evidence tidak applicable untuk konteks routing ini.")
    where = build_chroma_where(routing)
    stale = (
        needs_corpus_rebuild(vector_db_path=vector_db_path)
        if corpus_plan is None
        else _plan_is_stale(corpus_plan, vector_db_path)
    )
    if stale:
        return V3RetrievalResult(RetrievalState.CORPUS_STALE, routing, (), where, "Corpus policy v3 belum current; rebuild eksplisit diperlukan.")
    collection = _open_v3_collection(vector_db_path)
    embeddings = (encoder or _default_encoder)([query])
    result = collection.query(query_embeddings=embeddings, n_results=top_k, where=where)
    output = []
    seen = set()
    for index, chunk_id in enumerate(result.get("ids", [[]])[0]):
        if chunk_id in seen:
            continue
        metadata = result["metadatas"][0][index]
        if metadata.get("policy_id") not in routing.eligible_policy_ids:
            continue
        seen.add(chunk_id)
        output.append({
            "chunk_id": chunk_id,
            "source": metadata["source"],
            "page": int(metadata["page"]),
            "text": result["documents"][0][index],
            "policy_id": metadata["policy_id"],
            "policy_pack": metadata["policy_pack"],
            "domain_id": metadata["domain_id"],
            "document_type": metadata["document_type"],
            "classification": metadata["classification"],
            "effective_status": metadata["effective_status"],
            "distance": float(result["distances"][0][index]),
        })
    state = RetrievalState.SUCCESS if output else RetrievalState.EMPTY
    return V3RetrievalResult(state, routing, tuple(output), where)


def _plan_is_stale(plan: CorpusPlan, vector_db_path: str | Path) -> bool:
    try:
        verify_persisted_corpus(plan=plan, vector_db_path=vector_db_path)
    except ValueError:
        return True
    return False
