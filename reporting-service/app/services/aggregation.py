from app.clients.document_service import DocumentServiceClient
from app.schemas.document import DocumentStatus, DocumentSummary
from app.schemas.reports import (
    ProcessingStatsReport,
    RecentActivityItem,
    RecentActivityReport,
    StatusCounts,
    SummaryReport,
)

TERMINAL_STATUSES = {DocumentStatus.COMPLETED, DocumentStatus.FAILED}


async def _fetch_documents(client: DocumentServiceClient) -> list[DocumentSummary]:
    raw_documents = await client.fetch_all_documents()
    return [DocumentSummary.model_validate(doc) for doc in raw_documents]


async def build_summary_report(client: DocumentServiceClient) -> SummaryReport:
    documents = await _fetch_documents(client)

    counts = dict.fromkeys(DocumentStatus, 0)
    for document in documents:
        counts[document.status] += 1

    return SummaryReport(
        total_documents=len(documents),
        counts_by_status=StatusCounts(**{status.value: count for status, count in counts.items()}),
    )


async def build_processing_stats_report(client: DocumentServiceClient) -> ProcessingStatsReport:
    documents = await _fetch_documents(client)

    finished = [d for d in documents if d.status in TERMINAL_STATUSES]
    completed = [d for d in finished if d.status == DocumentStatus.COMPLETED]
    failed = [d for d in finished if d.status == DocumentStatus.FAILED]

    average_seconds = None
    if finished:
        durations = [(d.updated_at - d.created_at).total_seconds() for d in finished]
        average_seconds = sum(durations) / len(durations)

    failure_rate = len(failed) / len(finished) if finished else 0.0

    return ProcessingStatsReport(
        completed_count=len(completed),
        failed_count=len(failed),
        failure_rate=failure_rate,
        average_processing_seconds=average_seconds,
    )


async def build_recent_activity_report(
    client: DocumentServiceClient, limit: int
) -> RecentActivityReport:
    documents = await _fetch_documents(client)
    documents.sort(key=lambda d: d.updated_at, reverse=True)

    items = [
        RecentActivityItem(
            id=d.id, filename=d.filename, status=d.status, updated_at=d.updated_at
        )
        for d in documents[:limit]
    ]
    return RecentActivityReport(items=items)
