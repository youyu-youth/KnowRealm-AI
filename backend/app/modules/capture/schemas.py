from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class CaptureType(StrEnum):
    RECORDING = "RECORDING"
    AUDIO_IMPORT = "AUDIO_IMPORT"
    DOCUMENT_IMPORT = "DOCUMENT_IMPORT"
    MULTI_SOURCE = "MULTI_SOURCE"
    PASTE = "PASTE"
    QUICK_NOTE = "QUICK_NOTE"
    CLIP = "CLIP"


class RecordFileType(StrEnum):
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"


class RecordFileSourceType(StrEnum):
    RECORDED = "RECORDED"
    UPLOADED = "UPLOADED"


class RecordingSessionState(StrEnum):
    RECORDING = "RECORDING"
    PAUSED = "PAUSED"
    FINALIZING = "FINALIZING"
    DONE = "DONE"


class DocumentImportAccepted(BaseModel):
    record_id: str
    job_id: str


class AudioImportAccepted(BaseModel):
    record_id: str
    transcode_job_id: str
    asr_job_id: str


class CaptureBatchAccepted(BaseModel):
    record_id: str
    job_ids: list[str]


class TextCaptureCreate(BaseModel):
    capture_type: CaptureType
    content: str = Field(min_length=1)
    course_id: UUID | None = None


class TextCaptureAccepted(BaseModel):
    record_id: str
    summary_job_id: str | None
