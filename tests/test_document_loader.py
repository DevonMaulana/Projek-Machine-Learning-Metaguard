from pathlib import Path

import pytest

from rag.document_loader import DocumentLoadError, load_document, normalize_extracted_text


def test_normalize_extracted_text_joins_lines_and_keeps_paragraphs():
    text = "BAB I\nKetentuan umum\n\nPasal 1\nData  yang  tersedia."
    normalized = normalize_extracted_text(text)
    assert normalized == "BAB I Ketentuan umum\n\nPasal 1 Data yang tersedia."


def test_load_txt(tmp_path: Path):
    path = tmp_path / "guide.txt"
    path.write_text("Panduan publikasi dataset.", encoding="utf-8")
    assert load_document(path) == [{"source": "guide.txt", "page": 1, "text": "Panduan publikasi dataset."}]


def test_empty_and_unsupported_documents(tmp_path: Path):
    empty = tmp_path / "empty.txt"
    empty.write_text("  ", encoding="utf-8")
    with pytest.raises(DocumentLoadError, match="kosong"):
        load_document(empty)
    other = tmp_path / "guide.docx"
    other.write_bytes(b"x")
    with pytest.raises(DocumentLoadError, match="Format"):
        load_document(other)
