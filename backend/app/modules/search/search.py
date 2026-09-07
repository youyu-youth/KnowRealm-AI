from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.search.schemas import SearchOut, SearchQuery
from app.modules.search.service import SearchService
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/search",
    tags=["search"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("", response_model=SearchOut)
async def search(
    filters: Annotated[SearchQuery, Query()],
    session: AsyncSession = Depends(get_db),
) -> SearchOut:
    return await SearchService.search(session, filters.q, filters.limit)
