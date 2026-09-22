-- 通用 Agent 第二阶段工单 01：执行事实地基（spec 决策 2/3/22）。
-- ① agent_proposals.proposal_type CHECK 一次改造为「存量五类型白名单 + OP_ 前缀
--    通配」——后续新操作类型统一 OP_ 命名空间零迁移（类型执法在判别 schema
--    注册表，DB CHECK 只是纵深防御）。SQLite 不能就地修改 CHECK，照
--    0015/0026/0027/0028/0029 先例整表重建；存量行原样搬运。
-- ② 新建 agent_runs / agent_operations / agent_activity 三表（Operation 自始为
--    执行事实唯一源；runs 含 WAITING_JOB 预留枚举、operations 不持久 RUNNING）。
-- 存量 APPLIED 提案不回填 operations（新纪元起点，旧回执经既有提案查询可达）。
PRAGMA legacy_alter_table=ON;

ALTER TABLE agent_proposals RENAME TO agent_proposals_v29;

CREATE TABLE agent_proposals (
    id TEXT PRIMARY KEY,
    proposal_type TEXT NOT NULL CHECK (
        proposal_type IN (
            'ORGANIZE', 'MEMORY', 'RESEARCH_INGEST', 'COURSE_CREATE', 'TEXT_RECORD_ADD'
        )
        OR proposal_type GLOB 'OP_*'
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
FROM agent_proposals_v29;

DROP TABLE agent_proposals_v29;

CREATE INDEX idx_agent_proposals_status_created ON agent_proposals(status, created_at DESC);
CREATE INDEX idx_agent_proposals_target ON agent_proposals(target_type, target_id);

CREATE TABLE agent_runs (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    auth_mode TEXT NOT NULL CHECK (
        auth_mode IN ('REQUEST_APPROVAL', 'AUTO_APPROVE', 'FULL_ACCESS')
    ),
    instruction_text TEXT,
    proposal_id TEXT,
    status TEXT NOT NULL CHECK (
        status IN (
            'RUNNING', 'WAITING_USER', 'WAITING_JOB',
            'COMPLETED', 'PARTIAL_COMPLETED', 'FAILED', 'CANCELLED'
        )
    ),
    plan_json TEXT CHECK (plan_json IS NULL OR json_valid(plan_json)),
    plan_version INTEGER NOT NULL DEFAULT 1 CHECK (plan_version >= 1),
    waiting_reason TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE INDEX idx_agent_runs_status_created ON agent_runs(status, created_at DESC);
CREATE INDEX idx_agent_runs_session ON agent_runs(session_id);

CREATE TABLE agent_operations (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES agent_runs(id) ON DELETE CASCADE,
    proposal_id TEXT REFERENCES agent_proposals(id),
    action TEXT NOT NULL,
    level TEXT NOT NULL CHECK (level IN ('L0', 'L1', 'L2', 'L3')),
    target_type TEXT,
    target_id TEXT,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    snapshot_json TEXT CHECK (snapshot_json IS NULL OR json_valid(snapshot_json)),
    authorization_json TEXT CHECK (
        authorization_json IS NULL OR json_valid(authorization_json)
    ),
    status TEXT NOT NULL CHECK (
        status IN ('PLANNED', 'SUCCEEDED', 'FAILED', 'SKIPPED', 'CANCELLED')
    ),
    attempts INTEGER NOT NULL DEFAULT 1 CHECK (attempts >= 1),
    attempts_json TEXT CHECK (attempts_json IS NULL OR json_valid(attempts_json)),
    result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
    error_code TEXT,
    undo_of TEXT REFERENCES agent_operations(id) ON DELETE SET NULL,
    undone_by TEXT REFERENCES agent_operations(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE INDEX idx_agent_operations_run ON agent_operations(run_id);
CREATE INDEX idx_agent_operations_status_created ON agent_operations(status, created_at DESC);
CREATE INDEX idx_agent_operations_proposal ON agent_operations(proposal_id);

CREATE TABLE agent_activity (
    id TEXT PRIMARY KEY,
    activity_type TEXT NOT NULL CHECK (activity_type IN ('AUTH_MODE_SWITCH')),
    from_mode TEXT NOT NULL CHECK (
        from_mode IN ('REQUEST_APPROVAL', 'AUTO_APPROVE', 'FULL_ACCESS')
    ),
    to_mode TEXT NOT NULL CHECK (
        to_mode IN ('REQUEST_APPROVAL', 'AUTO_APPROVE', 'FULL_ACCESS')
    ),
    scope TEXT NOT NULL CHECK (scope IN ('GLOBAL', 'SESSION')),
    session_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_agent_activity_created ON agent_activity(created_at DESC);

PRAGMA legacy_alter_table=OFF;
