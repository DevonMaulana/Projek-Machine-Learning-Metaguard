"""Load supported policy documents into JSON-safe page records."""

from pathlib import Path
from typing import Any
import re


class DocumentLoadError(ValueError):
    """Raised when a policy document cannot be loaded."""


def normalize_extracted_text(text: str) -> str:
    """Normalize PDF line wrapping while retaining paragraph boundaries."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]*\n[ \t]*\n[ \t]*(?:\n[ \t]*)+", "\n\n", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return "\n\n".join(part.strip() for part in text.split("\n\n") if part.strip())


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
        return [{"source": file_path.name, "page": 1, "text": normalize_extracted_text(text)}]

    from pypdf import PdfReader

    reader = PdfReader(str(file_path))
    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append({"source": file_path.name, "page": page_number, "text": normalize_extracted_text(text)})
    if not pages:
        raise DocumentLoadError(f"PDF tidak memiliki teks yang dapat diekstrak: {file_path}")
    return pages
