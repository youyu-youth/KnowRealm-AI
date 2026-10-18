"""计划项练习准备 HTTP 入口。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning_plan import practice, practice_round
from app.modules.learning_plan.practice_schemas import (
    PracticeGradingRetry,
    PracticePreparationOut,
    PracticePrepareRequest,
    PracticeRequirementsOut,
    PracticeRequirementsUpdate,
    PracticeRoundOut,
    PracticeRoundStart,
    PracticeStateOut,
)
from app.shared.deps import get_db, require_launch_token
from app.shared.errors import CodedHTTPException

router = APIRouter(
    prefix="/api/plan-items", tags=["plan-practice"], dependencies=[Depends(require_launch_token)]
)


@router.get("/{item_id}/practice", response_model=PracticeStateOut)
async def get_practice(item_id: UUID, session: AsyncSession = Depends(get_db)) -> PracticeStateOut:
    return await practice.state(session, str(item_id))


@router.put("/{item_id}/practice/requirements", response_model=PracticeRequirementsOut)
async def put_requirements(
    item_id: UUID, payload: PracticeRequirementsUpdate, session: AsyncSession = Depends(get_db)
) -> PracticeRequirementsOut:
    async with session.begin():
        return await practice.confirm_requirements(session, str(item_id), payload)


@router.post(
    "/{item_id}/practice/preparations", response_model=PracticePreparationOut, status_code=202
)
async def post_preparation(
    item_id: UUID, payload: PracticePrepareRequest, session: AsyncSession = Depends(get_db)
) -> PracticePreparationOut:
    async with session.begin():
        return await practice.prepare(session, str(item_id), payload, authority="USER_MANUAL")


@router.post(
    "/{item_id}/practice/preparations/{preparation_id}/cancel",
    response_model=PracticePreparationOut,
)
async def cancel_preparation(
    item_id: UUID, preparation_id: UUID, session: AsyncSession = Depends(get_db)
) -> PracticePreparationOut:
    async with session.begin():
        return await practice.cancel(session, str(item_id), str(preparation_id))


@router.post("/{item_id}/practice/rounds", response_model=PracticeRoundOut)
async def post_round(
    item_id: UUID, payload: PracticeRoundStart, session: AsyncSession = Depends(get_db)
) -> PracticeRoundOut:
    """开始或继续一轮计划练习：从 READY 准备结果建卷，已有轮次直接返回。

    并发兜底：部分唯一索引拦截第二个建卷事务时，败方在重查后拿到同一轮。"""
    conflict: CodedHTTPException | None = None
    try:
        async with session.begin():
            return await practice_round.start_round(session, str(item_id), payload)
    except CodedHTTPException as exc:
        if exc.code != "PRACTICE_ROUND_CONFLICT":
            raise
        conflict = exc
    async with session.begin():
        current = await practice_round.latest_round(session, str(item_id))
        if current is None:
            assert conflict is not None
            raise conflict
        return await practice_round.round_out(session, current)


@router.post("/{item_id}/practice/rounds/{test_id}/retries", response_model=PracticeRoundOut)
async def retry_round_grading(
    item_id: UUID,
    test_id: UUID,
    payload: PracticeGradingRetry,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> PracticeRoundOut:
    async with session.begin():
        return await practice_round.retry_grading(
            session, request.app.state.data_dir, str(item_id), str(test_id), payload
        )
