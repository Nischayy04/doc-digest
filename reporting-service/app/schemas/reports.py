import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.document import DocumentStatus


class StatusCounts(BaseModel):
    UPLOADED: int
    PROCESSING: int
    COMPLETED: int
    FAILED: int


class SummaryReport(BaseModel):
    total_documents: int
    counts_by_status: StatusCounts


class ProcessingStatsReport(BaseModel):
    completed_count: int
    failed_count: int
    # failed / (completed + failed) — documents still in flight (UPLOADED/
    # PROCESSING) don't count against this, since they haven't succeeded
    # or failed yet.
    failure_rate: float
    # None when nothing has finished processing yet. See LEARNING.md Phase 3
    # for why this is an approximation (updated_at - created_at), not an
    # exact "time spent in PROCESSING" measurement.
    average_processing_seconds: float | None


class RecentActivityItem(BaseModel):
    id: uuid.UUID
    filename: str
    status: DocumentStatus
    updated_at: datetime


class RecentActivityReport(BaseModel):
    items: list[RecentActivityItem]
