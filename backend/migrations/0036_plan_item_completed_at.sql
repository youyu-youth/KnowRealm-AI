-- 计划项完成时间戳（通用 Agent 第三阶段工单 03，spec「完成语义边界」）：完成
-- （DONE）时写入、取消完成清空；跳过（SKIPPED）不写。学习时长统计由本时间戳
-- 单独承载（不产 learning_event、不进学习证据链，今日统计带此口径随工单 04）。
ALTER TABLE learning_plan_items ADD COLUMN completed_at TEXT;
