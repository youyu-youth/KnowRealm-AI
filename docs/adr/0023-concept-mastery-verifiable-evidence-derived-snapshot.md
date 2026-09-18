# 掌握度只由验证性证据经确定性引擎派生，拒绝猜测回填与多概念扇出

---
Status: accepted（2026-09-18，Concept Mastery V1 grill 定稿，concept-mastery-v1 plan 票 01~06 落地）
---

PRD 红线 #5 已定「AI 自述不是 Evidence」、#33 已定「LLM 评分 confidence 禁入掌握度」，但 Quiz 与 Concept 两条已交付链路长期未接通：Event/Evidence 的 `concept_id` 恒空、习题不知道自己评估哪个概念，「我对这个概念掌握到什么程度、依据是什么」无法回答。本 ADR 记录接通时的四条边界裁决（数据模型 v2.9，迁移 0024/0025）。

**决定**：

- **验证性 Evidence 是掌握度的唯一改变者**：V1 只消费带主概念且具有可判定结果（CORRECT/WRONG，简答 LLM 评分落定后同语义）的 Quiz Evidence。总结确认、知识点确认继续作为学习活动留痕（USER_CONFIRMATION 证据），但永不抬高掌握度；概念描述、AI 解释、Course Brain 推断一律不是能力证据。题目的 LLM 难度标签未校准，V1 只随事件记录、不参与数值计算。
- **掌握度 = 确定性派生快照，不是事实**：唯一写入口为 `learning/mastery.py` 纯函数引擎（零 LLM、零 IO），消费每个 Concept 最近 12 条有效证据，按四条半衰做序位加权；快照存 `user_concept_mastery`（每概念至多一条）并带 `algorithm_version`。证据与事件是上游事实（追加保留），快照任何时刻可由证据流全量重建——记录删除、归档退出、算法升级都表现为「重算」，不维护增量加减账本。少于 3 条证据输出 `NOT_ENOUGH_DATA`，分数与置信度均为空，不显示伪精确百分比。
- **Mastery 与 Forgetting 是两个状态**：Mastery 表示已验证能力，不随墙钟时间流逝自动下降——几天不打开应用不扣分；「多久没练会忘」属时间衰减风险，归 Forgetting Engine（V1 规则 / FSRS）与 `next_review_at`，本票不建列、不混算。`AT_RISK` / `MISCONCEPTION_RISK` 状态枚举 likewise 留给 Forgetting 与 Misconception。
- **拒绝猜测式归属**：一题至多一个可空主概念，生成时 AI 只从同课程 CONFIRMED 概念中建议、服务端校验；用户可在首次作答前修改或清空，首次作答后锁定（Event 写入时固化 `concept_id`，重放不改语义）。已作答但无归属的历史题**不做** LLM 批量猜测、不做 Record 全量广播、不自动回填——宁可覆盖率低，不制造错误归因；多 Concept Quiz 与一事件扇出多证据的模型明确不做。

## Considered Options

| 方案 | 结论 |
|------|------|
| **A. Quiz 可空主概念 + 事件固化 + 确定性引擎全量重建** | **采纳**——归属质量由用户首答前把关，派生链路可重放、可审计、零 token 成本 |
| B. 按 Record 全部 Concept 广播归属 | 否决——一条总结含十余个概念，一次作答给全部概念计分 = 伪覆盖率污染 |
| C. LLM 批量为历史已答习题回填概念 | 否决——模型自证其输出正确，违反红线 #5；错误归属一旦写入证据长期难清除 |
| D. 掌握度随时间自动衰减（复用 FSRS 半衰） | 否决——能力验证与遗忘风险语义不同；衰减留给 Forgetting，`last_verified_at` 已可供其消费 |
| E. 掌握度进 LangGraph / 由 Agent 计算 | 否决——纯数值确定性计算，红线 #2（确定性 Service 与 Graph 分离） |

## Consequences

- 掌握度准确性上限由「习题 × 主概念」归属质量决定；无 Course Brain、无已确认概念、用户清空归属时，作答照常但**不产生**掌握度进展——这是有意的诚实降级。
- Evidence Consumer 消费与重算同轮完成（30s 轮询）；重算失败不回滚已落库的 Event/Evidence，重试后记结构化错误；启动 `recover_snapshots` 重建缺失/版本过期快照，算法升级 = bump 版本号 + 全量重建。
- 公开面只有两个只读 API（课程聚合 + 概念详情）；不提供修改分数、手工标记已掌握或直接重算的写 API，前端与 Agent 都不能绕过唯一写入口。
- `quizzes.concept_id` 物理删除概念时 `ON DELETE SET NULL`（归属历史随之消失但事件/证据行保留）；快照表 `user_concept_mastery` 为 P4 Learner Brain 域首张落地表，`memory_strength` / `next_review_at` 等列待 Forgetting 落地再迁移。
