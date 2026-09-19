"""library 域路由：资料条目 / 统一入库 / 生命周期动作 / 联邦记录与资产 /
AI 整理与 agent_proposals 提案端点。"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.capture.ingest import LibraryIngestService
from app.modules.library import organize as library_organize  # noqa: F401 —— 导入即注册应用器
from app.modules.library.lifecycle import LibraryLifecycleService
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
    OrganizeProposeOut,
    OrganizeScanOut,
    ProposalCreateRequest,
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
_LIFECYCLE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_LIBRARY_RESPONSES,
    409: {"model": ErrorResponse},
}
_PROPOSAL_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
}
_ORGANIZE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_LIBRARY_RESPONSES,
    409: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
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


@library_router.patch(
    "/items/{item_id}", response_model=LibraryItemOut, responses=_LIFECYCLE_RESPONSES
)
async def patch_library_item(
    item_id: UUID,
    body: LibraryItemPatch,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LibraryItemOut:
    """重命名（title）/ 归类（course_id，null=取消归类）/ 收藏（favorite）。"""
    if not body.model_fields_set:
        raise CodedHTTPException(
            code="LIBRARY_PATCH_EMPTY",
            status_code=422,
            detail="至少提供一项可更新字段",
        )
    return await LibraryLifecycleService.patch_item(session, str(item_id), body)


@library_router.post(
    "/items/{item_id}/archive", response_model=LibraryItemOut, responses=_LIFECYCLE_RESPONSES
)
async def archive_library_item(
    item_id: UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> LibraryItemOut:
    """归档：退出默认浏览与来源召回，快照与关联保留。"""
    return await LibraryLifecycleService.set_archived(session, str(item_id), archived=True)


@library_router.post(
    "/items/{item_id}/unarchive", response_model=LibraryItemOut, responses=_LIFECYCLE_RESPONSES
)
async def unarchive_library_item(
    item_id: UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> LibraryItemOut:
    return await LibraryLifecycleService.set_archived(session, str(item_id), archived=False)


@library_router.delete(
    "/items/{item_id}",
    response_model=LibraryItemOut,
    responses={**_LIFECYCLE_RESPONSES, 204: {"description": "已物理删除"}},
)
async def delete_library_item(
    item_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    permanent: bool = False,
) -> LibraryItemOut:
    """软删入回收站（默认，30 天可恢复、不级联派生 Record）；permanent=true
    物理删除（存在未软删派生 Record 时 409），返回 204。"""
    if permanent:
        await LibraryLifecycleService.purge_item(request.app.state.session_factory, str(item_id))
        return Response(status_code=204)  # type: ignore[return-value]
    return await LibraryLifecycleService.soft_delete(session, str(item_id))


@library_router.post(
    "/items/{item_id}/restore", response_model=LibraryItemOut, responses=_LIFECYCLE_RESPONSES
)
async def restore_library_item(item_id: UUID, request: Request) -> LibraryItemOut:
    """回收站恢复：校验快照完整性并幂等重建索引。"""
    return await LibraryLifecycleService.restore(
        request.app.state.session_factory, request.app.state.data_dir, str(item_id)
    )


@library_router.post(
    "/items/{item_id}/retry", response_model=LibraryItemOut, responses=_LIFECYCLE_RESPONSES
)
async def retry_library_item(
    item_id: UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> LibraryItemOut:
    """失败重试：复用解析链最新 FAILED 任务（attempts 归零）。"""
    return await LibraryLifecycleService.retry_failed(session, str(item_id))


@library_router.post(
    "/items/{item_id}/refetch",
    status_code=202,
    response_model=LibraryIngestAccepted,
    responses=_LIFECYCLE_RESPONSES,
)
async def refetch_library_item(item_id: UUID, request: Request) -> LibraryIngestAccepted:
    """同 URL 重新抓取 → 新条目（不覆盖旧快照、不建版本表）。"""
    return await LibraryLifecycleService.refetch(request.app.state.session_factory, str(item_id))


@library_router.post(
    "/items/{item_id}/rebuild-index",
    status_code=202,
    response_model=dict[str, str],
    responses=_LIFECYCLE_RESPONSES,
)
async def rebuild_library_item_index(item_id: UUID, request: Request) -> dict[str, str]:
    """索引重建任务（INDEX_REBUILD）：索引是可再生衍生数据，条目存在即受理。"""
    job = await LibraryLifecycleService.enqueue_index_rebuild(
        request.app.state.session_factory, str(item_id)
    )
    return {"job_id": job.id}


@library_router.post(
    "/organize/scan", response_model=OrganizeScanOut, responses=_ORGANIZE_RESPONSES
)
async def scan_library_organize(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizeScanOut:
    """确定性检测（零 LLM）：重复哈希组 / 处理异常 / 未归类清单。"""
    return await library_organize.OrganizeService.scan(session)


@library_router.post(
    "/organize/propose", response_model=OrganizeProposeOut, responses=_ORGANIZE_RESPONSES
)
async def propose_library_organize(request: Request) -> OrganizeProposeOut:
    """LLM 生成结构化标题与归类建议 → ORGANIZE 提案（逐项确认应用）。"""
    return await library_organize.OrganizeService.propose_with_llm(
        request.app.state.session_factory,
        request.app.state.data_dir,
        request.app.state.organize_model,
    )


@library_router.get("/items/{item_id}/content", response_model=LibraryItemContentOut)
async def get_library_item_content(
    item_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    filters: Annotated[LibraryItemContentQuery, Query()],
) -> LibraryItemContentOut:
    return await LibraryService.get_content(session, str(item_id), filters.limit)


@proposals_router.post("", status_code=201, response_model=AgentProposalOut)
async def create_proposal(
    body: ProposalCreateRequest, session: Annotated[AsyncSession, Depends(get_db)]
) -> AgentProposalOut:
    """创建提案（不改事实）：payload 按 proposal_type 判别校验。

    当前消费方：研究会话对 web_search 候选来源的「建议保存」（RESEARCH_INGEST）。
    """
    return await ProposalService.create(session, body)


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
