from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.quiz import (
    QuizConflictResponse,
    QuizGenerateRequest,
    QuizJobAccepted,
    QuizReadOut,
)
from app.services.quiz_service import QuizAdoptionBlocked, QuizService

router = APIRouter(
    prefix="/api/records",
    tags=["quizzes"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("/{record_id}/quizzes", response_model=QuizReadOut)
async def get_quizzes(
    record_id: UUID,
    request: Request,
    include: Literal["superseded"] | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> QuizReadOut:
    return await QuizService.read(
        session,
        request.app.state.data_dir,
        str(record_id),
        include_superseded=include == "superseded",
    )


@router.post(
    "/{record_id}/quiz-jobs",
    response_model=QuizJobAccepted,
    status_code=202,
)
async def submit_quiz_job(
    record_id: UUID,
    body: QuizGenerateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> QuizJobAccepted:
    job_id = await QuizService.submit(
        session,
        request.app.state.data_dir,
        str(record_id),
        body,
    )
    await request.app.state.record_notifier.notify(str(record_id))
    return QuizJobAccepted(job_id=job_id)


@router.post(
    "/{record_id}/quiz-batches/{batch_id}/discards",
    response_model=QuizReadOut,
)
async def discard_quiz_batch(
    record_id: UUID,
    batch_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> QuizReadOut:
    result = await QuizService.discard(
        session,
        request.app.state.data_dir,
        str(record_id),
        str(batch_id),
    )
    await request.app.state.record_notifier.notify(str(record_id))
    return result


@router.post(
    "/{record_id}/quiz-batches/{batch_id}/confirmations",
    response_model=QuizReadOut,
    responses={409: {"model": QuizConflictResponse}},
)
async def adopt_quiz_batch(
    record_id: UUID,
    batch_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> QuizReadOut | JSONResponse:
    try:
        result = await QuizService.adopt(
            session,
            request.app.state.data_dir,
            str(record_id),
            str(batch_id),
        )
    except QuizAdoptionBlocked as error:
        body = QuizConflictResponse(
            detail=error.detail,
            blocked_reason=error.blocked_reason,
        )
        return JSONResponse(status_code=409, content=body.model_dump(mode="json"))
    await request.app.state.record_notifier.notify(str(record_id))
    return result
