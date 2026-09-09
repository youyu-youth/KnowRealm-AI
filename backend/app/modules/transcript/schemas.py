from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class AsrChunkStatus(StrEnum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class TranscriptAvailability(StrEnum):
    NOT_READY = "NOT_READY"
    READY = "READY"


class TranscriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    language: str
    content: str
    source_version: int
    edited_by_user: bool
    updated_at: datetime

    @field_serializer("updated_at")
    def serialize_utc(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class TranscriptReadOut(BaseModel):
    status: TranscriptAvailability
    transcript: TranscriptOut | None


class TranscriptSegmentOut(BaseModel):
    """句级转写分片：时间戳为 NULL 表示无时间轴来源（全库唯一退化态）。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    sequence_no: int = Field(description="课堂全局连续序号（跨文件递增）")
    record_start_ms: int | None = Field(
        description="课堂拼接时间轴起点（前序文件时长累加）；无时间轴来源为 null"
    )
    record_end_ms: int | None = Field(description="课堂拼接时间轴终点")
    file_start_ms: int | None = Field(description="文件内时间轴起点")
    file_end_ms: int | None = Field(description="文件内时间轴终点")
    speaker: str | None = Field(description="说话人；恒为 null（说话人分离预留）")
    content: str


class TranscriptUpdateRequest(BaseModel):
    content: str = Field(min_length=1)
    expected_source_version: int = Field(ge=1)
