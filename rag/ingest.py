"""CLI and library entry point for policy ingestion."""

from pathlib import Path
import re
from typing import Any

from rag.chunker import chunk_documents, is_meaningful_chunk
from rag.document_loader import DocumentLoadError, load_document
from rag.vector_store import DEFAULT_VECTOR_DB, add_chunks, collection_count, get_collection

POLICY_DIR = Path("data/policies")


def ingest_policies(policy_dir: str | Path = POLICY_DIR, vector_db_path: str | Path = DEFAULT_VECTOR_DB) -> dict[str, Any]:
    """Rebuild the local collection from supported policy files."""
    collection = get_collection(vector_db_path, rebuild=True)
    summary: dict[str, Any] = {"files_processed": 0, "pages_loaded": 0, "chunks_generated": 0, "chunks_filtered": 0, "chunks_deduplicated": 0, "chunks_indexed": 0, "chunks_created": 0, "collection_count": 0, "errors": []}
    final_chunks: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    seen_ids: set[str] = set()
    for path in sorted(Path(policy_dir).glob("*")):
        if path.suffix.lower() not in {".txt", ".pdf"}:
            continue
        try:
            documents = load_document(path)
            chunks = chunk_documents(documents)
            summary["chunks_generated"] += len(chunks)
            for chunk in chunks:
                if not is_meaningful_chunk(chunk["text"]):
                    summary["chunks_filtered"] += 1
                    continue
                text_key = re.sub(r"\s+", " ", chunk["text"]).strip().casefold()
                if text_key in seen_text:
                    summary["chunks_deduplicated"] += 1
                    continue
                seen_text.add(text_key)
                item = dict(chunk)
                base_id = str(item["chunk_id"])
                candidate = base_id
                suffix = 2
                while candidate in seen_ids:
                    candidate = f"{base_id}-d{suffix}"
                    suffix += 1
                item["chunk_id"] = candidate
                seen_ids.add(candidate)
                final_chunks.append(item)
            summary["files_processed"] += 1
            summary["pages_loaded"] += len(documents)
        except DocumentLoadError as error:
            summary["errors"].append(str(error))
    add_chunks(collection, final_chunks)
    summary["chunks_indexed"] = len(final_chunks)
    summary["chunks_created"] = summary["chunks_indexed"]
    summary["collection_count"] = collection_count(collection)
    return summary


if __name__ == "__main__":
    print(ingest_policies())
