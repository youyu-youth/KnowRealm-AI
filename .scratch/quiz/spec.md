# 习题生成与作答

Status: ready-for-agent

## Problem Statement

KnowRealm 已能走通「转写 → 结构化总结 → 确认 → 知识点沉淀」，但学习闭环到"读懂"为止：用户无法验证自己是否真的掌握了内容——没有按需生成的练习题，没有作答与判分，更没有任何可支撑未来掌握度建模的作答数据。习题能力目前只有记录详情里一个禁用的占位页签。

本功能是 MVP 四个学习事件（#43）中 QUIZ_ANSWERED 的落地点——#33 的动机写得很直白：作答历史若不落地就永久丢失。同时它承载一组已定稿的边界裁决：作答存储落在 quizzes 行上三列（不提前建 Wave B 的测验明细表）、一题一答保证事件幂等语义干净、批次采纳是管理动作而非学习行为（不发事件）、Summary 换代不使已采纳批次失效。违反任何一条都会污染学习事件事实性或提前支付 Wave B 的结构成本。

## Solution

总结确认后（Record=COMPLETED），用户在记录详情的「习题」页签按需生成：勾选题型（选择题 / 判断题 / 简答题）与总题数档位（3 / 5 / 10，默认 5、记住上次选择），后端以普通 async worker 单次结构化 LLM 调用（仅以已确认 Summary + 课程上下文为输入，无 LangGraph）产出候选，成功即落库为 DRAFT 候选批次（题目跨重启可继续审阅）。

候选**纯只读**：用户整批采用或丢弃，不能剔除、编辑或手工出题。采用后该批置 ACTIVE、旧 AI 批次自动置 SUPERSEDED（其作答与事件永不删除，API 可回溯）；采用本身不发学习事件。在途候选时重复生成被 409 阻止。

作答为逐题模式：客观题（单选选择题、判断题）提交即自动判分；简答题必须先提交非空作答才显示参考答案，用户对照自评对/错（二态）。一题一答，提交即锁定；可中途离开续答。每题在对错已知的那一刻（客观判分后 / 简答自评后）落一条幂等的 QUIZ_ANSWERED 事件，作答内容与事件同事务写回题目行上的三列。全部作答完成后展示完成态与答对计数。

Transcript 编辑或 Summary 调优换代后：已采纳批次照常可作答（已发生的学习事实不失效）；在途候选的采用被 409 阻止并引导基于新总结重新生成。

## User Stories

1. As an 学习者, I want to 总结确认后在习题页签选择题型组合并生成, so that 练习就在记录详情里随手可得。
2. As an 学习者, I want to 从 3/5/10 三档选择总题数, so that 我能按可用时间控制练习量。
3. As an 学习者, I want to 系统记住我上次的档位选择, so that 下次生成少一步操作。
4. As an 学习者, I want to 生成异步进行并展示进行中状态, so that 界面不被模型调用阻塞。
5. As an 学习者, I want to 生成失败时看到可重试的失败状态, so that 一次网络问题不会让功能报废。
6. As an 学习者, I want to 手动重试复用失败任务, so that 重试不产生重复任务堆积。
7. As an 学习者, I want to 前置不满足（未确认总结 / 缺 Provider / 未同意外发 / 课程归档）时得到下一步指引, so that 我知道去哪里补齐条件。
8. As an 学习者, I want to 恰好按所选档位出题且所选题型各至少一道, so that 我的选择被如实兑现。
9. As an 学习者, I want to 每道题字段完整（题干 / 选项 / 答案 / 解析，简答为参考答案）, so that 练习和订正都有效。
10. As an 学习者, I want to 模型产出不合格时自动重试、最终失败则任务失败而非半截入库, so that 不会出现残缺题目。
11. As an 学习者, I want to 题目只基于我确认过的总结生成, so that 题目与解析有可信依据。
12. As an 学习者, I want to 候选生成后先只读审阅再决定, so that AI 产出不直接生效。
13. As an 学习者, I want to 整批采用候选批次, so that 确认后即可开始练习。
14. As an 学习者, I want to 不满意时丢弃整批候选重新生成, so that 题目不好可以干脆重来。
15. As an 学习者, I want to 在途候选时重复生成被拒绝, so that 不会堆积多批未处理的候选。
16. As an 学习者, I want to 采用新批次时看到旧批次剩余未作答数的提醒, so that 我不会误丢没做完的练习。
17. As an 学习者, I want to 采用批次本身不产生学习记录, so that 我的学习事件流里只有真实的学习行为。
18. As an 学习者, I want to 过时批次的数据与我的作答永久保留, so that 「过时」不等于「丢失」。
19. As an 学习者, I want to 选择题以单选交互作答, so that 操作方式与题型一致。
20. As an 学习者, I want to 判断题以对 / 错二选作答, so that 一眼可答。
21. As an 学习者, I want to 客观题提交即自动判分, so that 反馈是即时的。
22. As an 学习者, I want to 简答题先提交自己的作答才能看参考答案, so that 练习价值不被剧透毁掉。
23. As an 学习者, I want to 简答题对照参考答案自评对 / 错, so that 主观题也有可用的对错信号。
24. As an 学习者, I want to 一题一答、提交后锁定只读, so that 我的作答反映真实掌握水平。
25. As an 学习者, I want to 中途离开后回来继续作答, so that 练习节奏由我掌握。
26. As an 学习者, I want to 已作答的题展示答案与解析, so that 订正有依据。
27. As an 学习者, I want to 未自评的简答题显示待自评状态并可补评, so that 没完成的一步不会丢。
28. As an 学习者, I want to 全部作答后看到完成态与答对计数, so that 这次练习有明确的收束。
29. As an 学习者, I want to 重复提交作答不产生副作用, so that 网络重试不会污染记录。
30. As an 学习者, I want to 随时基于当前已确认总结重新生成候选, so that 想再练就有一批新题。
31. As an 学习者, I want to 转写编辑或总结调优后已采纳批次仍可继续作答, so that 修正总结不清空进行中的练习。
32. As an 学习者, I want to 换代后在途候选的采用被阻止并引导重生成, so that 基于旧内容的候选不会伪装成当前资产。
33. As an 学习者, I want to 习题页签按记录状态解锁, so that 不可用的时候不产生误导。
34. As an 本地用户, I want to 作答与事件同事务落库, so that 崩溃不会留下半截记录。
35. As an 本地用户, I want to prompt 与输出全文（含题目正文）不进入日志, so that 我的学习内容不出现在日志文件里。
36. As an 本地用户, I want to 单次 LLM 请求有超时上限, so that 失联调用不会无限占用 worker。

## Implementation Decisions

### 数据与迁移

- 新建 `quizzes` 表（下一号迁移），按数据模型 v2.2（2026-08-25 修订版）：`generation_status` 单列状态（DRAFT / ACTIVE / SUPERSEDED）、软删列、`batch_id`、`generated_from_summary_id`、`question_type`（MULTIPLE_CHOICE / TRUE_FALSE / SHORT_ANSWER）、`stem` / `options_json` / `correct_answer_json` / `explanation`、`difficulty`（EASY / MEDIUM / HARD），加**作答三列**：`user_answer_json`、`answer_result`（可空 CORRECT / WRONG，NULL=简答已提交待自评）、`answered_at`（可空；非空=已作答锁定）。**不建** model / prompt_version / quality_score / cognitive_level / concept_id / source_anchor_id 列——溯源记生成任务的 result_json（07 先例），其余由后续迁移加列。
- `processing_jobs.job_type` 新增 `QUIZ_GENERATION`；新增部分唯一索引：每 Record 至多一个 PENDING/RUNNING 的习题任务（仿 KP 索引）。
- 批次与生成任务一一对应：`batch_id` 复用生成 Job id；批次溯源（model、prompt_version、题目条数、题型构成）记入 Job 的 result_json。
- 失败重试沿用 06/07 模式：手动重试复用失败 Job，不新建。
- 作答不建新表（08 裁决）：练习作答存 quizzes 行上三列；`quiz_tests` / `quiz_test_items` 留 Wave B，届时测验作答另落 items 表。

### 生成管线

- 不建 LangGraph Graph（红线 #2）：普通 async worker 单次结构化生成，复用既有 LLM 客户端与 llm_call_logs 埋点；prompt 版本化自 quiz_v1 起。
- 输入组装：课程 learning_context / education_stage / depth + 当前已确认 Summary——**仅此而已**，无转写 input_mode 分叉（转写级细节题留 Wave B 再议）。
- Pydantic 严格校验：一次调用混合产出多题型；items 总数严格 = 所选档位（3/5/10）；题型构成由模型决定，但所选题型至少各 1 道；选择题单选（选项 3~5 个，correct_answer = 正确项下标）；判断题 options 固定「对 / 错」两项、correct_answer = 下标（与选择题同构、判分逻辑统一）；简答题 options 为空、correct_answer = 参考答案文本；difficulty 由模型输出；题干 / 选项 / 解析字数上限由 Schema 就地约束。任何违规令 Job FAILED（错误码如 LLM_OUTPUT_INVALID），不自动修正、不自动付费重试。
- 前置校验（任一不满足返回 409，不建 Job）：存在当前 CONFIRMED Summary、课程 ACTIVE、Provider 已配置、外部处理同意有效；Job input_json 记录 provider_fingerprint 与 generated_from_summary_id。单次请求沿用 90 秒超时。
- worker 领取 / 发布两阶段复核绑定 Summary 仍为 CONFIRMED（转写换代会先将 Summary 置 SUPERSEDED，故无需另绑转写版本），失效则 CANCELLED；成功后在单事务内落整批 DRAFT 行。

### 作答与事件

- **一题一答**：行上 answered_at 非空即锁定，不可重做；重复提交幂等返回现状（幂等键唯一约束兜底并发）。
- 客观题提交即判分（下标精确匹配）；简答题必须先提交非空作答，端点才返回参考答案，自评二态 CORRECT / WRONG 写回行上。
- 作答与 QUIZ_ANSWERED 事件**同事务**：source_type=QUIZ_QUESTION、source_id=quiz_id、幂等键 `quiz-answered:{quiz_id}`、metadata={batch_id, question_type, generated_from_summary_id}、result 二态、difficulty 从题目行带出、score / duration_ms / concept_id 恒空；**用户所选答案不进事件**（行上有，事件保持行为日志定位）。
- 事件时机 = 对错已知时：客观题判分后、简答题自评后；未自评 = 待自评、不发事件、不算完成。批次完成 = 批内全部题目已作答（简答含自评）。
- **批次采纳不发学习事件**（四事件无 QUIZ_CONFIRMED 槽位；采纳是管理动作，不是学习行为——GLOSSARY.md「批次采纳」术语）。

### 批次生命周期

- 候选纯只读：整批采用 / 放弃；不剔除、不编辑、无手工出题；只有 ACTIVE 批次的题可作答。
- 采纳（单事务）：前置 = 批次绑定的 Summary 仍为 CONFIRMED 且课程仍 ACTIVE，否则 409 并引导丢弃重生成；效果 = 该批 DRAFT→ACTIVE、既有其他 AI ACTIVE 批次置 SUPERSEDED；重复采纳幂等返回现状。
- 换代联动：Transcript 编辑 / Summary 调优使旧 Summary 置 SUPERSEDED 后，**ACTIVE 批次仍可作答**（已采纳资产不失效）；SUPERSEDED 只由「确认新批次」触发；过时批次默认隐藏，`?include=superseded` API 可回溯、无 UI 入口。

### API 契约

- 读端点镜像 KP 的 action_required 模式：返回 ACTIVE 批次题目 + 行上作答态、在途 DRAFT 批次、action_required（GENERATE / ADOPT / RETRY / NONE）、active_job_id、blocked_reason（SUMMARY_NOT_CONFIRMED / SUMMARY_SUPERSEDED / COURSE_ARCHIVED / PROVIDER_NOT_CONFIGURED / CONSENT_REQUIRED）。
- 写端点：生成（提交 Job，202 返回 job_id）、批次采纳（HTTP 路径沿用 KP 的 confirmations 形状，域术语与 UI 文案为「采用」）、批次丢弃（软删整批 DRAFT）、提交作答（客观判分 / 简答提交）、提交自评；失败重试复用失败 Job。
- OpenAPI 是前端类型唯一契约：schema 变更先落 OpenAPI 再生成 api-types，前端不手写重复定义。

### 桌面端

- 「习题」页签为真实功能，解锁 = record COMPLETED：空态引导卡（未确认总结时指向总结页签）、生成对话框（题型多选 + 3/5/10 档单选，默认读偏好，提交后写回）、进行中态（复用 active_job_id 条件轮询 + 既有 SSE 失效链，不加新通道）、候选只读审阅 + 采用 / 丢弃、采用确认弹窗附「旧批次剩 N 题未作答」提示（不阻塞）、逐题作答界面（单选 / 对错二选 / 简答文本框 + 提交后展示参考答案与自评）、完成态 + 答对计数（X / Y）。
- 偏好 `quiz_last_count`：生成对话框读写（初始默认 5），键与 13 设置页共享，全部经 sidecar API。
- 文案全部走 i18n；交互组件用 shadcn/ui + Base UI 原语；图标 lucide；纯图标按钮带 aria-label。

## Testing Decisions

- 好测试只断言外部行为：HTTP 响应、数据库终态（quizzes 行、事件行、批次状态、软删标记）、UI 可见结果；不断言服务内部调用序列。
- 后端沿 07 先例：真实应用 + ASGI 传输 + 真实迁移库 + lifespan 启动的真实 worker，经 HTTP 驱动全流程；唯一新接缝 = 应用工厂注入的 FakeQuizModel（镜像 FakeKnowledgePointModel 缝），支持序列输出（测校验失败重试）与阻塞控制（测活跃任务防重）。
- 前端沿 RecordDetail 测试先例：MSW 在 HTTP 层 mock 新端点，渲染真实路由（`?tab=quiz`）断言页签解锁、生成对话框、审阅交互、作答流与状态文案。
- 必测场景：恰好按档位出题且所选题型各 ≥1、Schema 违规重试后 FAILED；409 矩阵（前置缺失 × 在途 DRAFT × 换代阻止 × 归档）；客观题判分正确性；简答先非空作答才见参考答案、自评二态、待自评可补评；重复提交幂等与事件唯一约束；一题一答锁定与中断续答；采用后旧批 SUPERSEDED 而作答与事件保留、`?include=superseded` 回溯；换代后 ACTIVE 批照常作答、在途 DRAFT 采用被 409；软删链路；偏好默认与写回。

## Out of Scope

- 组卷 / 测验模式 / AI 语义评分 / 低置信复核标记 / 错题本（15，Wave B）；`quiz_tests` / `quiz_test_items` 建表。
- 候选题剔除与编辑、确认后单题删除与编辑、手工出题；多选题与 PARTIAL 结果。
- concept_id 绑定与掌握度回填（P3）、cognitive_level（P5）、quality_score（评测域 Wave B）。
- 转写级细节题的 input_mode 分叉（Wave B 再议）；设置页 UI（13）；学习统计消费（17）；Markdown 导出（10）。
- LangGraph / Checkpointer（裁决明示不引入）。

## Further Notes

- 作答形态（逐题 + 简答自评）系 08 plan grill 定稿（2026-08-25），非 PRD 既有裁决——plan 原引「Q10 定稿」实为决策 #20（属 15 的 AI 评分域），引用已修正；两场预烤存档（docs/claudecode-vs-zcode.md）中的 A/B 分歧已裁定 B（作答三列在行）。
- 数据模型 v2.2 已于 2026-08-25 同步修订（quizzes 作答三列、砍列、learning_events 幂等键构造格式 `{event-slug}:{source-id}`）；GLOSSARY.md 新增「作答」「批次采纳」术语。
- Wave B 键位预留：测验模式同题再答的幂等键另立（`quiz-answered:test:{item_id}` 风格），避免与本批 `quiz-answered:{quiz_id}` 冲突。
- 全部裁决与回写记录见 `.scratch/function-plans-introduction/08-quiz.md`。
- 实现注意：仓库内另有会话在改 records 前端文件（keys.ts / RecordDetailPage 相关），动工前先确认错峰或其变更已提交。
