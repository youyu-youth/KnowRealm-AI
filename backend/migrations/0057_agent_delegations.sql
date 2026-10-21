CREATE TABLE agent_delegations (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL CHECK(agent_id = 'knowledge'),
    contract_version INTEGER NOT NULL DEFAULT 1,
    namespace TEXT NOT NULL,
    logical_call_id TEXT NOT NULL,
    args_fingerprint TEXT NOT NULL,
    input_json TEXT NOT NULL,
    job_id TEXT NOT NULL UNIQUE REFERENCES processing_jobs(id),
    status TEXT NOT NULL CHECK(status IN ('QUEUED','RUNNING','COMPLETED','PARTIAL','FAILED','INTERRUPTED','CANCELLED')),
    attempt INTEGER NOT NULL DEFAULT 0,
    claim_token TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    result_json TEXT,
    error_code TEXT,
    retry_request_id TEXT,
    decision_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    UNIQUE(turn_id, namespace, logical_call_id)
);
CREATE INDEX idx_agent_delegations_turn ON agent_delegations(turn_id);
CREATE TABLE agent_delegation_decisions (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    snapshot_id TEXT NOT NULL UNIQUE,
    decision_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
ALTER TABLE chat_model_requests ADD COLUMN execution_id TEXT REFERENCES agent_delegations(id);
ALTER TABLE chat_model_requests ADD COLUMN execution_attempt INTEGER;
ALTER TABLE chat_model_requests ADD COLUMN decision_id TEXT REFERENCES agent_delegation_decisions(id);
ALTER TABLE chat_turn_budget_calls ADD COLUMN execution_id TEXT REFERENCES agent_delegations(id);
ALTER TABLE chat_turn_waits ADD COLUMN execution_attempt INTEGER;
