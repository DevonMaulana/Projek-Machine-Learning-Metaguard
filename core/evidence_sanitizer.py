"""JSON-safe, bounded evidence values for MetaGuard findings."""

from __future__ import annotations

import math
from typing import Any, Iterable

MAX_EVIDENCE_ITEMS = 5
MAX_EVIDENCE_STRING_LENGTH = 300
TRUNCATION_MARKER = "...[dipotong]"


def _json_safe_value(value: Any) -> Any:
    """Convert one evidence scalar to a JSON-safe native value."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return str(value) if math.isnan(value) or math.isinf(value) else value
    if hasattr(value, "item"):
        try:
            return _json_safe_value(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)


def sanitize_evidence(evidence: Iterable[Any]) -> list[Any]:
    """Return at most five JSON-safe evidence values with bounded strings."""
    sanitized: list[Any] = []
    for value in evidence:
        if len(sanitized) >= MAX_EVIDENCE_ITEMS:
            break
        safe_value = _json_safe_value(value)
        if isinstance(safe_value, str) and len(safe_value) > MAX_EVIDENCE_STRING_LENGTH:
            safe_value = safe_value[:MAX_EVIDENCE_STRING_LENGTH] + TRUNCATION_MARKER
        sanitized.append(safe_value)
    return sanitized


def sanitize_policy_evidence_for_gemini(
    policy_evidence: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Bound Gemini-facing evidence while preserving citation identity metadata."""
    bounded: list[dict[str, Any]] = []
    for item in policy_evidence:
        if not isinstance(item, dict) or len(bounded) >= MAX_EVIDENCE_ITEMS:
            continue
        text = _json_safe_value(item.get("text", ""))
        if isinstance(text, str) and len(text) > MAX_EVIDENCE_STRING_LENGTH:
            text = text[:MAX_EVIDENCE_STRING_LENGTH] + TRUNCATION_MARKER
        clean = {
            "chunk_id": str(item.get("chunk_id", "")).strip(),
            "source": str(item.get("source", "")).strip(),
            "page": _json_safe_value(item.get("page")),
            "text": text,
        }
        for key in ("policy_id", "policy_pack", "domain_id", "document_type"):
            if key in item:
                clean[key] = str(item.get(key, "")).strip()
        bounded.append(clean)
    return bounded
