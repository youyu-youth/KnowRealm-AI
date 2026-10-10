-- ChatTurn 安全恢复与幂等（切换会话不中断任务，票 02）：
-- - chat_turn_tool_effects：副作用逐项恢复记录。来源键 = 稳定执行归属
--   （turn_id）+ checkpoint namespace + 逻辑调用身份（模型 tool_call id，
--   checkpoint 内稳定）+ effect_index；attempt 不进入来源键。调用计划先
--   持久化（PLANNED）才允许副作用执行；每项来源键、业务写入与可恢复
--   结果／回执同事务提交，恢复命中已成功项复用原结构化结果不再写业务。
-- - chat_turns.waiting_reason：WAITING_USER 等待原因（JSON：kind/detail；
--   kind ∈ PROVIDER_UNAVAILABLE/PROVIDER_CHANGED/MEMORY_OUTBOUND_REVOKED/
--   WEB_SEARCH_UNAVAILABLE/GRAPH_INCOMPATIBLE/CHECKPOINT_MISSING）。
-- - chat_turn_events 增加 'revision' 事件类型（模型节点重放的正文替换边界：
--   未完成 segment 被新 output_revision 替换，旧片段保留可查看）。SQLite
--   不能就地改 CHECK，照 0039/0042 先例整表重建，存量行原样搬运。
ALTER TABLE chat_turns ADD COLUMN waiting_reason TEXT;

PRAGMA legacy_alter_table=ON;

ALTER TABLE chat_turn_events RENAME TO chat_turn_events_v42;

CREATE TABLE chat_turn_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL CHECK (seq >= 1),
    attempt INTEGER NOT NULL,
    output_revision INTEGER NOT NULL,
    type TEXT NOT NULL CHECK (type IN (
        'token', 'commentary', 'tool_call', 'tool_result', 'citation', 'done',
        'revision'
    )),
    segment_id TEXT,
    tool_call_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

INSERT INTO chat_turn_events (
    id, turn_id, seq, attempt, output_revision, type, segment_id, tool_call_id,
    payload_json, created_at
)
SELECT
    id, turn_id, seq, attempt, output_revision, type, segment_id, tool_call_id,
    payload_json, created_at
FROM chat_turn_events_v42;

DROP TABLE chat_turn_events_v42;

PRAGMA legacy_alter_table=OFF;

CREATE UNIQUE INDEX idx_chat_turn_events_seq ON chat_turn_events(turn_id, seq);

CREATE TABLE chat_turn_tool_effects (
    id TEXT PRIMARY KEY,
    turn_id TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
    -- checkpoint 命名空间（chat-turn-{turn_id}）：与逻辑调用身份共同定位一次
    -- 工具调用；新轮次＝新 turn_id＝新逻辑调用，不误去重。
    namespace TEXT NOT NULL,
    -- 逻辑调用身份：模型 tool_call id（图续跑时同一 pending 调用 id 稳定）。
    logical_call_id TEXT NOT NULL,
    -- 多结果工具的逐项副作用序号（单效果恒 0）；计划固定时先全量落 PLANNED。
    effect_index INTEGER NOT NULL CHECK (effect_index >= 0),
    tool_name TEXT NOT NULL,
    -- 规范化参数指纹：同身份参数变化拒绝执行（防旧载荷在新执行下重放）。
    args_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PLANNED', 'SUCCEEDED', 'FAILED')),
    -- 可恢复结构化结果（含业务对象 ID 与回执载荷）；恢复时原样返回模型。
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_chat_turn_tool_effects_source
ON chat_turn_tool_effects(turn_id, namespace, logical_call_id, effect_index);
CREATE INDEX idx_chat_turn_tool_effects_turn ON chat_turn_tool_effects(turn_id);
