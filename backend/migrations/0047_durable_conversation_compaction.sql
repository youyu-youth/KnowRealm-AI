ALTER TABLE chat_context_states ADD COLUMN summary_id TEXT;
ALTER TABLE chat_context_inputs ADD COLUMN segment INTEGER NOT NULL DEFAULT 1;
ALTER TABLE chat_context_inputs ADD COLUMN summary_id TEXT;
ALTER TABLE chat_context_inputs ADD COLUMN summary_allowance INTEGER NOT NULL DEFAULT 4 CHECK (summary_allowance >= 4);
ALTER TABLE chat_model_requests ADD COLUMN purpose TEXT NOT NULL DEFAULT 'ANSWER' CHECK (purpose IN ('ANSWER', 'SUMMARY'));
ALTER TABLE chat_model_requests ADD COLUMN messages_json TEXT;
ALTER TABLE chat_model_requests ADD COLUMN retry_of TEXT;
CREATE TABLE chat_compactions (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
    input_fingerprint TEXT NOT NULL,
    context_version INTEGER NOT NULL,
    segment INTEGER NOT NULL,
    base_summary_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'WAITING', 'FAILED', 'COMPLETED')),
    plan_json TEXT NOT NULL,
    results_json TEXT NOT NULL DEFAULT '[]',
    summary_json TEXT,
    covered_json TEXT NOT NULL,
    requests_used INTEGER NOT NULL DEFAULT 0 CHECK (requests_used >= 0),
    error_code TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (turn_id, input_fingerprint)
);
CREATE INDEX idx_chat_compactions_turn ON chat_compactions(turn_id, created_at, id);
