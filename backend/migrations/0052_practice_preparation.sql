-- 计划练习准备；存量任务仅原样搬运，不回填业务状态。
PRAGMA legacy_alter_table=ON;

ALTER TABLE processing_jobs RENAME TO processing_jobs_v51;

CREATE TABLE processing_jobs (
    id TEXT PRIMARY KEY,
    record_id TEXT REFERENCES records(id) ON DELETE CASCADE,
    library_item_id TEXT REFERENCES library_items(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL CHECK (
        job_type IN (
            'ASR', 'AUDIO_TRANSCODE', 'DOCUMENT_PARSE', 'EMBEDDING',
            'CONCEPT_EXTRACTION', 'SUMMARY', 'KNOWLEDGE_EXTRACTION',
            'QUIZ_GENERATION', 'TODO_GENERATION', 'QUIZ_GRADING',
            'REVIEW_MATERIAL_GENERATION', 'WEB_FETCH', 'LIBRARY_BACKFILL',
            'INDEX_REBUILD', 'CLEANUP', 'BACKUP_EXPORT', 'AGENT_RUN',
            'PLAN_DRAFT', 'CHAT_TURN', 'PRACTICE_PREPARE'
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
    id, record_id, library_item_id, job_type, status, progress, attempts,
    max_attempts, next_run_at, input_json, result_json, error_code, error_message,
    started_at, finished_at, created_at, updated_at, waiting_reason
)
SELECT
    id, record_id, library_item_id, job_type, status, progress, attempts,
    max_attempts, next_run_at, input_json, result_json, error_code, error_message,
    started_at, finished_at, created_at, updated_at, waiting_reason
FROM processing_jobs_v51;

DROP TABLE processing_jobs_v51;

CREATE INDEX idx_processing_jobs_record ON processing_jobs(record_id);
CREATE INDEX idx_processing_jobs_library_item ON processing_jobs(library_item_id);
CREATE INDEX idx_processing_jobs_claim ON processing_jobs(status, next_run_at, created_at);
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
CREATE UNIQUE INDEX idx_processing_jobs_one_active_web_fetch
    ON processing_jobs(library_item_id)
    WHERE job_type = 'WEB_FETCH' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_index_rebuild
    ON processing_jobs(library_item_id)
    WHERE job_type = 'INDEX_REBUILD' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_agent_run
    ON processing_jobs(json_extract(input_json, '$.run_id'))
    WHERE job_type = 'AGENT_RUN' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_plan_draft
    ON processing_jobs(json_extract(input_json, '$.goal_id'))
    WHERE job_type = 'PLAN_DRAFT' AND status IN ('PENDING', 'RUNNING');

PRAGMA legacy_alter_table=OFF;

CREATE TABLE practice_requirements (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES learning_plan_items(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL CHECK (revision > 0),
    content_json TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    UNIQUE(item_id, revision)
);
CREATE TABLE practice_preparations (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES learning_plan_items(id) ON DELETE CASCADE,
    requirements_id TEXT NOT NULL REFERENCES practice_requirements(id) ON DELETE CASCADE,
    request_id TEXT NOT NULL UNIQUE,
    job_id TEXT NOT NULL REFERENCES processing_jobs(id) ON DELETE CASCADE,
    authority TEXT NOT NULL CHECK (authority IN ('USER_MANUAL', 'AGENT')),
    result_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_practice_preparations_item ON practice_preparations(item_id, created_at);
CREATE UNIQUE INDEX idx_processing_jobs_one_active_practice
    ON processing_jobs(json_extract(input_json, '$.item_id'))
    WHERE job_type = 'PRACTICE_PREPARE' AND status IN ('PENDING', 'RUNNING');
