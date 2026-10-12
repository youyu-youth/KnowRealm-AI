"""重生成学习计划工具（通用 Agent 第三阶段工单 03）：regenerate_plan。

目标或偏好变化时重排计划：读取当前 ACTIVE 版本的 user_locked 项（原样保留
不被 AI 重排）→ LLM 为其余部分产出新草案（生成上下文含锁定项清单，避免
重复安排）→ 确定性排期器在「每日预算 − 锁定占用」的剩余容量内铺排 →
组装 L2 换代载荷提交确认卡（载荷由工具构造、不经模型转述）。确认后旧版
SUPERSEDED 只读保留、新版本生效（spec 用户故事 15~16）。载荷派生基线在
LLM 调用前固化，提交时比对——窗口内目标 / 版本 / 锁定项被并发修改则拒绝
提交，不覆盖新状态。
"""

import json
from datetime import date
from itertools import groupby

from langchain_core.tools import tool
from loguru import logger
from sqlalchemy import select

from app.modules.agent.budget.service import budgeted
from app.modules.agent.operations.plan_regenerate import (
    REGENERATE_PLAN_ACTION,
    build_plan_regenerate_snapshot,
)
from app.modules.agent.operations.registry import submit_operation
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.turns.effects import EffectStatus, current_tool_call_identity
from app.modules.agent.turns.models import ChatTurnToolEffect
from app.modules.learning_plan.generation import (
    LockedDigest,
    PlanGenerationService,
    constraints_for,
)
from app.modules.learning_plan.models import LearningPlanItem
from app.modules.learning_plan.scheduling import (
    ScheduleInfeasible,
    local_today,
    pack_schedule_with_fixed,
)
from app.modules.learning_plan.schemas import (
    PlanConfirmCore,
    PlanItemType,
    PlanRegenerateCore,
    PlanRegenerateItem,
    PlanRegeneratePhase,
)
from app.modules.learning_plan.service import GoalService, PlanService, reason_of
from app.modules.llm.service import StructuredGenerationError

# 工具名（langchain @tool 注册名 = 函数名）。
REGENERATE_PLAN_TOOL_NAME = "regenerate_plan"

# 锁定项缺理由时的占位（正常不可达：确认落库恒写 reason_json）。
_LOCKED_FALLBACK_REASON = "用户锁定保留的计划项"


def _locked_phase(items: list[LearningPlanItem]) -> PlanRegeneratePhase:
    """锁定项组 → 载荷阶段：安排字段原样复制，状态不结转（归 PENDING）。"""
    return PlanRegeneratePhase(
        title=items[0].phase_title,
        items=[
            PlanRegenerateItem(
                action_type=PlanItemType(item.action_type),
                content=item.content,
                estimated_minutes=item.estimated_minutes or 30,
                reason=reason_of(item.reason_json) or _LOCKED_FALLBACK_REASON,
                record_id=item.record_id,
                concept_id=item.concept_id,
                scheduled_date=date.fromisoformat(item.scheduled_date),
                user_locked=True,
            )
            for item in items
        ],
    )


def build_regenerate_payload(
    goal_id: str,
    locked_items: list[LearningPlanItem],
    draft: PlanConfirmCore,
    dates: list[date],
) -> PlanRegenerateCore:
    """换代载荷组装（纯函数，测试缝）：锁定项按原阶段分组在前 + 新草案阶段
    在后（草案项按顺序取 dates 铺排，覆盖草案原全容量排期）。"""
    phases = [
        _locked_phase(list(group))
        for _title, group in groupby(locked_items, key=lambda item: item.phase_title)
    ]
    index = 0
    for phase in draft.phases:
        items = [
            PlanRegenerateItem(
                **item.model_dump(exclude={"scheduled_date"}),
                scheduled_date=dates[index + offset],
                user_locked=False,
            )
            for offset, item in enumerate(phase.items)
        ]
        index += len(phase.items)
        phases.append(PlanRegeneratePhase(title=phase.title, items=items))
    return PlanRegenerateCore(goal_id=goal_id, phases=phases)


def _budget_rejection() -> str:
    return json.dumps(
        {
            "ok": False,
            "error": "TOOL_CALL_LIMIT",
            "message": "本轮工具调用已达上限，请基于已获得的结果回答。",
        },
        ensure_ascii=False,
    )


@tool
@budgeted(_budget_rejection)
async def regenerate_plan(goal_id: str) -> str:
    """为目标重新生成学习计划（写操作，需用户在确认卡确认）：用户说「重新排一份计划 /
    目标变了帮我重排」且该目标已有生效计划时使用。

    当前版本中用户手动锁定过的计划项会原样保留（日期 / 时长 / 内容不变，
    不被 AI 重排），其余部分基于课程资料重新生成；确认后旧版本只读保留、
    新版本生效。必须传 goal_id（先用 list_goals 确认）；目标还没有生效计划
    时改用 generate_learning_plan。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"}, ensure_ascii=False)
    identity = current_tool_call_identity()
    if runtime.turn_id is not None and identity is not None:
        # 原始工具参数已由预算准入核对；成功回执优先于重新生成及目标状态读取。
        async with runtime.session_factory() as session, session.begin():
            if not await runtime.turn_write_allowed(session):
                return _structured_failure("CHAT_TURN_CANCELLED", "该轮次已停止")
            effect = await session.scalar(
                select(ChatTurnToolEffect).where(
                    ChatTurnToolEffect.turn_id == runtime.turn_id,
                    ChatTurnToolEffect.namespace == identity.namespace,
                    ChatTurnToolEffect.logical_call_id == identity.logical_call_id,
                    ChatTurnToolEffect.effect_index == 0,
                    ChatTurnToolEffect.tool_name == REGENERATE_PLAN_ACTION,
                    ChatTurnToolEffect.status == EffectStatus.SUCCEEDED.value,
                )
            )
            if effect is not None and effect.result_json is not None:
                return effect.result_json
    if runtime.llm_provider is None or not runtime.llm_provider.api_key:
        return json.dumps({"ok": False, "error": "LLM_PROVIDER_UNCONFIGURED"}, ensure_ascii=False)
    today = local_today()
    try:
        async with runtime.session_factory() as session:
            goal = await GoalService.get(session, goal_id)
            if goal is None:
                return _structured_failure("GOAL_NOT_FOUND", "目标不存在或所属课程已删除")
            if goal.status != "ACTIVE":
                return _structured_failure(
                    "GOAL_NOT_ACTIVE", "目标已完结或归档，只有进行中的目标可以重生成计划。"
                )
            active = await PlanService.get_active_for_goal(session, goal.id)
            if active is None:
                return _structured_failure(
                    "PLAN_NOT_FOUND",
                    "该目标还没有生效的学习计划；首次生成请用 generate_learning_plan。",
                )
            locked_items = [
                item
                for item in await PlanService.list_items(session, active.id)
                if item.user_locked
            ]
            materials = await PlanGenerationService.gather_materials(session, goal.course_id)
            evidence = await PlanGenerationService.retrieve_evidence(
                session, goal.course_id, goal.title
            )
            # 载荷派生基线（LLM 前固化，窗口竞态防线）：提交时与当前态比对，
            # 偏离即拒绝——旧载荷不得绑定新快照丢失窗口内的锁定编辑
            # （spec 用户故事 15「锁定项原样保留」）。
            basis_json = (
                await build_plan_regenerate_snapshot(session, goal, active)
            ).model_dump_json()
        # LLM 调用期间不占 DB 连接（与 generate_learning_plan 同模式）。
        if not materials:
            return _structured_failure(
                "PLAN_REGENERATE_NO_MATERIALS",
                "课程当前没有可用资料，无法重新生成计划；请先补充资料，"
                "或用 update_plan_item 逐项调整现有计划。",
            )
        locked_digests = [
            LockedDigest(
                scheduled_date=item.scheduled_date,
                content=item.content,
                minutes=item.estimated_minutes or 0,
            )
            for item in locked_items
        ]
        outcome = await PlanGenerationService.generate(
            session_factory=runtime.session_factory,
            goal=goal,
            provider=runtime.llm_provider,
            today=today,
            materials=materials,
            evidence=evidence,
            locked_items=locked_digests,
        )
        assert outcome.kind == "DRAFT" and outcome.plan is not None
        draft_minutes = [
            item.estimated_minutes for phase in outcome.plan.phases for item in phase.items
        ]
        dates = pack_schedule_with_fixed(
            draft_minutes,
            [
                (date.fromisoformat(item.scheduled_date), item.estimated_minutes or 0)
                for item in locked_items
            ],
            constraints_for(goal, today),
        )
        payload = build_regenerate_payload(goal.id, locked_items, outcome.plan, dates)
    except StructuredGenerationError as exc:
        return json.dumps({"ok": False, "error": exc.code}, ensure_ascii=False)
    except ScheduleInfeasible as exc:
        return json.dumps(
            {
                "ok": False,
                "error": "PLAN_SCHEDULE_INFEASIBLE",
                "message": (
                    f"{exc}。保留项已占用部分每日预算，请建议用户延长期限、"
                    "提高每日投入，或先解锁部分保留项。"
                ),
            },
            ensure_ascii=False,
        )
    except Exception:
        logger.warning("regenerate_plan_failed", error_code="PLAN_REGENERATE_FAILED")
        return json.dumps({"ok": False, "error": "PLAN_REGENERATE_FAILED"}, ensure_ascii=False)
    result = await submit_operation(
        runtime,
        REGENERATE_PLAN_ACTION,
        payload.model_dump(mode="json"),
        basis_json=basis_json,
    )
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def _structured_failure(error: str, message: str) -> str:
    return json.dumps(
        {"ok": False, "error": error, "message": message},
        ensure_ascii=False,
        separators=(",", ":"),
    )
