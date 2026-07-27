"""Deterministic character-based policy chunking."""

from typing import Any


def chunk_documents(
    documents: list[dict[str, Any]], *, chunk_size: int = 800, chunk_overlap: int = 120
) -> list[dict[str, Any]]:
    """Split page records into non-empty overlapping chunks."""
    if chunk_size <= 0:
        raise ValueError("chunk_size harus lebih besar dari nol.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap harus >= 0 dan lebih kecil dari chunk_size.")
    chunks = []
    for document in documents:
        text = str(document["text"])
        start = 0
        chunk_number = 1
        while start < len(text):
            end = min(start + chunk_size, len(text))
            content = text[start:end].strip()
            if content:
                chunks.append({
                    "chunk_id": f"{document['source']}-p{document['page']}-c{chunk_number}",
                    "source": str(document["source"]),
                    "page": int(document["page"]),
                    "text": content,
                })
                chunk_number += 1
            if end == len(text):
                break
            start = end - chunk_overlap
    return chunks
