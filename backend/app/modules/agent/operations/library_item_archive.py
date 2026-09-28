"""archive_library_item / restore_library_item 操作注册项（工单 03）。

复用 lifecycle 既有归档 / 恢复核心（set_archived_core，HTTP 路由与 Agent 应用器
共用）；快照读取器与目标定位复用 library_item_update 声明（library_item.*
三动作共用同一形状）。载荷契约见 agent/schemas.py。

工单 06：两动作可撤销——补偿器互为反向（归档的 Undo＝恢复、恢复的 Undo＝
重新归档），撤销前重验当前状态仍是原操作的执行结果。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.library_item_update import (
    capture_library_item_state,
    resolve_library_item_target,
)
from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    UndoOperationResult,
    assert_undo_state,
    parse_operation_payload,
    parse_undo_basis,
    register_operation,
)
from app.modules.agent.runs.models import AgentOperation
from app.modules.agent.schemas import (
    LibraryItemArchivePayload,
    LibraryItemArchiveResult,
    LibraryItemStateSnapshot,
)
from app.modules.library.lifecycle import LibraryLifecycleService
from app.modules.library.models import AgentProposal
from app.modules.library.schemas import ProposalType
from app.modules.library.service import LibraryService

# 工具名（langchain @tool 注册名 = 函数名）。
ARCHIVE_LIBRARY_ITEM_ACTION = "archive_library_item"
RESTORE_LIBRARY_ITEM_ACTION = "restore_library_item"


async def _apply_library_item_status(
    session: AsyncSession, proposal: AgentProposal, *, archived: bool
) -> LibraryItemArchiveResult:
    """OP_LIBRARY_ITEM_ARCHIVE / OP_LIBRARY_ITEM_RESTORE 应用器（调用方事务内）。

    执行前重验已由注册表适配器统一完成；重复归档 / 重复恢复由领域核心幂等
    守卫拒绝（409 稳定错误码 → 提案 FAILED 可重试）。"""
    payload = parse_operation_payload(proposal, LibraryItemArchivePayload)
    item = await LibraryService.active_item(session, payload.item_id)
    await LibraryLifecycleService.set_archived_core(session, item, archived=archived)
    return LibraryItemArchiveResult(item_id=payload.item_id, status=item.status)


async def apply_library_item_archive(
    session: AsyncSession, proposal: AgentProposal
) -> LibraryItemArchiveResult:
    return await _apply_library_item_status(session, proposal, archived=True)


async def apply_library_item_restore(
    session: AsyncSession, proposal: AgentProposal
) -> LibraryItemArchiveResult:
    return await _apply_library_item_status(session, proposal, archived=False)


async def _undo_library_item_status(
    session: AsyncSession, original: AgentOperation, *, archived: bool
) -> UndoOperationResult:
    """条目归档 / 恢复的共用补偿器：预期当前状态＝原操作执行结果，恢复＝
    反向翻转（set_archived_core，与 HTTP / Agent 正向路径同一核心）。"""
    payload, snapshot = parse_undo_basis(
        original, LibraryItemArchivePayload, LibraryItemStateSnapshot
    )
    item = await LibraryService.active_item(session, payload.item_id)
    assert_undo_state({"status": "ARCHIVED" if archived else "ACTIVE"}, {"status": item.status})
    await LibraryLifecycleService.set_archived_core(session, item, archived=not archived)
    return UndoOperationResult(restored={"status": snapshot.status})


async def undo_library_item_archive(
    session: AsyncSession, original: AgentOperation
) -> UndoOperationResult:
    return await _undo_library_item_status(session, original, archived=True)


async def undo_library_item_restore(
    session: AsyncSession, original: AgentOperation
) -> UndoOperationResult:
    return await _undo_library_item_status(session, original, archived=False)


register_operation(
    OperationSpec(
        action=ARCHIVE_LIBRARY_ITEM_ACTION,
        proposal_type=ProposalType.OP_LIBRARY_ITEM_ARCHIVE,
        level=OperationLevel.L1,
        payload_schema=LibraryItemArchivePayload,
        result_schema=LibraryItemArchiveResult,
        applier=apply_library_item_archive,
        capture_state=capture_library_item_state,
        target_resolver=resolve_library_item_target,
        undoer=undo_library_item_archive,
    )
)
register_operation(
    OperationSpec(
        action=RESTORE_LIBRARY_ITEM_ACTION,
        proposal_type=ProposalType.OP_LIBRARY_ITEM_RESTORE,
        level=OperationLevel.L1,
        payload_schema=LibraryItemArchivePayload,
        result_schema=LibraryItemArchiveResult,
        applier=apply_library_item_restore,
        capture_state=capture_library_item_state,
        target_resolver=resolve_library_item_target,
        undoer=undo_library_item_restore,
    )
)
