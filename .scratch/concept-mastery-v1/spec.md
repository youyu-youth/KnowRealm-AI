# Concept 级学习证据与 Mastery V1

Status: ready-for-agent

依据：2026-09-16 `grill-with-docs` 七轮裁决（Q1～Q22 全部按推荐）+ `to-spec` 测试接缝确认。

## Problem Statement

课程大脑已经能把多条 Record 中的内容整理为经用户确认、可追溯的 Course 级 Concept，学习事件与学习证据管道也已经记录总结确认、知识点确认和 Quiz 作答。但两条链路尚未接通：现有 Event/Evidence 的 `concept_id` 恒为空，Quiz 不知道自己实际评估哪个 Concept，系统因而无法回答“我对这个概念掌握到什么程度、依据是什么”。

课程详情里的 Knowledge GPS 与掌握度卡仍使用确定性示意数据。它们会显示看似精确、实际并非来自用户学习行为的章节百分比，既不能用于长期学习决策，也无法回溯到具体作答。若直接把 Record 的全部 Concept、AI 生成内容或内容审核动作当作能力证据，又会制造更严重的误判。

本功能需要在不混淆 KP、Concept、Learning Evidence、Mastery 与 Forgetting 的前提下，建立一条最小但完整、确定性、可解释、可重建的真实闭环。

## Solution

为每道 Quiz 增加一个可空的“主概念”：生成时只能从所在 Record 已确认的 Concept 中建议一个，用户可在首次作答前修改或清空，首次作答后固定。只有带主概念且具有可判定结果的 Quiz Evidence 才进入 Mastery；总结确认、知识点确认继续作为学习活动留痕，但不会抬高掌握度。

Evidence Consumer 将 Event 中已固化的 Concept 原样写入 Evidence，随后由确定性 Mastery Engine 从最近 12 条有效 Quiz Evidence 重建 Concept Mastery 快照。Mastery 不由 LLM 计算，不随墙钟时间自动衰减，失败时不损害上游 Event/Evidence。课程与 Concept 只读 API 向前端提供状态分布、快照和可追溯证据。

Knowledge GPS、课程概览与 Course Brain 使用真实 Mastery 数据替换示意掌握度：Concept 级显示数值、Confidence、证据量和最近验证时间；课程级只显示覆盖率与状态分布，不伪造课程平均分；Course Brain 仅增加非侵入式状态标记，不让节点主颜色冒充掌握度。

## User Stories

1. As a 学习者, I want to 每道习题明确它主要评估哪个 Concept, so that 作答可以成为 Concept 级学习证据。
2. As a 学习者, I want to AI 只从当前 Record 已确认的 Concept 中建议主概念, so that 候选或其他课程的 Concept 不会污染学习状态。
3. As a 学习者, I want to 在首次作答前修改 AI 建议的主概念, so that 我能纠正错误归属。
4. As a 学习者, I want to 清空无法可靠归属的主概念, so that 系统宁可少算也不错误归因。
5. As a 学习者, I want to 没有 Course Brain 或没有已确认 Concept 时仍可正常生成和作答习题, so that Mastery 能力不会破坏现有学习流程。
6. As a 学习者, I want to 首次作答后主概念保持固定, so that 同一历史行为重放时不会改变语义。
7. As a 学习者, I want to 已作答的历史习题不被系统自动猜测 Concept, so that 旧数据不会被不可靠回填。
8. As a 学习者, I want to 未作答的历史习题仍可在作答前选择主概念, so that 现有题库可以从现在开始积累真实 Mastery。
9. As a 学习者, I want to 无主概念的作答继续保留原始 Event/Evidence, so that 学习历史不会因暂时不能归属而丢失。
10. As a 学习者, I want to Quiz 作答成功后自动进入 Concept Evidence 管道, so that 不需要额外点击或配置。
11. As a 学习者, I want to 只有实际作答结果可以改变 Mastery V1, so that 确认 AI 总结或知识点不会被误认为已经掌握。
12. As a 学习者, I want to AI 生成的解释、Concept 描述和 Course Brain 推断永不成为能力证据, so that 模型不能自证其输出正确。
13. As a 学习者, I want to 同一次作答重试或重复提交只产生一份 Evidence, so that Mastery 不会被重复灌水。
14. As a 学习者, I want to 模拟测试的每道题按自己的主概念积累 Evidence, so that 卷面总分不会掩盖不同 Concept 的表现。
15. As a 学习者, I want to 交卷事件不额外产生 Mastery Evidence, so that 逐题结果与卷面结果不会双计。
16. As a 学习者, I want to 少于三条有效 Evidence 时看到“数据不足”, so that 一次偶然答对不会显示伪精确掌握度。
17. As a 学习者, I want to 达到三条 Evidence 后看到 Mastery 数值及 LOW Confidence, so that 我能区分初步表现与稳定结论。
18. As a 学习者, I want to 最近表现比很久以前的表现更影响当前 Mastery, so that 早期错误不会永久拖低后来真正学会的内容。
19. As a 学习者, I want to Mastery 不因几天没有打开应用而自动下降, so that 已验证能力与遗忘风险不会混为一谈。
20. As a 学习者, I want to 题目难度标签暂不直接修改 Mastery, so that 未校准的 AI 难度不会制造伪科学权重。
21. As a 学习者, I want to Confidence 表示证据充足程度而不是成绩好坏, so that “低分但证据充分”也能被准确表达。
22. As a 学习者, I want to 连续取得新进步后状态能从 WEAK 恢复到 LEARNING 或 STABLE, so that Mastery 反映当前已验证能力。
23. As a 学习者, I want to 低 Confidence 的高分仍保持 LEARNING, so that 少量全对不会过早宣称稳定掌握。
24. As a 学习者, I want to Knowledge GPS 按 Concept 显示真实状态, so that 我能找到需要继续学习的内容。
25. As a 学习者, I want to 按 Mastery 状态筛选 Concept, so that 我能优先查看 WEAK 或数据不足的内容。
26. As a 学习者, I want to 每个 Concept 显示 Evidence 数量和最近验证时间, so that 我能判断状态的新鲜程度和依据规模。
27. As a 学习者, I want to 点击 Concept 查看贡献给 Mastery 的 Quiz Evidence, so that 每个结果都可以解释。
28. As a 学习者, I want to 从 Evidence 跳回对应习题或模拟测试结果, so that 我能复盘具体错误。
29. As a 学习者, I want to 课程概览显示已确认 Concept 的证据覆盖率, so that 我知道课程大脑中还有多少内容未经验证。
30. As a 学习者, I want to 课程概览显示四类状态数量, so that 我能理解整体学习分布而不是被单一平均分误导。
31. As a 学习者, I want to Course Brain 图谱保留知识关系的原有视觉语义, so that Mastery 不会遮蔽 Concept 结构。
32. As a 学习者, I want to Course Brain 节点提供非侵入式 Mastery 标记和详情, so that 我可以在知识结构中理解自己的学习状态。
33. As a 学习者, I want to 未构建 Course Brain 时看到明确引导而非虚假 Mastery, so that 空状态不会假装已有数据。
34. As a 学习者, I want to Candidate Concept 永不进入 Mastery, so that 尚未治理的重复或错误概念不会形成长期状态。
35. As a 学习者, I want to Archived Concept 保留历史 Mastery 和 Evidence, so that 归档不会篡改过去的学习事实。
36. As a 学习者, I want to Archived Concept 默认退出活跃课程聚合, so that 退役内容不会影响当前覆盖率。
37. As a 学习者, I want to 删除 Record 后相关 Evidence 不再参与 Mastery, so that 已删除内容不会继续影响学习状态。
38. As a 学习者, I want to 删除 Record 时历史 Event/Evidence 仍保留审计价值, so that 删除业务内容不会重写事实历史。
39. As a 学习者, I want to 算法升级后 Mastery 自动按新版本重建, so that 不会同时存在多种不可辨认的计算口径。
40. As a 学习者, I want to Mastery 计算失败时 Event/Evidence 仍安全保存, so that 派生状态故障不会造成事实丢失。
41. As a 学习者, I want to 应用重启后缺失或过期的 Mastery 快照自动恢复, so that 崩溃不会永久留下空洞。
42. As a 学习者, I want to Mastery 更新允许短暂后台延迟但最终自动出现, so that Quiz 请求无需承担额外计算耦合。
43. As a 学习者, I want to 不能手工输入 Mastery 百分比或直接标记已掌握, so that Mastery 始终保持证据含义。
44. As a 学习者, I want to Mastery 与所有学习数据继续保存在本地数据目录, so that 功能维持本地优先与可搬移承诺。
45. As a 学习者, I want to Mastery 计算不消耗额外 token, so that 后台学习状态更新零费用。
46. As a 维护者, I want to Event、Evidence 与 Mastery 的职责单向清晰, so that Quiz、Tutor 等业务未来不能绕过唯一写入口。
47. As a 维护者, I want to 从 Evidence 全量确定性重建任意 Concept 快照, so that 算法调优和数据失效不需要维护增量补丁账本。
48. As a 维护者, I want to 每个 Mastery 快照记录算法版本, so that 可识别和重建旧口径结果。
49. As a 维护者, I want to 使用现有 Evidence Consumer 而不是新建队列, so that 系统保持单机架构简单。
50. As a 维护者, I want to API 只暴露 Mastery 只读查询, so that 前端和 Agent 都不能直接篡改学习状态。

## Implementation Decisions

### 领域与交付边界

- 本次交付一个完整闭环：Quiz 主概念 → Concept Event/Evidence → Mastery Engine → 只读 API → Knowledge GPS / 课程概览 / Course Brain 展示。
- 对外作为一次完整功能交付；内部后续使用 `to-tickets` 拆成带阻塞关系的 tracer-bullet 垂直工单。
- Knowledge Point 仍是 Record 级资产，Concept 仍是 Course 级规范节点，二者不合并。
- 只有 `CONFIRMED` Concept 接收新的 Concept Evidence。`CANDIDATE` 永不进入 Mastery；`ARCHIVED` 保留历史快照与 Evidence，但退出活跃聚合且不接收新证据。
- Mastery 表示已验证能力，Forgetting Risk 表示时间衰减风险。Mastery 不因墙钟时间流逝自动变化。
- Mastery V1 只消费具有可判定结果的 Quiz Evidence。`SUMMARY_CONFIRMED` 与 `KNOWLEDGE_CONFIRMED` 保留为学习活动 Evidence，但不进入 Mastery 计算。
- 不允许业务模块、前端或 Agent 直接修改 Mastery；唯一写入口为确定性 Mastery Engine。

### Quiz 主概念

- Quiz 增加可空主概念归属；V1 一题至多一个主概念，不新增多对多表。
- 生成 Quiz 时，模型只能从该 Record 对应的 `CONFIRMED` Concept 清单中建议一个主概念；返回值必须经过服务端 ID/课程/状态校验。
- 无 Course Brain、无已确认 Concept、模型未选择或校验失败时，主概念为空，原生成与作答流程继续可用。
- 用户可以在首次作答前修改或清空主概念。首次作答后归属固定，普通 Quiz 与模拟测试题均遵守同一语义。
- 已作答且主概念为空的历史 Quiz 不做自动回填、不做 Record 全量广播、不调用 LLM 批量猜测；未作答旧题仍可在首次作答前归属。
- Event 写入时固化 `concept_id`，Evidence Builder 只复制 Event 中的值，禁止在重放时查询可变化的 `record_concepts` 推导归属。
- 一题一个主概念使“一 Event 至多一 Evidence”的现有唯一约束继续成立，不改变为扇出模型。

### 数据模型

- 新迁移为 Quiz 增加可空 `concept_id`。服务端保证它属于同课程且状态为 `CONFIRMED`；历史行保持空值。
- 新增 `user_concept_mastery`，每个 Concept 至多一条快照；Concept 被物理删除时快照随之清理，状态归档不删除快照。
- V1 快照只保存当前真实使用的字段：课程、Concept、Mastery、Confidence、Evidence 总数/正向数/负向数、最近练习时间、最近验证时间、算法版本、更新时间。
- `memory_strength`、`transfer_score`、`reasoning_score`、`next_review_at` 不在本次建列；对应功能落地时再迁移。
- Event/Evidence 的 `concept_id` 继续保持追加事实语义，不因 Concept 重命名改变；候选永不接证据，因此现有候选合并不需要迁移 Mastery。
- 不为本功能引入向量表、任务表、死信表、外部数据库或新依赖。

### Mastery 算法 V1

- 算法是普通确定性 Python Service，不进入 LangGraph，不调用 LLM。
- 只读取 Concept 最近 12 条有效、带分数的 Quiz Evidence；按 `occurred_at` 排序并以稳定 ID 打破平局。
- 关联 Record 已软删除、课程不匹配、Concept 非 `CONFIRMED` 或归属为空的 Evidence 不参与活跃计算。
- 题目难度在 V1 中保留但不参与数值计算，因为当前难度是未校准的模型标签。
- 下面公式来自 Grill 阶段的场景原型，作为 V1 数值合同：

```text
rank_weight = 0.5 ^ (距最新 Evidence 的条数 / 4)
effective_weight = rank_weight × evidence.weight × evidence.confidence
mastery_score = Σ(score × effective_weight) / Σ(effective_weight)

effective_count = Σ(evidence.weight × evidence.confidence) / 0.72
mastery_confidence = min(1, effective_count / 8)
```

- 排名权重以四条 Evidence 为半衰跨度，只在 Evidence 集变化或显式重算时改变；不读取当前日期。
- 当前 Quiz 的 `weight=0.9`、`confidence=0.8`，因此单条标准 Quiz 的有效计数为 1。
- 少于 3 条有效 Evidence：`NOT_ENOUGH_DATA`，不显示 Mastery 百分比。
- 达到 3 条后显示百分比；Confidence 分档为：有效计数 3～4 为 `LOW`，5～7 为 `MEDIUM`，8 及以上为 `HIGH`。
- 状态规则：分数小于 0.50 为 `WEAK`；分数至少 0.80 且 Confidence 高于 `LOW` 为 `STABLE`；其余为 `LEARNING`。
- `AT_RISK` 与 `MISCONCEPTION_RISK` 不在 V1 生成，分别留给 Forgetting 与 Misconception 功能。
- 正向/负向 Evidence 数量按已有判定结果统计，不通过难度或 Mastery 阈值重新发明结果语义。
- 黄金场景：3 次全对 = 100% + LOW；4 错后 4 对约 67%；4 对后 4 错约 33%；8 次对错交替约 46%；6 错后 6 对约 74%。

### 计算、失效与恢复

- Quiz 业务事务继续只负责业务状态与 Event 同事务落库，不直接计算或写 Mastery。
- 现有 Evidence Consumer 生成 Concept Evidence 后触发受影响 Concept 的全量重算；继续接受后台最终一致性，正常更新延迟上限沿用现有约 30 秒轮询。
- Event 与 Evidence 是上游事实，Mastery 是下游派生快照。Mastery 重算失败不得回滚已经成功持久化的 Event/Evidence。
- Mastery 重算单独重试并记录结构化错误；不增加死信表。应用启动时扫描缺失或算法版本过期的快照并重建。
- Record 软删除后，相关历史 Event/Evidence 保留，但通过 Event 的 Record 归属排除出有效集合，并重算受影响 Concept。
- Course 删除遵循现有 Record 删除链；Concept 物理删除后快照清理，Event/Evidence 仍遵守既有事实保留纪律。
- Concept 重命名不改变 ID，不触发迁移。Concept 归档保留快照但退出活跃查询；若未来恢复，可从保留 Evidence 重建。
- 算法升级只增加算法版本并重建快照，不原地修补旧分数，也不维护加减账本。

### API 合同

- 新增课程 Mastery 只读查询，返回课程覆盖率、四类状态计数以及 Concept Mastery 列表；支持按状态筛选，并只聚合活跃 `CONFIRMED` Concept。
- 新增 Concept Mastery 只读查询，返回快照、状态、Confidence 分档、有效 Evidence 列表和可跳转的业务来源信息。
- Evidence 列表按时间倒序，明确区分普通 Quiz 与模拟测试题；只返回实际参与当前算法版本的有效 Evidence。
- 数据不足的 Concept 返回显式 `NOT_ENOUGH_DATA`，Mastery 数值为空，而不是返回 0%。
- 无 Mastery 行但 Concept 已确认时返回可消费的空状态，不把“尚未计算”伪装成 404。
- Course Brain API 继续负责知识结构，Mastery API 负责学习者状态；前端在查询层组合两者，不扩张 CourseBrainService 的职责。
- 不提供修改分数、标记已掌握或直接重算任意数值的公共写 API。

### Desktop 体验

- Knowledge GPS 从章级示意数据改为真实 Concept Mastery 列表，展示状态、可用时的百分比、Confidence、Evidence 数量和最近验证时间。
- 支持按 `NOT_ENOUGH_DATA / WEAK / LEARNING / STABLE` 筛选；默认排序优先暴露 WEAK、LEARNING 与数据不足项，稳定项靠后。
- 课程概览卡删除模拟章节与模拟百分比，改为已确认 Concept 数、具备验证 Evidence 的覆盖率及四类状态分布。
- 不显示“课程总掌握度”单一百分比。
- Course Brain 图谱保留现有 Concept/Relation 视觉语言，只增加小型状态标记、Tooltip 信息与详情内容；节点主颜色不直接编码 Mastery。
- Concept 详情展示参与计算的 Quiz Evidence，并复用现有路由能力跳转到普通 Quiz 或模拟测试结果；不能定位时仍展示来源文本与时间。
- 空课程、未构建 Course Brain、零已确认 Concept、零 Evidence、后台计算中、请求失败均有明确且诚实的状态。
- 新增或修改的全部 UI 文案同步中英文资源，使用现有设计令牌、Base UI/shadcn 原语和 TanStack Query；不建立第二份前端持久化 Mastery 状态。
- UI 实现遵循 `impeccable`，覆盖亮色、暗色、窄窗口、键盘焦点、可读对比度和 `prefers-reduced-motion`；页面仍遵守固定工作区与局部滚动约束。

### 文档与交付

- 本决策满足难逆转、非显然且存在真实权衡三项条件，应新增 ADR，记录验证性 Evidence 边界、确定性派生快照及与 Forgetting 分离的理由。
- 数据模型升版并重命名，标记 Quiz 主概念与 Mastery 表已实施；同步功能基线、技术栈、扩展设计、领域词汇和全部交叉引用。
- 完成功能后更新项目进度文档，保持其不超过 200 行并删除过期的 Mastery 示意描述。
- 规格批准后使用 `to-tickets` 生成本地 tracer-bullet 垂直工单；不沿用按数据库/API/UI 分层的横向票据。

## Testing Decisions

- 测试只证明当前功能的外部合同，不断言私有函数调用次数、SQL 拼接形态或组件内部状态。
- 最高后端接缝为：通过 HTTP 完成 Quiz 作答，调用现有 Evidence Consumer 单轮入口，再通过 HTTP 查询 Course/Concept Mastery。该接缝覆盖 Event、Evidence、Mastery、持久化、过滤与响应合同，不新增测试专用后门。
- Quiz 主概念通过现有 Quiz HTTP 测试扩展，覆盖：仅允许同课程 CONFIRMED Concept、可空、首次作答前可修改、作答后拒绝变更、无 Course Brain 零回归、事务失败不落 Event。
- Evidence Consumer 测试扩展为 Event `concept_id` 原样复制、无归属仍为空、一 Event 一 Evidence、重复扫描幂等、Mastery 失败不丢 Evidence。
- Mastery 算法保留一个纯函数接缝，以表驱动黄金样本验证 12 条窗口、四条半衰、Confidence、最小证据数和状态分类；这是一项数值合同，不能只靠端到端测试间接覆盖。
- 生命周期测试覆盖 Record 删除排除、Archived Concept 保留但不聚合、算法版本过期重建、缺失快照启动恢复及跨课程防护。
- API 测试覆盖空状态、状态分布、覆盖率、筛选、Evidence 顺序、来源类型、已删除 Record 排除和 Archived Concept 行为。
- 前端最高接缝沿用课程详情的 MSW 渲染测试，通过用户交互验证 Knowledge GPS、概览卡、Course Brain 标记、筛选和 Evidence 下钻；不为新 UI 另造平行状态容器。
- 前端测试覆盖加载、错误、数据不足、四类状态、中英文 key 一致性及无单一课程平均分。
- 后端验收运行相关测试后再运行全量 pytest、ruff、pyright 与 OpenAPI 契约检查；测试临时目录在结束后删除。
- 前端验收运行相关测试后再运行稳定并发的全量测试、lint、触及文件格式检查与 build；不借机修复无关基线问题。
- jsdom/MSW、lint 与 build 不作为真实 Tauri/WebView2 视觉证据。自动化通过后单独检查亮色、暗色、窄窗口和关键交互，并保留用户真机验收清单，不代勾用户验收。

## Out of Scope

- Misconception Engine、误区确认或纠错训练。
- Forgetting Engine、Memory Strength、遗忘风险、FSRS、复习调度与 `next_review_at`。
- Tutor、Teach-back、Recall Verification、Transfer Challenge 及其新 Evidence 类型。
- Learner Digital Twin、学习目标、学习计划、Autopilot 与 Agent 学习上下文中间件。
- 多 Concept Quiz、多对多 Quiz-Concept 关联和一 Event 扇出多 Evidence。
- 对已作答历史 Quiz 的 LLM 批量归属、Record 全量广播或其他猜测式回填。
- 手工编辑 Mastery、手工标记已掌握、课程总掌握度或排行榜。
- 使用 AI 难度标签调整 Mastery，或引入 IRT、BKT、机器学习训练和在线实验平台。
- 随时间自动衰减 Mastery；任何遗忘语义留给 F9。
- 为 Mastery 引入 LangGraph、SubAgent、MCP、新队列、向量库或外部服务。
- 修改 Course Brain 的 Concept 抽取、关系治理或 B2 检索算法。

## Further Notes

- `record_concepts.evidence_count` 表示内容来源命中次数，不是学习者 Learning Evidence，UI 与代码命名必须避免混淆。
- Course Brain 构建产生的来源锚点会在重建时替换，不能被当作 Quiz Evidence 的长期稳定归属；V1 通过 Event 的业务来源回溯 Quiz。
- Mastery 的准确性上限首先由 Quiz 与 Concept 的归属质量决定。宁可保持空值和数据不足，也不通过 Record 粒度广播追求虚假覆盖率。
- 当前权重与 Confidence 规则是可版本化的 V1 产品合同，不是永恒真理；未来调整必须新增算法版本、补充黄金样本并全量重建，不静默改变旧口径。
- 规格发布后下一步是运行 `to-tickets`，先让用户确认垂直切片与阻塞边，再写入一票一文件的本地工单。
