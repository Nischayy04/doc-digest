import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus


class DocumentRead(BaseModel):
    """API-facing shape of a Document. Deliberately separate from the ORM
    model — the DB schema and the public API contract are allowed to
    diverge (e.g. we never expose file_path)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    status: DocumentStatus
    extracted_metadata: dict | None
    summary: str | None
    created_at: datetime
    updated_at: datetime
