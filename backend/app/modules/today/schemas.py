from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_serializer


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
    total_ms: int = Field(description="当日学习时长（毫秒），无学习为 0")
