"""Load supported policy documents into JSON-safe page records."""

from pathlib import Path
from typing import Any


class DocumentLoadError(ValueError):
    """Raised when a policy document cannot be loaded."""


def load_document(path: str | Path) -> list[dict[str, Any]]:
    """Load one UTF-8 TXT or text-extractable PDF document."""
    file_path = Path(path)
    if not file_path.is_file():
        raise DocumentLoadError(f"Dokumen tidak ditemukan: {file_path}")
    suffix = file_path.suffix.lower()
    if suffix not in {".txt", ".pdf"}:
        raise DocumentLoadError("Format dokumen harus .txt atau .pdf.")
    if suffix == ".txt":
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentLoadError(f"Encoding TXT tidak sesuai UTF-8: {file_path}") from exc
        if not text.strip():
            raise DocumentLoadError(f"Dokumen kosong: {file_path}")
        return [{"source": file_path.name, "page": 1, "text": text}]

    from pypdf import PdfReader

    reader = PdfReader(str(file_path))
    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({"source": file_path.name, "page": page_number, "text": text})
    if not pages:
        raise DocumentLoadError(f"PDF tidak memiliki teks yang dapat diekstrak: {file_path}")
    return pages
