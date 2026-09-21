-- 通用 Agent 第一阶段工单 03：agent_proposals 支持 TEXT_RECORD_ADD 操作提案。
-- proposal_type CHECK 放开 'TEXT_RECORD_ADD'（向课程添加文本记录）。SQLite 不能
-- 就地修改 CHECK，照 0015/0026/0027/0028 先例整表重建；存量行原样搬运。
PRAGMA legacy_alter_table=ON;

ALTER TABLE agent_proposals RENAME TO agent_proposals_v28;

CREATE TABLE agent_proposals (
    id TEXT PRIMARY KEY,
    proposal_type TEXT NOT NULL CHECK (
        proposal_type IN (
            'ORGANIZE', 'MEMORY', 'RESEARCH_INGEST', 'COURSE_CREATE', 'TEXT_RECORD_ADD'
        )
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
    payload_json, evidence_refs_json, result_json, error_code, created_at, decided_at
)
SELECT
    id, proposal_type, status, session_id, message_id, target_type, target_id,
    payload_json, evidence_refs_json, result_json, error_code, created_at, decided_at
FROM agent_proposals_v28;

DROP TABLE agent_proposals_v28;

CREATE INDEX idx_agent_proposals_status_created ON agent_proposals(status, created_at DESC);
CREATE INDEX idx_agent_proposals_target ON agent_proposals(target_type, target_id);
