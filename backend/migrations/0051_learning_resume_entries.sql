CREATE TABLE learning_resume_entries (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('RECORD', 'QUIZ_TEST', 'CHAT_SESSION')),
    target_id TEXT NOT NULL,
    record_tab TEXT CHECK (record_tab IN ('summary', 'transcript', 'knowledge-points', 'quiz', 'review', 'todo')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (kind, target_id),
    CHECK (kind = 'RECORD' OR record_tab IS NULL)
);
CREATE INDEX idx_learning_resume_recent ON learning_resume_entries(updated_at DESC, id DESC);
