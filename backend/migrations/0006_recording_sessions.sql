CREATE TABLE recording_sessions (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE SET NULL,
    title TEXT,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('RECORDING', 'PAUSED', 'FINALIZING', 'DONE')),
    chunk_paths TEXT NOT NULL
);
