"""add_shared_ref / remove_shared_ref 操作注册项（通用 Agent 第三阶段工单 05）。

「把机器学习课的那篇论文引用到 Agent 工程课」→ 模型经 search_courses /
list_library_items 固化双 id → 薄工具提交 L1 提案（快照同事务固化）→ 确认卡
预览引用关系 → 用户确认 → 应用器经 SharedRefService 落引用行（与页面路由
共用同一校验链）。删除引用不动原资料（spec 用户故事 25）；引用增删可直接
反向操作，不在撤销范围。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    parse_operation_payload,
    register_operation,
)
from app.modules.agent.schemas import (
    SharedRefAddStateSnapshot,
    SharedRefPayload,
    SharedRefRemoveStateSnapshot,
    SharedRefResult,
)
from app.modules.course.service import CourseService
from app.modules.library.models import AgentProposal, CourseSharedRef, LibraryItem
from app.modules.library.schemas import ProposalType
from app.modules.library.shared_refs import SharedRefService, validate_add
from app.shared.errors import CodedHTTPException

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
ADD_SHARED_REF_ACTION = "add_shared_ref"
REMOVE_SHARED_REF_ACTION = "remove_shared_ref"


async def _require_ref(session: AsyncSession, payload: SharedRefPayload) -> str:
    """引用行 id：不存在 → SHARED_REF_NOT_FOUND。"""
    found = await session.scalar(
        select(CourseSharedRef.id).where(
            CourseSharedRef.course_id == payload.course_id,
            CourseSharedRef.library_item_id == payload.library_item_id,
        )
    )
    if found is None:
        raise CodedHTTPException(
            code="SHARED_REF_NOT_FOUND",
            status_code=404,
            detail="共享引用不存在或已删除",
        )
    return found


async def _item_title(session: AsyncSession, item_id: str) -> str:
    title = await session.scalar(select(LibraryItem.title).where(LibraryItem.id == item_id))
    return title if title is not None else ""


async def capture_shared_ref_add_state(
    session: AsyncSession, payload: SharedRefPayload
) -> SharedRefAddStateSnapshot:
    """添加前状态读取器：课程 / 条目 / 归属 / 重复校验（validate_add 全链），
    不达即结构化拒绝（零提案）；课程与条目双目标态进快照——确认窗口内任一
    方变化（改名 / 归属迁移）→ 快照比对失效重新确认。"""
    await validate_add(session, payload.course_id, payload.library_item_id)
    course = await CourseService.get(session, payload.course_id)
    assert course is not None  # validate_add 已拒不可达课程
    item = await session.get(LibraryItem, payload.library_item_id)
    assert item is not None  # validate_add 已拒不可达条目
    return SharedRefAddStateSnapshot(
        course_updated_at=course.updated_at,
        course_name=course.name,
        item_title=item.title,
        item_owner_course_id=item.course_id,
    )


async def capture_shared_ref_remove_state(
    session: AsyncSession, payload: SharedRefPayload
) -> SharedRefRemoveStateSnapshot:
    """删除前状态读取器：引用不存在 → SHARED_REF_NOT_FOUND（零提案）；
    引用行 id 入快照绑定对象版本——确认窗口内引用被删重建（行身份变化，
    ADR-0026）或课程改名 / 条目改名 → 快照比对失效重新确认；课程名与条目
    标题供确认卡核对移除哪条关系（同一资料可被多空间引用）。"""
    course = await CourseService.get(session, payload.course_id)
    if course is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND",
            status_code=404,
            detail="课程不存在或已删除",
        )
    return SharedRefRemoveStateSnapshot(
        ref_id=await _require_ref(session, payload),
        course_name=course.name,
        item_title=await _item_title(session, payload.library_item_id),
    )


def resolve_shared_ref_target(payload: SharedRefPayload) -> tuple[str, str]:
    return "library_item", payload.library_item_id


async def apply_shared_ref_add(session: AsyncSession, proposal: AgentProposal) -> SharedRefResult:
    """OP_SHARED_REF_ADD 应用器（调用方事务内）：经领域核心落引用行。"""
    payload = parse_operation_payload(proposal, SharedRefPayload)
    created = await SharedRefService.add_core(session, payload.course_id, payload.library_item_id)
    return SharedRefResult(
        course_id=created.course_id,
        library_item_id=created.library_item_id,
        title=created.title,
    )


async def apply_shared_ref_remove(
    session: AsyncSession, proposal: AgentProposal
) -> SharedRefResult:
    """OP_SHARED_REF_REMOVE 应用器：删除引用行（原资料不动）。"""
    payload = parse_operation_payload(proposal, SharedRefPayload)
    title = await _item_title(session, payload.library_item_id)
    await SharedRefService.remove_core(session, payload.course_id, payload.library_item_id)
    return SharedRefResult(
        course_id=payload.course_id,
        library_item_id=payload.library_item_id,
        title=title,
    )


register_operation(
    OperationSpec(
        action=ADD_SHARED_REF_ACTION,
        proposal_type=ProposalType.OP_SHARED_REF_ADD,
        level=OperationLevel.L1,
        payload_schema=SharedRefPayload,
        result_schema=SharedRefResult,
        applier=apply_shared_ref_add,
        capture_state=capture_shared_ref_add_state,
        target_resolver=resolve_shared_ref_target,
        undo_reason="引用增删可直接反向操作（再引用 / 再删除），不在撤销范围",
    )
)
register_operation(
    OperationSpec(
        action=REMOVE_SHARED_REF_ACTION,
        proposal_type=ProposalType.OP_SHARED_REF_REMOVE,
        level=OperationLevel.L1,
        payload_schema=SharedRefPayload,
        result_schema=SharedRefResult,
        applier=apply_shared_ref_remove,
        capture_state=capture_shared_ref_remove_state,
        target_resolver=resolve_shared_ref_target,
        undo_reason="引用增删可直接反向操作（再引用 / 再删除），不在撤销范围",
    )
)
