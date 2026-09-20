"""learner 域 Pydantic 契约（工单 06）：学习画像「AI 记忆」视图与长期记忆外发开关。"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.modules.library.schemas import MemoryItemText

# 显式偏好条数上限：稳定偏好的短句表述集合，防自由文本情节记忆（ADR-0025）；
# 单条限长复用 library 域 MemoryItemText 的同一约束。
EXPLICIT_ITEMS_MAX_COUNT = 20


class MemoryOutboundOut(BaseModel):
    """长期记忆外发状态：enabled=独立开关；consent 绑定供应商身份（fingerprint）。"""

    enabled: bool
    consent_granted_at: str | None
    consent_current: bool


class LearnerPreferenceOut(BaseModel):
    """学习画像「AI 记忆」单例视图：显式偏好直编，观察偏好带置信度/证据数/确认时间。"""

    model_config = ConfigDict(from_attributes=True)

    explicit_items: list[str]
    observed_entries: dict[str, str]
    observed_confidence: float | None
    evidence_count: int
    last_observed_at: datetime | None
    updated_at: datetime
    memory_outbound: MemoryOutboundOut

    @field_serializer("last_observed_at", "updated_at")
    def _ser(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(UTC).isoformat()


class LearnerPreferenceUpdate(BaseModel):
    """显式偏好全量替换（契约 §2.5：PUT 立即生效）；观察偏好不经此端点。"""

    items: list[MemoryItemText] = Field(max_length=EXPLICIT_ITEMS_MAX_COUNT)


class MemoryOutboundUpdate(BaseModel):
    """外发开关载荷：关闭=记忆保留本地、不注入发给 LLM 的上下文。"""

    enabled: bool
