import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class DocumentStatus(str, Enum):
    """A deliberate duplicate of document-service's DocumentStatus, not a
    shared import — the two services don't share Python code, only the
    HTTP contract. If document-service ever adds a new status, this needs
    updating by hand; that's the cost of decoupling, paid on purpose. See
    LEARNING.md Phase 3."""

    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DocumentSummary(BaseModel):
    """reporting-service's own view of a Document — only the fields
    needed for aggregation, parsed out of document-service's API
    responses. Deliberately excludes content_type/file_size/
    extracted_metadata, which document-service returns but no report here
    uses."""

    id: uuid.UUID
    filename: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
