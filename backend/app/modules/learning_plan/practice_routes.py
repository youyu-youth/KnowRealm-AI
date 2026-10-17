"""计划项练习准备 HTTP 入口。"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning_plan import practice
from app.modules.learning_plan.practice_schemas import (
    PracticePreparationOut,
    PracticePrepareRequest,
    PracticeRequirementsOut,
    PracticeRequirementsUpdate,
    PracticeStateOut,
)
from app.shared.deps import get_db, require_launch_token

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
