-- 研究会话 V1：chat_sessions.mode CHECK 放开 'RESEARCH'（会话创建请求 mode
-- 字面量同步放开为 ASK | RESEARCH）。SQLite 不能就地修改 CHECK，照 0015/0026
-- 先例整表重建；零新列、零数据变更，存量行原样搬运。
PRAGMA legacy_alter_table=ON;

ALTER TABLE chat_sessions RENAME TO chat_sessions_v26;

CREATE TABLE chat_sessions (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE SET NULL,
    record_id TEXT REFERENCES records(id) ON DELETE SET NULL,
    concept_id TEXT,
    library_item_id TEXT REFERENCES library_items(id) ON DELETE SET NULL,
    mode TEXT NOT NULL CHECK (
        mode IN ('ASK', 'COURSE_QA', 'SOCRATIC_TUTOR', 'TEACH_BACK', 'RESEARCH')
    ),
    scope TEXT NOT NULL DEFAULT 'FREE' CHECK (
        scope IN ('FREE', 'RECORD', 'LIBRARY_ITEM', 'COURSE', 'ALL')
    ),
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

INSERT INTO chat_sessions (
    id, course_id, record_id, concept_id, library_item_id, mode, scope,
    title, created_at, updated_at, deleted_at
)
SELECT
    id, course_id, record_id, concept_id, library_item_id, mode, scope,
    title, created_at, updated_at, deleted_at
FROM chat_sessions_v26;

DROP TABLE chat_sessions_v26;

CREATE INDEX idx_chat_sessions_list ON chat_sessions(deleted_at, updated_at DESC);
