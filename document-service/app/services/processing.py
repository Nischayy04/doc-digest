import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.processing_history import ProcessingHistory
from app.services.checks import CHECKS
from app.services.extraction import extract_metadata, extract_text
from app.services.summarization import generate_summary

logger = logging.getLogger(__name__)


def _transition(db: Session, document: Document, to_status: DocumentStatus, message: str) -> None:
    from_status = document.status
    db.add(
        ProcessingHistory(
            document_id=document.id,
            from_status=from_status,
            to_status=to_status,
            message=message,
        )
    )
    document.status = to_status
    db.add(document)
    db.commit()
    logger.info(
        "Document %s: %s -> %s (%s)",
        document.id,
        from_status.value,
        to_status.value,
        message,
    )


def process_document(document_id: UUID) -> None:
    """The UPLOADED -> PROCESSING -> COMPLETED/FAILED pipeline.

    Runs as a FastAPI BackgroundTask, which executes after the upload
    request's response has been sent — the request's own DB session is
    already closed by then, so this opens a session of its own.
    """
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.warning("process_document called for missing document %s", document_id)
            return

        _transition(db, document, DocumentStatus.PROCESSING, "Processing started")

        for check in CHECKS:
            result = check(document)
            if not result.passed:
                _transition(db, document, DocumentStatus.FAILED, result.message)
                return

        try:
            metadata = extract_metadata(document)
        except Exception as exc:
            logger.warning("Metadata extraction failed for document %s", document_id, exc_info=exc)
            _transition(db, document, DocumentStatus.FAILED, f"Metadata extraction failed: {exc}")
            return

        document.extracted_metadata = metadata

        # Summarization is a best-effort enhancement layered on top of the
        # core pipeline, not a workflow gate like the checks/extraction
        # above — if Ollama is down, slow, or errors, the document should
        # still complete normally rather than fail the whole upload.
        try:
            document.summary = generate_summary(extract_text(document))
        except Exception as exc:
            logger.warning("Summarization failed for document %s", document_id, exc_info=exc)
            document.summary = None

        _transition(db, document, DocumentStatus.COMPLETED, "Processing completed")
    finally:
        db.close()
