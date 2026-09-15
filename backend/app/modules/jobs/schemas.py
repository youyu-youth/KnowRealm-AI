from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProcessingJobType(StrEnum):
    AUDIO_TRANSCODE = "AUDIO_TRANSCODE"
    ASR = "ASR"
    DOCUMENT_PARSE = "DOCUMENT_PARSE"
    SUMMARY = "SUMMARY"
    KNOWLEDGE_EXTRACTION = "KNOWLEDGE_EXTRACTION"
    QUIZ_GENERATION = "QUIZ_GENERATION"
    TODO_GENERATION = "TODO_GENERATION"
    QUIZ_GRADING = "QUIZ_GRADING"
    REVIEW_MATERIAL_GENERATION = "REVIEW_MATERIAL_GENERATION"
    CONCEPT_EXTRACTION = "CONCEPT_EXTRACTION"


class ProcessingJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProcessingJobErrorCode(StrEnum):
    AUDIO_TRANSCODE_FAILED = "AUDIO_TRANSCODE_FAILED"
    ASR_AUTH_FAILED = "ASR_AUTH_FAILED"
    ASR_QUOTA_EXHAUSTED = "ASR_QUOTA_EXHAUSTED"
    ASR_TEMPORARY_UNAVAILABLE = "ASR_TEMPORARY_UNAVAILABLE"
    ASR_SUBMIT_UNKNOWN = "ASR_SUBMIT_UNKNOWN"
    ASR_RECOGNITION_FAILED = "ASR_RECOGNITION_FAILED"
    ASR_TASK_EXPIRED = "ASR_TASK_EXPIRED"
    NO_SPEECH_DETECTED = "NO_SPEECH_DETECTED"
    NON_UTF8_TEXT = "NON_UTF8_TEXT"
    CORRUPT_DOCUMENT = "CORRUPT_DOCUMENT"
    PASSWORD_PROTECTED = "PASSWORD_PROTECTED"
    FORMAT_MISMATCH = "FORMAT_MISMATCH"
    NO_EXTRACTABLE_TEXT = "NO_EXTRACTABLE_TEXT"
    TEMPORARY_IO = "TEMPORARY_IO"
    SQLITE_BUSY = "SQLITE_BUSY"
    WORKER_INTERRUPTED = "WORKER_INTERRUPTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_STRUCTURED_OUTPUT = "INVALID_STRUCTURED_OUTPUT"
    PROVIDER_REQUEST_FAILED = "PROVIDER_REQUEST_FAILED"
    STALE_TRANSCRIPT = "STALE_TRANSCRIPT"
    LLM_OUTPUT_INVALID = "LLM_OUTPUT_INVALID"


class ProcessingJobWaitingReason(StrEnum):
    CONSENT_REQUIRED = "CONSENT_REQUIRED"
    ASR_KEY_REQUIRED = "ASR_KEY_REQUIRED"
    OFFLINE = "OFFLINE"


class ProcessingJobRetryRequest(BaseModel):
    record_id: UUID


class ProcessingJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    record_id: str | None
    job_type: ProcessingJobType
    status: ProcessingJobStatus
    progress: float
    attempts: int
    max_attempts: int
    waiting_reason: ProcessingJobWaitingReason | None
    error_code: ProcessingJobErrorCode | None
    retryable: bool
    sequence_no: int = 0
    source_name: str | None = None


class RecordJobsOut(BaseModel):
    jobs: list[ProcessingJobOut]
    progress: float
