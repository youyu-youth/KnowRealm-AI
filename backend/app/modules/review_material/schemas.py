import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
)


class ReviewMaterialStatus(StrEnum):
    GENERATED = "GENERATED"
    CONFIRMED = "CONFIRMED"
    SUPERSEDED = "SUPERSEDED"


class ReviewMaterialContent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    quick_review: str = Field(min_length=1, max_length=5000, description="考前速记 Markdown")
    key_list: list[str] = Field(
        min_length=1,
        max_length=50,
        description="按内容密度生成的 Top 重点清单",
    )
    mind_map_markdown: str = Field(
        min_length=1,
        max_length=5000,
        description="仅含标题与列表行的 Markdown 大纲",
    )

    @field_validator("key_list")
    @classmethod
    def validate_key_list(cls, value: list[str]) -> list[str]:
        items = [item.strip() for item in value]
        if any(not item or len(item) > 80 for item in items):
            raise ValueError("重点清单每项必须为 1 至 80 字")
        return items

    @field_validator("mind_map_markdown")
    @classmethod
    def validate_mind_map(cls, value: str) -> str:
        return check_mind_map_lines(value)

    @classmethod
    def from_draft(cls, draft: "ReviewMaterialDraft") -> "ReviewMaterialContent":
        """宽松草稿 → 严格契约：超长清单项按标点确定性切分。"""
        return cls(
            quick_review=draft.quick_review,
            key_list=split_key_items(draft.key_list),
            mind_map_markdown=draft.mind_map_markdown,
        )


class ReviewMaterialDraft(BaseModel):
    """LLM 产出的宽松校验版：flash 级模型稳定写超 80 字清单项且无法按提示纠正，
    每项长度在此不设限，由 from_draft 切分归一；其余约束与严格版一致。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    quick_review: str = Field(min_length=1, max_length=5000, description="考前速记 Markdown")
    key_list: list[Annotated[str, StringConstraints(min_length=1)]] = Field(
        min_length=1,
        max_length=50,
        description="按内容密度生成的 Top 重点清单",
    )
    mind_map_markdown: str = Field(
        min_length=1,
        max_length=5000,
        description="仅含标题与列表行的 Markdown 大纲",
    )

    @field_validator("mind_map_markdown")
    @classmethod
    def validate_mind_map(cls, value: str) -> str:
        return check_mind_map_lines(value)


_KEY_ITEM_MAX_LENGTH = 80
_KEY_ITEM_SPLITTERS = "。；;，,、"


def check_mind_map_lines(value: str) -> str:
    allowed = re.compile(r"^(?:#{1,6}\s+\S|[-*+]\s+\S|\d+[.)]\s+\S)")
    if any(line.strip() and not allowed.match(line.strip()) for line in value.splitlines()):
        raise ValueError("Markdown 大纲只能包含标题与列表行")
    return value


def split_key_items(items: list[str]) -> list[str]:
    """超 80 字清单项按句读切分为多条；无标点可切时硬切；总数截到 50。"""
    result: list[str] = []
    for raw in items:
        text = raw.strip()
        while len(text) > _KEY_ITEM_MAX_LENGTH:
            cut = max(
                text.rfind(ch, 1, _KEY_ITEM_MAX_LENGTH + 1) for ch in _KEY_ITEM_SPLITTERS
            )
            if cut <= 0:
                cut = _KEY_ITEM_MAX_LENGTH
            piece = text[:cut].strip(_KEY_ITEM_SPLITTERS + " ")
            if piece:
                result.append(piece)
            text = text[cut:].lstrip(_KEY_ITEM_SPLITTERS + " ")
        if text:
            result.append(text)
    return result[:50]


class ReviewMaterialAction(StrEnum):
    NONE = "NONE"
    CONFIGURE_PROVIDER = "CONFIGURE_PROVIDER"
    GRANT_CONSENT = "GRANT_CONSENT"
    GENERATE = "GENERATE"
    RETRY = "RETRY"


class ReviewMaterialBlockedReason(StrEnum):
    SUMMARY_NOT_CONFIRMED = "SUMMARY_NOT_CONFIRMED"
    COURSE_ARCHIVED = "COURSE_ARCHIVED"
    TRANSCRIPT_NOT_READY = "TRANSCRIPT_NOT_READY"


class ReviewMaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    record_id: str
    version_no: int
    transcript_source_version: int
    generated_from_summary_id: str | None
    quick_review: str
    key_list: list[str]
    mind_map_markdown: str
    status: ReviewMaterialStatus
    model: str
    prompt_version: str
    user_feedback: str | None = None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class ReviewMaterialReadOut(BaseModel):
    review_material: ReviewMaterialOut | None
    action_required: ReviewMaterialAction
    blocked_reason: ReviewMaterialBlockedReason | None = None
    active_job_id: str | None = None
    transcript_stale: bool = False


class ReviewMaterialAdjustRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    feedback: str = Field(min_length=1, max_length=1000, description="调整反馈")


class ReviewMaterialJobAccepted(BaseModel):
    job_id: str
