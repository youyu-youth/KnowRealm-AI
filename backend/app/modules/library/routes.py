"""library 域路由：资料条目 / 统一入库 / 联邦记录与资产 / agent_proposals 提案端点。"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.capture.ingest import LibraryIngestService
from app.modules.library.proposals import ProposalService
from app.modules.library.schemas import (
    AgentProposalOut,
    LibraryAssetListQuery,
    LibraryAssetOut,
    LibraryIngestAccepted,
    LibraryIngestRequest,
    LibraryItemContentOut,
    LibraryItemContentQuery,
    LibraryItemDetailOut,
    LibraryItemListOut,
    LibraryItemListQuery,
    LibraryItemOut,
    LibraryItemPatch,
    LibraryRecordListQuery,
    LibraryRecordOut,
    ProposalListQuery,
)
from app.modules.library.service import LibraryService
from app.shared.deps import get_db, require_launch_token
from app.shared.errors import CodedHTTPException
from app.shared.schemas import ErrorResponse

_LIBRARY_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
}
_INGEST_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_LIBRARY_RESPONSES,
    400: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    507: {"model": ErrorResponse},
}
_PROPOSAL_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
}

library_router = APIRouter(
    prefix="/api/library",
    tags=["library"],
    dependencies=[Depends(require_launch_token)],
    responses=_LIBRARY_RESPONSES,
)
proposals_router = APIRouter(
    prefix="/api/proposals",
    tags=["proposals"],
    dependencies=[Depends(require_launch_token)],
    responses=_PROPOSAL_RESPONSES,
)


@library_router.post(
    "/ingest",
    status_code=202,
    response_model=LibraryIngestAccepted,
    responses=_INGEST_RESPONSES,
)
async def ingest_library_item(
    request: Request, body: LibraryIngestRequest
) -> LibraryIngestAccepted:
    """统一入库（web/text）：立即建条目；web 另建 WEB_FETCH 任务异步抓取净化。"""
    session_factory = request.app.state.session_factory
    if body.source.value == "web":
        return await LibraryIngestService.ingest_web(session_factory, body)
    return await LibraryIngestService.ingest_text(session_factory, request.app.state.data_dir, body)


@library_router.post(
    "/ingest/file",
    status_code=202,
    response_model=LibraryIngestAccepted,
    responses=_INGEST_RESPONSES,
)
async def ingest_library_file(
    request: Request,
    file: Annotated[UploadFile, File()],
    course_id: Annotated[UUID | None, Form()] = None,
    allow_duplicate: Annotated[bool, Form()] = False,
) -> LibraryIngestAccepted:
    """统一入库（本地文件）：复用文档导入校验与解析分片管线，另建资料条目。"""
    return await LibraryIngestService.ingest_file(
        request.app.state.session_factory,
        request.app.state.data_dir,
        file,
        str(course_id) if course_id is not None else None,
        allow_duplicate,
    )


@library_router.get("/items", response_model=LibraryItemListOut)
async def list_library_items(
    session: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[LibraryItemListQuery, Query()],
) -> LibraryItemListOut:
    return await LibraryService.list_items(session, filters)


@library_router.get("/records", response_model=list[LibraryRecordOut])
async def list_library_records(
    session: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[LibraryRecordListQuery, Query()],
) -> list[LibraryRecordOut]:
    return await LibraryService.list_records(session, filters)


@library_router.get("/assets", response_model=list[LibraryAssetOut])
async def list_library_assets(
    session: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[LibraryAssetListQuery, Query()],
) -> list[LibraryAssetOut]:
    return await LibraryService.list_assets(session, filters)


@library_router.get("/items/{item_id}", response_model=LibraryItemDetailOut)
async def get_library_item(
    item_id: UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> LibraryItemDetailOut:
    return await LibraryService.get_item(session, str(item_id))


@library_router.patch("/items/{item_id}", response_model=LibraryItemOut)
async def patch_library_item(
    item_id: UUID,
    body: LibraryItemPatch,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LibraryItemOut:
    if body.favorite is None:
        raise CodedHTTPException(
            code="LIBRARY_PATCH_EMPTY",
            status_code=422,
            detail="至少提供一项可更新字段",
        )
    return await LibraryService.patch_item(session, str(item_id), body.favorite)


@library_router.get("/items/{item_id}/content", response_model=LibraryItemContentOut)
async def get_library_item_content(
    item_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[LibraryItemContentQuery, Query()],
) -> LibraryItemContentOut:
    return await LibraryService.get_content(session, str(item_id), filters.limit)


@proposals_router.get("", response_model=list[AgentProposalOut])
async def list_proposals(
    session: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[ProposalListQuery, Query()],
) -> list[AgentProposalOut]:
    return await ProposalService.list_proposals(session, filters)


@proposals_router.post("/{proposal_id}/confirm", response_model=AgentProposalOut)
async def confirm_proposal(
    proposal_id: UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> AgentProposalOut:
    return await ProposalService.confirm(session, str(proposal_id))


@proposals_router.post("/{proposal_id}/reject", response_model=AgentProposalOut)
async def reject_proposal(
    proposal_id: UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> AgentProposalOut:
    return await ProposalService.reject(session, str(proposal_id))
