# 学习事件消费走独立水位循环，不入 processing_jobs

---
Status: accepted（2026-09-14，A3「事件消费框架 + Evidence Builder」grill 定稿）
---

扩展文档 §39.2 为 A3 基础设施留了二选一：`learning_events` 写入 → 进程内异步 dispatch → Evidence Builder，「复用 JobRunner 或 asyncio 任务」。四事件（SUMMARY_CONFIRMED / KNOWLEDGE_CONFIRMED / QUIZ_ANSWERED / QUIZ_TEST_COMPLETED）与业务动作同事务写入（数据模型 v2.5 定稿，幂等键 `{event-slug}:{source-id}`）；消费侧把事件确定性转换为 `learning_evidence`（迁移 0021，`event_id` 唯一约束作重放幂等键）。

**决定**：

- **消费形态 = 独立 asyncio 后台循环 + 单调 id 水位扫描**：`id > 水位` 逐条取事件、逐条确定性转换、幂等 upsert evidence；纯周期扫描（约 30s）+ 启动即扫，不做写入时推送唤醒（本期零前端消费者，延迟无感知面）。
- **与 ADR-0012 的边界**：0012 管辖 processing_jobs 队列的执行体；learning_events 消费是毫秒级确定性纯函数、个人学习行为日量几十条，领取三态/attempts/next_run_at 协议对其是过度设计，每条事件一行 job 徒增表膨胀。进程内非 job 后台机制已有先例（RecordInvalidationNotifier）。
- **失败语义 = 重试 3 次后跳过 + error 日志 + 计数告警**，不建死信表、不阻塞水位：证据可由事件流重放再生（truncate 后全量重建即修复），个别行缺失非灾难；停在失败行会造毒丸。
- **Evidence Builder 零 LLM**（红线 #2：确定性 Service 与 Graph 分离）：LLM 蒸馏（EvoScientist 式 observation 提炼）属 P4 画像域，本期只借「事件 → 后台确定性转换 → 可重放」形态，不引任何运行时记忆框架（§39.2 既有裁定：单用户场景 SQLite 业务表即记忆）。
- 测验逐题事件在评分完成时写（score 齐，`occurred_at` 取 `quiz_test_items.answered_at`，键位 `quiz-answered:test:{item_id}`）；交卷事件不产 evidence（避免逐题 + 汇总双计 weight）。

## Considered Options

| 方案 | 结论 |
|------|------|
| **A. 独立水位循环（asyncio task）** | **采纳**——轻量、零表膨胀、崩溃恢复 = 启动全量补扫 + event_id 幂等去重 |
| B. 每条事件入 processing_jobs，新 worker 类型 EVENT_CONSUME | 否决——重协议套纯函数转换，job 行随事件量线性膨胀 |
| C. 进程内 Notifier 推送、无兜底扫描 | 否决——崩溃窗口丢消费，违背事件流完整性 |

## Consequences

- 水位扫描禁止 `NOT EXISTS` 相关子查询（O(N×M) 地雷，sidecar 启动超时前科 65a1dac），一律单调 id 比较走索引。
- 未来 UI 需要即时性时，在循环骨架上加推送唤醒，形态不变。
- `learning_evidence.event_id` 唯一约束是对数据模型 v2.5 `(event_id)` 普通索引的字段级收紧，落地票内升版 v2.6 重命名（F1 CHECK 收紧先例）。
- Mastery（红线 #3 唯一写入口 Mastery Engine，P4）与 agent 学习上下文中间件是 evidence 的两个未来消费者；本期仅随实现提供只读查询能力，不建消费者。

## 落地备注（2026-09-14，learning-evidence 票 03/04 实施定稿）

- **水位键 = SQLite 隐式 rowid**：`learning_events.id` 是 uuid4（非单调），无法直接作「单调 id」水位；实现落在追加型表的隐式 rowid 上（严格递增、走表 b-tree，禁 NOT EXISTS 同样满足）。本决定中的「单调 id 比较」按此落地形态理解。
- **幂等方式 = event_id 预查点查跳过**（与统一事件写入函数同款先例），非 INSERT 撞唯一约束；唯一约束仍作竞态兜底（撞上走失败重试路径自愈）。点查走唯一索引，不属上述禁止的 NOT EXISTS 扫描。
- **「重试 3 次」= 单条共 3 次尝试**（`MAX_CONVERSION_ATTEMPTS=3`），第 3 次失败才计跳过告警。
- 数据模型已升 v2.6 重命名（event_id 唯一收紧落档）；`docs/后端错误码清单.md` 为 HTTP 错误响应码清单，消费循环两个纯日志码（EVIDENCE_CONSUME_FAILED / EVIDENCE_CONVERSION_FAILED）不入册（先例 WORKER_INTERRUPTED 同）。
