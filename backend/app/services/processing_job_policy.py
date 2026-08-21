from app.schemas.document import ProcessingJobErrorCode

RETRYABLE_PROCESSING_JOB_ERROR_CODES = frozenset(
    {
        ProcessingJobErrorCode.TEMPORARY_IO,
        ProcessingJobErrorCode.SQLITE_BUSY,
        ProcessingJobErrorCode.WORKER_INTERRUPTED,
    }
)
