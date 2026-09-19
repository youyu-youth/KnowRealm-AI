from app.modules.jobs.schemas import ProcessingJobErrorCode

RETRYABLE_PROCESSING_JOB_ERROR_CODES = frozenset(
    {
        ProcessingJobErrorCode.TEMPORARY_IO,
        ProcessingJobErrorCode.SQLITE_BUSY,
        ProcessingJobErrorCode.WORKER_INTERRUPTED,
        ProcessingJobErrorCode.AUDIO_TRANSCODE_FAILED,
        ProcessingJobErrorCode.ASR_AUTH_FAILED,
        ProcessingJobErrorCode.ASR_QUOTA_EXHAUSTED,
        ProcessingJobErrorCode.ASR_TEMPORARY_UNAVAILABLE,
        ProcessingJobErrorCode.ASR_SUBMIT_UNKNOWN,
        ProcessingJobErrorCode.ASR_RECOGNITION_FAILED,
        ProcessingJobErrorCode.ASR_TASK_EXPIRED,
        ProcessingJobErrorCode.LIBRARY_BACKFILL_FAILED,
    }
)
