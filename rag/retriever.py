"""Evidence-only retrieval from the local MetaGuard policy collection."""

from pathlib import Path
from typing import Any

from rag.vector_store import DEFAULT_VECTOR_DB, get_collection, get_embedding_model


def retrieve_policy_chunks(
    query: str, top_k: int = 4, vector_db_path: str | Path = DEFAULT_VECTOR_DB
) -> list[dict[str, Any]]:
    """Return the nearest policy chunks without generating an answer."""
    if not query.strip():
        raise ValueError("Query tidak boleh kosong.")
    if top_k < 1:
        raise ValueError("top_k harus minimal 1.")
    collection = get_collection(vector_db_path)
    if collection.count() == 0:
        return []
    embedding = get_embedding_model().encode([query], normalize_embeddings=True).tolist()
    result = collection.query(query_embeddings=embedding, n_results=top_k)
    output = []
    for index, text in enumerate(result["documents"][0]):
        metadata = result["metadatas"][0][index]
        output.append({"chunk_id": result["ids"][0][index], "source": metadata["source"], "page": int(metadata["page"]), "text": text, "distance": float(result["distances"][0][index])})
    return output
