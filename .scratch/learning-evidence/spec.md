# A3 事件消费框架 + Evidence Builder 最小版

Status: ready-for-agent

## Problem Statement

学习者每天都在发生学习行为——确认一份 AI 总结、确认一批知识点候选、答一道已采纳习题、交一份模拟测试。按产品长期方向（「个人学习大脑」：掌握度、误概念诊断、遗忘复习调度），这些行为是唯一的原始事实来源；但当前工作台没有把它们记录为结构化事实，行为发生即蒸发。学习事件不可再生——管道每晚一天上线，就永久丢一天的学习行为积累。

这也是既定设计与代码现实之间的一块落差：数据模型 v2.5 §4.5 早已把 learning_events 提前至 P1（四事件 MVP），表模型已就位，却零写入、零消费；learning_evidence 表尚未落地。F1（Segment + Source Anchor）已交付其数据前置，本功能补齐「学习事件 → 学习证据」管道本体。

## Solution

工作台在后台自动把四类已发生的学习行为记录为带幂等键的学习事件（与业务动作同事务写入，追加型不软删），并由一个独立的后台消费循环把事件按确定性映射规则转换为带权重/置信度的学习证据落库。全程零感知、零配置、零 token（无 LLM 参与），数据全部落在本地 SQLite、随数据目录一体备份导出。

证据具有重放性质：由事件流经确定性规则转换而来，可随时全量重建；真正不可再生的只有事件本身，而事件同事务写、不丢。个别转换失败不阻塞、不丢事件，修复后重放即恢复。本期为未来的 Mastery Engine 与 agent 学习上下文中间件提供数据底座与只读查询能力，不建任何消费者。

## User Stories

1. As a 学习者, I want to 确认一份 AI 总结时系统自动记录这个学习行为, so that 我的理解确认无需任何额外操作就成为长期学习状态的一部分。
2. As a 学习者, I want to 确认一批知识点候选时自动记录, so that 知识内化的自证被留存为证据。
3. As a 学习者, I want to 每答一道已采纳习题时自动记录（含对错与自评）, so that 每次练习都算数。
4. As a 学习者, I want to 模拟测试逐题评分完成后自动记录每题作答（带分数）, so that 测验练习成为最有分量的学习证据。
5. As a 学习者, I want to 交卷完成时自动记录一次测验完成事件, so that 测验行为本身进入事实流。
6. As a 学习者, I want to 全程无感知、无弹窗、无配置项, so that 后台积累不增加任何使用负担。
7. As a 学习者, I want to 记录与转换不消耗任何 token, so that 后台积累零费用（BYO-key 敏感）。
8. As a 学习者, I want to 事件与证据全部落在本地数据库、随数据目录备份导出迁移, so that 学习历史是我可搬走的资产。
9. As a 学习者, I want to 同一行为重复触发不产生重复记录（幂等键去重）, so that 未来统计与掌握度不被灌水。
10. As a 学习者, I want to 应用崩溃或重启后已发生的事件不丢、消费自动补齐, so that 稳定性不影响积累。
11. As a 学习者, I want to 事实流追加不可变（不随记录删除被篡改或清除）, so that 学习历史完整可审计。
12. As a 学习者, I want to 逐题模式一题一答各记一条事件, so that 细粒度行为不被汇总抹平。
13. As a 学习者, I want to 简答题自评对错同样记录为证据, so that 主观题练习一样积累。
14. As a 学习者, I want to 模拟测试同题再答另立事件键位, so that 重测演进在未来掌握度里可区分。
15. As a 学习者, I want to 同一个行为只记一个事件, so that 事实流干净不冗余。
16. As a 学习者, I want to 已归档课程的历史事件与证据保留, so that 归档不篡改历史（归档下的新动作本就被既有闸门拦住）。
17. As a Mastery Engine（未来唯一写入口）, I want to 按概念、课程、时间取证据流, so that 掌握度计算有单一可信输入。
18. As a agent 学习上下文中间件（未来）, I want to 一个只读查询能力按记录与课程取证据, so that 对话能感知我的学习历史。
19. As a 复习调度（未来）, I want to 事件与证据带行为发生时刻, so that 遗忘曲线有时序依据。
20. As a 维护者, I want to 证据表可清空后由事件流全量重放重建, so that 转换规则升级后能安全重建派生数据。
21. As a 维护者, I want to 消费失败有日志与计数告警, so that 转换问题能被发现与修复。
22. As a 维护者, I want to 水位扫描走单调 id 索引, so that 事件量增长不拖慢启动与消费。
23. As a 维护者, I want to 事件到证据的映射规则集中一处可读, so that 调整权重与置信度不用翻散落代码。

## Implementation Decisions

**范围**：四事件写入 + 独立消费循环 + 确定性转换落 learning_evidence + 薄只读查询。零 LLM、零前端、零新 API 端点、零新 SSE 事件。

**数据层（迁移 0021）**：

- learning_evidence 按数据模型 §4.5 字段落地：id / course_id / concept_id（本期恒 NULL，Concept 为 P3 实体）/ event_id / evidence_type / result / score / difficulty / weight / confidence（0~1 CHECK）/ source_anchor_id（本期恒 NULL，锚点回填属后续溯源域）/ metadata_json / occurred_at / created_at。
- **event_id 唯一约束**（对 v2.5 普通 `(event_id)` 索引的字段级收紧）——重放幂等的数据库级保障；一事件至多一证据。
- 索引按 v2.5：(concept_id, occurred_at desc)；唯一约束即覆盖 event_id 查询。
- user_version 20→21；全部硬编码 user_version 断言同步（以 grep 实测处数为准，0020 时为 11 处）。
- learning_events 模型维持现位（record 域）不迁移；learning_evidence 模型、消费器、查询能力落**新 learning 域模块**（feature-first，先例：source_anchor 模块）。

**事件写入（同事务挂点，统一经 learning 域提供的事件写入函数，传入业务事务会话）**：

| 挂点 | 事件 | 幂等键 | 关键字段 |
| --- | --- | --- | --- |
| 总结确认端点事务 | SUMMARY_CONFIRMED | `summary-confirmed:{summary_id}` | occurred_at=确认时刻 |
| 知识点候选批次确认事务 | KNOWLEDGE_CONFIRMED | `knowledge-confirmed:{batch_id}` | source=批次 |
| 逐题模式作答事务 | QUIZ_ANSWERED | `quiz-answered:{quiz_id}` | score 由 answer_result 映射（1/0，简答自评同）、difficulty 取习题难度、occurred_at=作答时刻 |
| 测验逐题评分完成（评分 job 写回尾部，同事务） | QUIZ_ANSWERED | `quiz-answered:test:{item_id}` | score 取逐题评分、occurred_at 取该题作答时刻（answered_at） |
| 交卷完成（评分落定处，同事务） | QUIZ_TEST_COMPLETED | `quiz-test-completed:{test_id}` | score 取卷面总分、occurred_at=完成时刻 |

- 批次采纳（习题/Todo）不发事件——既定语义（GLOSSARY.md「批次采纳」词条）；chat 行为不属学习事件（四事件 MVP 既定）。
- schema_version 起始 1；metadata_json 按事件类型记决策性上下文（题型、模式、课程等），不塞冗余快照。
- 幂等冲突（键已存在）= 静默跳过，不报错（同事务重试场景）。

**消费循环（ADR-0021）**：

- 独立 asyncio 后台任务，随应用 lifespan 启停（先例：JobRunner、RecordInvalidationNotifier 同类并存）。
- 纯周期扫描约 30s 一轮 + 启动即扫；不做写入时推送唤醒（本期零 UI 消费者）。
- 单调 id 水位：`id > 水位` 逐条取、逐条转换、幂等 upsert（撞 event_id 唯一约束即忽略）；水位仅在行处理后推进，崩溃重启从头全量补扫，靠唯一约束天然去重。**禁止 NOT EXISTS 相关子查询**（O(N×M) 前科）。
- 失败语义：单条转换失败重试 3 次后跳过 + error 日志 + 内存计数告警；不建死信表、不阻塞水位（证据可重放再生，个别缺失非灾难）。

**映射规则（集中一处声明，Q3 定稿）**：

| 事件 | evidence_type | score | difficulty | weight / confidence |
| --- | --- | --- | --- | --- |
| QUIZ_ANSWERED（逐题 + 测验键位） | QUIZ | 事件 score | 事件 difficulty | 0.9 / 0.8 |
| SUMMARY_CONFIRMED | USER_CONFIRMATION | —— | —— | 0.3 / 0.7 |
| KNOWLEDGE_CONFIRMED | USER_CONFIRMATION | —— | —— | 0.4 / 0.7 |
| QUIZ_TEST_COMPLETED | **不产证据** | —— | —— | ——（逐题已产，避免双计） |

- 数值为 Mastery 域调参初值，非产品语义承诺。

**查询能力**：learning 域内薄只读查询（按记录/课程/概念取证据），不建独立服务层抽象、不暴露 API——未来学习上下文中间件与统计的共同底座。

**agent 技术**：本期零 LLM、不引任何运行时记忆框架（§39.2 既有裁定：单用户场景 SQLite 业务表即记忆）；EvoScientist 蒸馏技法（三段节奏、observation schema）属 P4 画像域。

## Testing Decisions

- 好测试只断言外部行为：端点动作后事件行存在且字段正确、消费一轮后证据按映射落行、重跑不重、全量重放可重建、失败跳过且水位推进——不断言内部循环结构。
- **接缝（与用户确认）**：唯一新接缝 = 消费器「单轮执行」入口（服务级函数，测试直接调一轮，不等周期、不 monkeypatch 时钟——ADR-0012 runner 正式接缝同款纪律）。
- 事件写入：扩展现有 HTTP 级测试文件（总结/知识点/习题/模拟测试四域），断言同事务性（动作成功才落行、动作失败不落行）、幂等键、字段取值。
- 消费器与查询：新建服务级测试文件（先例：test_segment_search.py），覆盖映射表逐条、幂等重跑、崩溃全量重放重建、失败 3 次跳过、水位推进、测验键位与逐题键位共存。
- 迁移：user_version 断言同步（既定惯例）。
- 后端门禁全绿（pytest --basetemp=.pytest-tmp、ruff、pyright strict、openapi 逐字一致——本期零 schema 变更应零 diff）。

## Out of Scope

- Mastery Engine 与 user_concept_mastery 的任何计算或写入（红线 #3，P4）。
- 前端任何呈现、诊断端点、API 暴露、SSE 事件。
- agent 学习上下文中间件（agent/middleware/ 的后续工单）。
- LLM 画像蒸馏 / LearnerProfileService（P4）。
- source_anchor 回填（evidence.source_anchor_id 本期恒 NULL）。
- 事件类型扩展（TEACH_BACK / RECALL / MARKER / MISCONCEPTION / chat 等，按数据模型全集属后续域）。
- Record 删除时「按 record_id 排除出掌握度计算」的消费侧规则（P4 Mastery 职责；本期仅保证行不级联删除）。
- B1 web_search、B2 跨记录问答、sqlite-vec / semantic_embeddings。

## Further Notes

- 架构决策：ADR-0021（独立水位消费循环、与 ADR-0012 的边界、失败语义、禁 NOT EXISTS）；红线 #2（确定性 Service 与 Graph 分离）禁止 Evidence Builder 引入 LLM。
- 文档收尾：落地票内数据模型升 v2.6 重命名（event_id 唯一收紧，F1 CHECK 收紧先例）并同步全部交叉引用（PRD / 技术栈 / GLOSSARY.md / 扩展文档头部）。
- 事件写入函数的会话复用：挂点事务与事件写入必须同一事务会话，禁止独立连接写事件（崩溃窗口会造成动作成功而事件丢失）。
- 形态参考：docs/research/ 下 EvoScientist 架构分析（事件 → 后台确定性转换 → 可重放；其 LLM 蒸馏部分明确不搬）。
- QUIZ_TEST_COMPLETED 不产证据的双计规避为既定决策；未来若 Mastery 需要卷面级信号，从事件流直接取，不经 evidence。
