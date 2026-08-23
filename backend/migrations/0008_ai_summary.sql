CREATE TABLE llm_call_logs (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    graph_name TEXT NOT NULL,
    graph_node TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    embedding_model TEXT,
    token_usage_json TEXT NOT NULL,
    latency_ms INTEGER NOT NULL CHECK (latency_ms >= 0),
    retrieval_count INTEGER,
    evidence_count INTEGER,
    interrupt_count INTEGER NOT NULL DEFAULT 0 CHECK (interrupt_count >= 0),
    error_code TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_llm_call_logs_created_at ON llm_call_logs(created_at DESC);
CREATE INDEX idx_llm_call_logs_request_id ON llm_call_logs(request_id);

CREATE TABLE learning_events (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    record_id TEXT,
    concept_id TEXT,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'SUMMARY_CONFIRMED', 'KNOWLEDGE_CONFIRMED', 'QUIZ_ANSWERED',
            'QUIZ_TEST_COMPLETED', 'TEACH_BACK_COMPLETED', 'TUTOR_CHECK_COMPLETED',
            'REVIEW_VERIFIED', 'MARKER_CREATED', 'MISCONCEPTION_CONFIRMED',
            'MISCONCEPTION_RESOLVED', 'PLAN_ITEM_COMPLETED', 'CONCEPT_MASTERED'
        )
    ),
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    result TEXT,
    score REAL,
    difficulty TEXT,
    duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    metadata_json TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_learning_events_occurred ON learning_events(occurred_at DESC);
CREATE INDEX idx_learning_events_concept_occurred
    ON learning_events(concept_id, occurred_at DESC);
CREATE INDEX idx_learning_events_course_type_occurred
    ON learning_events(course_id, event_type, occurred_at DESC);

CREATE UNIQUE INDEX idx_processing_jobs_one_active_summary
    ON processing_jobs(record_id)
    WHERE job_type = 'SUMMARY' AND status IN ('PENDING', 'RUNNING');
