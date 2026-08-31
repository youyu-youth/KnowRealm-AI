from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.quiz_test import (
    QuizTestAnswerRequest,
    QuizTestConflictOut,
    QuizTestCreateOut,
    QuizTestCreateRequest,
    QuizTestDetailOut,
    QuizTestListOut,
    QuizTestSummaryOut,
)
from app.services.quiz_test_service import QuizTestBlocked, QuizTestService

router = APIRouter(
    prefix="/api",
    tags=["quiz-tests"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.post(
    "/courses/{course_id}/quiz-tests",
    response_model=QuizTestCreateOut,
    status_code=201,
    responses={409: {"model": QuizTestConflictOut | ErrorResponse}},
)
async def create_quiz_test(
    course_id: UUID,
    body: QuizTestCreateRequest,
    session: AsyncSession = Depends(get_db),
) -> QuizTestCreateOut | JSONResponse:
    try:
        return await QuizTestService.create(session, str(course_id), body)
    except QuizTestBlocked as error:
        conflict = QuizTestConflictOut(
            detail=error.detail,
            blocked_reason=error.blocked_reason,
        )
        return JSONResponse(status_code=409, content=conflict.model_dump(mode="json"))


@router.get(
    "/courses/{course_id}/quiz-tests",
    response_model=QuizTestListOut,
)
async def list_quiz_tests(
    course_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> QuizTestListOut:
    return await QuizTestService.list_for_course(session, str(course_id))


@router.get(
    "/quiz-tests/{test_id}",
    response_model=QuizTestDetailOut,
    responses={409: {"model": QuizTestConflictOut}},
)
async def get_quiz_test(
    test_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> QuizTestDetailOut | JSONResponse:
    try:
        result = await QuizTestService.get(session, str(test_id))
    except QuizTestBlocked as error:
        conflict = QuizTestConflictOut(
            detail=error.detail,
            blocked_reason=error.blocked_reason,
        )
        return JSONResponse(status_code=409, content=conflict.model_dump(mode="json"))
    if result is None:
        raise HTTPException(status_code=404, detail="模拟测试不存在")
    return result


@router.post(
    "/quiz-tests/{test_id}/answers",
    response_model=QuizTestDetailOut,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def answer_quiz_test_item(
    test_id: UUID,
    body: QuizTestAnswerRequest,
    session: AsyncSession = Depends(get_db),
) -> QuizTestDetailOut:
    return await QuizTestService.answer_item(session, str(test_id), body)


@router.post(
    "/quiz-tests/{test_id}/submit",
    response_model=QuizTestDetailOut,
    responses={409: {"model": ErrorResponse}},
)
async def submit_quiz_test(
    test_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> QuizTestDetailOut:
    return await QuizTestService.submit(session, request.app.state.data_dir, str(test_id))


@router.post(
    "/quiz-tests/{test_id}/regrade",
    response_model=QuizTestDetailOut,
    responses={409: {"model": ErrorResponse}},
)
async def regrade_quiz_test(
    test_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> QuizTestDetailOut:
    return await QuizTestService.regrade(session, request.app.state.data_dir, str(test_id))


@router.post(
    "/quiz-tests/{test_id}/abandon",
    response_model=QuizTestSummaryOut,
    responses={409: {"model": ErrorResponse}},
)
async def abandon_quiz_test(
    test_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> QuizTestSummaryOut:
    return await QuizTestService.abandon(session, str(test_id))
