from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import CourseCreate, CourseOut, CourseType, EducationStage, ErrorResponse
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
    session: AsyncSession = Depends(get_db),
    q: Annotated[str | None, Query(max_length=100)] = None,
    education_stage: Annotated[EducationStage | None, Query()] = None,
    course_type: Annotated[CourseType | None, Query()] = None,
) -> list[CourseOut]:
    courses = await CourseService.list(session, q, education_stage, course_type)
    return [CourseOut.model_validate(course) for course in courses]
