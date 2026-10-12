CREATE TABLE chat_turn_budget_calls (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
    namespace TEXT NOT NULL,
    logical_call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    args_fingerprint TEXT NOT NULL,
    policy_version INTEGER NOT NULL CHECK (policy_version > 0),
    UNIQUE (turn_id, namespace, logical_call_id)
);

CREATE TABLE chat_turn_budget_outputs (
    id TEXT PRIMARY KEY,
    call_id TEXT NOT NULL REFERENCES chat_turn_budget_calls(id) ON DELETE CASCADE,
    chars_fed INTEGER NOT NULL CHECK (chars_fed >= 0)
);
CREATE INDEX idx_chat_turn_budget_outputs_call ON chat_turn_budget_outputs(call_id);
