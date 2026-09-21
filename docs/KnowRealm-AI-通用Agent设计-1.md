结论：KnowRealm 不需要再引入一套“超级 Agent 平台”。最合适的形态是：

> 一个通用对话 Agent 负责理解、澄清、规划与编排；现有领域 Service 负责真正执行业务；JobRunner 负责长任务；统一策略层负责权限、确认、幂等、审计与恢复。

这样既能实现“用户只说目标”，又不会让模型直接操作数据库、文件或 UI。

## 一、当前项目已经具备的底座

现在并非从零开始：

- Chat 已使用 `deepagents.create_deep_agent`，并预留 `tools / subagents / skills / backend / middleware` 扩展点：[graph.py (line 142)](/E:/workspace/project/my/KnowRealm-AI/backend/app/modules/agent/graph.py:142)。
- 已有 `search_library`、`web_search`、`propose_memory`、`propose_ingest` 等真实工具。
- 内置文件、Shell、`task` 等 Deep Agents 工具被显式隐藏，安全边界是正确的：[skeleton.py (line 13)](/E:/workspace/project/my/KnowRealm-AI/backend/app/modules/agent/middleware/skeleton.py:13)。
- 已有五档 RAG Scope、逐字引用校验、Course Brain、Learner Memory。
- 已有持久化 `agent_proposals`、确认、失败重试机制。
- 已有 `ProcessingJob` / JobRunner，可处理解析、索引、AI 生成等长任务。
- Course、Record、Todo、KnowledgePoint、Library 等领域都已有可复用 Service。

但当前 Agent 本质上仍是“增强问答 Agent”，不是“通用执行 Agent”：

- 没有课程、记录、Todo 等通用写工具。
- 没有页面选择上下文。
- 没有持久化 Agent Run、计划、步骤和执行时间线。
- 没有统一风险策略与 Undo。
- 工具执行主要依赖一次 SSE 请求，不能完整承载跨分钟、跨重启的多步骤任务。
- 当前 `agent_proposals` 只有 `ORGANIZE / MEMORY / RESEARCH_INGEST` 三类：[schemas.py (line 269)](/E:/workspace/project/my/KnowRealm-AI/backend/app/modules/library/schemas.py:269)。

另外，项目锁定的是 `deepagents 0.7.13`：[uv.lock (line 480)](/E:/workspace/project/my/KnowRealm-AI/backend/uv.lock:480)。该版本的 Todo Planning 需要显式加入 `TodoListMiddleware`，当前代码并未启用，所以“用了 Deep Agents”不等于已经具备任务规划。

## 二、推荐的总体架构

```
用户自然语言 + 当前页面 Context
              │
              ▼
      KnowRealm General Agent
   意图理解 / 澄清 / 规划 / 重规划
              │
              ▼
       Agent Tool Gateway
   实体解析 / 权限 / 风险 / 幂等
              │
       ┌──────┴──────┐
       ▼             ▼
领域 Service      JobRunner
同步业务写入      解析/索引/生成等长任务
       │             │
       └──────┬──────┘
              ▼
   结果 / 进度 / 审计 / Undo Receipt
```

状态应继续分离：

- `knowrealm.db`：业务事实、Agent Run、审批、操作回执、审计。
- `langgraph.db`：模型循环、Checkpoint、interrupt/resume 等运行态。
- `processing_jobs`：确定性后台任务。
- 文件目录：原始资料和快照。
- Agent、Tool、Skill、MCP、SubAgent 均不得绕过领域 Service 写业务表。

## 三、Agent Tool 层如何设计

不要把每个 HTTP CRUD 端点都复制成一个 Tool，也不要只提供一个巨大的 `execute_anything`。

建议模型侧保持约 6～8 个领域工具：

| 工具组             | 能力                                                        |
| ------------------ | ----------------------------------------------------------- |
| `resolve_entity`   | 按名称、当前页面、Scope 查找 Course、Record、LibraryItem 等 |
| `course_action`    | 创建、修改、归档、删除课程                                  |
| `record_action`    | 创建文本记录、归类、升级、删除                              |
| `task_action`      | 创建、修改、完成、删除 Record Todo                          |
| `library_action`   | 入库、归类、收藏、归档、恢复、重建                          |
| `knowledge_action` | 创建知识点、Course Brain 候选、整理知识内容                 |
| `search_library`   | 继续复用当前 RAG 深模块                                     |
| `propose_memory`   | 继续沿用现有记忆治理路径                                    |

工具内部统一进入一个 `AgentActionExecutor`，而不是直接写 ORM：

```
Tool 参数
→ Pydantic ActionSpec
→ EntityResolver
→ ActionPolicy
→ 领域 Service
→ ActionResult / JobRef / UndoReceipt
```

推荐的公共契约至少包含：

- `action_id`
- `operation`
- `target_type / target_id`
- `arguments`
- `context_source`
- `preconditions`
- `idempotency_key`
- `risk_level`
- `result_entity_refs`
- `job_ids`
- `error_code / retryable`
- `undo_receipt`

已有 Service 可以直接复用，例如：

- `CourseService`：[service.py (line 24)](/E:/workspace/project/my/KnowRealm-AI/backend/app/modules/course/service.py:24)
- `TextCaptureService`：[text_capture.py (line 36)](/E:/workspace/project/my/KnowRealm-AI/backend/app/modules/capture/text_capture.py:36)
- `RecordClassificationService`：[classification.py (line 69)](/E:/workspace/project/my/KnowRealm-AI/backend/app/modules/record/classification.py:69)
- `TodoService`：[todo/service.py (line 203)](/E:/workspace/project/my/KnowRealm-AI/backend/app/modules/todo/service.py:203)
- `KnowledgePointService`：[knowledge_point/service.py (line 214)](/E:/workspace/project/my/KnowRealm-AI/backend/app/modules/knowledge_point/service.py:214)
- `ProcessingJobService`：[jobs/service.py (line 34)](/E:/workspace/project/my/KnowRealm-AI/backend/app/modules/jobs/service.py:34)

Tool 应直接调用这些 Service，不应在 FastAPI 进程内部再调用自己的 HTTP API。

## 四、Context Awareness

需要新增一个每轮消息携带的 `UiContextSnapshot`，至少包括：

- 当前 route；
- 当前 Course / Record / LibraryItem；
- 当前 Tab；
- 当前选中的实体 ID 列表；
- 当前高亮内容；
- Context 生成时间和版本。

后端将它校验并转换成 `AgentRuntimeContext`。前端传来的 ID 只是提示，不是授权，仍需回查数据库。

上下文优先级建议固定为：

1. 用户本轮明确指定的目标；
2. 当前选中对象；
3. 当前页面对象；
4. Chat Session Scope；
5. Learner Memory 中已确认的偏好；
6. 仍无法唯一确定时询问用户。

例如“帮我加一条记录”：

- 当前页面在某课程中：默认该课程。
- 页面不在课程内，但当前会话是 COURSE Scope：使用挂载课程。
- 找到多个同名课程：询问用户选择。
- 不允许模型猜一个课程 ID。

当前 `ChatSessionCreate` 只支持会话范围和挂载对象，没有页面 Context：[schemas.py (line 36)](/E:/workspace/project/my/KnowRealm-AI/backend/app/modules/agent/schemas.py:36)。

## 五、Clarification 不应完全依赖 Prompt

缺失字段应由 Action Schema 确定，模型只负责把问题说得自然。

例如当前 `CourseCreate` 真正的必填契约是：

- `name`
- `learning_context`
- SCHOOL 时需要 `education_stage`
- 其他场景需要 `depth`

见 [course/schemas.py (line 61)](/E:/workspace/project/my/KnowRealm-AI/backend/app/modules/course/schemas.py:61)。

因此用户只说“帮我创建一个课程”时，Agent 应先问课程名称和学习场景，再根据场景补问阶段或深度。“是否导入资料”是可选后续动作，不应阻塞课程创建。

建议将未完成意图保存为结构化草稿：

```
intent=create_course
known={name: "Python 学习"}
missing={learning_context, depth_or_stage}
status=WAITING_INPUT
```

下一轮只补充缺失字段，不重新理解整段对话。

## 六、权限与确认机制

现行 ADR 要求所有 Agent 写入先提案：[ADR-0024 (line 18)](/E:/workspace/project/my/KnowRealm-AI/docs/adr/0024-unified-library-item-and-rag-boundary.md:18)。这与“信息足够时直接创建”存在冲突，必须通过新 ADR 明确修改，而不能在代码里悄悄放开。

推荐风险矩阵：

| 等级 | 操作                                           | 行为                   |
| ---- | ---------------------------------------------- | ---------------------- |
| R0   | 查询、检索、读取状态                           | 直接执行               |
| R1   | 用户明确要求的单对象、可撤销创建或修改         | 直接执行并提供 Undo    |
| R2   | 批量创建、移动、归档、跨课程整理、联网入库     | 展示影响范围后一次确认 |
| R3   | 删除课程、覆盖内容、长期记忆写入、外部系统写入 | 强制确认               |
| 禁止 | 物理删除、任意 SQL、任意路径、宿主机 Shell     | 不向 Agent 暴露        |

“用户明确说创建课程”可以作为 R1 授权；但“帮我整理一下”不能被解释成删除或大规模移动。

课程删除当前会连带软删 Record、取消任务并触发 Mastery 重算：[course/service.py (line 110)](/E:/workspace/project/my/KnowRealm-AI/backend/app/modules/course/service.py:110)。它不应在第一版 Agent 中自动执行，且最好先补课程恢复能力。

## 七、Planning、长任务与恢复

建议新增最小的 `agent_runs`，不要把通用任务状态塞进 `processing_jobs`：

```
RECEIVED
→ RESOLVING_CONTEXT
→ WAITING_INPUT
→ PLANNING
→ WAITING_APPROVAL
→ EXECUTING
→ WAITING_JOB
→ SUCCEEDED / PARTIAL / FAILED / CANCELLED
```

`agent_runs` 保存：

- 用户目标；
- Context 快照；
- 当前状态；
- LangGraph thread ID；
- 当前步骤；
- 等待中的 proposal/job；
- 最终摘要和错误。

详细模型状态继续留在 LangGraph Checkpoint。业务写操作另外保存 `agent_action_receipts`，用于审计、幂等和 Undo。

长任务的原则：

- Agent 负责决定“做什么”。
- JobRunner 负责“解析、抓取、索引、生成”。
- Agent 得到 `job_id` 后进入 `WAITING_JOB`，不让模型循环轮询。
- Job 完成后由协调器恢复同一个 Run，继续下一步。
- 应用重启时扫描未终态 Run，根据 Job 和 Proposal 状态恢复。
- 客户端断开不应等于任务失败。

## 八、失败、重试与重新规划

Tool 错误需要统一分类：

- `TRANSIENT`：网络、临时锁，可幂等重试。
- `STALE_STATE`：目标被修改，刷新后重新规划。
- `NEEDS_INPUT`：缺少字段或目标不唯一。
- `NEEDS_APPROVAL`：等待用户确认。
- `POLICY_DENIED`：权限禁止，不得靠重试绕过。
- `DOMAIN_CONFLICT`：课程已归档、Record 已归类等。
- `FATAL`：不可恢复。

每个步骤必须带 `idempotency_key=run_id:step_id`，避免断线重试重复创建五门相同课程。

多对象任务不要开一个超长数据库事务。逐项提交、逐项记录结果，最终返回成功、失败和可重试子集。

## 九、Undo

Undo 不能实现成数据库回滚或反向 SQL，而应调用领域 Service 的补偿动作。

首版可支持：

- 新建 Course/Record/Todo/KP → 在满足版本条件时软删；
- 重命名/修改元数据 → 恢复旧值；
- LibraryItem 归档 → 取消归档；
- LibraryItem 软删 → 使用现有 restore；
- 批量操作 → 逆序执行可撤销步骤。

以下不应声称可 Undo：

- 物理删除；
- 已外发的网络请求；
- 用户后续又修改过的实体；
- 当前没有恢复接口的 Course 删除。

Undo Receipt 必须保存执行前快照和 `expected_updated_at`，防止覆盖用户后续修改。

## 十、RAG、Memory、Skills、MCP、SubAgent 的统一位置

| 能力          | 在 KnowRealm 中的职责                          |
| ------------- | ---------------------------------------------- |
| RAG           | 提供可追溯业务证据，不提供写权限               |
| Memory        | 提供经确认的用户偏好与学习状态                 |
| Skills        | 提供任务做法、Prompt 和流程知识，不能扩大权限  |
| Tools         | 唯一可执行能力入口                             |
| MCP           | 外部工具的适配来源，不用于包装内部领域 Service |
| SubAgent      | 隔离复杂上下文或并行研究，不承担最终业务写入   |
| JobRunner     | 执行确定性长任务                               |
| General Agent | 理解、规划、调用与重规划                       |

建议暂时不启用通用 Skills、MCP 和 SubAgent：

- 创建课程、记录、Todo 不需要 SubAgent。
- 内部 KnowRealm 能力直接调用 Service，比 MCP 更简单可靠。
- Skills 只有在出现多套稳定、可复用的专业工作流后再加入。
- SubAgent 只在“多论文并行分析”“不同来源独立研究”确实带来上下文隔离或并行收益时启用。
- 即使启用 SubAgent，也应默认只读或只产出提案，由主 Agent 执行最终写入。

## 十一、当前产品能力上的真实缺口

有些目标不能只靠加 Tool：

- 已归类 Record 当前不支持跨课程重新归类，会返回 `RECORD_ALREADY_CLASSIFIED`：[classification.py (line 71)](/E:/workspace/project/my/KnowRealm-AI/backend/app/modules/record/classification.py:71)。
- Todo 当前是 Record 级，不是 Course 级学习计划。
- `learning_goals / learning_plans / learning_plan_items` 仍是 P6 规划模型，尚未形成可调用的领域模块。
- 因此“把 5 篇论文放进新课程，并生成课程级学习计划和任务”的完整闭环，需要先实施 Learning Plan 领域能力；不能把多个 Record Todo 冒充课程学习计划。
- Learner Memory 已实现的是偏好和部分学习状态，不是任意“项目记忆”或自动聊天总结。
- 当前没有通用 Agent Run 历史、暂停、继续、取消和 Undo UI。

## 十二、推荐实施顺序

1. 先定新 ADR：通用 Agent 权限矩阵、显式指令是否允许 R1 直写、Agent Run 与 Checkpoint 边界。
2. 第一条纵向闭环只做：
   - 当前页面 Context；
   - 查找/创建课程；
   - 在课程中创建文本记录；
   - 创建 Record Todo；
   - 操作回执和低风险 Undo。
3. 第二阶段加入 `agent_runs`、计划、等待 Job、跨重启继续、重试和重新规划。
4. 第三阶段加入 Library、Knowledge、批量整理和审批预览。
5. 第四阶段先实现 Learning Plan 领域模块，再开放“生成学习计划”工具。
6. 最后才根据评测结果启用 Skills、MCP client 或 Specialized SubAgent。

第一阶段就能验证最关键的用户体验：

> “在 Python 学习课程中添加一条今天学习 FastAPI 的记录。”

Agent 唯一解析课程 → 调用 `TextCaptureService` → 返回 Record 与 Summary Job → 在同一任务卡持续反馈进度。这个闭环成立后，再扩展批量与长期任务，风险最小。

本轮仅完成只读分析，没有修改文件；工作区原有未提交修改保持不动。