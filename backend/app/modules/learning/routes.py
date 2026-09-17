"""learning 域 HTTP 路由：课程 Mastery 只读查询（无写入口）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning.schemas import CourseMasteryOut, CourseMasteryQuery
from app.modules.learning.service import MasteryService
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/courses",
    tags=["mastery"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("/{course_id}/mastery", response_model=CourseMasteryOut)
async def get_course_mastery(
    course_id: str,
    filters: Annotated[CourseMasteryQuery, Query()],
    session: AsyncSession = Depends(get_db),
) -> CourseMasteryOut:
    return await MasteryService.list_course_mastery(session, course_id, filters.status)
