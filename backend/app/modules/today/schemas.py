from datetime import UTC, date, datetime

from pydantic import BaseModel, Field, field_serializer

from app.modules.learning_plan.schemas import PlanItemType


class TodaySummaryTodoOut(BaseModel):
    record_id: str
    title: str
    course_id: str
    course_name: str
    ready_at: datetime

    @field_serializer("ready_at")
    def serialize_ready_at(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class TodayPlanItemOut(BaseModel):
    """今日待学的计划项投影（跨空间）：排期日 ≤ 今天且未完成的 ACTIVE 计划项。

    勾选完成走课程嵌套的计划项端点（item_id + plan_id + course_id 三元组即
    完整定位）；goal_title / course_name 供分组标注来源。
    """

    item_id: str
    plan_id: str
    course_id: str
    course_name: str = Field(description="来源知识空间名（跨空间并列标注）")
    goal_id: str
    goal_title: str
    action_type: PlanItemType
    content: str
    estimated_minutes: int | None = Field(default=None, description="预估投入分钟数")
    scheduled_date: date = Field(description="排期日期（早于今天即逾期）")
    user_locked: bool = Field(description="用户锁定项（重生成原样保留）")


class TodayStatsOut(BaseModel):
    total_learning_ms: int = Field(description="累计学习时长（毫秒），仅音频类记录贡献")
    record_count: int = Field(description="学习记录总数（含失败、速记、收件箱未归类）")
    course_count: int = Field(description="课程总数（含已归档）")
    ai_summary_count: int = Field(description="AI 总结次数（含重新生成版本）")
    quiz_generated_count: int = Field(description="习题生成次数（含历史批次）")
    quiz_answered_count: int = Field(description="习题完成次数（逐题作答口径）")
    chat_turn_count: int = Field(description="问答轮次（用户提问消息数）")


class TodayTrendPointOut(BaseModel):
    date: str = Field(description="捕获日（ISO 日期）")
    total_ms: int = Field(
        description="当日学习时长（毫秒）＝记录捕获时长＋当日完成计划项的预估时长，无学习为 0"
    )
