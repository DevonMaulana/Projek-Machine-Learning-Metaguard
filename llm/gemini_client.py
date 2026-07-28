"""Gemini client for structured MetaGuard analysis."""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field


class EvidenceReference(BaseModel):
    """Reference to one retrieved policy chunk."""

    chunk_id: str
    source: str
    page: int
    relevance: str


class PriorityAction(BaseModel):
    """One suggested improvement action."""

    priority: str
    action: str
    reason: str


class GeminiAnalysis(BaseModel):
    """Structured output returned by Gemini."""

    summary: str
    metadata_assessment: list[str] = Field(default_factory=list)
    data_quality_assessment: list[str] = Field(default_factory=list)
    priority_actions: list[PriorityAction] = Field(default_factory=list)
    evidence_references: list[EvidenceReference] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _build_analysis_payload(
    profile: dict[str, Any],
    findings: list[dict[str, Any]],
    metadata: dict[str, Any],
    metadata_validation: dict[str, Any],
    policy_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a compact JSON-safe payload for Gemini."""
    return {
        "profile": {
            "row_count": profile.get("row_count"),
            "column_count": profile.get("column_count"),
            "duplicate_rows": profile.get("duplicate_rows"),
            "fully_empty_columns": profile.get("fully_empty_columns", []),
        },
        "findings": findings,
        "metadata": metadata,
        "metadata_validation": metadata_validation,
        "policy_evidence": policy_evidence,
    }


def analyze_with_gemini(
    profile: dict[str, Any],
    findings: list[dict[str, Any]],
    metadata: dict[str, Any],
    metadata_validation: dict[str, Any],
    policy_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Analyze MetaGuard results using one Gemini API call.

    The function returns a JSON-safe dictionary validated through Pydantic.
    """
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY belum dikonfigurasi.")

    if not model_name:
        raise RuntimeError("GEMINI_MODEL belum dikonfigurasi.")

    if not policy_evidence:
        raise ValueError(
            "Policy evidence belum tersedia. Jalankan retrieval terlebih dahulu."
        )

    payload = _build_analysis_payload(
        profile=profile,
        findings=findings,
        metadata=metadata,
        metadata_validation=metadata_validation,
        policy_evidence=policy_evidence,
    )

    instruction = """
Anda adalah analis kualitas data untuk prototipe MetaGuard.

Tugas:
1. Analisis ringkasan profil dataset, temuan kualitas, metadata,
   validasi metadata, dan evidence kebijakan yang diberikan.
2. Gunakan hanya informasi pada payload.
3. Jangan membuat kesimpulan hukum.
4. Jangan menyatakan dataset patuh atau tidak patuh terhadap regulasi.
5. Setiap referensi kebijakan harus memakai chunk_id, source, dan page
   yang benar-benar tersedia dalam policy_evidence.
6. Bedakan temuan deterministik dari interpretasi.
7. Gunakan Bahasa Indonesia.
8. Berikan tindakan prioritas yang konkret dan singkat.
9. Sebutkan keterbatasan analisis bila evidence tidak cukup.
"""

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model_name,
        contents=(
            instruction
            + "\n\nPAYLOAD METAGUARD:\n"
            + json.dumps(payload, ensure_ascii=False)
        ),
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=GeminiAnalysis,
        ),
    )

    if not response.text:
        raise RuntimeError("Gemini tidak mengembalikan respons.")

    try:
        parsed = GeminiAnalysis.model_validate_json(response.text)
    except ValueError as error:
        raise RuntimeError(
            "Respons Gemini tidak sesuai schema yang diharapkan."
        ) from error

    return parsed.model_dump(mode="json")