import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.document import DocumentStatus, document_status_enum


class ProcessingHistory(Base):
    """One row per status transition a Document goes through. Append-only —
    nothing here is ever updated or deleted, so it doubles as an audit log
    of the full processing timeline for a document."""

    __tablename__ = "processing_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[DocumentStatus | None] = mapped_column(document_status_enum, nullable=True)
    to_status: Mapped[DocumentStatus] = mapped_column(document_status_enum, nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
