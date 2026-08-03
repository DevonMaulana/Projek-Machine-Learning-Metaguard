from core.analysis_state import build_analysis_fingerprint, reset_analysis_results


def test_fingerprint_is_deterministic() -> None:
    metadata = {
        "title": "Data Puskesmas",
        "producer_opd": "Dinas Kesehatan",
    }

    first = build_analysis_fingerprint(
        file_name="data.csv",
        file_bytes=b"id,name\n1,A",
        metadata=metadata,
    )
    second = build_analysis_fingerprint(
        file_name="data.csv",
        file_bytes=b"id,name\n1,A",
        metadata=metadata,
    )

    assert first == second


def test_fingerprint_changes_when_file_changes() -> None:
    metadata = {"title": "Data Puskesmas"}

    first = build_analysis_fingerprint(
        file_name="data.csv",
        file_bytes=b"id\n1",
        metadata=metadata,
    )
    second = build_analysis_fingerprint(
        file_name="data.csv",
        file_bytes=b"id\n2",
        metadata=metadata,
    )

    assert first != second


def test_fingerprint_changes_when_metadata_changes() -> None:
    first = build_analysis_fingerprint(
        file_name="data.csv",
        file_bytes=b"id\n1",
        metadata={"title": "Data A"},
    )
    second = build_analysis_fingerprint(
        file_name="data.csv",
        file_bytes=b"id\n1",
        metadata={"title": "Data B"},
    )

    assert first != second


def test_metadata_order_does_not_change_fingerprint() -> None:
    first = build_analysis_fingerprint(
        file_name="data.csv",
        file_bytes=b"id\n1",
        metadata={
            "title": "Data",
            "producer_opd": "Dinas",
        },
    )
    second = build_analysis_fingerprint(
        file_name="data.csv",
        file_bytes=b"id\n1",
        metadata={
            "producer_opd": "Dinas",
            "title": "Data",
        },
    )

    assert first == second


def test_metadata_whitespace_is_normalized() -> None:
    first = build_analysis_fingerprint(
        file_name="data.csv",
        file_bytes=b"id\n1",
        metadata={"title": "Data"},
    )
    second = build_analysis_fingerprint(
        file_name="data.csv",
        file_bytes=b"id\n1",
        metadata={"title": "  Data  "},
    )

    assert first == second


def test_parsing_configuration_changes_fingerprint() -> None:
    common = {
        "file_name": "data.csv",
        "file_bytes": b"a,b\n1,2\n",
        "metadata": {"title": "Data"},
    }
    comma = build_analysis_fingerprint(
        **common,
        ingestion_config={"delimiter": ",", "encoding": "utf-8"},
    )
    semicolon = build_analysis_fingerprint(
        **common,
        ingestion_config={"delimiter": ";", "encoding": "utf-8"},
    )
    assert comma != semicolon


def test_fingerprint_only_uses_active_chunk_and_sample_settings() -> None:
    common = {"file_name": "data.csv", "file_bytes": b"id\n1", "metadata": {}}
    exact_one = build_analysis_fingerprint(**common, ingestion_config={"analysis_mode": "exact", "chunk_size": 1, "sample_size": 1, "sample_seed": 1})
    exact_two = build_analysis_fingerprint(**common, ingestion_config={"analysis_mode": "exact", "chunk_size": 99, "sample_size": 99, "sample_seed": 99})
    sampled_one = build_analysis_fingerprint(**common, ingestion_config={"analysis_mode": "sampled", "chunk_size": 1, "sample_size": 10, "sample_seed": 1})
    sampled_two = build_analysis_fingerprint(**common, ingestion_config={"analysis_mode": "sampled", "chunk_size": 99, "sample_size": 10, "sample_seed": 1})
    sampled_other_seed = build_analysis_fingerprint(**common, ingestion_config={"analysis_mode": "sampled", "sample_size": 10, "sample_seed": 2})
    assert exact_one == exact_two
    assert sampled_one == sampled_two
    assert sampled_one != sampled_other_seed


def test_reset_analysis_results_only_clears_derived_outputs() -> None:
    state = {"policy_evidence": [{"query": "x"}], "gemini_analysis": {"summary": "x"}, "evidence_review": {"status": "valid"}, "report_payload": {"schema_version": "1.0"}, "other": "keep"}
    assert reset_analysis_results(state) is True
    assert state["policy_evidence"] == []
    assert state["gemini_analysis"] == {}
    assert state["evidence_review"] == {}
    assert state["report_payload"] == {}
    assert state["other"] == "keep"
