"""update_plan_item / complete_plan_item 操作注册项（通用 Agent 第三阶段工单 03）。

「把这条改到周五 / 这条完成了」→ 模型经 get_plan 固化 item_id → 薄工具提交
L1 提案（快照同事务固化）→ 确认卡 before/after 预览 → 用户确认 → 应用器经
PlanItemService 就地改当前版本计划项。编辑置 user_locked（重生成原样保留，
spec 用户故事 15）；完成 = DONE + completed_at（学习时长统计口径，不产
learning_event、不动 Concept Mastery，spec 用户故事 17）。

本模块同时注册页面直改计划项的 Operation 审计钩子（learning_plan.audit 反转，
工单 03：计划 Tab 的编辑 / 完成 / 跳过按钮点击即用户授权，trigger=USER_MANUAL，
与 Agent 路径同一 agent_operations 事实源）。
"""

import json
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    register_operation,
)
from app.modules.agent.runs.schemas import OperationAuthorization
from app.modules.agent.runs.service import record_direct_execution
from app.modules.agent.schemas import (
    PlanItemCompletePayload,
    PlanItemCompleteResult,
    PlanItemStateSnapshot,
    PlanItemUpdatePayload,
    PlanItemUpdateResult,
)
from app.modules.course.models import Course
from app.modules.learning_plan.audit import register_manual_audit_recorder
from app.modules.learning_plan.models import LearningGoal, LearningPlan, LearningPlanItem
from app.modules.learning_plan.schemas import PlanItemUpdate
from app.modules.learning_plan.service import PlanItemService
from app.modules.library.schemas import ProposalType
from app.shared.errors import CodedHTTPException

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
UPDATE_PLAN_ITEM_ACTION = "update_plan_item"
COMPLETE_PLAN_ITEM_ACTION = "complete_plan_item"

# 项级可修改字段（快照 / 回执 before/after 投影的键集）。
PLAN_ITEM_UPDATE_FIELDS = ("scheduled_date", "estimated_minutes", "content")


async def load_item_context(
    session: AsyncSession, item_id: str
) -> tuple[LearningPlanItem, LearningPlan, LearningGoal] | None:
    """计划项 + 所在计划 + 归属目标（课程软删 / 不存在 = None；工单 03 共用）。"""
    statement = (
        select(LearningPlanItem, LearningPlan, LearningGoal)
        .join(LearningPlan, LearningPlan.id == LearningPlanItem.plan_id)
        .join(LearningGoal, LearningGoal.id == LearningPlan.goal_id)
        .join(Course, Course.id == LearningGoal.course_id)
        .where(LearningPlanItem.id == item_id, Course.deleted_at.is_(None))
    )
    row = (await session.execute(statement)).one_or_none()
    return None if row is None else (row[0], row[1], row[2])


def _require_item(found: tuple[LearningPlanItem, LearningPlan, LearningGoal]) -> None:
    """项级动作前置：仅当前生效版本的计划项可改（历史版本只读）。"""
    PlanItemService.require_active_plan(found[1])


def _item_not_found() -> CodedHTTPException:
    return CodedHTTPException(
        code="PLAN_ITEM_NOT_FOUND", status_code=404, detail="计划项不存在或所属课程已删除"
    )


def item_state_snapshot(
    found: tuple[LearningPlanItem, LearningPlan, LearningGoal],
) -> PlanItemStateSnapshot:
    item, plan, goal = found
    return PlanItemStateSnapshot(
        item_id=item.id,
        plan_id=plan.id,
        plan_version=plan.plan_version,
        plan_status=plan.status,
        goal_status=goal.status,
        phase_title=item.phase_title,
        content=item.content,
        scheduled_date=date.fromisoformat(item.scheduled_date),
        estimated_minutes=item.estimated_minutes,
        status=item.status,
        user_locked=item.user_locked,
    )


async def capture_plan_item_state(
    session: AsyncSession, payload: PlanItemUpdatePayload | PlanItemCompletePayload
) -> PlanItemStateSnapshot:
    """执行前快照读取器：项不可达（PLAN_ITEM_NOT_FOUND）或版本非 ACTIVE
    （PLAN_VERSION_NOT_ACTIVE）→ 结构化拒绝（零提案）。"""
    found = await load_item_context(session, payload.item_id)
    if found is None:
        raise _item_not_found()
    _require_item(found)
    return item_state_snapshot(found)


def resolve_plan_item_target(
    payload: PlanItemUpdatePayload | PlanItemCompletePayload,
) -> tuple[str, str]:
    return "plan_item", payload.item_id


async def apply_plan_item_update(
    session: AsyncSession, payload: PlanItemUpdatePayload, _execution_id: str
) -> PlanItemUpdateResult:
    """OP_PLAN_ITEM_UPDATE 应用器（调用方事务内）：经领域核心就地修改 +
    user_locked 置位，返回修改字段 before / after 对照。"""
    found = await load_item_context(session, payload.item_id)
    if found is None:
        raise _item_not_found()
    _require_item(found)
    item, plan, goal = found
    provided = {
        key: value
        for key, value in payload.model_dump(exclude_unset=True).items()
        if key in PLAN_ITEM_UPDATE_FIELDS and value is not None
    }
    before = {field: getattr(item, field) for field in PLAN_ITEM_UPDATE_FIELDS}
    if provided:
        await PlanItemService.update_core(session, item, PlanItemUpdate(**provided))
    after = {field: getattr(item, field) for field in PLAN_ITEM_UPDATE_FIELDS}
    changed = {key for key in before if before[key] != after[key]}
    return PlanItemUpdateResult(
        item_id=item.id,
        plan_id=plan.id,
        goal_id=goal.id,
        before={key: before[key] for key in changed},
        after={key: after[key] for key in changed},
        user_locked=item.user_locked,
    )


async def apply_plan_item_complete(
    session: AsyncSession, payload: PlanItemCompletePayload, _execution_id: str
) -> PlanItemCompleteResult:
    """OP_PLAN_ITEM_COMPLETE 应用器：DONE + 完成时间戳（不进学习证据链）。"""
    found = await load_item_context(session, payload.item_id)
    if found is None:
        raise _item_not_found()
    _require_item(found)
    item, plan, goal = found
    await PlanItemService.complete_core(session, item)
    return PlanItemCompleteResult(
        item_id=item.id,
        plan_id=plan.id,
        goal_id=goal.id,
        status=item.status,
        completed_at=item.completed_at,
    )


register_operation(
    OperationSpec(
        action=UPDATE_PLAN_ITEM_ACTION,
        proposal_type=ProposalType.OP_PLAN_ITEM_UPDATE,
        level=OperationLevel.L1,
        payload_schema=PlanItemUpdatePayload,
        result_schema=PlanItemUpdateResult,
        applier=apply_plan_item_update,
        capture_state=capture_plan_item_state,
        target_resolver=resolve_plan_item_target,
        undo_reason="计划项修改暂不在撤销范围，可再次编辑改回或要求重新生成",
    )
)
register_operation(
    OperationSpec(
        action=COMPLETE_PLAN_ITEM_ACTION,
        proposal_type=ProposalType.OP_PLAN_ITEM_COMPLETE,
        level=OperationLevel.L1,
        payload_schema=PlanItemCompletePayload,
        result_schema=PlanItemCompleteResult,
        applier=apply_plan_item_complete,
        capture_state=capture_plan_item_state,
        target_resolver=resolve_plan_item_target,
        undo_reason="计划项完成是事实记录（完成时间戳进学习时长统计），不在撤销范围",
    )
)


async def _record_manual_operation(
    session: AsyncSession,
    action: str,
    target: tuple[str, str],
    payload: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """页面直改计划项的审计行（USER_MANUAL，调用方事务内；L1 单对象修改）。"""
    await record_direct_execution(
        session,
        action=action,
        level=OperationLevel.L1.value,
        target=target,
        payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        authorization=OperationAuthorization(trigger="USER_MANUAL"),
        result_dict=result,
    )


register_manual_audit_recorder(_record_manual_operation)
