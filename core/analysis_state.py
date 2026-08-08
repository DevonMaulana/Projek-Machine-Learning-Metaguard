"""Deterministic fingerprints for MetaGuard analysis state."""

from __future__ import annotations

import hashlib
import json
from typing import Any, MutableMapping


def normalize_ingestion_config(ingestion_config: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only parsing settings that affect the active analysis mode."""
    config = ingestion_config or {}
    mode = str(config.get("analysis_mode", config.get("mode", "exact")))
    normalized = {
        "encoding": config.get("encoding"),
        "delimiter": config.get("delimiter"),
        "quote_character": config.get("quote_character"),
        "parsing_mode": config.get("parsing_mode"),
        "header_row": config.get("header_row"),
        "missing_value_tokens": list(config.get("missing_value_tokens", [])),
        "analysis_mode": mode,
    }
    if mode == "chunked":
        normalized["chunk_size"] = config.get("chunk_size")
    elif mode == "sampled":
        normalized["sample_size"] = config.get("sample_size")
        normalized["sample_seed"] = config.get("sample_seed")
    return normalized


def reset_analysis_results(session_state: MutableMapping[str, Any]) -> bool:
    """Clear results derived from a CSV or parsing configuration."""
    keys = (
        "policy_evidence",
        "policy_evidence_retrieval_completed",
        "evidence_sufficiency",
        "retrieval_attempts",
        "gemini_analysis",
        "evidence_review",
        "report_payload",
        "metadata_validation_completed",
        "contextual_validation_completed",
        "contextual_validation",
        "agent_state",
        "agent_decision",
        "agent_audit",
    )
    had_results = any(bool(session_state.get(key)) for key in keys)
    session_state["policy_evidence"] = []
    session_state["policy_evidence_retrieval_completed"] = False
    session_state["evidence_sufficiency"] = {}
    session_state["retrieval_attempts"] = []
    session_state["gemini_analysis"] = {}
    session_state["evidence_review"] = {}
    session_state["report_payload"] = {}
    session_state["metadata_validation_completed"] = False
    session_state["contextual_validation_completed"] = False
    session_state["contextual_validation"] = {}
    session_state["agent_state"] = None
    session_state["agent_decision"] = None
    session_state["agent_audit"] = []
    return had_results


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
        "ingestion_config": normalize_ingestion_config(ingestion_config),
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
