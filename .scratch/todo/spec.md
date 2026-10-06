# Todo 清单

Status: ready-for-agent

## Problem Statement

KnowRealm 的学习闭环目前到「练完」为止：转写 → 总结确认 → 知识点沉淀 → 习题作答。但一节课留下的不只是知识，还有**行动项**——复习某节、补作业、查参考资料、做课后题。这些待办目前无处安放：要么散落在用户自己的备忘录里与学习记录割裂，要么干脆遗漏。记录详情里的「Todo」页签只是一个禁用占位。

Todo 是四个后续 AI 资产里最轻的一个（PRD §4.4.2），定位为独立小闭环：AI 从已确认总结中建议待办，用户修剪采纳后随手勾选完成。同时它承载两条已定稿的边界裁决：**接管语义**（ADR 0011——用户编辑或勾完的 AI 项脱离批次生命周期，永不随换代退场）与**门控解耦**（手动增删改不依赖总结确认，仅 AI 生成走门控）。Todo 不产生 learning_events（不在 MVP 四事件内，#43），与 Plan Item / Agent Action 三表分立（红线 #9）。

## Solution

总结确认后（Record=COMPLETED），用户在记录详情的「Todo」页签一键生成建议（零参数，prompt 约束 3~8 条、贴合总结内容），后端以普通 async worker 单次结构化 LLM 调用（仅以已确认 Summary + 课程上下文为输入，无 LangGraph）产出候选，成功即落库为 DRAFT 候选批次。

候选可**逐条修剪**（KP 式）：编辑文字、剔除不要的条目——修剪不算接管，项仍属批次。用户整批「采纳」或「丢弃」；采纳后该批置 ACTIVE、旧 AI 批次自动置 SUPERSEDED（数据保留、API 可回溯）；采纳本身不发学习事件。在途候选时重复生成被 409 阻止。

采纳后的清单是混排的一张列表：ACTIVE 的 AI 项 + 手工项 + 被接管项，按追加顺序排列。勾选 DONE 原位划线弱化（不过滤）；**编辑 ACTIVE 的 AI 项或勾选 DONE 即触发接管**（generation_status 置 NULL）——该条从此是用户内容，永不随批次换代退场，取消勾选不回退。手动增删改在页签解锁后始终可用，与总结确认状态解耦；仅「生成」按钮受前置门控（未确认总结 / 缺 Provider / 未同意外发 / 课程归档 / 换代）指引。

## User Stories

1. As an 学习者, I want to 总结确认后在 Todo 页签一键生成建议待办, so that 课堂行动项不用自己回想整理。
2. As an 学习者, I want to 生成数量由模型按总结内容决定（3~8 条）, so that 建议量贴合这节课的实际待办密度而非固定数字。
3. As an 学习者, I want to 生成异步进行并展示进行中状态, so that 界面不被模型调用阻塞。
4. As an 学习者, I want to 生成期间旧 Todo 照常可见可用, so that 重新生成不打断我正在进行的勾选。
5. As an 学习者, I want to 生成失败时看到可重试的失败状态, so that 一次网络问题不会让功能报废。
6. As an 学习者, I want to 手动重试复用失败任务, so that 重试不产生重复任务堆积。
7. As an 学习者, I want to 前置不满足（未确认总结 / 缺 Provider / 未同意外发 / 课程归档）时得到下一步指引, so that 我知道去哪里补齐条件。
8. As an 学习者, I want to 候选先审阅再生效, so that AI 产出不直接进入我的清单。
9. As an 学习者, I want to 候选可逐条编辑文字, so that AI 措辞不合我意时能就地改。
10. As an 学习者, I want to 候选可逐条剔除, so that 不要的建议不混进清单。
11. As an 学习者, I want to 整批采纳候选, so that 修剪完一键确认生效。
12. As an 学习者, I want to 不满意时丢弃整批候选重新生成, so that 建议质量差可以干脆重来。
13. As an 学习者, I want to 在途候选时重复生成被拒绝, so that 不会堆积多批未处理的候选。
14. As an 学习者, I want to 采纳后可随时基于当前已确认总结重新生成, so that 清单能跟着我的学习推进更新。
15. As an 学习者, I want to 采纳新批次后旧 AI 批次退场但数据保留, so that 「过时」不等于「丢失」。
16. As an 学习者, I want to 不经 AI 手工新增条目, so that 想到什么直接记。
17. As an 学习者, I want to 总结还没确认时也能手工增删改, so that 想到就记不必先走完总结流程。
18. As an 学习者, I want to 任意条目可编辑、删除, so that 清单始终是我的清单。
19. As an 学习者, I want to 勾选完成后条目原位划线弱化, so that 完成情况一目了然。
20. As an 学习者, I want to 取消勾选恢复未完成态, so that 误触可纠正。
21. As an 学习者, I want to 勾选状态持久、重启后保持, so that 清单是可信的。
22. As an 学习者, I want to 新条目追加在列表尾部, so that 清单顺序与我的添加顺序一致。
23. As an 学习者, I want to 转写编辑或总结调优后既有 Todo 不被删除, so that 已记下的待办不因内容修正消失。
24. As an 学习者, I want to 换代后重新生成并采纳时手工项保留, so that 我自己记的不受 AI 批次更替影响。
25. As an 学习者, I want to 我编辑过的 AI 项不随批次换代退场, so that 我改写过的内容是我的。
26. As an 学习者, I want to 我勾完的 AI 项不随批次换代退场, so that 我做完的事不会消失。
27. As an 学习者, I want to 采纳批次与勾选完成都不产生学习事件, so that 事件流里只有真实的学习行为。
28. As an 学习者, I want to Todo 页签按记录状态解锁, so that 不可用的时候不产生误导。
29. As an 本地用户, I want to 每次写操作同事务落库, so that 崩溃不会留下半截记录。
30. As an 本地用户, I want to prompt 与输出全文不进入日志, so that 我的学习内容不出现在日志文件里。
31. As an 本地用户, I want to 单次 LLM 请求有超时上限, so that 失联调用不会无限占用 worker。

## Implementation Decisions

### 数据与迁移

- 新建 `todo_items` 表（下一号迁移，紧接 0011），按数据模型 v2.2 全列：`batch_id`（可空；AI 批次共用，手工项空）、`content`、`status`（TODO / DONE）、`source`（AI / MANUAL）、`generated_from_summary_id`（可空；仅 AI 来源绑定 Summary）、`generation_status`（可空；AI 来源 DRAFT / ACTIVE / SUPERSEDED，手工项与被接管项为 NULL）、`sort_order`、`updated_at`、软删列。
- `processing_jobs.job_type` 新增 `TODO_GENERATION`；新增部分唯一索引：每 Record 至多一个 PENDING/RUNNING 的 Todo 任务（仿 KP/Quiz 索引）。
- 批次与生成任务一一对应：`batch_id` 复用生成 Job id；批次溯源（model、prompt_version、条数）记入 Job 的 result_json（07 先例）。
- 失败重试沿用 06/07/08 模式：同 Summary 的失败 Job 手动重试时复用，不新建。
- Record 软删级联 todo（数据模型 v2.2 既定：同事务级联软删，迟到结果不得写回）。

### 生成管线

- 不建 LangGraph Graph（红线 #2）：普通 async worker 单次结构化生成，复用既有 LLM 客户端与 llm_call_logs 埋点；prompt 版本化自 todo_v1 起。
- **零参数**：无题型/数量选择，提交即建 Job。输入组装 = 课程 learning_context / education_stage / depth + 当前已确认 Summary——仅此而已。
- Pydantic 严格校验：每条 content 非空且带字数上限；总条数 3~8，由模型按总结内容决定；任何违规令 Job FAILED（错误码如 LLM_OUTPUT_INVALID），不自动修正、不自动付费重试。
- 前置校验（任一不满足返回 409，不建 Job）：存在当前 CONFIRMED Summary、课程 ACTIVE、Provider 已配置、外部处理同意有效；Job input_json 记录 provider_fingerprint 与 generated_from_summary_id。单次请求沿用 90 秒超时。
- worker 领取 / 发布两阶段复核绑定 Summary 仍为 CONFIRMED，失效则 CANCELLED；成功后在单事务内落整批 DRAFT 行（批内按模型输出顺序分配 sort_order，整批追加在现有清单尾部之后）。

### 批次生命周期与接管

- **候选修剪（KP 式）**：DRAFT 行可编辑 content、可删除（软删）；修剪不算接管，项仍属批次、随采纳整体 ACTIVE。DRAFT 项不可勾选 DONE（候选未生效，同构于「只有 ACTIVE 可作答」）。
- 采纳（单事务）：前置 = 批次绑定的 Summary 仍为 CONFIRMED 且课程仍 ACTIVE，否则 409 并引导丢弃重生成；效果 = 该批 DRAFT→ACTIVE、既有其他 AI **ACTIVE** 批次置 SUPERSEDED；重复采纳幂等返回现状。采纳不发学习事件。
- 丢弃：软删整批 DRAFT（Quiz discard 同构）。
- **接管（ADR 0011）**：对 ACTIVE 的 AI 项编辑 content 或勾选 DONE（含 TODO→DONE 与取消）即置 generation_status = NULL，该行退出批次生命周期；SUPERSEDED 更新的谓词只匹配 ACTIVE 行，NULL 天然跳过。取消勾选不回退（幂等）。删除 ACTIVE 的 AI 项 = 直接软删，不涉接管。
- 换代联动：Transcript 编辑 / Summary 调优后既有 Todo 一律不动；SUPERSEDED 只由「确认新批次」触发；过时批次默认隐藏，`?include=superseded` API 可回溯、无 UI 入口。

### 手动 CRUD 与门控解耦

- 页签解锁 = record COMPLETED（同 Quiz）；解锁后手动新增 / 编辑 / 删除 / 勾选**不受任何 blocked_reason 限制**，生成 Job 在途时亦照常。
- 仅「生成」入口走 blocked_reason 门控（SUMMARY_NOT_CONFIRMED / SUMMARY_SUPERSEDED / COURSE_ARCHIVED / PROVIDER_NOT_CONFIGURED / CONSENT_REQUIRED，照抄 Quiz 枚举）。
- 手工新增：source=MANUAL、generation_status 为 NULL、sort_order 取当前最大值 +1 追加尾部。编辑/勾选为单行更新，最后写入生效（sidecar 单写者，无乐观锁）。
- 勾选切换幂等：重复置同态返回现状。

### API 契约

- 读端点镜像 KP/Quiz 的 action_required 模式：返回可见条目（ACTIVE AI 项 + 手工项 + 被接管项混排 by sort_order + 在途 DRAFT 批次）、action_required（GENERATE / ADOPT / RETRY / NONE）、active_job_id、blocked_reason。
- 写端点：生成（提交 Job，202 返回 job_id）、批次采纳（沿用 confirmations 路径形状，域术语与 UI 文案为「采纳」）、批次丢弃（软删整批 DRAFT）、条目新增 / 编辑 / 删除、勾选切换。条目写端点按行的 generation_status 分权：DRAFT 行仅允许编辑与删除（修剪），ACTIVE/NULL 行全操作。
- OpenAPI 是前端类型唯一契约：schema 变更先落 OpenAPI 再生成 api-types，前端不手写重复定义。

### 桌面端

- 「Todo」页签从禁用占位转真实功能，解锁 = record COMPLETED；页签 label 既有 i18n key 沿用。
- TodoPanel：DRAFT 候选单独区块（逐条编辑 / 删除 + 整批采纳 / 丢弃）；主清单一张混排列表（勾选 checkbox、行内编辑、删除，DONE 划线弱化原位保留）；进行中态复用 active_job_id 条件轮询（不加新通道）；blocked 空态给下一步指引（未确认总结时指向总结页签、未同意时一键授权）。
- 文案全部走 i18n；交互组件用 shadcn/ui + Base UI 原语；图标 lucide；纯图标按钮带 aria-label。

## Testing Decisions

- 好测试只断言外部行为：HTTP 响应、数据库终态（todo_items 行、批次状态、软删标记）、UI 可见结果；不断言服务内部调用序列。
- 后端沿 07/08 先例：真实应用 + ASGI 传输 + 真实迁移库 + lifespan 启动的真实 worker，经 HTTP 驱动全流程；**唯一新接缝 = 应用工厂注入的 FakeTodoModel**（镜像 FakeQuizModel 缝），支持序列输出（测校验失败重试）与阻塞控制（测活跃任务防重）。
- 前端沿 RecordDetail 测试先例：MSW 在 HTTP 层 mock 新端点，渲染真实路由（`?tab=todo`）断言页签解锁、候选修剪、采纳丢弃、勾选编辑与状态文案。
- 必测场景：零参数产出 3~8 条、条数与 content Schema 违规令 Job FAILED；409 矩阵（前置缺失 × 在途 DRAFT × 换代阻止 × 归档）；候选修剪（编辑/删除 DRAFT 行）后整批采纳生效；采纳后旧 AI 批次中仅仍 ACTIVE 的行置 SUPERSEDED，**被接管项（NULL）与手工项保留**；接管触发点（编辑 ACTIVE AI 项→NULL、勾 DONE→NULL、取消勾选不回退）；DRAFT 项勾选被拒；toggle 幂等；blocked_reason 下手动 CRUD 可用；Record 软删级联；sort_order 追加语义；`?include=superseded` 回溯。

## Out of Scope

- Learning Plan Item（目标级计划项）与 Autopilot Action（P6）——三表分立（红线 #9）。
- learning_events 写入（#43 四事件外；COMPLETE_TODO 属 P6 Agent Action 域）。
- 拖拽排序、DONE 过滤 / 折叠 / 统计、批量勾选、批量清理已完成。
- 截止日期 / 提醒 / 通知（PRD 未定义，P4+ 再议）。
- Markdown 导出（10）、设置页（13）、学习统计消费（17）、首页今日焦点聚合。
- LangGraph / Checkpointer（裁决明示不引入）。

## Further Notes

- 六项裁决（HITL=KP 式修剪 / 门控解耦 / 接管语义 / 零参数 / 不拖拽 / 划线弱化）系 2026-08-25 grill 定稿；接管机制见 ADR 0011；票面已同步修订（`.scratch/function-plans-introduction/09-todo-list.md`）。
- 数据模型 v2.2 的 todo_items 注释「手工/用户修改项不自动换代」在本 spec 精确化为「勾 DONE 也算接管」；数据模型文档未改动，如需同步措辞再议。
- 术语见 GLOSSARY.md：「候选批次」（已扩至 Todo）、「批次采纳」（已泛化）、「接管」（新增）。
- 实现注意：仓库内另有会话在改 records 前端文件（QuizPanel / RecordDetail.test），动工前先确认其变更已提交或错峰。
