PRAGMA legacy_alter_table=ON;

ALTER TABLE processing_jobs RENAME TO processing_jobs_v15;

CREATE TABLE processing_jobs (
    id TEXT PRIMARY KEY,
    record_id TEXT REFERENCES records(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL CHECK (
        job_type IN (
            'ASR', 'AUDIO_TRANSCODE', 'DOCUMENT_PARSE', 'EMBEDDING',
            'CONCEPT_EXTRACTION', 'SUMMARY', 'KNOWLEDGE_EXTRACTION',
            'QUIZ_GENERATION', 'TODO_GENERATION', 'QUIZ_GRADING',
            'CLEANUP', 'BACKUP_EXPORT'
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
FROM processing_jobs_v15;

DROP TABLE processing_jobs_v15;

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

CREATE TABLE quiz_tests (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id),
    record_id TEXT REFERENCES records(id) CHECK (record_id IS NULL),
    mode TEXT NOT NULL CHECK (mode IN ('MOCK', 'ADAPTIVE')),
    status TEXT NOT NULL CHECK (
        status IN ('IN_PROGRESS', 'GRADING', 'GRADING_FAILED', 'COMPLETED', 'ABANDONED')
    ),
    score REAL CHECK (score IS NULL OR score BETWEEN 0 AND 1),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE INDEX idx_quiz_tests_course_created
    ON quiz_tests(course_id, created_at DESC);

CREATE TABLE quiz_test_items (
    id TEXT PRIMARY KEY,
    test_id TEXT NOT NULL REFERENCES quiz_tests(id) ON DELETE CASCADE,
    quiz_id TEXT NOT NULL REFERENCES quizzes(id),
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    user_answer_json TEXT CHECK (
        user_answer_json IS NULL OR json_valid(user_answer_json)
    ),
    result TEXT CHECK (
        result IS NULL OR result IN ('CORRECT', 'WRONG', 'PARTIAL')
    ),
    score REAL CHECK (score IS NULL OR score BETWEEN 0 AND 1),
    ai_grade_json TEXT CHECK (
        ai_grade_json IS NULL OR json_valid(ai_grade_json)
    ),
    answered_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    UNIQUE(test_id, sequence_no)
);
