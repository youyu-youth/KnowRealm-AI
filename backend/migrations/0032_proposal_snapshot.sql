-- 通用 Agent 第二阶段工单 03：执行前快照机制的提案侧载体。
-- agent_proposals 增加 snapshot_json：提交时后端同事务固化（直接目标 updated_at
-- ＋修改动作 before 值＋级联影响清单字段，spec 决策 12），确认卡预览、执行前
-- 重验与 Undo 补偿三用；旧提案（含存量 ORGANIZE）无快照＝NULL，沿用现行路径。
-- 可空列直加，无需整表重建。
ALTER TABLE agent_proposals ADD COLUMN snapshot_json TEXT CHECK (
    snapshot_json IS NULL OR json_valid(snapshot_json)
);
