"""CLI and library entry point for policy ingestion."""

from pathlib import Path
from typing import Any

from rag.chunker import chunk_documents
from rag.document_loader import DocumentLoadError, load_document
from rag.vector_store import DEFAULT_VECTOR_DB, add_chunks, collection_count, get_collection

POLICY_DIR = Path("data/policies")


def ingest_policies(policy_dir: str | Path = POLICY_DIR, vector_db_path: str | Path = DEFAULT_VECTOR_DB) -> dict[str, Any]:
    """Rebuild the local collection from supported policy files."""
    collection = get_collection(vector_db_path, rebuild=True)
    summary: dict[str, Any] = {"files_processed": 0, "pages_loaded": 0, "chunks_created": 0, "collection_count": 0, "errors": []}
    for path in sorted(Path(policy_dir).glob("*")):
        if path.suffix.lower() not in {".txt", ".pdf"}:
            continue
        try:
            documents = load_document(path)
            chunks = chunk_documents(documents)
            add_chunks(collection, chunks)
            summary["files_processed"] += 1
            summary["pages_loaded"] += len(documents)
            summary["chunks_created"] += len(chunks)
        except DocumentLoadError as error:
            summary["errors"].append(str(error))
    summary["collection_count"] = collection_count(collection)
    return summary


if __name__ == "__main__":
    print(ingest_policies())
