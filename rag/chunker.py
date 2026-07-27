"""Deterministic paragraph-oriented policy chunking and filtering."""

import re
from typing import Any


def is_meaningful_chunk(text: str, minimum_length: int = 150) -> bool:
    """Return whether text has enough substantive content for retrieval."""
    stripped = text.strip()
    if len(stripped) < minimum_length:
        return False
    if re.fullmatch(r"[\W_\d]+", stripped, flags=re.UNICODE):
        return False
    if re.fullmatch(r"(?:halaman\s*)?\d+", stripped, flags=re.IGNORECASE):
        return False
    words = re.findall(r"\b\w+\b", stripped, flags=re.UNICODE)
    return len(words) >= 12


def _safe_end(text: str, start: int, target: int) -> int:
    boundaries = [match.end() + start for match in re.finditer(r"(?:[.!?](?=\s|$)|\s+)", text[start:target])]
    return max(boundaries) if boundaries else target


def _make_chunk(document: dict[str, Any], content: str, number: int) -> dict[str, Any]:
    return {"chunk_id": f"{document['source']}-p{document['page']}-c{number}", "source": str(document["source"]), "page": int(document["page"]), "text": content.strip()}


def chunk_documents(documents: list[dict[str, Any]], *, chunk_size: int = 800, chunk_overlap: int = 120, minimum_length: int = 150) -> list[dict[str, Any]]:
    """Combine paragraphs near the target size without cutting words."""
    if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_size harus positif dan chunk_overlap harus lebih kecil.")
    result: list[dict[str, Any]] = []
    for document in documents:
        paragraphs = [part.strip() for part in str(document["text"]).split("\n\n") if part.strip()]
        blocks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}" if current else paragraph
            if current and len(candidate) > chunk_size:
                blocks.append(current)
                current = paragraph
            else:
                current = candidate
        if current:
            blocks.append(current)
        merged: list[str] = []
        for block in blocks:
            if merged and len(block) < minimum_length and len(merged[-1]) + 2 + len(block) <= chunk_size * 1.35:
                merged[-1] = f"{merged[-1]}\n\n{block}"
            else:
                merged.append(block)
        for number, block in enumerate(merged, start=1):
            if len(block) > chunk_size:
                start = 0
                while start < len(block):
                    end = min(start + chunk_size, len(block))
                    end = _safe_end(block, start, end)
                    text = block[start:end].strip()
                    if text:
                        result.append(_make_chunk(document, text, number))
                        number += 1
                    if end == len(block):
                        break
                    start = max(start + 1, end - chunk_overlap)
            elif block.strip():
                result.append(_make_chunk(document, block, number))
    return result
