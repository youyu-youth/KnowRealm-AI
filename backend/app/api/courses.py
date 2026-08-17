from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import CourseCreate, CourseOut
from app.services.course_service import CourseService

router = APIRouter(
    prefix="/api/courses",
    tags=["courses"],
    dependencies=[Depends(require_launch_token)],
)


@router.post("", response_model=CourseOut, status_code=201)
async def create_course(
    payload: CourseCreate,
    session: AsyncSession = Depends(get_db),
) -> CourseOut:
    course = await CourseService.create(session, payload)
    return CourseOut.model_validate(course)


@router.get("", response_model=list[CourseOut])
async def list_courses(session: AsyncSession = Depends(get_db)) -> list[CourseOut]:
    courses = await CourseService.list(session)
    return [CourseOut.model_validate(course) for course in courses]
