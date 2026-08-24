# 知识点提取

Status: ready-for-agent

## Problem Statement

KnowRealm 已能完成「转写 → 结构化总结 → 确认」的闭环，确认后 Record 进入 COMPLETED，但学习链到此为止：一节课里真正值得记住的知识点仍埋在总结和转写里，用户只能靠手工抄写沉淀，无法筛选、纠错、分级，也没有任何后续能力（习题、复习、导出、对话引用）可以消费的结构化知识点资产。

本功能是总结确认后的第一项后续 AI 能力，也是 MVP 四个学习事件（#43）中 KNOWLEDGE_CONFIRMED 的落地点。如果候选生成后不落库（关窗即丢）、确认无幂等（重复点击重复计事件）、批次换代时误删用户已编辑内容、或把 Record 级知识点与 Course 级概念混同，会同时破坏 HITL 可信度、学习事件事实性和概念分层的红线 #9。

## Solution

总结确认后（Record=COMPLETED），用户在记录详情的「知识点」页签按需触发生成：后端以单次结构化 LLM 调用（无 LangGraph，普通 worker）从课程上下文 + 已确认 Summary + 转写（超长时仅 Summary 并在 UI 明示）提取候选，**生成成功即落库为 DRAFT 候选行**（按批次分组），因此跨重启、隔天都能继续筛选。

用户在候选批次内删除、编辑（名称/详情/标签/五星重要度），手工补充的条目立即保存为独立行（不属于任何批次）。确认批次后候选整体转为 ACTIVE、旧 AI 批次自动置 SUPERSEDED、一次确认动作落一条幂等的 KNOWLEDGE_CONFIRMED 事件；手工编辑与补充的内容永不因批次换代被删除。确认之后仍可继续编辑、删除、补充。

每条 AI 批次绑定生成时的已确认 Summary；转写被编辑换代后，在途候选的确认被阻止并引导基于新总结重新生成，已保存知识点保持可见可编辑。批次溯源（模型、prompt 版本、条数）记录在生成任务的结果 JSON 中，知识点表保持精简单列状态。

桌面端落地真实的「知识点」页签，其余未接入能力以 PRD 命名（习题/复习/Todo/Ask AI）禁用展示；生成进度复用既有任务轮询，不新增推送通道。

## User Stories

1. As an 学习者, I want to 总结确认后在知识点页签一键生成候选, so that 提取知识点的动作就在记录详情里完成。
2. As an 学习者, I want to 总结未确认时看到明确的引导空态, so that 我知道下一步是先去确认总结。
3. As an 学习者, I want to 尚未生成时看到生成按钮和说明, so that 我能理解这个动作会产生什么。
4. As an 学习者, I want to 生成提交立即返回并看到进行中状态, so that 界面不被模型调用阻塞。
5. As an 学习者, I want to 生成失败时看到可重试的失败状态, so that 一次网络问题不会让功能报废。
6. As an 学习者, I want to 手动重试复用失败任务, so that 重试不产生重复任务堆积。
7. As an 学习者, I want to 缺 Provider 或外发同意时得到下一步指引, so that 我知道去哪里补齐条件而不是对着报错发呆。
8. As an 学习者, I want to 候选生成后直接进入可编辑列表, so that 筛选纠错不需要额外的导入步骤。
9. As an 学习者, I want to 删除不需要的候选, so that 最终保存的只有我认可的内容。
10. As an 学习者, I want to 编辑候选的名称、详情、标签和重要度, so that AI 的表述可以被纠正。
11. As an 学习者, I want to 用五颗星标记重要度, so that 重要性一眼可辨且随手可调。
12. As an 学习者, I want to 维护每条知识点的少量标签, so that 之后的检索和引用有抓手。
13. As an 学习者, I want to 手工补充自己的知识点, so that AI 漏掉的内容当场补上。
14. As an 学习者, I want to 手工补充即时保存, so that 不小心关窗也不会丢内容。
15. As an 学习者, I want to 关闭应用后隔天继续筛选同一批候选, so that 审阅没有会话时限。
16. As an 学习者, I want to 不满意时丢弃整批候选, so that 我可以干脆地从头再来。
17. As an 学习者, I want to 确认保存候选批次, so that 知识点成为这条记录的正式学习资产。
18. As an 学习者, I want to 重复点击确认不产生任何副作用, so that 网络重试不会造成重复事件。
19. As an 学习者, I want to 确认后列表内容与顺序保持稳定, so that 落定瞬间没有视觉跳变。
20. As an 学习者, I want to 确认后仍可编辑或删除知识点, so that 记错的内容随时可以修正。
21. As an 学习者, I want to 确认后仍可继续手工补充, so that 资产随理解加深而增长。
22. As an 学习者, I want to 基于当前已确认总结重新生成候选, so that 总结改进后知识点能够跟上。
23. As an 学习者, I want to 新候选审阅期间旧知识点保持可用, so that 重新生成不是破坏性操作。
24. As an 学习者, I want to 确认新批次后旧 AI 批次自动过时, so that 列表里始终只有一套有效知识点。
25. As an 学习者, I want to 手工编辑和补充的内容永不因换代被删, so that 我的劳动成果是安全的。
26. As an 学习者, I want to 过时批次的数据仍可回溯, so that 「过时」不等于「丢失」。
27. As an 学习者, I want to 已有在途候选时重复生成被拒绝, so that 不会堆积多批未处理的候选。
28. As an 学习者, I want to 转写编辑后已保存知识点仍然可见可编辑, so that 修正转写错字不会清空学习资产。
29. As an 学习者, I want to 转写换代后在途候选的确认被阻止, so that 基于旧内容的候选不会伪装成当前资产。
30. As an 学习者, I want to 确认被阻止时得到重新生成的引导, so that 我知道如何推进而不是被困在原地。
31. As an 学习者, I want to 新总结确认后重新生成入口自动恢复, so that 流程能够自然衔接。
32. As an 学习者, I want to 归档的课程不能再触发生成或确认, so that 已归档知识空间不会继续消费外部服务。
33. As an 学习者, I want to 超长转写时基于总结提取并明确告知, so that 我知道这批候选的依据是什么。
34. As an 学习者, I want to 候选数量由内容密度决定, so that 简短的记录不会被硬凑条数。
35. As an 学习者, I want to 知识点页签按记录状态解锁, so that 不可用的时候不产生误导。
36. As an 学习者, I want to 未接入的能力以真实命名禁用展示, so that 我知道产品还有哪些可期待的能力。
37. As an 学习者, I want to 已保存知识点默认按重要度排序, so that 最重要的内容永远排在前面。
38. As an 本地用户, I want to prompt 与输出全文不进入日志, so that 我的学习内容不出现在日志文件里。
39. As an 本地用户, I want to 单次 LLM 请求有 90 秒超时, so that 失联调用不会无限占用 worker。

## Implementation Decisions

### 数据与迁移

- 新建 `knowledge_points` 表（下一号迁移），按数据模型 v2.2（2026-08-24 修订版）：`generation_status` 单列状态（DRAFT / ACTIVE / SUPERSEDED）、软删、`batch_id` 与 `generated_from_summary_id` 可空、`importance` REAL 承载 1~5、`tags` JSON 数组（≤5 个）、`source_anchor_id` 列预留 P1 恒空。不建批次表，不加 model/prompt_version 列。
- processing_jobs 的 `job_type` 枚举新增 `KNOWLEDGE_EXTRACTION`；新增部分唯一索引：每 Record 至多一个 PENDING/RUNNING 的 KP 任务（仿 SUMMARY 索引）。
- 批次与生成任务一一对应：`batch_id` 直接复用生成 Job 的 id；批次溯源（model、prompt_version、候选条数、输入模式 FULL_TRANSCRIPT / SUMMARY_ONLY）记入该 Job 的 result_json。
- 失败重试沿用 06 模式：手动重试复用失败 Job，不新建。

### 生成管线

- 不建 LangGraph Graph（红线 #2）：普通 async worker 单次结构化生成，复用既有 LLM 客户端与 llm_call_logs 埋点；prompt 版本化自 kp_v1 起。
- 输入组装：课程 learning_context / education_stage / depth + 当前已确认 Summary（topic/abstract/sections）+ 转写全文；转写超过 3 万 Unicode code point 时仅送 Summary，响应与 UI 标识「基于总结提取」——非静默截断（沿用 06 的分级线与计数口径）。
- Pydantic 严格校验候选输出：1~20 条，name ≤100 字、detail ≤2000 字、tags ≤5 个各 ≤20 字、importance 为 1~5 整数；任何违规令 Job FAILED（错误码如 LLM_OUTPUT_INVALID），不自动修正、不自动付费重试。
- 前置校验（任一不满足返回 409，不建 Job）：存在当前 CONFIRMED Summary、课程 ACTIVE、Provider 已配置、外部处理同意有效；Job input_json 记录 provider_fingerprint 与 generated_from_summary_id。单次请求 90 秒超时。
- 生成成功即在单事务内落整批 DRAFT 行；每 Record 至多一个在途 DRAFT 批次，存在时再生成返回 409。

### API 契约

- 读端点镜像 Summary 的 action_required 模式：返回已保存（ACTIVE）知识点、在途 DRAFT 批次行、action_required（GENERATE / CONFIRM / RETRY / NONE）、active_job_id 与 blocked_reason；`?include=superseded` 返回过时批次行（回溯口径）。
- 写端点：生成（提交 Job）、手工新增（立即 ACTIVE 的独立行）、单条编辑与软删（DRAFT 与 ACTIVE 行均可）、批次确认、批次丢弃（软删整批 DRAFT 行）。
- 确认语义（单事务）：前置 = 批次绑定的 Summary 仍为 CONFIRMED 且课程仍 ACTIVE，否则 409 并引导丢弃重生成；效果 = 该批 DRAFT 行置 ACTIVE、既有其他 AI ACTIVE 批次置 SUPERSEDED、落一条 KNOWLEDGE_CONFIRMED 事件；重复确认幂等返回现状。
- 事件契约：source_type=KNOWLEDGE_BATCH、source_id=batch_id、幂等键 `knowledge-confirmed:{batch_id}`、metadata={batch_id, confirmed_count, generated_from_summary_id}；确认后的手工增删改不再落事件。

### 桌面端

- 「知识点」页签为真实功能：空态引导卡（#42：未确认总结时指向总结页签）、生成按钮、进行中态（复用任务轮询，不新增通道）、候选审阅列表（删除/编辑/补充）、确认与丢弃动作。
- 占位页签一次对齐 PRD 命名：知识点（本功能）/ 习题 / 复习 / Todo / Ask AI，未接入者保持禁用并说明原因。
- 编辑组件复用同一套 UI 服务于候选审阅与确认后的持续编辑；重要度五星可编辑；已保存列表默认按重要度降序。

## Testing Decisions

- 好测试只断言外部行为：HTTP 响应、数据库终态（事件行、批次状态、软删标记）、UI 可见结果；不断言服务内部调用序列。
- 后端沿 06 先例：真实应用 + ASGI 传输 + 真实迁移库 + lifespan 启动的真实 worker，经 HTTP 驱动全流程；唯一新接缝 = 应用工厂注入的 KP 生成 Fake 模型（镜像 SummaryModel 缝），支持序列输出与阻塞控制以测试并发与迟到场景。
- 前端沿 RecordDetail 测试先例：MSW 在 HTTP 层 mock 新端点，渲染真实路由断言页签解锁、审阅交互、确认/丢弃与状态文案。
- 必测场景：409 矩阵（前置缺失×在途批次×换代阻止×归档）、双确认幂等与事件唯一约束、重启后 DRAFT 审阅可继续、转写编辑阻止确认且已保存行不受影响、超长转写仅送 Summary 且标识可见、Schema 违规 FAILED、确认新批次后旧 AI 批次 SUPERSEDED 而手工行保留、部分唯一索引防并发重复提交。

## Out of Scope

- 知识点解释对话入口（归 12 的 @知识点模式）；Concept 抽取与对齐（P3，红线 #9 两侧不得互并）。
- 来源锚点的实际数据与跳转（Segment/锚点表 P2 起完整，本功能列预留恒空）。
- 跨记录知识点汇总视图、SUPERSEDED 批次的历史查看 UI（接口可查即回溯）。
- Markdown 导出（10）、Chat 上下文消费（12）、今日页待办入口（本功能纯按需触发，无待办）。
- LangGraph / Checkpointer（裁决明示不引入）。

## Further Notes

- 本功能是 MVP 四事件（#43）中 SUMMARY_CONFIRMED 之后第二个落地者；事件粒度为「一次确认动作一事件」，与 06 的 Summary 粒度先例一致。
- 数据模型文档 v2.2 已于 2026-08-24 同步修订（knowledge_points 取消独立 status 列、importance 定标、tags 上限）。
- 全部 16 项 grill 裁决与回写记录见 `.scratch/function-plans-introduction/07-knowledge-points.md`。
