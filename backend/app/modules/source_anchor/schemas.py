from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SourceAnchorType(StrEnum):
    AUDIO_SEGMENT = "AUDIO_SEGMENT"
    DOCUMENT_SEGMENT = "DOCUMENT_SEGMENT"
    USER_NOTE = "USER_NOTE"
    CHAT_MESSAGE = "CHAT_MESSAGE"


class SourceAnchorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    course_id: str
    source_type: SourceAnchorType
    source_id: str
    record_id: str | None = Field(description="关联学习记录 id；非记录类来源为 null")
    record_file_id: str | None
    course_material_id: str | None
    transcript_segment_id: str | None
    document_segment_id: str | None
    start_offset: int | None
    end_offset: int | None
    page_no: int | None
