from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models.document import ProcessingJob
from app.schemas.document import ProcessingJobStatus


async def cancel_nonterminal_jobs(
    session: AsyncSession,
    record_filter: ColumnElement[bool],
    *,
    now: datetime,
) -> None:
    await session.execute(
        update(ProcessingJob)
        .where(
            record_filter,
            ProcessingJob.status.in_((ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING)),
        )
        .values(
            status=ProcessingJobStatus.CANCELLED,
            next_run_at=None,
            finished_at=now,
            updated_at=now,
        )
    )
