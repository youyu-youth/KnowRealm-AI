from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.quiz import QuizGenerateRequest, QuizJobAccepted, QuizReadOut
from app.services.quiz_service import QuizService

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
    session: AsyncSession = Depends(get_db),
) -> QuizReadOut:
    return await QuizService.read(session, request.app.state.data_dir, str(record_id))


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
