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
    ingestion: dict[str, Any] | None = None,
    analysis_context: dict[str, Any] | None = None,
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
        "ingestion": {
            "mode": (ingestion or {}).get("mode", "exact"),
            "analysis_scope": (ingestion or {}).get("analysis_scope", "full"),
            "total_rows": (ingestion or {}).get("total_rows"),
            "rows_loaded": (ingestion or {}).get("rows_loaded"),
            "sampled_rows": (ingestion or {}).get("sampled_rows", 0),
            "sample_size_requested": (ingestion or {}).get("sample_size_requested"),
            "sample_seed": (ingestion or {}).get("sample_seed"),
            "sampling_method": (ingestion or {}).get("sampling_method"),
            "sampling_applied": (ingestion or {}).get("sampling_applied", False),
            "warnings": (ingestion or {}).get("warnings", []),
        },
        "analysis_context": analysis_context or {},
    }


def analyze_with_gemini(
    profile: dict[str, Any],
    findings: list[dict[str, Any]],
    metadata: dict[str, Any],
    metadata_validation: dict[str, Any],
    policy_evidence: list[dict[str, Any]],
    ingestion: dict[str, Any] | None = None,
    analysis_context: dict[str, Any] | None = None,
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
        ingestion=ingestion,
        analysis_context=analysis_context,
    )

    sampling_instruction = ""
    if payload["ingestion"]["analysis_scope"] == "sampled":
        sampling_instruction = """
10. Hasil memakai sampled analysis: temuan dan profil hanya mewakili baris
    yang dianalisis, bukan seluruh dataset. Jangan menggeneralisasi angka
    temuan sebagai hasil exact seluruh dataset; bedakan total_rows dan
    rows_loaded, serta sebutkan keterbatasan sampling pada summary atau
    limitations.
"""

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
11. Untuk check_id "duplicate_identifier", count adalah jumlah baris yang
    terlibat dalam duplikasi, bukan selalu jumlah identifier unik. Evidence
    hanya contoh yang mungkin dibatasi; jangan menganggapnya daftar lengkap.
12. Untuk check_id "numeric_outlier", ini adalah Temuan Deterministik:
    sistem mendeteksi nilai di luar batas IQR. Jangan menyatakan nilainya pasti
    salah atau melabelinya Temuan Interpretatif; validitasnya perlu verifikasi
    manusia dan sumber data.
13. Jangan mengubah count atau percentage, membuat temuan baru, menyebut kolom
    atau evidence yang tidak ada pada payload, atau memberikan keputusan maupun
    kesimpulan kepatuhan hukum.
14. Temuan deterministik pada payload bersifat authoritative. Evidence hanya
    konteks kebijakan pendukung; kecukupan evidence bukan bukti kepatuhan.
15. Cite hanya chunk_id, source, dan page yang tersedia pada policy_evidence.
""" + sampling_instruction

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
