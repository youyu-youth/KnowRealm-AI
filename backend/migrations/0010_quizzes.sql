-- legacy_alter_table=ON：rename 不改写引用方 FK 文本（否则 knowledge_points.batch_id
-- 会被改指向下面的临时表 processing_jobs_v9，DROP 后留下悬空引用）。
PRAGMA legacy_alter_table=ON;

ALTER TABLE processing_jobs RENAME TO processing_jobs_v9;

CREATE TABLE processing_jobs (
    id TEXT PRIMARY KEY,
    record_id TEXT REFERENCES records(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL CHECK (
        job_type IN (
            'ASR', 'AUDIO_TRANSCODE', 'DOCUMENT_PARSE', 'EMBEDDING',
            'CONCEPT_EXTRACTION', 'SUMMARY', 'KNOWLEDGE_EXTRACTION',
            'QUIZ_GENERATION', 'CLEANUP', 'BACKUP_EXPORT'
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
FROM processing_jobs_v9;

DROP TABLE processing_jobs_v9;

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

CREATE TABLE quizzes (
    id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    batch_id TEXT REFERENCES processing_jobs(id) ON DELETE SET NULL,
    generated_from_summary_id TEXT REFERENCES ai_summaries(id) ON DELETE SET NULL,
    generation_status TEXT NOT NULL CHECK (
        generation_status IN ('DRAFT', 'ACTIVE', 'SUPERSEDED')
    ),
    question_type TEXT NOT NULL CHECK (
        question_type IN ('MULTIPLE_CHOICE', 'TRUE_FALSE', 'SHORT_ANSWER')
    ),
    stem TEXT NOT NULL CHECK (length(stem) BETWEEN 1 AND 500),
    options_json TEXT NOT NULL CHECK (
        json_valid(options_json) AND json_type(options_json) = 'array'
    ),
    correct_answer_json TEXT NOT NULL CHECK (json_valid(correct_answer_json)),
    explanation TEXT NOT NULL CHECK (length(explanation) BETWEEN 1 AND 2000),
    difficulty TEXT NOT NULL CHECK (difficulty IN ('EASY', 'MEDIUM', 'HARD')),
    user_answer_json TEXT,
    answer_result TEXT CHECK (
        answer_result IS NULL OR answer_result IN ('CORRECT', 'WRONG')
    ),
    answered_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE INDEX idx_quizzes_record_status_created
    ON quizzes(record_id, generation_status, created_at);
CREATE INDEX idx_quizzes_batch ON quizzes(batch_id);

CREATE UNIQUE INDEX idx_processing_jobs_one_active_quiz_generation
    ON processing_jobs(record_id)
    WHERE job_type = 'QUIZ_GENERATION' AND status IN ('PENDING', 'RUNNING');
