"""Deterministic, boundary-aware policy chunking."""

import re
from typing import Any


def _boundary_positions(text: str, start: int, end: int) -> list[int]:
    """Return positions after paragraph, sentence, and whitespace boundaries."""
    positions: list[int] = []
    for match in re.finditer(r"\n\s*\n", text[start:end]):
        positions.append(start + match.end())
    for match in re.finditer(r"[.!?](?=\s|$)", text[start:end]):
        positions.append(start + match.end())
    for match in re.finditer(r"\s+", text[start:end]):
        positions.append(start + match.end())
    return sorted(set(position for position in positions if start < position <= end))


def _choose_end(text: str, start: int, target: int) -> int:
    """Choose the best available boundary without exceeding the target."""
    boundaries = _boundary_positions(text, start, target)
    return max(boundaries) if boundaries else target


def _choose_start(text: str, lower: int, upper: int, target: int) -> int:
    """Move an overlap start to the nearest safe boundary."""
    boundaries = _boundary_positions(text, lower, upper)
    if not boundaries:
        return target
    return min(boundaries, key=lambda position: (abs(position - target), position))


def chunk_documents(
    documents: list[dict[str, Any]], *, chunk_size: int = 800, chunk_overlap: int = 120
) -> list[dict[str, Any]]:
    """Split page records into non-empty chunks aligned to readable boundaries.

    The requested size and overlap are targets. Paragraph, sentence, and
    whitespace boundaries are preferred; a hard character boundary is used
    only when no safe boundary exists.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size harus lebih besar dari nol.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap harus >= 0 dan lebih kecil dari chunk_size.")
    chunks: list[dict[str, Any]] = []
    for document in documents:
        text = str(document["text"])
        start = 0
        chunk_number = 1
        while start < len(text):
            target_end = min(start + chunk_size, len(text))
            end = _choose_end(text, start, target_end)
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
            previous_start = start
            overlap_start = max(start, end - chunk_overlap)
            start = _choose_start(text, overlap_start, end, overlap_start)
            if start <= previous_start:
                start = overlap_start
    return chunks
