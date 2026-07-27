"""Persistent Chroma vector store backed by a cached MiniLM embedder."""

from functools import lru_cache
from pathlib import Path
from typing import Any

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION_NAME = "metaguard_policies"
DEFAULT_VECTOR_DB = Path("vector_db")


@lru_cache(maxsize=1)
def get_embedding_model() -> Any:
    """Load the embedding model once per process, using its local cache."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def get_collection(vector_db_path: str | Path = DEFAULT_VECTOR_DB, *, rebuild: bool = False) -> Any:
    """Create or open the persistent MetaGuard Chroma collection."""
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=str(vector_db_path),
        settings=Settings(anonymized_telemetry=False),
    )
    if rebuild:
        try:
            client.delete_collection(COLLECTION_NAME)
        except ValueError:
            pass
    return client.get_or_create_collection(COLLECTION_NAME)


def add_chunks(collection: Any, chunks: list[dict[str, Any]]) -> None:
    """Embed and add chunks with primitive Chroma metadata."""
    if not chunks:
        return
    model = get_embedding_model()
    texts = [chunk["text"] for chunk in chunks]
    embeddings = model.encode(texts, normalize_embeddings=True).tolist()
    collection.add(
        ids=[chunk["chunk_id"] for chunk in chunks],
        documents=texts,
        embeddings=embeddings,
        metadatas=[{"source": str(c["source"]), "page": int(c["page"])} for c in chunks],
    )


def collection_count(collection: Any) -> int:
    """Return the number of stored chunks."""
    return int(collection.count())
