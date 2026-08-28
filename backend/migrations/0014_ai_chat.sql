CREATE TABLE profile (
    id TEXT PRIMARY KEY,
    nickname TEXT,
    avatar_file TEXT,
    primary_role TEXT CHECK (
        primary_role IS NULL
        OR primary_role IN ('STUDENT', 'DEVELOPER', 'OFFICE_WORKER', 'OTHER')
    ),
    about_me TEXT CHECK (about_me IS NULL OR length(about_me) <= 200),
    updated_at TEXT NOT NULL
);

CREATE TABLE chat_sessions (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE SET NULL,
    record_id TEXT REFERENCES records(id) ON DELETE SET NULL,
    concept_id TEXT,
    mode TEXT NOT NULL CHECK (
        mode IN ('ASK', 'COURSE_QA', 'SOCRATIC_TUTOR', 'TEACH_BACK')
    ),
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE INDEX idx_chat_sessions_list ON chat_sessions(deleted_at, updated_at DESC);

CREATE TABLE chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('USER', 'ASSISTANT', 'SYSTEM', 'TOOL')),
    content TEXT NOT NULL,
    citations_json TEXT,
    model TEXT,
    token_usage_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_chat_messages_session_created ON chat_messages(session_id, created_at);
