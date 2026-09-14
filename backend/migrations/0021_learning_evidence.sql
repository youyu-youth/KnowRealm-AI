-- 学习证据：学习事件经确定性映射派生的可再生数据（A3）。
-- event_id 唯一约束 = 重放幂等的数据库级保障（一事件至多一证据，对数据模型
-- v2.5 普通 (event_id) 索引的字段级收紧）；整表可清空后由事件流全量重放重建。
-- 追加型不软删：无 updated_at/deleted_at 列，不随业务记录删除而变化。
CREATE TABLE learning_evidence (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL,
    concept_id TEXT,
    event_id TEXT NOT NULL UNIQUE,
    evidence_type TEXT NOT NULL CHECK (
        evidence_type IN (
            'QUIZ', 'RECALL', 'TEACH_BACK', 'TUTOR_CHECK', 'TRANSFER',
            'CLASSROOM_SIGNAL', 'USER_CONFIRMATION'
        )
    ),
    result TEXT,
    score REAL,
    difficulty TEXT,
    weight REAL NOT NULL CHECK (weight >= 0 AND weight <= 1),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    source_anchor_id TEXT,
    metadata_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_learning_evidence_concept_occurred
    ON learning_evidence(concept_id, occurred_at DESC);
