import sys
import types

from rag.vector_store import COLLECTION_NAME, get_collection


def test_collection_disables_anonymous_telemetry(monkeypatch, tmp_path):
    captured = {}

    class FakeSettings:
        def __init__(self, **kwargs):
            captured["settings"] = kwargs
            self.anonymized_telemetry = kwargs["anonymized_telemetry"]

    class FakeClient:
        def get_or_create_collection(self, name):
            captured["collection"] = name
            return object()

        def delete_collection(self, name):
            captured["deleted"] = name

    chromadb = types.ModuleType("chromadb")
    chromadb.PersistentClient = lambda **kwargs: (captured.update(kwargs) or FakeClient())
    config = types.ModuleType("chromadb.config")
    config.Settings = FakeSettings
    monkeypatch.setitem(sys.modules, "chromadb", chromadb)
    monkeypatch.setitem(sys.modules, "chromadb.config", config)

    get_collection(tmp_path)

    assert captured["path"] == str(tmp_path)
    assert captured["settings"].anonymized_telemetry is False
    assert captured["collection"] == COLLECTION_NAME
