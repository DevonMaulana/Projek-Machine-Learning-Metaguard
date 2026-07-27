import pytest

from rag.chunker import chunk_documents, is_meaningful_chunk


def test_short_document_preserves_metadata():
    chunks = chunk_documents([{"source": "a.pdf", "page": 1, "text": "abc"}], chunk_size=5, chunk_overlap=1)
    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == "a.pdf-p1-c1"
    assert chunks[0]["source"] == "a.pdf"


def test_long_document_overlap_and_unique_ids():
    text = "alpha beta gamma delta epsilon zeta eta theta"
    chunks = chunk_documents([{"source": "a.txt", "page": 1, "text": text}], chunk_size=18, chunk_overlap=5)
    assert len(chunks) > 1
    assert all(not chunk["text"].startswith(" ") and not chunk["text"].endswith(" ") for chunk in chunks)
    assert all(" " not in chunk["text"][:1] for chunk in chunks)
    assert len({chunk["chunk_id"] for chunk in chunks}) == len(chunks)
    assert all(chunk["text"] for chunk in chunks)


def test_invalid_overlap_rejected():
    with pytest.raises(ValueError):
        chunk_documents([], chunk_size=5, chunk_overlap=5)


def test_words_are_not_split_and_source_information_is_preserved():
    text = "Dataset menjelaskan rentang waktu yang dicakup oleh dataset dan wilayah pengamatan."
    chunks = chunk_documents([{"source": "policy.txt", "page": 2, "text": text}], chunk_size=35, chunk_overlap=8)
    assert all(chunk["text"] == chunk["text"].strip() for chunk in chunks)
    assert all(chunk["text"].split()[0] != "askan" for chunk in chunks[1:])
    assert len({chunk["chunk_id"] for chunk in chunks}) == len(chunks)
    assert all(chunk["source"] == "policy.txt" and chunk["page"] == 2 for chunk in chunks)
    combined = " ".join(chunk["text"] for chunk in chunks)
    for phrase in ("menjelaskan", "rentang waktu", "wilayah pengamatan"):
        assert phrase in combined


def test_short_paragraphs_are_combined_and_uninformative_chunks_rejected():
    paragraphs = ["Ini adalah paragraf kebijakan yang cukup informatif untuk retrieval lokal." * 2,
                  "Ketentuan ini menjelaskan tugas produsen data dan walidata secara ringkas." * 2]
    chunks = chunk_documents([{"source": "policy.txt", "page": 1, "text": "\n\n".join(paragraphs)}], chunk_size=400)
    assert len(chunks) == 1
    assert all(len(chunk["text"]) >= 150 for chunk in chunks)
    assert not is_meaningful_chunk("  12  ")
    assert not is_meaningful_chunk("*** --- ___")
