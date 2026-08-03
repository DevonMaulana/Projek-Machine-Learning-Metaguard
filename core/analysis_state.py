"""Deterministic fingerprints for MetaGuard analysis state."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def build_analysis_fingerprint(
    file_name: str,
    file_bytes: bytes,
    metadata: dict[str, Any],
    ingestion_config: dict[str, Any] | None = None,
) -> str:
    """Build a deterministic fingerprint from CSV content and metadata."""
    normalized_metadata = {
        str(key): str(value).strip()
        for key, value in sorted(metadata.items())
    }

    payload = {
        "file_name": file_name,
        "file_sha256": hashlib.sha256(file_bytes).hexdigest(),
        "metadata": normalized_metadata,
        "ingestion_config": ingestion_config or {},
    }

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()
