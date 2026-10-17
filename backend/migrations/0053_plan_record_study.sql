ALTER TABLE learning_plan_items ADD COLUMN study_visit_id TEXT;
ALTER TABLE learning_plan_items ADD COLUMN study_record_id TEXT;
ALTER TABLE learning_plan_items ADD COLUMN study_started_at TEXT;
ALTER TABLE learning_plan_items ADD COLUMN study_tab TEXT NOT NULL DEFAULT 'summary'
    CHECK (study_tab IN ('summary', 'transcript', 'knowledge-points', 'quiz', 'review', 'todo'));
