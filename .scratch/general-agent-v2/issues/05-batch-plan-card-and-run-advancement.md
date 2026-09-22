# 05 — 批量计划卡与 Run 推进

**What to build:** 批量整理走「计划卡＋Run」：Agent 产出结构化计划卡（逐项列出目标、参数、计划版本），整卡一次确认即批次授权；确认后创建 Run 与 PLANNED operations，由 JobRunner 内 AGENT_RUN 触发 job 逐步推进（job 是无状态触发器，Run 状态是唯一事实源）；「帮我批准」档不超 10 目标＋10 写操作自动执行、超阈值仍出计划卡；批次部分失败独立继续、依赖阻塞；冲突可等待用户处理、跨重启接续不重做已成功项；随时取消且已提交结果保留。用户可演示（Q1 场景）：十项整理任务前两项成功、第三项冲突 → 任务转等待 → 重启应用 → 处理冲突 → 继续完成剩余项，前两项不重做。

**实施约束:** 实施决策见 [spec](../spec.md) 决策 6~8、11、13（同一 run 至多一个活动触发 job；推进 worker 只认 RUNNING；唤醒仅显式动作＋原子抢占；WAITING_JOB 枚举预留不启用；计划修改版本递增重新确认；执行中新增目标超已批准集合任何档位升回确认）。

**Blocked by:** 02 三档授权与自动执行、03 修改与归档动作、04 删除与跨课迁移。

**Status:** ready-for-agent

- [ ] 计划工具＋OP_BATCH 提案类型（OP_ 命名空间，spec 决策 1/13）：payload 携带对象集合＋逐项参数＋plan_version；确认前创建不改任何业务事实
- [ ] 确认→创建 Run（auth_mode / instruction_text / proposal_id 固化）＋PLANNED operations＋AGENT_RUN 触发 job；帮我批准 ≤10 目标且 ≤10 写操作直建 run（计入已完成项、拆调用 / 重启不重置、同 operation 重试不重复计项），超阈值出计划卡；完全访问不受确认阈值限制但受固定计划约束
- [ ] AGENT_RUN 推进 worker：WorkerSpec 声明式接入（无状态触发 job）；领取守卫（同 run 至多一个活动 job）；逐 operation 原子执行；每步前重检取消 / 授权 / 版本
- [ ] 部分失败语义：独立项继续；依赖失败项后续置 SKIPPED；授权失效 / 取消 / 系统性故障停止推进；终态判定 COMPLETED / PARTIAL_COMPLETED / FAILED / CANCELLED
- [ ] Run 等待与唤醒：冲突或需确认转 WAITING_USER（waiting_reason）；唤醒仅显式动作（继续指令 / 失败项重试 / 冲突项解决 / 取消）＋原子抢占；会话消息流注入本会话非终态 run 摘要（提示非指令）
- [ ] 取消：持久化取消端点（cancel_requested），推进中每步检查，取消后不新增动作、已提交结果保留
- [ ] 重启恢复：启动扫描 RUNNING 且无活动触发 job 的 run 重投触发（recover_interrupted 先例）；不重做已成功项
- [ ] 计划修改：版本递增＋重新确认；执行中重规划新增目标超已批准集合 → 升回确认（完全访问亦然）
- [ ] 前端计划卡（整卡确认、逐项参数、版本变化重新确认）＋Run 进度呈现（执行中 / 等待 / 部分完成、逐项结果、失败项重试与继续按钮）＋操作历史分区 run 展开接真
- [ ] 新增错误码登记＋zh/en 双语同步；api-types regenerate；runs 子包零领域 import 的 AST 防线延续
- [ ] 门禁全套过（后端 pytest / ruff / pyright、前端 vitest / lint / build、OpenAPI --check）

**用户真机验收（单列，不代勾）：**

- 真实模型跑通 Q1 十项场景：冲突 → 等待 → 重启应用 → 处理冲突 → 继续完成，已成功项零重复。
- 帮我批准档批量归类 10 条以内自动执行＋批次回执；构造超阈值场景仍出计划卡。
- 批量执行中途取消：不再新增动作、已完成项在操作历史如实呈现。
