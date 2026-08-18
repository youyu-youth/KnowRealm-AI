from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import CourseCreate, CourseListQuery, CourseOut, ErrorResponse
from app.services.course_service import CourseService

router = APIRouter(
    prefix="/api/courses",
    tags=["courses"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
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
