"""confirm_plan 操作注册项（通用 Agent 第三阶段工单 02；确认卡编辑随工单 03）。

「基于这门课生成四周学习计划」→ generate_learning_plan 只读产出草案（零
落库）→ 模型把草案经 confirm_plan 原样提交 → OP_PLAN_CONFIRM 提案（草案
确认卡）→ 用户确认 → 应用器经领域核心写 learning_plans（ACTIVE）与
learning_plan_items（spec 用户故事 9/11：草案不持久化，确认才落库）。

L2（计划头 + 批量项创建）：AUTO_APPROVE 档仍落确认卡（spec「草案卡即确认
闸门」）、FULL_ACCESS 直执行。快照读取器承担状态依赖约束的提交时拒绝
（已有进行中计划 PLAN_ACTIVE_EXISTS 零提案）；排期重算比对是提交时专属
执法（submission_validator，工单 03 拆出：确认时不重跑——用户在确认卡上
的编辑是合法自由，边界由确认路径的草案编辑校验器承担）。重生成在
plan_regenerate（工单 03），不在本动作面。
"""

from datetime import UTC, date, datetime

from pydantic import ValidationError
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
from app.modules.course_brain.models import Concept
from app.modules.course_brain.schemas import ConceptStatus
from app.modules.learning_plan.generation import constraints_for
from app.modules.learning_plan.models import LearningGoal
from app.modules.learning_plan.scheduling import ScheduleInfeasible, pack_schedule
from app.modules.learning_plan.schemas import PlanConfirmCore, PlanRegenerateCore
from app.modules.learning_plan.service import GoalService, PlanService
from app.modules.library.models import AgentProposal
from app.modules.library.proposals import register_draft_edit_validator
from app.modules.library.schemas import ProposalType
from app.modules.record.models import Record
from app.shared.errors import CodedHTTPException

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
CONFIRM_PLAN_ACTION = "confirm_plan"


async def capture_plan_confirm_state(
    session: AsyncSession, payload: PlanConfirmPayload
) -> PlanConfirmStateSnapshot:
    """状态读取与结构化校验（提交与确认两路共用，零提案拒绝）：

    - 目标不可达 / 非进行中 → GOAL_NOT_FOUND / GOAL_NOT_ACTIVE；
    - 已有进行中计划 → PLAN_ACTIVE_EXISTS（重生成走 regenerate_plan）；
    - STUDY_RECORD 引用的记录不属于本课程或不可见 → PLAN_DRAFT_INVALID；
    - REVIEW_CONCEPT 引用的概念不属于本课程或已归档 → PLAN_DRAFT_INVALID。
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
    await require_records_visible(session, goal.course_id, payload)
    await require_concepts_visible(session, goal.course_id, payload)
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


async def validate_plan_confirm_submission(
    session: AsyncSession, payload: PlanConfirmPayload
) -> None:
    """提交时专属执法（工单 03 拆出）：排期重算比对（模型转述草案漂移防线）。

    只在提交 / 直执行两路跑：确认时不重跑——用户在确认卡上的编辑改日期是
    合法自由，其边界由 validate_plan_draft_edit 承担（日期落在 [提交日, 期限]
    内即可）；目标态变化已由快照比对覆盖。
    """
    goal = await GoalService.get(session, payload.goal_id)
    if goal is None:
        raise CodedHTTPException(
            code="GOAL_NOT_FOUND", status_code=404, detail="目标不存在或所属课程已删除"
        )
    _require_schedule_matches(payload, goal, datetime.now(UTC).date())


async def validate_plan_draft_edit(
    session: AsyncSession, proposal: AgentProposal, edited_payload: dict[str, object]
) -> dict[str, object]:
    """确认卡编辑载荷校验（工单 03，spec 用户故事 9）：schema 执法 + 日期
    边界（不早于今天、不晚于目标期限），返回清洗后的载荷写入提案行——
    确认卡所见（编辑后）与落库所写保持同一份。

    编辑后的排期不要求与确定性铺排逐位一致（那是模型转述漂移的提交时
    防线）；每日总量与 daily_minutes 的一致性同样不强制——显式编辑即用户
    主权，边界只保「不落在区间外」。
    """
    try:
        payload = PlanConfirmPayload.model_validate(edited_payload)
    except ValidationError as exc:
        raise CodedHTTPException(
            code="PLAN_DRAFT_INVALID",
            status_code=422,
            detail="编辑后的草案结构无效，请检查日期、时长与内容",
        ) from exc
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
    today = datetime.now(UTC).date()
    deadline = date.fromisoformat(goal.target_date) if goal.target_date is not None else None
    for item in (i for phase in payload.phases for i in phase.items):
        if item.scheduled_date < today:
            raise CodedHTTPException(
                code="PLAN_DRAFT_INVALID",
                status_code=422,
                detail="编辑后的排期日期不能早于今天",
            )
        if deadline is not None and item.scheduled_date > deadline:
            raise CodedHTTPException(
                code="PLAN_DRAFT_INVALID",
                status_code=422,
                detail=f"编辑后的排期日期不能晚于目标期限 {deadline.isoformat()}",
            )
    return payload.model_dump(mode="json")


async def require_records_visible(
    session: AsyncSession, course_id: str, payload: PlanConfirmCore | PlanRegenerateCore
) -> None:
    """STUDY_RECORD 的 record_id 必须是本课程可见记录（防模型编造引用）。

    确认与重生成两动作共用（工单 03 起公开）。"""
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


async def require_concepts_visible(
    session: AsyncSession, course_id: str, payload: PlanConfirmCore | PlanRegenerateCore
) -> None:
    """REVIEW_CONCEPT 的 concept_id 必须是本课程未归档概念（防模型编造引用）。

    与 record_id 同口径的提交时校验：编造 / 他课 / 已归档概念在此拒绝并附
    可修正的领域错误（PLAN_DRAFT_INVALID），而不是等确认落库撞 FK 炸成
    INTERNAL（载荷已定、重试必再失败、模型无法自纠）。确认与重生成共用。
    """
    concept_ids = {
        item.concept_id
        for phase in payload.phases
        for item in phase.items
        if item.concept_id is not None
    }
    if not concept_ids:
        return
    visible = set(
        (
            await session.scalars(
                select(Concept.id).where(
                    Concept.id.in_(concept_ids),
                    Concept.course_id == course_id,
                    Concept.status != ConceptStatus.ARCHIVED.value,
                )
            )
        ).all()
    )
    missing = sorted(concept_ids - visible)
    if missing:
        raise CodedHTTPException(
            code="PLAN_DRAFT_INVALID",
            status_code=422,
            detail=(
                "草案引用了不属于本课程或已归档的概念（"
                + "、".join(missing)
                + "），请修正后重新提交"
            ),
            params={"conceptIds": ", ".join(missing)},
        )


def _require_schedule_matches(payload: PlanConfirmPayload, goal: LearningGoal, today: date) -> None:
    """排期确定性重算比对（spec：日期铺排由确定性校验承担；提交时防线）。

    锚点 = **提交日**（validate 传入的 today，可信生成日期）：草案提案活不过
    下一条用户消息（弃置语义），generate 与 confirm_plan 同轮流执行、两者
    today 一致——载荷日期必须与「从提交日起铺排」逐位一致；起点回挪（虚增
    期限容量，原 goal.updated_at 锚的漏洞）或起点后移（模型私选起点）都由
    比对直接拒绝并附期望日期。跨午夜的极端时序会拒掉合法草案，但拒错方向
    安全：错误附期望日期，模型按期望重交即自愈。
    """
    minutes = [item.estimated_minutes for phase in payload.phases for item in phase.items]
    claimed = [item.scheduled_date for phase in payload.phases for item in phase.items]
    assert claimed, "schema 保证至少一个计划项"
    try:
        expected = pack_schedule(minutes, constraints_for(goal, today))
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
        submission_validator=validate_plan_confirm_submission,
        undo_reason="计划确认暂不在撤销范围；调整或重生成用 update_plan_item / regenerate_plan",
    )
)
register_draft_edit_validator(ProposalType.OP_PLAN_CONFIRM, validate_plan_draft_edit)
