import json

import rag.ingest as ingest


class FakeCollection:
    def __init__(self):
        self.count_value = 0


def test_ingestion_filters_and_deduplicates_before_embedding(monkeypatch, tmp_path):
    policy = tmp_path / "policy.txt"
    policy.write_text("fixture", encoding="utf-8")
    collection = FakeCollection()
    embedded = []

    monkeypatch.setattr(ingest, "get_collection", lambda *args, **kwargs: collection)
    monkeypatch.setattr(ingest, "load_document", lambda path: [{"source": path.name, "page": 1, "text": "x"}])
    monkeypatch.setattr(ingest, "chunk_documents", lambda documents: [
        {"chunk_id": "a", "source": "policy.txt", "page": 1, "text": ("Ini adalah isi kebijakan yang menjelaskan data dan metadata untuk publikasi secara jelas dan terstruktur. " * 2)},
        {"chunk_id": "b", "source": "policy.txt", "page": 1, "text": ("Ini  adalah isi kebijakan yang menjelaskan data dan metadata untuk publikasi secara jelas dan terstruktur. " * 2)},
        {"chunk_id": "c", "source": "policy.txt", "page": 1, "text": "pendek"},
    ])
    monkeypatch.setattr(ingest, "add_chunks", lambda target, chunks: (embedded.extend(chunks), setattr(target, "count_value", len(chunks))))
    monkeypatch.setattr(ingest, "collection_count", lambda target: target.count_value)

    summary = ingest.ingest_policies(tmp_path, tmp_path / "db")

    assert len(embedded) == summary["chunks_indexed"] == 1
    assert summary["chunks_generated"] == 3
    assert summary["chunks_filtered"] == 1
    assert summary["chunks_deduplicated"] == 1
    assert summary["collection_count"] == 1
    json.dumps(summary)
