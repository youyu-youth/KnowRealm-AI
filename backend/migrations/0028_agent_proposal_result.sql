-- 通用 Agent 第一阶段工单 02：agent_proposals 支持操作提案与操作回执。
-- ① proposal_type CHECK 放开 'COURSE_CREATE'；② 增加 result_json 可空列
-- （APPLIED 时由确认事务写入类型化结果，其余状态恒 NULL）。SQLite 不能就地
-- 修改 CHECK，照 0015/0026/0027 先例整表重建；存量行原样搬运（result_json
-- 为新增列，存量行为 NULL）。
PRAGMA legacy_alter_table=ON;

ALTER TABLE agent_proposals RENAME TO agent_proposals_v27;

CREATE TABLE agent_proposals (
    id TEXT PRIMARY KEY,
    proposal_type TEXT NOT NULL CHECK (
        proposal_type IN ('ORGANIZE', 'MEMORY', 'RESEARCH_INGEST', 'COURSE_CREATE')
    ),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'APPLIED', 'REJECTED', 'FAILED')),
    session_id TEXT,
    message_id TEXT,
    target_type TEXT,
    target_id TEXT,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    evidence_refs_json TEXT CHECK (
        evidence_refs_json IS NULL OR json_valid(evidence_refs_json)
    ),
    result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
    error_code TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);

INSERT INTO agent_proposals (
    id, proposal_type, status, session_id, message_id, target_type, target_id,
    payload_json, evidence_refs_json, error_code, created_at, decided_at
)
SELECT
    id, proposal_type, status, session_id, message_id, target_type, target_id,
    payload_json, evidence_refs_json, error_code, created_at, decided_at
FROM agent_proposals_v27;

DROP TABLE agent_proposals_v27;

CREATE INDEX idx_agent_proposals_status_created ON agent_proposals(status, created_at DESC);
CREATE INDEX idx_agent_proposals_target ON agent_proposals(target_type, target_id);
