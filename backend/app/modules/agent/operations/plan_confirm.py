"""confirm_plan 操作注册项（通用 Agent 第三阶段工单 02）。

「基于这门课生成四周学习计划」→ generate_learning_plan 只读产出草案（零
落库）→ 模型把草案经 confirm_plan 原样提交 → OP_PLAN_CONFIRM 提案（草案
确认卡，只读预览）→ 用户确认 → 应用器经领域核心写 learning_plans（ACTIVE）
与 learning_plan_items（spec 用户故事 9/11：草案不持久化，确认才落库）。

L2（计划头 + 批量项创建）：AUTO_APPROVE 档仍落确认卡（spec「草案卡即确认
闸门」）、FULL_ACCESS 直执行。快照读取器三用之外还承担两项状态依赖约束的
提交时拒绝：已有进行中计划（PLAN_ACTIVE_EXISTS 零提案）；排期与目标期限 /
预算的重算比对（模型转述草案漂移 → PLAN_SCHEDULE_INVALID 拒绝并附期望日期，
模型修正后重交）。重生成（新版本 + SUPERSEDED）随工单 03，不在本动作面。
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    parse_operation_payload,
    register_operation,
)
from app.modules.agent.schemas import (
    PlanConfirmPayload,
    PlanConfirmResult,
    PlanConfirmStateSnapshot,
)
from app.modules.course.service import CourseService
from app.modules.learning_plan.generation import constraints_for
from app.modules.learning_plan.models import LearningGoal
from app.modules.learning_plan.scheduling import ScheduleInfeasible, pack_schedule
from app.modules.learning_plan.service import GoalService, PlanService
from app.modules.library.models import AgentProposal
from app.modules.library.schemas import ProposalType
from app.modules.record.models import Record
from app.shared.errors import CodedHTTPException

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
CONFIRM_PLAN_ACTION = "confirm_plan"


async def capture_plan_confirm_state(
    session: AsyncSession, payload: PlanConfirmPayload
) -> PlanConfirmStateSnapshot:
    """提交时状态读取与结构化校验（零提案拒绝）：

    - 目标不可达 / 非进行中 → GOAL_NOT_FOUND / GOAL_NOT_ACTIVE；
    - 已有进行中计划 → PLAN_ACTIVE_EXISTS（重生成随工单 03）；
    - STUDY_RECORD 引用的记录不属于本课程或不可见 → PLAN_DRAFT_INVALID；
    - 排期重算与载荷日期不一致（模型转述漂移 / 目标约束变化）→
      PLAN_SCHEDULE_INVALID 并附期望日期（模型修正后重交）。
    """
    goal = await GoalService.get(session, payload.goal_id)
    if goal is None:
        raise CodedHTTPException(
            code="GOAL_NOT_FOUND", status_code=404, detail="目标不存在或所属课程已删除"
        )
    if goal.status != "ACTIVE":
        raise CodedHTTPException(
            code="GOAL_NOT_ACTIVE",
            status_code=409,
            detail="目标已完结或归档，只有进行中的目标可以制定计划",
        )
    await PlanService.require_no_active(session, goal.id)
    await _require_records_visible(session, goal.course_id, payload)
    _require_schedule_matches(payload, goal)
    course = await CourseService.get(session, goal.course_id)
    return PlanConfirmStateSnapshot(
        updated_at=goal.updated_at,
        title=goal.title,
        target_date=(
            date.fromisoformat(goal.target_date) if goal.target_date is not None else None
        ),
        daily_minutes=goal.daily_minutes,
        course_name=course.name if course is not None else goal.course_id,
    )


async def _require_records_visible(
    session: AsyncSession, course_id: str, payload: PlanConfirmPayload
) -> None:
    """STUDY_RECORD 的 record_id 必须是本课程可见记录（防模型编造引用）。"""
    record_ids = {
        item.record_id
        for phase in payload.phases
        for item in phase.items
        if item.record_id is not None
    }
    if not record_ids:
        return
    visible = set(
        (
            await session.scalars(
                select(Record.id).where(
                    Record.id.in_(record_ids),
                    Record.course_id == course_id,
                    Record.deleted_at.is_(None),
                )
            )
        ).all()
    )
    missing = sorted(record_ids - visible)
    if missing:
        raise CodedHTTPException(
            code="PLAN_DRAFT_INVALID",
            status_code=422,
            detail="草案引用了不属于本课程的资料记录，请修正后重新提交",
            params={"recordIds": ", ".join(missing)},
        )


def _require_schedule_matches(payload: PlanConfirmPayload, goal: LearningGoal) -> None:
    """排期确定性重算比对（spec：日期铺排由确定性校验承担）。

    锚点 = 草案首日（跨天确认时以生成日为基线仍逐位一致），但**不得早于目标
    当前版本的 updated_at 日期**——草案只会在目标定型后生成，起点早于该日 =
    模型编造（回挪起点会虚增期限容量，破坏「每日总量与 daily_minutes 相容」
    的容量口径）。
    """
    minutes = [item.estimated_minutes for phase in payload.phases for item in phase.items]
    claimed = [item.scheduled_date for phase in payload.phases for item in phase.items]
    assert claimed, "schema 保证至少一个计划项"
    floor = goal.updated_at.date()
    if claimed[0] < floor:
        raise CodedHTTPException(
            code="PLAN_SCHEDULE_INVALID",
            status_code=422,
            detail=(
                f"草案排期起点早于目标当前版本（{floor.isoformat()}），"
                "起点不得早于目标定版日，请修正后重新提交"
            ),
        )
    try:
        expected = pack_schedule(minutes, constraints_for(goal, claimed[0]))
    except ScheduleInfeasible as exc:
        raise CodedHTTPException(
            code="PLAN_SCHEDULE_INFEASIBLE",
            status_code=422,
            detail=f"{exc}，请修正草案（精简总量 / 拆分超预算单项）或建议用户调整目标",
        ) from exc
    if expected != claimed:
        raise CodedHTTPException(
            code="PLAN_SCHEDULE_INVALID",
            status_code=422,
            detail=(
                "草案排期与目标约束不符，期望日期："
                + "、".join(value.isoformat() for value in expected)
                + "，请按期望日期修正后重新提交"
            ),
            params={"expectedDates": "、".join(value.isoformat() for value in expected)},
        )


def resolve_plan_confirm_target(payload: PlanConfirmPayload) -> tuple[str, str]:
    return "goal", payload.goal_id


async def apply_plan_confirm(session: AsyncSession, proposal: AgentProposal) -> PlanConfirmResult:
    """OP_PLAN_CONFIRM 应用器（提案框架契约：调用方事务内、不得自行 begin）。

    执行前重验（目标可达 + 快照比对 + 状态依赖约束）已由注册表适配器与
    capture 完成存储层前置；此处经领域核心落库（require_no_active 与部分
    唯一索引仍是并发兜底）。
    """
    payload = parse_operation_payload(proposal, PlanConfirmPayload)
    goal = await GoalService.get(session, payload.goal_id)
    if goal is None:
        raise CodedHTTPException(
            code="GOAL_NOT_FOUND", status_code=404, detail="目标不存在或所属课程已删除"
        )
    if goal.status != "ACTIVE":
        raise CodedHTTPException(
            code="GOAL_NOT_ACTIVE",
            status_code=409,
            detail="目标已完结或归档，只有进行中的目标可以制定计划",
        )
    plan = await PlanService.confirm_core(session, goal, payload)
    dates = sorted(item.scheduled_date for phase in payload.phases for item in phase.items)
    return PlanConfirmResult(
        plan_id=plan.id,
        goal_id=goal.id,
        course_id=goal.course_id,
        plan_version=plan.plan_version,
        item_count=len(dates),
        first_date=dates[0] if dates else None,
        last_date=dates[-1] if dates else None,
    )


register_operation(
    OperationSpec(
        action=CONFIRM_PLAN_ACTION,
        proposal_type=ProposalType.OP_PLAN_CONFIRM,
        level=OperationLevel.L2,
        payload_schema=PlanConfirmPayload,
        result_schema=PlanConfirmResult,
        applier=apply_plan_confirm,
        capture_state=capture_plan_confirm_state,
        target_resolver=resolve_plan_confirm_target,
        undo_reason="计划确认暂不在撤销范围；调整或重生成能力随后续工单提供",
    )
)
