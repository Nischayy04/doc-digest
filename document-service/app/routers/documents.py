import os
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.chat_message import ChatMessage
from app.models.document import Document, DocumentStatus
from app.models.processing_history import ProcessingHistory
from app.schemas.chat_message import AskRequest, ChatMessageRead
from app.schemas.document import DocumentRead
from app.schemas.processing_history import ProcessingHistoryRead
from app.services.chat import ask_question
from app.services.processing import process_document
from app.services.storage import UploadTooLargeError, save_upload_file

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Document:
    try:
        file_path, file_size = save_upload_file(file)
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    document = Document(
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        file_size=file_size,
        file_path=file_path,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    background_tasks.add_task(process_document, document.id)

    return document


@router.get("", response_model=list[DocumentRead])
def list_documents(
    skip: int = 0, limit: int = 50, db: Session = Depends(get_db)
) -> list[Document]:
    return (
        db.query(Document)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(document_id: UUID, db: Session = Depends(get_db)) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/{document_id}/content")
def get_document_content(document_id: UUID, db: Session = Depends(get_db)) -> FileResponse:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not os.path.exists(document.file_path):
        # Shouldn't happen in normal operation, but the DB row and the file
        # on disk are two separate things — worth a clear error instead of
        # FileResponse's raw FileNotFoundError if they ever drift apart.
        raise HTTPException(status_code=404, detail="Stored file is missing from disk")

    return FileResponse(
        path=document.file_path,
        media_type=document.content_type,
        filename=document.filename,
    )


@router.get("/{document_id}/history", response_model=list[ProcessingHistoryRead])
def get_document_history(
    document_id: UUID, db: Session = Depends(get_db)
) -> list[ProcessingHistory]:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return (
        db.query(ProcessingHistory)
        .filter(ProcessingHistory.document_id == document_id)
        .order_by(ProcessingHistory.created_at)
        .all()
    )


@router.get("/{document_id}/messages", response_model=list[ChatMessageRead])
def get_document_messages(
    document_id: UUID, db: Session = Depends(get_db)
) -> list[ChatMessage]:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return (
        db.query(ChatMessage)
        .filter(ChatMessage.document_id == document_id)
        .order_by(ChatMessage.created_at)
        .all()
    )


@router.post("/{document_id}/ask", response_model=ChatMessageRead)
def ask_document_question(
    document_id: UUID, request: AskRequest, db: Session = Depends(get_db)
) -> ChatMessage:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.status != DocumentStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail="Document must have completed processing before it can be asked about",
        )

    return ask_question(db, document, request.question)
