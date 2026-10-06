CREATE TABLE chat_response_processes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_message_id TEXT NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    assistant_message_id TEXT REFERENCES chat_messages(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED', 'INTERRUPTED')),
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    ended_at TEXT,
    elapsed_ms INTEGER NOT NULL DEFAULT 0 CHECK (elapsed_ms >= 0),
    entries_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX idx_chat_response_processes_session
ON chat_response_processes(session_id, started_at, id);
