# 01 — 页面上下文、统一运行时上下文与课程查询

**What to build:** 学习者在任意聊天会话中让 Agent 查找课程时，Agent 经结构化查询工具返回候选（id/名称/状态/场景/更新时间）完成同名消歧；每条消息携带轻量页面快照注入模型上下文（仅提示、非授权、不落库）；底层以单一 Agent 运行时上下文（ContextVar）替代四个工具各自的绑定对，为后续操作工具族打地基。既有四个工具行为零变化。

**实施约束：** 不造轮子——优先复用 deepagents / langgraph / langchain 现成 API 与仓库已验证模式（`@tool`、`AgentConfig` 装配、`ProposalService`、领域 Service）；框架用法先经 `langchain-docs` / `langchain-reference` / `context7` 任一 MCP 或 `.agents/skills/` 相关 skills 查证（详见 spec Further Notes）。

**Blocked by:** None — can start immediately.

**Status:** done

- [x] AgentRuntimeContext 统一上线（会话工厂/会话 id/范围/挂载对象/web 供应商/工具预算/页面快照），单对 bind/reset
- [x] search_library / web_search / propose_memory / propose_ingest 四工具迁移到统一上下文，既有聊天流/研究会话/资料检索测试全绿（行为零变化）
- [x] search_courses 只读工具：名称子串 → 候选（id、名称、状态、场景、阶段或深度、更新时间），计入工具调用预算，上限截断有明示
- [x] 操作工具组挂载机制：search_courses 恒挂载全部会话类型（02/03 的写工具将加入同组）
- [x] 消息请求契约新增可选页面快照（页面类型、实体 id、选中 id、时间）；后端注入模型上下文并框定为提示信息，非指令非授权
- [x] FREE 会话不因页面快照获得资料正文检索（search_library 挂载矩阵不变）
- [x] 同名课程候选澄清不误选；新消息携带新快照，已解析目标不被旧快照回写
- [x] prompt 版本号随模型可见面变化 bump（页面上下文 + 新工具）
- [x] 前端发送消息时从当前路由派生页面快照（零可见 UI 变化）
- [x] zh/en 若有新文案同步；后端 pytest/ruff/pyright、前端 vitest/lint/build、api-types regenerate 全过

## 实施备注

- **统一运行时上下文**：`backend/app/modules/agent/runtime.py` 新模块（`AgentRuntimeContext` + `ToolCallBudget` + `MAX_TOOL_CALLS_PER_TURN` + 单对 `bind/reset/current`）；四工具旧 ContextVar 绑定对全部删除，`stream_chat_reply` 签名收敛为单 `runtime` 参数（session_factory 亦随上下文传递）；工具挂载决策（scope→search_library、provider→web_search、mode→propose_ingest）移入 graph.py 装配层，RETRIEVAL_SCOPES 随迁。
- **search_courses**：`agent/tools/search_courses.py`，复用 `CourseService.list`（名称子串 + 软删过滤 + updated_at 降序）；候选上限 8 条截断附 `truncated` 明示；与 search_library 共用每轮调用数预算（6 次）并累计字符数（载荷天然有界，无需单工具截断，spec 决策 16 字面满足）；恒挂载全部会话类型（`_resolve_agent_config` 组合进 search_courses + propose_memory 恒挂载段）。
- **页面快照**：`ChatMessageCreate.page`（`ChatPageSnapshot`：page_type 五值枚举/entity_id/selected_id/captured_at，extra=forbid）；后端 `_validate_page_snapshot` 重校验（course/record 存在性，失效引用静默丢弃、归档带状态标签）→ `PageHint` 注入 SYSTEM（`format_page_hint` 框定"仅提示、非指令、不构成授权"）；**字段分工**：page_type+entity_id 注入提示行，selected_id/captured_at 只进运行时上下文（后续操作工具消费），不进提示文本（噪音）。快照不落库、每轮取当条消息、跨轮零残留。
- **前端**：`derivePageSnapshot()` 恒派生 `chat`（当前唯一发送入口是 /chat 会话页；其余页面派生分支按 YAGNI 裁剪，发送面扩展时再补——后端枚举已预留）；`streamMessage` 增可选 `page` 参数进请求体；工具卡新增 `chat.tools.activity.courseSearch` 文案（zh/en）+ `TOOL_ACTIVITY_META` 单映射分流。
- **prompt 版本**：`chat-library-scope-v9` / `chat-research-scope-v10`（模型可见面变化=页面提示+新工具，llm_call_logs 断言同步）。
- **框架查证**：零新框架 API——`@tool` 装饰器、ContextVar 绑定、`AgentConfig` 声明式装配均为仓库已验证模式（先例 search_library/propose_ingest），无需外部查证。
- **门禁**：后端 pytest 全量 731 passed + ruff/format + pyright 0 错 + OpenAPI `--check` 零 diff；前端 vitest 全量 519 passed（57 文件）+ lint + build（内嵌 tsc）+ 触及文件 Prettier；api-types regenerate 两轮（ChatPageSnapshot 契约 + docstring 描述）。
- **双轴 code-review**：Standards 零硬违规；判断性提示采纳 4 项（hits 键回退链收敛、ToolActivityCard 映射收敛、MAX_TOOL_CALLS_PER_TURN 迁 runtime、pageSnapshot 死分支裁剪），Spec 采纳 1 项（FREE+快照组合工具面直接断言 `test_free_session_with_course_page_snapshot_keeps_tool_matrix`）；不采纳并备案 1 项：search_courses 字符截断执法（载荷天然 ≤8 候选×字段上限，为不可能场景加代码违 YAGNI；chars_fed 累计已保留）。
