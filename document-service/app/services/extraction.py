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


def extract_text(document: Document) -> str:
    """Returns the document's full text content, for use as LLM context
    (summarization, Q&A) — unlike extract_metadata, this isn't stored on the
    document, it's re-read from file_path on demand each time it's needed."""
    extension = Path(document.filename).suffix.lower()
    if extension == ".pdf":
        reader = PdfReader(document.file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if extension == ".txt":
        return Path(document.file_path).read_text(encoding="utf-8", errors="replace")
    raise ValueError(f"No text extractor registered for extension '{extension}'")
