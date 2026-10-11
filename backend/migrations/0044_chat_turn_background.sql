-- 回答等待与任务控制归属；业务任务生命周期独立于 ChatTurn。
CREATE TABLE chat_turn_runs (
    turn_id TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    control_scope TEXT NOT NULL CHECK (control_scope IN ('EXCLUSIVE', 'SHARED', 'INDEPENDENT')),
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
    PRIMARY KEY (turn_id, run_id)
);
CREATE UNIQUE INDEX idx_chat_turn_exclusive_run ON chat_turn_runs(run_id)
    WHERE control_scope = 'EXCLUSIVE';
CREATE TABLE chat_turn_waits (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
    namespace TEXT NOT NULL,
    logical_call_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('RUN', 'JOB')),
    target_id TEXT NOT NULL,
    source_operation_id TEXT REFERENCES agent_operations(id) ON DELETE SET NULL,
    interrupt_id TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (turn_id, namespace, logical_call_id)
);
CREATE INDEX idx_chat_turn_waits_target ON chat_turn_waits(target_type, target_id);
ALTER TABLE chat_turns ADD COLUMN compacted_seq INTEGER NOT NULL DEFAULT 0 CHECK (compacted_seq >= 0);
ALTER TABLE chat_turns ADD COLUMN snapshot_json TEXT;
