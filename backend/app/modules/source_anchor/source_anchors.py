from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.source_anchor.schemas import SourceAnchorOut
from app.modules.source_anchor.service import SourceAnchorService
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/records",
    tags=["source-anchors"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("/{record_id}/source-anchors", response_model=list[SourceAnchorOut])
async def list_record_source_anchors(
    record_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> list[SourceAnchorOut]:
    return await SourceAnchorService.list_by_record(session, str(record_id))
