"""update_library_item 操作注册项（通用 Agent 第二阶段工单 03）。

「把这个条目改名为 X / 归到课程 Y」→ 模型经 search_library 消歧固化 item_id →
薄工具创建 OP_LIBRARY_ITEM_UPDATE 提案（提交时同事务固化执行前快照）→ 确认卡
before/after 预览 → 确认 → 执行前重验后经 lifecycle 事务内核心落库（与 HTTP
路由共用同一校验链；收藏不接入，spec 决策 14）。载荷契约见 agent/schemas.py。

工单 06：本动作可撤销——补偿器 undo_update_library_item（重命名 / 归类的
Undo，恢复快照 before 值）。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    UndoOperationResult,
    assert_undo_state,
    assert_undo_version,
    parse_undo_basis,
    register_operation,
)
from app.modules.agent.runs.models import AgentOperation
from app.modules.agent.schemas import (
    LibraryItemArchivePayload,
    LibraryItemStateSnapshot,
    LibraryItemUpdatePayload,
    LibraryItemUpdateResult,
)
from app.modules.library.lifecycle import LibraryLifecycleService
from app.modules.library.schemas import LibraryItemPatch, ProposalType
from app.modules.library.service import LibraryService

# 工具名（langchain @tool 注册名 = 函数名）。
UPDATE_LIBRARY_ITEM_ACTION = "update_library_item"

# OP_LIBRARY_ITEM_UPDATE 可修改字段（快照 before 投影与回执 after 投影的键集）。
LIBRARY_ITEM_UPDATE_FIELDS = ("title", "course_id")


async def capture_library_item_state(
    session: AsyncSession, payload: LibraryItemUpdatePayload | LibraryItemArchivePayload
) -> LibraryItemStateSnapshot:
    """执行前快照读取器（library_item.* 三动作共用）：不存在/已软删 → 404。"""
    item = await LibraryService.active_item(session, payload.item_id)
    return LibraryItemStateSnapshot(
        updated_at=item.updated_at,
        title=item.title,
        course_id=item.course_id,
        status=item.status,
    )


def resolve_library_item_target(
    payload: LibraryItemUpdatePayload | LibraryItemArchivePayload,
) -> tuple[str, str]:
    return "library_item", payload.item_id


async def apply_library_item_update(
    session: AsyncSession, payload: LibraryItemUpdatePayload, _execution_id: str
) -> LibraryItemUpdateResult:
    """OP_LIBRARY_ITEM_UPDATE 应用器（提案框架契约：调用方事务内、不得自行 begin）。

    执行前重验已由注册表适配器统一完成；经 lifecycle 事务内核心落库（标题空值
    / 归类目标课程校验与 HTTP 路由同源）。"""
    item = await LibraryService.active_item(session, payload.item_id)
    before = {field: getattr(item, field) for field in LIBRARY_ITEM_UPDATE_FIELDS}
    # 工具面已滤 None（模型无法传递显式 null）：值非 None 的字段才是要修改的
    # 字段（取消归类 / 收藏不接入，走页面路径）。
    provided = {
        key: value
        for key, value in payload.model_dump().items()
        if key != "item_id" and value is not None
    }
    await LibraryLifecycleService.patch_core(session, item, LibraryItemPatch(**provided))
    after = {field: getattr(item, field) for field in LIBRARY_ITEM_UPDATE_FIELDS}
    return LibraryItemUpdateResult(
        item_id=payload.item_id,
        before={key: before[key] for key in before if before[key] != after[key]},
        after={key: after[key] for key in before if before[key] != after[key]},
        after_updated_at=item.updated_at,
    )


async def undo_update_library_item(
    session: AsyncSession, original: AgentOperation
) -> UndoOperationResult:
    """update_library_item 补偿器（工单 06）：重命名 / 归类的 Undo。

    撤销前重验两道：条目当前 title / course_id 必须等于原操作执行后的预期态
    （payload 变换应用到快照），且目标版本等于 result 固化的执行后版本戳
    （改走又改回＝值复原但版本已变，仍拒绝，spec 决策 19）——期间被手动
    改过 → OPERATION_UNDO_CONFLICT（不覆盖后续修改）；恢复＝把原载荷修改
    过的字段写回快照 before 值。"""
    payload, snapshot, result = parse_undo_basis(
        original, LibraryItemUpdatePayload, LibraryItemStateSnapshot, LibraryItemUpdateResult
    )
    item = await LibraryService.active_item(session, payload.item_id)
    expected = {
        "title": payload.title if payload.title is not None else snapshot.title,
        "course_id": (payload.course_id if payload.course_id is not None else snapshot.course_id),
    }
    assert_undo_state(expected, {"title": item.title, "course_id": item.course_id})
    assert_undo_version(result.after_updated_at, item.updated_at)
    restore = {
        key: getattr(snapshot, key)
        for key in LIBRARY_ITEM_UPDATE_FIELDS
        if getattr(payload, key) is not None
    }
    await LibraryLifecycleService.patch_core(session, item, LibraryItemPatch(**restore))
    return UndoOperationResult(restored=restore)


register_operation(
    OperationSpec(
        action=UPDATE_LIBRARY_ITEM_ACTION,
        proposal_type=ProposalType.OP_LIBRARY_ITEM_UPDATE,
        level=OperationLevel.L1,
        payload_schema=LibraryItemUpdatePayload,
        result_schema=LibraryItemUpdateResult,
        applier=apply_library_item_update,
        capture_state=capture_library_item_state,
        target_resolver=resolve_library_item_target,
        undoer=undo_update_library_item,
    )
)
