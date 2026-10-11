"""update_goal 操作注册项（通用 Agent 第三阶段工单 01）：目标编辑与状态流转。

「把目标期限改到月底」/「这个目标完成了」→ 模型经 list_goals 固化 goal_id →
薄工具创建 OP_GOAL_UPDATE 提案（提交时同事务固化执行前快照）→ 确认卡
before/after 预览 → 用户确认 → 应用器先执行前重验（快照比对），再经领域
核心落库（字段编辑与状态流转共用同一事务）。快照一份三用：预览、重验、
后续 Undo 补偿。编辑与状态流转均只对 ACTIVE 目标开放（GOAL_NOT_ACTIVE）。
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    register_operation,
)
from app.modules.agent.schemas import (
    GoalStateSnapshot,
    GoalUpdatePayload,
    GoalUpdateResult,
)
from app.modules.learning_plan.schemas import GoalStatus, GoalType, GoalUpdate
from app.modules.learning_plan.service import GoalService
from app.modules.library.schemas import ProposalType
from app.shared.errors import CodedHTTPException

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
UPDATE_GOAL_ACTION = "update_goal"

# OP_GOAL_UPDATE 可修改字段（快照 before 投影与回执 after 投影的键集）。
GOAL_UPDATE_FIELDS = ("title", "target_date", "daily_minutes", "target_score")


async def capture_goal_state(
    session: AsyncSession, payload: GoalUpdatePayload
) -> GoalStateSnapshot:
    """执行前快照读取器：不存在 / 课程已软删 → 结构化拒绝（零提案）。"""
    goal = await GoalService.get(session, payload.goal_id)
    if goal is None:
        raise CodedHTTPException(code="GOAL_NOT_FOUND", status_code=404, detail="学习目标不存在")
    return GoalStateSnapshot(
        updated_at=goal.updated_at,
        title=goal.title,
        goal_type=GoalType(goal.goal_type),
        status=goal.status,
        # ORM 列是 String（ISO 日期串），快照字段以 date 声明——显式解析收窄。
        target_date=date.fromisoformat(goal.target_date) if goal.target_date else None,
        daily_minutes=goal.daily_minutes,
        target_score=goal.target_score,
    )


def resolve_goal_target(payload: GoalUpdatePayload) -> tuple[str, str]:
    return "goal", payload.goal_id


async def apply_goal_update(
    session: AsyncSession, payload: GoalUpdatePayload, _execution_id: str
) -> GoalUpdateResult:
    """OP_GOAL_UPDATE 应用器（提案框架契约：调用方事务内、不得自行 begin）。

    执行前重验已由注册表适配器统一完成（快照比对）；此处先应用字段编辑、
    再执行状态流转（同一事务），返回被修改字段的 before / after 对照与
    执行后状态。
    """
    goal = await GoalService.get(session, payload.goal_id)
    if goal is None:
        raise CodedHTTPException(code="GOAL_NOT_FOUND", status_code=404, detail="学习目标不存在")
    before = {field: getattr(goal, field) for field in GOAL_UPDATE_FIELDS}
    # 工具面已滤 None（模型无法传显式 null），payload 非 None 字段＝本次要改的
    # 字段（与 update_course 同口径闭环）。
    provided = {
        key: value
        for key, value in payload.model_dump().items()
        if key in GOAL_UPDATE_FIELDS and value is not None
    }
    if provided:
        await GoalService.update_core(session, goal, GoalUpdate(**provided))
    if payload.status is not None:
        await GoalService.set_status_core(session, goal, GoalStatus(payload.status))
    after = {field: getattr(goal, field) for field in GOAL_UPDATE_FIELDS}
    changed = {key for key in before if before[key] != after[key]}
    return GoalUpdateResult(
        goal_id=payload.goal_id,
        before={key: before[key] for key in changed},
        after={key: after[key] for key in changed},
        after_status=goal.status,
        after_updated_at=goal.updated_at,
    )


register_operation(
    OperationSpec(
        action=UPDATE_GOAL_ACTION,
        proposal_type=ProposalType.OP_GOAL_UPDATE,
        level=OperationLevel.L1,
        payload_schema=GoalUpdatePayload,
        result_schema=GoalUpdateResult,
        applier=apply_goal_update,
        capture_state=capture_goal_state,
        target_resolver=resolve_goal_target,
        undo_reason="目标修改暂不在撤销范围，可在对话中再次调整或手动改回",
    )
)
