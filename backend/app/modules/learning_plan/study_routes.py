"""计划项资料学习 HTTP 接缝。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning_plan import study
from app.modules.learning_plan.study_schemas import (
    RecordStudyOut,
    RecordStudyStart,
    RecordStudyTabUpdate,
)
from app.shared.deps import get_db, require_launch_token

router = APIRouter(
    prefix="/api/plan-items", tags=["plan-study"], dependencies=[Depends(require_launch_token)]
)


@router.get("/{item_id}/study", response_model=RecordStudyOut)
async def get_study(
    item_id: UUID,
    q: str = Query(default="", max_length=200),
    session: AsyncSession = Depends(get_db),
) -> RecordStudyOut:
    return await study.state(session, str(item_id), q=q)


@router.post("/{item_id}/study/start", response_model=RecordStudyOut)
async def start_study(
    item_id: UUID, body: RecordStudyStart, session: AsyncSession = Depends(get_db)
) -> RecordStudyOut:
    return await study.start(session, str(item_id), body)


@router.put("/{item_id}/study/tab", response_model=RecordStudyOut)
async def save_study_tab(
    item_id: UUID, body: RecordStudyTabUpdate, session: AsyncSession = Depends(get_db)
) -> RecordStudyOut:
    return await study.save_tab(session, str(item_id), body)
