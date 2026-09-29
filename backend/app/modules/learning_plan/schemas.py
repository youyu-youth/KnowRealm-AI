"""学习计划域 API Schema：学习目标（工单 01）与学习计划草案 / 确认形状（工单 02）。

时间序列化统一 UTC ``Z``；target_date / scheduled_date 是按日的期限与排期
（YYYY-MM-DD，无时段）。
"""

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


def _serialize_utc(value: datetime) -> str:
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def clean_goal_title(value: str) -> str:
    """目标标题清洗（领域 schema 与 Agent 载荷 schema 共用）：去首尾空白、
    空白即拒；可选字段由调用方先判 None。"""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("目标标题不能为空白")
    return cleaned


class GoalType(StrEnum):
    SKILL = "SKILL"
    EXAM = "EXAM"
    PROJECT = "PROJECT"
    READING = "READING"
    CUSTOM = "CUSTOM"


class GoalScopeSource(StrEnum):
    """目标范围来源（spec 决策：AI_INFERRED 必须用户确认才生效）。"""

    USER_CONFIRMED = "USER_CONFIRMED"
    COURSE_SELECTION = "COURSE_SELECTION"
    AI_INFERRED = "AI_INFERRED"


class GoalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class GoalCreate(BaseModel):
    """HTTP 创建契约：页面 / Agent 应用器共用领域核心，本 schema 是页面入口。

    页面创建恒为用户确认范围（scope_source=USER_CONFIRMED）；Agent 路径的
    AI_INFERRED + 确认卡语义由应用器经领域核心参数传入，不走本 schema。
    """

    model_config = ConfigDict(extra="forbid")

    goal_type: GoalType = Field(description="目标类型")
    title: str = Field(min_length=1, max_length=200, description="目标标题")
    target_date: date | None = Field(default=None, description="期限（按日）")
    daily_minutes: int | None = Field(
        default=None, gt=0, le=24 * 60, description="计划每日投入分钟数"
    )
    target_score: float | None = Field(
        default=None, ge=0, le=100, description="目标分数（如考试目标分，可选）"
    )

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return clean_goal_title(value)


class GoalUpdate(BaseModel):
    """目标编辑契约（期限 / 每日投入 / 标题 / 目标分数）：仅 ACTIVE 目标可改。"""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200, description="目标标题")
    target_date: date | None = Field(default=None, description="期限（按日）")
    daily_minutes: int | None = Field(
        default=None, gt=0, le=24 * 60, description="计划每日投入分钟数"
    )
    target_score: float | None = Field(default=None, ge=0, le=100, description="目标分数（可选）")

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        return clean_goal_title(value) if value is not None else None


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    goal_type: GoalType
    title: str
    target_date: date | None = Field(default=None, description="期限（按日）")
    daily_minutes: int | None = Field(default=None, description="计划每日投入分钟数")
    target_score: float | None = Field(default=None, description="目标分数（可选）")
    scope_source: GoalScopeSource
    scope_confirmed: bool
    status: GoalStatus
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        return _serialize_utc(value)


class GoalCreateCore(BaseModel):
    """领域核心创建参数（HTTP 与 Agent 应用器共用）：scope 语义显式传入。

    Agent 路径传 scope_source=AI_INFERRED + scope_confirmed=True（确认卡即
    用户确认）；AI_INFERRED 未确认由领域核心拒绝（不变量，spec 用户故事 6）。
    """

    model_config = ConfigDict(extra="forbid")

    goal_type: GoalType
    title: str
    target_date: date | None = None
    daily_minutes: int | None = Field(default=None, gt=0, le=24 * 60)
    target_score: float | None = Field(default=None, ge=0, le=100)
    scope_source: GoalScopeSource = GoalScopeSource.USER_CONFIRMED
    scope_confirmed: bool = True

    @model_validator(mode="after")
    def _require_confirmed_scope(self) -> "GoalCreateCore":
        if self.scope_source == GoalScopeSource.AI_INFERRED and not self.scope_confirmed:
            raise ValueError("AI 推断的目标范围必须经用户确认")
        return self


# ---------------------------------------------------------------------------
# 学习计划（工单 02）：草案（LLM 结构化输出）、无资料建议、确认载荷与投影。
# 草案不持久化——learning_plans 仅在用户确认时写入（spec 用户故事 11）。
# ---------------------------------------------------------------------------


class PlanStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    COMPLETED = "COMPLETED"


class PlanItemType(StrEnum):
    """计划项动作四类（spec 领域模型定稿）：学习资料 / 做习题 / 复习概念 / 自由任务。"""

    STUDY_RECORD = "STUDY_RECORD"
    PRACTICE_QUIZ = "PRACTICE_QUIZ"
    REVIEW_CONCEPT = "REVIEW_CONCEPT"
    CUSTOM = "CUSTOM"


_UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


def clean_plan_text(value: str, message: str) -> str:
    """草案文本共享清洗（clean_goal_title 同模式）：去首尾空白、拒空白。"""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(message)
    return cleaned


class PlanDraftItem(BaseModel):
    """LLM 草案计划项（无日期——排期由确定性排期器分配，脚本优先 LLM 次之）。

    record_id 仅 STUDY_RECORD 且生成上下文给了资料清单时填写（应用器校验
    归属）；concept_id 预留 REVIEW_CONCEPT 关联（本期生成上下文不含概念清单，
    恒缺省）。
    """

    model_config = ConfigDict(extra="forbid")

    action_type: PlanItemType = Field(description="动作类型")
    content: str = Field(min_length=1, max_length=200, description="具体要做什么")
    estimated_minutes: int = Field(gt=0, le=600, description="预估投入分钟数（1~600）")
    reason: str = Field(min_length=1, max_length=300, description="逐项生成理由")
    record_id: str | None = Field(
        default=None, pattern=_UUID_PATTERN, description="学习对象记录 id（仅 STUDY_RECORD）"
    )
    concept_id: str | None = Field(
        default=None, pattern=_UUID_PATTERN, description="复习概念 id（仅 REVIEW_CONCEPT）"
    )

    @field_validator("content", "reason")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return clean_plan_text(value, "计划项内容与理由不能为空白")


class PlanDraftPhase(BaseModel):
    """LLM 草案阶段：分组标签 + 顺序排列的计划项（排期按此顺序贪心铺排）。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=60, description="阶段标题")
    items: list[PlanDraftItem] = Field(min_length=1, max_length=15, description="本阶段计划项")

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value: str) -> str:
        return clean_plan_text(value, "阶段标题不能为空白")


class PlanDraft(BaseModel):
    """LLM 结构化草案输出（工单 02 生成契约）：阶段划分 + 逐项内容 / 时长 / 理由。"""

    model_config = ConfigDict(extra="forbid")

    phases: list[PlanDraftPhase] = Field(min_length=1, max_length=8, description="阶段划分")


class PlanSuggestedContent(BaseModel):
    """无资料路径的建议学习内容条目。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120, description="建议学习的内容主题")
    why: str = Field(min_length=1, max_length=300, description="为什么值得先学")

    @field_validator("title", "why")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return clean_plan_text(value, "建议内容不能为空白")


class PlanMaterialGap(BaseModel):
    """无资料路径的资料缺口条目（引导用户补充资料后再生成正式计划）。"""

    model_config = ConfigDict(extra="forbid")

    what: str = Field(min_length=1, max_length=120, description="缺什么资料")
    why: str = Field(min_length=1, max_length=300, description="为什么需要它")

    @field_validator("what", "why")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        return clean_plan_text(value, "资料缺口不能为空白")


class PlanSuggestions(BaseModel):
    """无资料路径的 LLM 结构化输出（spec 用户故事 8）：建议学习内容 + 资料缺口。"""

    model_config = ConfigDict(extra="forbid")

    suggested_contents: list[PlanSuggestedContent] = Field(
        min_length=1, max_length=10, description="建议学习内容"
    )
    material_gaps: list[PlanMaterialGap] = Field(
        min_length=1, max_length=10, description="资料缺口清单"
    )


class PlanConfirmItem(PlanDraftItem):
    """确认载荷计划项：草案项 + 确定性排期器分配的日期（按日）。"""

    scheduled_date: date = Field(description="排期日期（YYYY-MM-DD，由排期器分配）")


class PlanConfirmPhase(BaseModel):
    """确认载荷阶段：草案阶段 + 携带日期的计划项。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=60, description="阶段标题")
    items: list[PlanConfirmItem] = Field(min_length=1, max_length=15, description="本阶段计划项")


class PlanConfirmCore(BaseModel):
    """确认载荷领域核心（Agent 载荷与排期校验共用）：goal + 带日期的阶段草案。"""

    model_config = ConfigDict(extra="forbid")

    goal_id: str = Field(pattern=_UUID_PATTERN, description="目标学习目标 id")
    phases: list[PlanConfirmPhase] = Field(min_length=1, max_length=8, description="阶段草案")


class PlanItemOut(BaseModel):
    """计划项投影（get_plan 工具与后续计划 Tab 路由共用）。"""

    id: str
    action_type: PlanItemType
    content: str
    record_id: str | None = None
    concept_id: str | None = None
    phase_title: str
    priority: int
    estimated_minutes: int | None = None
    scheduled_date: date
    status: str
    user_locked: bool
    reason: str | None = None


class PlanOut(BaseModel):
    """计划版本投影（只读消费面；progress 派生项数由调用方按需扩展）。"""

    id: str
    goal_id: str
    course_id: str
    plan_version: int
    status: PlanStatus
    effective_from: date
    effective_to: date | None = None
    items: list[PlanItemOut]
