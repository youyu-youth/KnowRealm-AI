PRAGMA legacy_alter_table=ON;
ALTER TABLE records RENAME TO records_old;

CREATE TABLE records (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE CASCADE,
    capture_type TEXT NOT NULL CHECK (
        capture_type IN (
            'RECORDING', 'AUDIO_IMPORT', 'DOCUMENT_IMPORT', 'MULTI_SOURCE',
            'PASTE', 'QUICK_NOTE', 'CLIP'
        )
    ),
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'NOTE', 'DRAFT', 'CONTENT_PROCESSING', 'SUMMARY_PENDING',
            'SUMMARY_PROCESSING', 'SUMMARY_READY', 'COMPLETED', 'FAILED'
        )
    ),
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    summary_confirmed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

INSERT INTO records SELECT * FROM records_old;
DROP TABLE records_old;

CREATE INDEX idx_records_created_at ON records(created_at DESC);
CREATE INDEX idx_records_course_created_at ON records(course_id, created_at DESC);
CREATE INDEX idx_records_status ON records(status);
PRAGMA legacy_alter_table=OFF;
