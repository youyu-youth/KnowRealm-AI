-- 通用 Agent 第三阶段工单 08 存量缺口（codex 审查发现）：中断恢复预算
-- max_attempts 1→3 只落在新建路径（ingest.create_web_ingest_rows /
-- plan_draft.apply_plan_draft_generate），升级前已落库的 WEB_FETCH /
-- PLAN_DRAFT 未终态任务仍为 1——重启恢复 attempts(1) < max(1) 不成立，
-- 直接翻终态 FAILED（WORKER_INTERRUPTED），违反 spec US32「应用重启后
-- 未完成的长任务自动对账恢复继续」。照 0022 回填先例新增迁移对齐存量：
-- 仅限这两类 job 的 PENDING/RUNNING 行（终态是史实不改写；其余 job 类型
-- max_attempts=1 是刻意合同——LLM 域等 22 个 worker 中断翻终态为既定通道，
-- 不触碰）。纯数据回填零 DDL；迁移先于 worker 恢复执行（main.py lifespan
-- 顺序），回填后 recover 预算内回 PENDING 自动重投。幂等：已为 3 的行不命中。
UPDATE processing_jobs
SET max_attempts = 3
WHERE job_type IN ('WEB_FETCH', 'PLAN_DRAFT')
  AND status IN ('PENDING', 'RUNNING')
  AND max_attempts < 3;
