-- Run 等待与结果绑定（通用 Agent 第三阶段工单 06，spec M2 执行闭环）：
-- agent_runs 补 waiting_job_id 列——WAITING_JOB 状态记录所等待的后台 job
-- （资料解析等），推进 worker 领取触发 job 时核对它的终态决定续跑 / 失败；
-- 启动对账（recover 扫描 WAITING_JOB 的 Run 重投触发）与运行期核对共用同一
-- 分流路径。唤醒与终态时清空（waiting_reason 同口径清列）。
ALTER TABLE agent_runs ADD COLUMN waiting_job_id TEXT;
