-- Course Brain 数据底座（F4，ADR-0022）：课程级概念 / 概念关系 / 记录-概念出现索引。
-- concepts 无 deleted_at：ARCHIVED 即退役语义（候选忽略亦置 ARCHIVED）；
-- CONFIRMED 概念的 (course_id, normalized_name) 唯一由部分唯一索引在库级兜底
-- （v2.7「SQLite 无部分唯一索引」论断有误，0017 已有先例）。
-- normalized_name 由应用层确定性函数生成（strip → 空白折叠 → 全角转半角 → casefold）。

CREATE TABLE concepts (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    canonical_name TEXT NOT NULL CHECK (length(trim(canonical_name)) BETWEEN 1 AND 100),
    normalized_name TEXT NOT NULL CHECK (length(normalized_name) >= 1),
    description TEXT NOT NULL DEFAULT '',
    concept_type TEXT NOT NULL DEFAULT 'TERM',
    importance INTEGER NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'CANDIDATE'
        CHECK (status IN ('CANDIDATE', 'CONFIRMED', 'ARCHIVED')),
    source TEXT NOT NULL DEFAULT 'AI_EXTRACTED'
        CHECK (source IN ('AI_EXTRACTED', 'USER_CONFIRMED', 'SYSTEM')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_concepts_course_confirmed
    ON concepts(course_id, normalized_name)
    WHERE status = 'CONFIRMED';
CREATE INDEX idx_concepts_course_status ON concepts(course_id, status);

CREATE TABLE concept_relations (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    source_concept_id TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    target_concept_id TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL CHECK (
        relation_type IN (
            'PREREQUISITE', 'PART_OF', 'RELATED_TO', 'COMPARE_WITH', 'CAUSES', 'APPLIES_TO'
        )
    ),
    confidence REAL NOT NULL DEFAULT 0 CHECK (confidence BETWEEN 0 AND 1),
    evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
    status TEXT NOT NULL DEFAULT 'CANDIDATE'
        CHECK (status IN ('CANDIDATE', 'CONFIRMED', 'DISMISSED')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (source_concept_id != target_concept_id),
    UNIQUE (source_concept_id, target_concept_id, relation_type)
);

CREATE INDEX idx_concept_relations_course_status ON concept_relations(course_id, status);

CREATE TABLE record_concepts (
    id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    concept_id TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    knowledge_point_id TEXT REFERENCES knowledge_points(id) ON DELETE SET NULL,
    relevance REAL NOT NULL DEFAULT 0 CHECK (relevance BETWEEN 0 AND 1),
    evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
    first_start_ms INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (record_id, concept_id)
);

CREATE INDEX idx_record_concepts_concept ON record_concepts(concept_id);
CREATE INDEX idx_record_concepts_record ON record_concepts(record_id);

-- source_anchor_links.resource_type 值域扩展 'CONCEPT'：SQLite 不可 ALTER CHECK，
-- 按仓库 rename→重建→拷贝→drop 惯例（0017 同款；legacy_alter_table=ON 防 rename
-- 改写其他表引用本表的 FK 文本）。
PRAGMA legacy_alter_table=ON;

ALTER TABLE source_anchor_links RENAME TO source_anchor_links_v22;

CREATE TABLE source_anchor_links (
    id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL CHECK (
        resource_type IN (
            'SUMMARY', 'KNOWLEDGE_POINT', 'QUIZ', 'MISCONCEPTION',
            'CHAT_MESSAGE', 'RECORD_ANALYSIS', 'CONCEPT'
        )
    ),
    resource_id TEXT NOT NULL,
    source_anchor_id TEXT NOT NULL REFERENCES source_anchors(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL CHECK (
        relation_type IN ('SUPPORTS', 'PRIMARY', 'CONTRADICTS', 'REFERENCES')
    ),
    UNIQUE (resource_type, resource_id, source_anchor_id, relation_type)
);

INSERT INTO source_anchor_links (
    id, resource_type, resource_id, source_anchor_id, relation_type
)
SELECT id, resource_type, resource_id, source_anchor_id, relation_type
FROM source_anchor_links_v22;

DROP TABLE source_anchor_links_v22;

PRAGMA legacy_alter_table=OFF;
