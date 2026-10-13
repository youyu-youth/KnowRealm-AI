CREATE TABLE chat_context_outputs (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
    namespace TEXT NOT NULL,
    logical_call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    args_fingerprint TEXT NOT NULL,
    content TEXT NOT NULL,
    inline_content TEXT,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(turn_id, namespace, logical_call_id)
);
CREATE INDEX ix_context_outputs_turn ON chat_context_outputs(turn_id);
