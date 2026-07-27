import pytest

from rag.chunker import chunk_documents


def test_short_document_preserves_metadata():
    chunks = chunk_documents([{"source": "a.pdf", "page": 1, "text": "abc"}], chunk_size=5, chunk_overlap=1)
    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == "a.pdf-p1-c1"
    assert chunks[0]["source"] == "a.pdf"


def test_long_document_overlap_and_unique_ids():
    chunks = chunk_documents([{"source": "a.txt", "page": 1, "text": "abcdefghij"}], chunk_size=5, chunk_overlap=2)
    assert [chunk["text"] for chunk in chunks] == ["abcde", "defgh", "ghij"]
    assert len({chunk["chunk_id"] for chunk in chunks}) == len(chunks)
    assert all(chunk["text"] for chunk in chunks)


def test_invalid_overlap_rejected():
    with pytest.raises(ValueError):
        chunk_documents([], chunk_size=5, chunk_overlap=5)

