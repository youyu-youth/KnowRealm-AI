ALTER TABLE processing_jobs ADD COLUMN waiting_reason TEXT CHECK (
    waiting_reason IS NULL OR waiting_reason IN ('CONSENT_REQUIRED', 'ASR_KEY_REQUIRED', 'OFFLINE')
);

CREATE UNIQUE INDEX idx_record_files_record_sequence_unique
    ON record_files(record_id, sequence_no);

CREATE TABLE ai_summaries (
    id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    transcript_source_version INTEGER NOT NULL CHECK (transcript_source_version >= 1),
    topic TEXT NOT NULL,
    abstract TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('GENERATED', 'CONFIRMED', 'SUPERSEDED')),
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    token_usage_json TEXT NOT NULL,
    latency_ms INTEGER NOT NULL CHECK (latency_ms >= 0),
    user_feedback TEXT,
    confirmed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    UNIQUE (record_id, version_no)
);

CREATE INDEX idx_ai_summaries_record_status ON ai_summaries(record_id, status);
