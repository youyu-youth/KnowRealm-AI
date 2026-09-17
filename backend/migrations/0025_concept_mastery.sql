-- Concept Mastery 派生快照（Concept Mastery V1 票 02）：每个 Concept 至多一条。
-- 只持久化 V1 真实使用的字段（课程 / 分数 / Confidence / 证据计数 / 最近练习与
-- 验证时间 / 算法版本 / 更新时间）；Forgetting、Transfer、Reasoning 字段待对应
-- 功能落地再迁移。唯一写入口 = Mastery Engine；快照可由有效证据全量重建。
-- Concept 物理删除级联清理快照；状态归档保留快照（退出活跃聚合）。
CREATE TABLE user_concept_mastery (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    concept_id TEXT NOT NULL UNIQUE REFERENCES concepts(id) ON DELETE CASCADE,
    mastery_score REAL CHECK (mastery_score IS NULL OR mastery_score BETWEEN 0 AND 1),
    mastery_confidence REAL CHECK (
        mastery_confidence IS NULL OR mastery_confidence BETWEEN 0 AND 1
    ),
    evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
    positive_evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (positive_evidence_count >= 0),
    negative_evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (negative_evidence_count >= 0),
    last_practiced_at TEXT,
    last_verified_at TEXT,
    algorithm_version TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_user_concept_mastery_course ON user_concept_mastery(course_id);
