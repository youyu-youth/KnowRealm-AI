from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.library.shared_refs import REQUEST_COURSE_ID
from app.modules.quiz.schemas import (
    QuizConceptUpdateRequest,
    QuizConflictResponse,
    QuizGenerateRequest,
    QuizJobAccepted,
    QuizObjectiveAnswerRequest,
    QuizOut,
    QuizReadOut,
    QuizSelfAssessmentRequest,
    QuizShortAnswerRequest,
)
from app.modules.quiz.service import QuizAdoptionBlocked, QuizService
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

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
    course_id: REQUEST_COURSE_ID = None,
) -> QuizJobAccepted:
    job_id = await QuizService.submit(
        session,
        request.app.state.data_dir,
        str(record_id),
        body,
        request_course_id=None if course_id is None else str(course_id),
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


@router.put(
    "/{record_id}/quizzes/{quiz_id}/concept",
    response_model=QuizOut,
    responses={404: {"model": ErrorResponse}},
)
async def set_quiz_concept(
    record_id: UUID,
    quiz_id: UUID,
    body: QuizConceptUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> QuizOut:
    result = await QuizService.set_concept(
        session,
        str(record_id),
        str(quiz_id),
        body,
    )
    await request.app.state.record_notifier.notify(str(record_id))
    return result


@router.post(
    "/{record_id}/quizzes/{quiz_id}/answers",
    response_model=QuizOut,
)
async def answer_quiz(
    record_id: UUID,
    quiz_id: UUID,
    body: QuizObjectiveAnswerRequest | QuizShortAnswerRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> QuizOut:
    if isinstance(body, QuizShortAnswerRequest):
        result, changed = await QuizService.answer_short(
            session,
            str(record_id),
            str(quiz_id),
            body,
        )
    else:
        result, changed = await QuizService.answer_objective(
            session,
            str(record_id),
            str(quiz_id),
            body,
        )
    if changed:
        await request.app.state.record_notifier.notify(str(record_id))
    return result


@router.post(
    "/{record_id}/quizzes/{quiz_id}/self-assessments",
    response_model=QuizOut,
)
async def self_assess_short_quiz(
    record_id: UUID,
    quiz_id: UUID,
    body: QuizSelfAssessmentRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> QuizOut:
    result, changed = await QuizService.self_assess_short(
        session,
        str(record_id),
        str(quiz_id),
        body,
    )
    if changed:
        await request.app.state.record_notifier.notify(str(record_id))
    return result
