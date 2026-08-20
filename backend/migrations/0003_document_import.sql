CREATE TABLE record_files (
    id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    file_type TEXT NOT NULL CHECK (file_type IN ('AUDIO', 'DOCUMENT')),
    source_type TEXT NOT NULL CHECK (source_type IN ('RECORDED', 'UPLOADED')),
    file_path TEXT NOT NULL,
    original_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size INTEGER NOT NULL CHECK (file_size >= 0),
    duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    sequence_no INTEGER NOT NULL CHECK (sequence_no >= 0),
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE INDEX idx_record_files_record_sequence
    ON record_files(record_id, sequence_no);
CREATE INDEX idx_record_files_content_hash ON record_files(content_hash);

CREATE TABLE transcripts (
    id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL UNIQUE REFERENCES records(id) ON DELETE CASCADE,
    language TEXT NOT NULL,
    content TEXT NOT NULL,
    source_version INTEGER NOT NULL CHECK (source_version >= 1),
    edited_by_user INTEGER NOT NULL CHECK (edited_by_user IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE TABLE processing_jobs (
    id TEXT PRIMARY KEY,
    record_id TEXT REFERENCES records(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL CHECK (
        job_type IN (
            'ASR', 'AUDIO_TRANSCODE', 'DOCUMENT_PARSE', 'EMBEDDING',
            'CONCEPT_EXTRACTION', 'SUMMARY', 'CLEANUP', 'BACKUP_EXPORT'
        )
    ),
    status TEXT NOT NULL CHECK (
        status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')
    ),
    progress REAL NOT NULL CHECK (progress BETWEEN 0 AND 1),
    attempts INTEGER NOT NULL CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL CHECK (max_attempts > 0),
    next_run_at TEXT,
    input_json TEXT NOT NULL,
    result_json TEXT,
    error_code TEXT,
    error_message TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_processing_jobs_record ON processing_jobs(record_id);
CREATE INDEX idx_processing_jobs_claim
    ON processing_jobs(status, next_run_at, created_at);
