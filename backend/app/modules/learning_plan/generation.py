"""学习计划生成服务（通用 Agent 第三阶段工单 02）。

两条路径（spec 用户故事 7/8）：
- 有资料：聚合课程可见记录（标题 + 已确认总结摘要）＋ 复用既有检索
  （LibraryRetrievalService，COURSE 范围逐字引文）作为生成上下文，LLM 产出
  结构化草案，再由确定性排期器铺排日期；
- 无资料（纯目标起点）：LLM 产出建议学习内容 + 资料缺口清单，引导补充资料。

草案不持久化（spec 用户故事 11）：本服务零业务写，learning_plans 仅在用户
经确认卡确认后由 PlanService.confirm_core 写入。LLM 失败复用
StructuredGenerationError 稳定错误码；铺不开抛 ScheduleInfeasible，均由
Agent 工具转结构化载荷交模型如实转述。
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.learning_plan.models import LearningGoal
from app.modules.learning_plan.scheduling import (
    DEFAULT_DAILY_MINUTES,
    ScheduleConstraints,
    pack_schedule,
)
from app.modules.learning_plan.schemas import (
    PlanConfirmCore,
    PlanConfirmItem,
    PlanConfirmPhase,
    PlanDraft,
    PlanSuggestions,
)
from app.modules.library.retrieval import (
    SEARCH_LIBRARY_LIMIT,
    LibraryRetrievalService,
    RetrievalScope,
)
from app.modules.library.schemas import ChatScope
from app.modules.llm.service import (
    OpenAiCompatiblePlanDraftModel,
    OpenAiCompatiblePlanSuggestionsModel,
    PlanDraftModel,
    PlanSuggestionsModel,
    call_plan_draft_model,
    call_plan_suggestions_model,
)
from app.modules.record.models import Record
from app.modules.settings.config import LlmProviderConfig
from app.modules.summary.models import AiSummary
from app.modules.summary.schemas import AiSummaryStatus

# 生成 prompt 版本（评测黄金集回归触发点，随模型可见面变化 bump）。
PLAN_PROMPT_VERSION = "learning-plan-v1"

# 生成上下文预算：单条总结摘要 / 单条引文截断与资料条数上限（防 prompt 膨胀）。
SUMMARY_EXCERPT_MAX_CHARS = 500
EVIDENCE_QUOTE_MAX_CHARS = 200
MATERIALS_MAX_COUNT = 30
EVIDENCE_MAX_COUNT = 8

# 学习对象提示词表（action_type 语义进生成契约）。
_ACTION_TYPE_GUIDE = (
    "STUDY_RECORD=学习一份已有资料（课前预习 / 精读，可关联 record_id）、"
    "PRACTICE_QUIZ=做习题巩固、REVIEW_CONCEPT=复习已学概念、CUSTOM=自由任务"
)


@dataclass(frozen=True)
class MaterialDigest:
    """课程可见资料摘要行：标题 + 已确认总结（无总结仅标题）。"""

    record_id: str
    title: str
    capture_type: str
    summary_excerpt: str


@dataclass(frozen=True)
class EvidenceDigest:
    """复用既有检索取得的逐字引文行（COURSE 范围，来源标题 + 截断引文）。"""

    source_title: str
    quote: str


@dataclass(frozen=True)
class PlanGenerationOutcome:
    """生成结果：DRAFT=带日期草案（确认载荷形状）／SUGGESTIONS=建议与缺口。"""

    kind: str
    plan: PlanConfirmCore | None = None
    suggestions: PlanSuggestions | None = None
    total_minutes: int = 0
    constraints: ScheduleConstraints | None = None
    materials_used: int = 0


def constraints_for(goal: LearningGoal, today: date) -> ScheduleConstraints:
    """目标 → 排期约束：期限与每日投入缺省时无界 / 用默认日预算。"""
    deadline = date.fromisoformat(goal.target_date) if goal.target_date is not None else None
    daily = goal.daily_minutes if goal.daily_minutes is not None else DEFAULT_DAILY_MINUTES
    return ScheduleConstraints(start_date=today, deadline=deadline, daily_minutes=daily)


class PlanGenerationService:
    @staticmethod
    async def gather_materials(session: AsyncSession, course_id: str) -> list[MaterialDigest]:
        """课程可见记录 + 已确认总结摘要（复用既有查询面，零新检索设施）。"""
        records = list(
            (
                await session.execute(
                    select(Record.id, Record.title, Record.capture_type)
                    .where(Record.course_id == course_id, Record.deleted_at.is_(None))
                    .order_by(Record.created_at)
                    .limit(MATERIALS_MAX_COUNT)
                )
            ).all()
        )
        if not records:
            return []
        summary_rows = (
            await session.execute(
                select(AiSummary.record_id, AiSummary.topic, AiSummary.abstract).where(
                    AiSummary.record_id.in_([row[0] for row in records]),
                    AiSummary.status == AiSummaryStatus.CONFIRMED.value,
                    AiSummary.deleted_at.is_(None),
                )
            )
        ).all()
        summaries = {row[0]: (row[1], row[2]) for row in summary_rows}
        digests: list[MaterialDigest] = []
        for record_id, title, capture_type in records:
            summary = summaries.get(record_id)
            excerpt = ""
            if summary is not None:
                excerpt = f"{summary[0]}：{summary[1]}".strip()[:SUMMARY_EXCERPT_MAX_CHARS]
            digests.append(
                MaterialDigest(
                    record_id=record_id,
                    title=title,
                    capture_type=capture_type,
                    summary_excerpt=excerpt,
                )
            )
        return digests

    @staticmethod
    async def retrieve_evidence(
        session: AsyncSession, course_id: str, query: str
    ) -> list[EvidenceDigest]:
        """复用既有 COURSE 范围检索：目标标题为查询词，逐字引文作内容佐证。"""
        result = await LibraryRetrievalService.search(
            session,
            RetrievalScope(scope=ChatScope.COURSE, course_id=course_id),
            query,
            SEARCH_LIBRARY_LIMIT,
        )
        return [
            EvidenceDigest(
                source_title=hit.source_title, quote=hit.quote[:EVIDENCE_QUOTE_MAX_CHARS]
            )
            for hit in result.evidence_hits[:EVIDENCE_MAX_COUNT]
        ]

    @staticmethod
    def build_draft_prompt(
        goal: LearningGoal,
        today: date,
        materials: list[MaterialDigest],
        evidence: list[EvidenceDigest],
        constraints: ScheduleConstraints,
    ) -> str:
        lines = [
            "你是学习计划设计师。基于以下学习目标与课程资料生成学习计划草案。",
            "",
            "【学习目标】",
            f"- 类型：{goal.goal_type}；标题：{goal.title}",
        ]
        if goal.target_date is not None:
            lines.append(f"- 期限：{goal.target_date}")
        if goal.daily_minutes is not None:
            lines.append(f"- 计划每日投入：{goal.daily_minutes} 分钟")
        if goal.target_score is not None:
            lines.append(f"- 目标分数：{goal.target_score}")
        lines += [
            "",
            "【排期约束（日期由系统按项序铺排，你不要安排日期）】",
            f"- 今日：{today.isoformat()}；排期从今日开始",
        ]
        if constraints.deadline is not None:
            capacity_days = (constraints.deadline - today).days + 1
            capacity_minutes = max(0, capacity_days) * constraints.daily_minutes
            lines += [
                f"- 期限：{constraints.deadline.isoformat()}（含今日共 {capacity_days} 天）",
                f"- 每日预算：{constraints.daily_minutes} 分钟；"
                f"全部计划项总时长不要超过约 {capacity_minutes} 分钟",
            ]
        else:
            lines.append(
                f"- 无期限；每日预算：{constraints.daily_minutes} 分钟，按合理节奏安排总量"
            )
        lines += ["", "【课程资料】"]
        if materials:
            for material in materials:
                entry = f"- record_id={material.record_id}《{material.title}》"
                if material.summary_excerpt:
                    entry += f"：{material.summary_excerpt}"
                lines.append(entry)
        else:
            lines.append("（无）")
        if evidence:
            lines += ["", "【资料内容引文（逐字摘录，可用于把握主题侧重）】"]
            for hit in evidence:
                lines.append(f"- 《{hit.source_title}》：{hit.quote}")
        lines += [
            "",
            "【输出要求】",
            "1. 分 2~5 个阶段（阶段标题简短），每阶段 1~8 个计划项，按学习顺序排列；",
            f"2. 每个计划项给出：action_type（{_ACTION_TYPE_GUIDE}）、content"
            "（具体做什么，80 字内）、estimated_minutes（预估分钟）、reason"
            "（为什么这样安排，60 字内）；",
            "3. action_type=STUDY_RECORD 且【课程资料】中有对应资料时，"
            "把该资料的 record_id 原样填入 record_id 字段（没有就省略，不要编造）；",
            "4. 计划应贴着资料内容与目标期限，总量不超过排期约束中的容量。",
        ]
        return "\n".join(lines)

    @staticmethod
    def build_suggestions_prompt(goal: LearningGoal) -> str:
        lines = [
            "你是学习规划顾问。学习者设定了学习目标，但课程内还没有任何资料，"
            "无法生成正式学习计划。请给出建议学习内容与资料缺口清单。",
            "",
            "【学习目标】",
            f"- 类型：{goal.goal_type}；标题：{goal.title}",
        ]
        if goal.target_date is not None:
            lines.append(f"- 期限：{goal.target_date}")
        if goal.daily_minutes is not None:
            lines.append(f"- 计划每日投入：{goal.daily_minutes} 分钟")
        lines += [
            "",
            "【输出要求】",
            "1. suggested_contents：3~8 条建议学习的内容主题"
            "（title 主题名 + why 为什么值得先学）；",
            "2. material_gaps：2~6 条资料缺口（what 缺什么资料 + why 为什么需要它），"
            "按对达成目标的重要性排序。",
        ]
        return "\n".join(lines)

    @staticmethod
    def _pack_draft(
        draft: PlanDraft, goal_id: str, constraints: ScheduleConstraints
    ) -> PlanConfirmCore:
        """草案 + 排期约束 → 确认载荷形状（排期器铺不开抛 ScheduleInfeasible）。"""
        minutes = [item.estimated_minutes for phase in draft.phases for item in phase.items]
        dates = pack_schedule(minutes, constraints)
        phases: list[PlanConfirmPhase] = []
        index = 0
        for phase in draft.phases:
            items = [
                PlanConfirmItem(
                    **item.model_dump(),
                    scheduled_date=dates[index + offset],
                )
                for offset, item in enumerate(phase.items)
            ]
            index += len(phase.items)
            phases.append(PlanConfirmPhase(title=phase.title, items=items))
        return PlanConfirmCore(goal_id=goal_id, phases=phases)

    @staticmethod
    async def generate(
        *,
        session_factory: async_sessionmaker[AsyncSession],
        goal: LearningGoal,
        provider: LlmProviderConfig,
        today: date,
        materials: list[MaterialDigest],
        evidence: list[EvidenceDigest],
        draft_model: PlanDraftModel | None = None,
        suggestions_model: PlanSuggestionsModel | None = None,
    ) -> PlanGenerationOutcome:
        """按资料有无分流的生成入口（调用方不持 DB 会话，LLM 调用期间零连接占用）。

        草案路径返回确认载荷形状（含排期日期）与总量；无资料路径返回建议与
        缺口。LLM 失败抛 StructuredGenerationError（稳定错误码），总量铺不开
        抛 ScheduleInfeasible，均由 Agent 工具转结构化载荷。
        """
        if not materials:
            result = await call_plan_suggestions_model(
                session_factory=session_factory,
                plan_suggestions_model=(
                    suggestions_model or OpenAiCompatiblePlanSuggestionsModel()
                ),
                provider=provider,
                prompt=PlanGenerationService.build_suggestions_prompt(goal),
                prompt_version=PLAN_PROMPT_VERSION,
            )
            return PlanGenerationOutcome(kind="SUGGESTIONS", suggestions=result.content)
        constraints = constraints_for(goal, today)
        result = await call_plan_draft_model(
            session_factory=session_factory,
            plan_draft_model=draft_model or OpenAiCompatiblePlanDraftModel(),
            provider=provider,
            prompt=PlanGenerationService.build_draft_prompt(
                goal, today, materials, evidence, constraints
            ),
            prompt_version=PLAN_PROMPT_VERSION,
        )
        plan = PlanGenerationService._pack_draft(result.content, goal.id, constraints)
        total = sum(item.estimated_minutes for phase in plan.phases for item in phase.items)
        return PlanGenerationOutcome(
            kind="DRAFT",
            plan=plan,
            total_minutes=total,
            constraints=constraints,
            materials_used=len(materials),
        )


def draft_summary(plan: PlanConfirmCore) -> str:
    """确认载荷 → 模型可见的单行摘要（工具载荷 message 用，轻量不复述全文）。"""
    items = [item for phase in plan.phases for item in phase.items]
    dates = [item.scheduled_date for item in items]
    span = f"{min(dates).isoformat()} ~ {max(dates).isoformat()}" if dates else "—"
    return (
        f"草案共 {len(plan.phases)} 个阶段、{len(items)} 个计划项，"
        f"排期 {span}（未保存，需用户确认后才落库）"
    )
