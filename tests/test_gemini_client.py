import json

import pytest

from llm.gemini_client import (
    GeminiAnalysis,
    _build_analysis_payload,
    analyze_with_gemini,
)


def test_build_analysis_payload_is_json_safe() -> None:
    payload = _build_analysis_payload(
        profile={
            "row_count": 10,
            "column_count": 6,
            "duplicate_rows": 1,
            "fully_empty_columns": [],
        },
        findings=[
            {
                "check_id": "duplicate_rows",
                "severity": "medium",
            }
        ],
        metadata={
            "title": "Data Puskesmas",
        },
        metadata_validation={
            "completeness_score": 100,
            "status": "Lengkap",
        },
        policy_evidence=[
            {
                "query": "pemeriksaan kualitas data",
                "results": [
                    {
                        "chunk_id": "policy-p1-c1",
                        "source": "policy.pdf",
                        "page": 1,
                        "text": "Data perlu diperiksa.",
                        "distance": 0.2,
                    }
                ],
            }
        ],
    )

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
    )

    assert "Data Puskesmas" in encoded
    assert payload["profile"]["row_count"] == 10
    assert payload["profile"]["column_count"] == 6
    assert payload["profile"]["duplicate_rows"] == 1


def test_sampled_ingestion_context_is_in_payload() -> None:
    payload = _build_analysis_payload(
        profile={"row_count": 50},
        findings=[],
        metadata={},
        metadata_validation={},
        policy_evidence=[{"query": "metadata", "results": []}],
        ingestion={
            "mode": "sampled",
            "analysis_scope": "sampled",
            "total_rows": 1000,
            "rows_loaded": 50,
            "sampled_rows": 50,
            "sample_size_requested": 50,
            "sample_seed": 42,
            "sampling_method": "reservoir_sampling",
            "sampling_applied": True,
            "warnings": ["Analisis menggunakan sampel deterministik."],
        },
    )
    assert payload["ingestion"]["analysis_scope"] == "sampled"
    assert payload["ingestion"]["total_rows"] == 1000
    assert payload["ingestion"]["rows_loaded"] == 50
    assert payload["ingestion"]["sample_size_requested"] == 50
    assert payload["ingestion"]["sampling_applied"] is True


def test_sampled_prompt_prevents_full_dataset_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return type("Response", (), {"text": '{"summary":"Sampel.","limitations":["Sampel."]}'})()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr("llm.gemini_client.load_dotenv", lambda: False)
    monkeypatch.setattr("llm.gemini_client.genai.Client", FakeClient)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")
    monkeypatch.setenv("GEMINI_MODEL", "dummy-model")

    analyze_with_gemini(
        profile={"row_count": 50}, findings=[], metadata={}, metadata_validation={},
        policy_evidence=[{"query": "metadata", "results": []}],
        ingestion={"mode": "sampled", "analysis_scope": "sampled", "total_rows": 1000, "rows_loaded": 50, "sampled_rows": 50, "sample_size_requested": 50, "sample_seed": 42, "warnings": []},
    )

    content = str(captured["contents"])
    assert "Hasil memakai sampled analysis" in content
    assert '"total_rows": 1000' in content
    assert '"rows_loaded": 50' in content
    assert '"sample_size_requested": 50' in content


def test_prompt_preserves_deterministic_finding_terminology(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return type("Response", (), {"text": '{"summary":"ok"}'})()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr("llm.gemini_client.load_dotenv", lambda: False)
    monkeypatch.setattr("llm.gemini_client.genai.Client", FakeClient)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")
    monkeypatch.setenv("GEMINI_MODEL", "dummy-model")
    analyze_with_gemini({}, [], {}, {}, [{"query": "x", "results": []}])
    content = str(captured["contents"])
    assert "jumlah baris yang" in content
    assert "di luar batas IQR" in content
    assert "Jangan mengubah count atau percentage" in content
    assert "kesimpulan kepatuhan hukum" in content


def test_full_scope_prompt_does_not_require_sampling_limitations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return type("Response", (), {"text": '{"summary":"ok"}'})()

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr("llm.gemini_client.load_dotenv", lambda: False)
    monkeypatch.setattr("llm.gemini_client.genai.Client", FakeClient)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key")
    monkeypatch.setenv("GEMINI_MODEL", "dummy-model")
    analyze_with_gemini(
        {}, [], {}, {}, [{"query": "x", "results": []}],
        ingestion={"mode": "sampled", "analysis_scope": "full", "total_rows": 3, "rows_loaded": 3, "sampled_rows": 3, "sampling_applied": False},
    )
    content = str(captured["contents"])
    assert "Hasil memakai sampled analysis" not in content
    assert "keterbatasan sampling" not in content


def test_gemini_analysis_schema_is_json_safe() -> None:
    result = GeminiAnalysis(
        summary="Dataset memerlukan perbaikan.",
        metadata_assessment=[
            "Metadata telah diisi.",
        ],
        data_quality_assessment=[
            "Terdapat baris duplikat.",
        ],
        priority_actions=[
            {
                "priority": "tinggi",
                "action": "Tinjau baris duplikat.",
                "reason": (
                    "Duplikasi dapat memengaruhi hasil analisis."
                ),
            }
        ],
        evidence_references=[
            {
                "chunk_id": "policy-p1-c1",
                "source": "policy.pdf",
                "page": 1,
                "relevance": (
                    "Evidence membahas pemeriksaan kualitas data."
                ),
            }
        ],
        limitations=[
            "Analisis hanya menggunakan evidence yang diberikan.",
        ],
    )

    output = result.model_dump(
        mode="json",
    )

    encoded = json.dumps(
        output,
        ensure_ascii=False,
    )

    assert "policy.pdf" in encoded
    assert output["summary"] == "Dataset memerlukan perbaikan."
    assert output["priority_actions"][0]["priority"] == "tinggi"


def test_missing_policy_evidence_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm.gemini_client.load_dotenv",
        lambda: False,
    )
    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "dummy-key",
    )
    monkeypatch.setenv(
        "GEMINI_MODEL",
        "dummy-model",
    )

    with pytest.raises(
        ValueError,
        match="Policy evidence belum tersedia",
    ):
        analyze_with_gemini(
            profile={},
            findings=[],
            metadata={},
            metadata_validation={},
            policy_evidence=[],
        )


def test_missing_api_key_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm.gemini_client.load_dotenv",
        lambda: False,
    )
    monkeypatch.delenv(
        "GEMINI_API_KEY",
        raising=False,
    )
    monkeypatch.setenv(
        "GEMINI_MODEL",
        "dummy-model",
    )

    with pytest.raises(
        RuntimeError,
        match="GEMINI_API_KEY",
    ):
        analyze_with_gemini(
            profile={},
            findings=[],
            metadata={},
            metadata_validation={},
            policy_evidence=[
                {
                    "query": "metadata",
                    "results": [],
                }
            ],
        )


def test_missing_model_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "llm.gemini_client.load_dotenv",
        lambda: False,
    )
    monkeypatch.setenv(
        "GEMINI_API_KEY",
        "dummy-key",
    )
    monkeypatch.delenv(
        "GEMINI_MODEL",
        raising=False,
    )

    with pytest.raises(
        RuntimeError,
        match="GEMINI_MODEL",
    ):
        analyze_with_gemini(
            profile={},
            findings=[],
            metadata={},
            metadata_validation={},
            policy_evidence=[
                {
                    "query": "metadata",
                    "results": [],
                }
            ],
        )


def test_api_is_not_called_when_configuration_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_called = False

    class FakeModels:
        def generate_content(self, *args, **kwargs):
            nonlocal api_called
            api_called = True
            raise AssertionError(
                "API tidak boleh dipanggil pada konfigurasi invalid."
            )

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr(
        "llm.gemini_client.load_dotenv",
        lambda: False,
    )
    monkeypatch.setattr(
        "llm.gemini_client.genai.Client",
        FakeClient,
    )
    monkeypatch.delenv(
        "GEMINI_API_KEY",
        raising=False,
    )
    monkeypatch.setenv(
        "GEMINI_MODEL",
        "dummy-model",
    )

    with pytest.raises(
        RuntimeError,
        match="GEMINI_API_KEY",
    ):
        analyze_with_gemini(
            profile={},
            findings=[],
            metadata={},
            metadata_validation={},
            policy_evidence=[
                {
                    "query": "metadata",
                    "results": [],
                }
            ],
        )

    assert api_called is False
