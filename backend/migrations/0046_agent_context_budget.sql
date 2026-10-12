CREATE TABLE chat_context_states (
    session_id TEXT PRIMARY KEY REFERENCES chat_sessions(id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    segment INTEGER NOT NULL DEFAULT 1 CHECK (segment > 0)
);
CREATE TABLE chat_context_inputs (
    turn_id TEXT PRIMARY KEY REFERENCES chat_turns(id) ON DELETE CASCADE,
    context_version INTEGER NOT NULL,
    policy_json TEXT NOT NULL,
    messages_json TEXT
);
CREATE TABLE chat_model_requests (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('STARTED', 'COMPLETED', 'FAILED', 'BLOCKED')),
    input_fingerprint TEXT NOT NULL,
    estimate_json TEXT NOT NULL,
    usage_json TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_chat_model_requests_turn ON chat_model_requests(turn_id, created_at, id);
