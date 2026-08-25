CREATE TABLE todo_items (
    id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    batch_id TEXT REFERENCES processing_jobs(id) ON DELETE SET NULL,
    content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 500),
    status TEXT NOT NULL CHECK (status IN ('TODO', 'DONE')),
    source TEXT NOT NULL CHECK (source IN ('AI', 'MANUAL')),
    generated_from_summary_id TEXT REFERENCES ai_summaries(id) ON DELETE SET NULL,
    generation_status TEXT CHECK (
        generation_status IS NULL
        OR generation_status IN ('DRAFT', 'ACTIVE', 'SUPERSEDED')
    ),
    sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE INDEX idx_todo_items_record_sort ON todo_items(record_id, sort_order);
CREATE INDEX idx_todo_items_batch ON todo_items(batch_id);
