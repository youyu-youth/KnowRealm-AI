import asyncio
import json
import shutil
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.modules.jobs import ProcessingJobService
from app.modules.jobs.schemas import RecordJobsOut
from app.schemas.document import (
    TranscriptAvailability,
    TranscriptOut,
    TranscriptReadOut,
    TranscriptUpdateRequest,
)
from app.schemas.record import (
    RecordClassificationRequest,
    RecordOut,
    RecordStatus,
    RecordUpgradeAccepted,
    RecordUpgradeRequest,
)
from app.services.record_classification_service import RecordClassificationService
from app.services.record_service import RecordService
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api",
    tags=["records"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)

STREAMING_RECORD_STATUSES = {
    RecordStatus.CONTENT_PROCESSING,
    RecordStatus.SUMMARY_PROCESSING,
}


@router.get("/inbox", response_model=list[RecordOut])
async def list_inbox_records(
    session: AsyncSession = Depends(get_db),
) -> list[RecordOut]:
    records = await RecordService.list_inbox(session)
    return [RecordOut.model_validate(record) for record in records]


@router.get("/records/{record_id}", response_model=RecordOut)
async def get_record(
    record_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> RecordOut:
    record = await RecordService.get(session, str(record_id))
    if record is None:
        raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
    return RecordOut.model_validate(record)


@router.get("/records/{record_id}/jobs", response_model=RecordJobsOut)
async def get_record_jobs(
    record_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> RecordJobsOut:
    if await RecordService.get(session, str(record_id)) is None:
        raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
    return await ProcessingJobService.list_for_record(session, str(record_id))


@router.get("/records/{record_id}/transcript", response_model=TranscriptReadOut)
async def get_record_transcript(
    record_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> TranscriptReadOut:
    record = await RecordService.get(session, str(record_id))
    if record is None:
        raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
    transcript = await RecordService.get_transcript(session, str(record_id))
    if transcript is None:
        return TranscriptReadOut(status=TranscriptAvailability.NOT_READY, transcript=None)
    return TranscriptReadOut(
        status=TranscriptAvailability.READY,
        transcript=TranscriptOut.model_validate(transcript),
    )


@router.patch("/records/{record_id}/transcript", response_model=TranscriptOut)
async def update_record_transcript(
    record_id: UUID,
    body: TranscriptUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TranscriptOut:
    transcript = await RecordService.update_transcript(session, str(record_id), body)
    await request.app.state.record_notifier.notify(str(record_id))
    return TranscriptOut.model_validate(transcript)


@router.delete(
    "/records/{record_id}",
    status_code=204,
    response_class=Response,
    response_model=None,
)
async def delete_record(
    record_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    if not await RecordService.soft_delete(session, str(record_id)):
        raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
    for cache_dir in (
        Path(request.app.state.data_dir) / "cache" / "audio" / str(record_id),
        Path(request.app.state.data_dir) / "cache" / "sources" / str(record_id),
    ):
        await asyncio.to_thread(shutil.rmtree, cache_dir, ignore_errors=True)
    await request.app.state.record_notifier.notify(str(record_id))
    return Response(status_code=204)


@router.post(
    "/records/{record_id}/classification",
    response_model=RecordOut,
    responses={409: {"model": ErrorResponse}},
)
async def classify_record(
    record_id: UUID,
    body: RecordClassificationRequest,
    session: AsyncSession = Depends(get_db),
) -> RecordOut:
    record = await RecordClassificationService.classify(
        session,
        str(record_id),
        str(body.course_id),
    )
    return RecordOut.model_validate(record)


@router.post(
    "/records/{record_id}/upgrade",
    response_model=RecordUpgradeAccepted,
    responses={409: {"model": ErrorResponse}},
)
async def upgrade_record(
    record_id: UUID,
    body: RecordUpgradeRequest,
    request: Request,
) -> RecordUpgradeAccepted:
    record, summary_job_id = await RecordClassificationService.upgrade(
        request.app.state.session_factory,
        request.app.state.data_dir,
        str(record_id),
        str(body.course_id) if body.course_id is not None else None,
    )
    return RecordUpgradeAccepted(
        record=RecordOut.model_validate(record),
        summary_job_id=summary_job_id,
    )


@router.get("/records/{record_id}/events", response_class=EventSourceResponse)
async def stream_record_events(
    record_id: UUID,
    request: Request,
) -> EventSourceResponse:
    value = str(record_id)
    async with request.app.state.session_factory() as session:
        record = await RecordService.get(session, value)
        if record is None:
            raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
        initially_streaming = record.status in STREAMING_RECORD_STATUSES

    async def still_streaming() -> bool:
        session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
        async with session_factory() as session:
            record = await RecordService.get(session, value)
            return record is not None and record.status in STREAMING_RECORD_STATUSES

    async def events() -> AsyncGenerator[ServerSentEvent]:
        notifier = request.app.state.record_notifier
        version = notifier.version(value)
        yield ServerSentEvent(
            event="invalidate",
            data=json.dumps({"record_id": value}, separators=(",", ":")),
        )
        if not initially_streaming:
            return
        while not await request.is_disconnected():
            try:
                version = await asyncio.wait_for(
                    notifier.wait_for_change(value, version), timeout=15
                )
            except TimeoutError:
                continue
            yield ServerSentEvent(
                event="invalidate",
                data=json.dumps({"record_id": value}, separators=(",", ":")),
            )
            if not await still_streaming():
                return

    return EventSourceResponse(events(), ping=15)


@router.get("/courses/{course_id}/records", response_model=list[RecordOut])
async def list_course_records(
    course_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> list[RecordOut]:
    records = await RecordService.list_for_course(session, str(course_id))
    if records is None:
        raise HTTPException(status_code=404, detail="课程不存在或已删除")
    return [RecordOut.model_validate(record) for record in records]
