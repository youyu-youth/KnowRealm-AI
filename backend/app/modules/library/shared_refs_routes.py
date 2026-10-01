"""共享来源引用 HTTP 路由（通用 Agent 第三阶段工单 05）：课程嵌套端点。

列表 / 添加 / 删除三端点（薄路由，事务与领域约束在 SharedRefService）；
REQUEST_COURSE_ID（请求方知识空间 query，见 shared_refs 模块）由三个资产
生成路由（总结 / 知识点 / 习题）跨模块复用——携带时生成 Service 对共享
资料只读执法（SHARED_REF_ASSET_READ_ONLY）。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.library.schemas import SharedRefAdd, SharedRefOut
from app.modules.library.shared_refs import SharedRefService
from app.shared.deps import get_db, require_launch_token
from app.shared.errors import CodedHTTPException
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/courses",
    tags=["shared-refs"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


def _course_not_found() -> CodedHTTPException:
    return CodedHTTPException(code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除")


@router.get("/{course_id}/shared-refs", response_model=list[SharedRefOut])
async def list_course_shared_refs(
    course_id: str,
    session: AsyncSession = Depends(get_db),
) -> list[SharedRefOut]:
    """本空间引用清单（available=False 行展示「来源已删除」，仍可删除引用）。"""
    refs = await SharedRefService.list_for_course(session, course_id)
    if refs is None:
        raise _course_not_found()
    return refs


@router.post("/{course_id}/shared-refs", response_model=SharedRefOut, status_code=201)
async def add_course_shared_ref(
    course_id: str,
    payload: SharedRefAdd,
    session: AsyncSession = Depends(get_db),
) -> SharedRefOut:
    """引用一份归属他空间的资料：原归属不变、不重复入库。"""
    return await SharedRefService.add(session, course_id, payload.library_item_id)


@router.delete(
    "/{course_id}/shared-refs/{library_item_id}",
    status_code=204,
    response_class=Response,
    response_model=None,
)
async def remove_course_shared_ref(
    course_id: str,
    library_item_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """删除引用行（原资料不动）。"""
    await SharedRefService.remove(session, course_id, str(library_item_id))
    return Response(status_code=204)
