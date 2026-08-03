from core.analysis_state import build_analysis_fingerprint


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
