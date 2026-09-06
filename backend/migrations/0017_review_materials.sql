PRAGMA legacy_alter_table=ON;

ALTER TABLE processing_jobs RENAME TO processing_jobs_v16;

CREATE TABLE processing_jobs (
    id TEXT PRIMARY KEY,
    record_id TEXT REFERENCES records(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL CHECK (
        job_type IN (
            'ASR', 'AUDIO_TRANSCODE', 'DOCUMENT_PARSE', 'EMBEDDING',
            'CONCEPT_EXTRACTION', 'SUMMARY', 'KNOWLEDGE_EXTRACTION',
            'QUIZ_GENERATION', 'TODO_GENERATION', 'QUIZ_GRADING',
            'REVIEW_MATERIAL_GENERATION', 'CLEANUP', 'BACKUP_EXPORT'
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
    updated_at TEXT NOT NULL,
    waiting_reason TEXT CHECK (
        waiting_reason IS NULL OR waiting_reason IN (
            'CONSENT_REQUIRED', 'ASR_KEY_REQUIRED', 'OFFLINE'
        )
    )
);

INSERT INTO processing_jobs (
    id, record_id, job_type, status, progress, attempts, max_attempts,
    next_run_at, input_json, result_json, error_code, error_message,
    started_at, finished_at, created_at, updated_at, waiting_reason
)
SELECT
    id, record_id, job_type, status, progress, attempts, max_attempts,
    next_run_at, input_json, result_json, error_code, error_message,
    started_at, finished_at, created_at, updated_at, waiting_reason
FROM processing_jobs_v16;

DROP TABLE processing_jobs_v16;

PRAGMA legacy_alter_table=OFF;

CREATE INDEX idx_processing_jobs_record ON processing_jobs(record_id);
CREATE INDEX idx_processing_jobs_claim
    ON processing_jobs(status, next_run_at, created_at);
CREATE UNIQUE INDEX idx_processing_jobs_one_active_summary
    ON processing_jobs(record_id)
    WHERE job_type = 'SUMMARY' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_knowledge_extraction
    ON processing_jobs(record_id)
    WHERE job_type = 'KNOWLEDGE_EXTRACTION' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_quiz_generation
    ON processing_jobs(record_id)
    WHERE job_type = 'QUIZ_GENERATION' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_todo_generation
    ON processing_jobs(record_id)
    WHERE job_type = 'TODO_GENERATION' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_review_material_generation
    ON processing_jobs(record_id)
    WHERE job_type = 'REVIEW_MATERIAL_GENERATION' AND status IN ('PENDING', 'RUNNING');

CREATE TABLE review_materials (
    id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    transcript_source_version INTEGER NOT NULL CHECK (transcript_source_version >= 1),
    generated_from_summary_id TEXT REFERENCES ai_summaries(id) ON DELETE SET NULL,
    quick_review TEXT NOT NULL CHECK (length(trim(quick_review)) BETWEEN 1 AND 20000),
    key_list_json TEXT NOT NULL CHECK (json_valid(key_list_json)),
    mind_map_markdown TEXT NOT NULL CHECK (
        length(trim(mind_map_markdown)) BETWEEN 1 AND 20000
    ),
    status TEXT NOT NULL CHECK (status IN ('GENERATED', 'CONFIRMED', 'SUPERSEDED')),
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    user_feedback TEXT,
    token_usage_json TEXT NOT NULL CHECK (json_valid(token_usage_json)),
    latency_ms INTEGER NOT NULL CHECK (latency_ms >= 0),
    confirmed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    UNIQUE(record_id, version_no)
);

CREATE INDEX idx_review_materials_record_version
    ON review_materials(record_id, version_no DESC);
