import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Enum, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DocumentStatus(str, enum.Enum):
    """The full workflow vocabulary, defined upfront.

    Only UPLOADED is set by anything in Phase 1 — PROCESSING/COMPLETED/FAILED
    are used starting Phase 2. They're declared together because Postgres
    ALTER TYPE ... ADD VALUE on an existing enum is awkward (can't run inside
    the same transaction as other schema changes), so it's simpler to fix the
    full set of states in the first migration than to add to it later.
    """

    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# Defined once and reused across every column that needs it (Document.status,
# ProcessingHistory.from_status/to_status). Postgres represents this as one
# named ENUM type in the database — reusing the same SQLAlchemy Enum object
# is what tells SQLAlchemy/Alembic "this is the same type", so it's created
# once instead of erroring on a duplicate CREATE TYPE.
document_status_enum = Enum(DocumentStatus, name="document_status")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        document_status_enum,
        nullable=False,
        default=DocumentStatus.UPLOADED,
    )
    extracted_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
