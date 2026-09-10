from pathlib import Path

from pypdf import PdfReader

from app.models.document import Document


def extract_metadata(document: Document) -> dict:
    """Dispatches to a format-specific extractor based on file extension.

    Only called after check_extension_allowed has passed, so the extension
    is always one of ALLOWED_EXTENSIONS by the time we get here.
    """
    extension = Path(document.filename).suffix.lower()
    if extension == ".pdf":
        return _extract_pdf_metadata(document.file_path)
    if extension == ".txt":
        return _extract_text_metadata(document.file_path)
    raise ValueError(f"No metadata extractor registered for extension '{extension}'")


def _extract_pdf_metadata(file_path: str) -> dict:
    reader = PdfReader(file_path)
    return {"page_count": len(reader.pages)}


def _extract_text_metadata(file_path: str) -> dict:
    text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    return {"word_count": len(text.split())}
