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
