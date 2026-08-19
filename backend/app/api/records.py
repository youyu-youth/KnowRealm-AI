from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.record import RecordOut
from app.services.record_service import RecordService

router = APIRouter(
    prefix="/api",
    tags=["records"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("/courses/{course_id}/records", response_model=list[RecordOut])
async def list_course_records(
    course_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> list[RecordOut]:
    records = await RecordService.list_for_course(session, str(course_id))
    if records is None:
        raise HTTPException(status_code=404, detail="课程不存在或已删除")
    return [RecordOut.model_validate(record) for record in records]
