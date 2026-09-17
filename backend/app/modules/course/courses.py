from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.course.schemas import (
    CourseCreate,
    CourseDetailOut,
    CourseListQuery,
    CourseOut,
    CourseUpdate,
)
from app.modules.course.service import CourseService
from app.modules.learning.service import MasteryService
from app.shared.deps import get_db, require_launch_token
from app.shared.errors import CodedHTTPException
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/courses",
    tags=["courses"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.post("", response_model=CourseOut, status_code=201)
async def create_course(
    payload: CourseCreate,
    session: AsyncSession = Depends(get_db),
) -> CourseOut:
    course = await CourseService.create(session, payload)
    return CourseOut.model_validate(course)


@router.get("", response_model=list[CourseOut])
async def list_courses(
    filters: Annotated[CourseListQuery, Query()],
    session: AsyncSession = Depends(get_db),
) -> list[CourseOut]:
    courses = await CourseService.list(
        session,
        filters.q,
        filters.education_stage,
        filters.course_type,
    )
    return [CourseOut.model_validate(course) for course in courses]


@router.get("/{course_id}", response_model=CourseDetailOut)
async def get_course(
    course_id: str,
    session: AsyncSession = Depends(get_db),
) -> CourseDetailOut:
    course = await CourseService.get(session, course_id)
    if course is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    return CourseDetailOut.model_validate(course)


@router.patch("/{course_id}", response_model=CourseOut)
async def update_course(
    course_id: str,
    payload: CourseUpdate,
    session: AsyncSession = Depends(get_db),
) -> CourseOut:
    course = await CourseService.update(session, course_id, payload)
    if course is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    return CourseOut.model_validate(course)


@router.delete("/{course_id}", status_code=204, response_class=Response, response_model=None)
async def delete_course(
    course_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    affected_concepts = await CourseService.soft_delete(session, course_id)
    if affected_concepts is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    # 删除事务已提交；重算失败只记日志，不回滚删除。
    await MasteryService.recompute_concepts(request.app.state.session_factory, affected_concepts)
    return Response(status_code=204)
