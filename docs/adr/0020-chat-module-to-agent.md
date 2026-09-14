# Chat 模块升级为统一 Agent 模块（modules/agent）

---
Status: accepted（2026-09-14，grill 两轮 + 生态调研定稿）
---

Chat Agent 代码（deepagents 骨架迁移后，ADR-0018）集中在 `modules/chat/`，`graph.py` 巨石化（641 行混装上下文组装 / 引用解析 / 骨架装配 / 流式生成四种异质职责）；后续 A 系列能力（学习上下文中间件、Tutor 变体）与 §40.4 长期方向（RAG / Memory / Skills / MCP / SubAgents）都需要清晰的 Agent 能力落位。本次将 `chat` 模块重构升级为统一的 `agent` 模块，**行为零变更**（openapi 与留档逐字一致、435 项测试全绿），只动结构。

**决定**：

- **模块边界 = 取代而非并存**：`modules/agent` 完全取代 `modules/chat`——对话产品面（会话/消息/路由）与 agent 能力面（骨架装配/工具/中间件）同居一个 feature-first 域；模块数不变，法定依赖方向改为 `agent`/`today` 下游。否决「chat 保留产品面 + agent 独立能力模块」：当前 agent 能力的唯一消费者就是 chat，拆分即为单消费者造跨模块抽象（违背 ADR-0018 精神）。
- **graph.py 641 行按职责拆三**：`context.py`（上下文组装：轮次窗口 / 字符预算 / 挂载材料指令——A 系列学习上下文中间件的扩展落点）、`citations.py`（引用块解析与逐字校验，纯函数独立可测）、`graph.py`（deepagents 装配：`AgentConfig` + 变体常量 + `stream_chat_reply` 流式路径）。产品面五文件（`chat_sessions` / `session_service` / `message_service` / `models` / `schemas`）原样迁移仅改 import。
- **能力子包只建有内容的**：`tools/`（一工具一文件，按工具名命名，`search_transcript` 先入）+ `middleware/`（`skeleton.py` 空骨架闸门：内置工具排除件 + no-op 摘要件）。**mcp/、skills/、memory/、subagents/ 不建空壳目录**，接入时才建（落位规则写在模块 `__init__` docstring 与本文，`AgentConfig.skills/subagents` 字段已预留）。
- **summary / review_material 两 LangGraph 图不收编**：job 驱动的单发工作流（无工具循环、无对话交互），域归属清晰；维持 ADR-0018「迁移与否由各自需求驱动，届时若共享装配再上提」。
- **变体升格路径**：agent 变体多于一个图文件时，`graph.py` 升格为 `graphs/<name>.py`（open-swe 模式）。生态调研依据：open-swe = `agent/graphs/` 一图一文件（多图产品）、Yuxi = agent 目录内 `graph.py`、EvoScientist = 单文件组合根；与本项目「模块内图入口叫 graph.py」惯例（summary / review_material）一致，故单图阶段取 `graph.py`。
- **对外契约零变化**：API 前缀 `/api/chat-sessions`、SSE 事件集、ORM 表名（`chat_sessions`/`chat_messages`）、checkpoint thread 命名（`chat-{session_id}`）、`app.state.chat_checkpointer` 等状态键全部不改。

## Considered Options

| 方案 | 结论 |
|------|------|
| **A. modules/agent 取代 chat + graph 按职责拆三 + 只建有内容的子包** | **采纳**——消除巨石、建立能力落位、回归面最小 |
| B. chat 保留产品面 + modules/agent 独立能力模块 | 否决——立刻制造单消费者模块，为一次性重构造跨模块抽象 |
| C. `app/agent/` 提为 modules 平级核心层 | 否决——chat 专属业务装配（挂载上下文/引用校验）会被逼进核心层或被迫抽注册间接层 |
| D. 整文件只挪目录不拆 graph.py | 否决——641 行四职责巨石正是本次重构要解决的问题 |
| E. 建 mcp/skills/memory/subagents 全套空目录占位 | 否决——空壳违背 ADR-0015「`__init__` 只写 docstring」的纪律意图，误导读者以为能力已就位 |

## Consequences

- ADR-0018 中「`AgentConfig`/`build_agent`/`CHAT_AGENT_CONFIG` 全部留在 `modules/chat/graph.py`」的路径表述由**本文覆盖**（0018 正文保持史实不改）；其「新变体 = 新增常量实例，不建工厂类/注册表」等其余决定继续有效。
- 外部引用面 3 处随迁：`main.py`、`today/service.py`、`tests/test_chat_sessions.py` + `test_chat_streaming.py`。
- 两个空骨架中间件从 graph.py 私有（`_ExcludeDeepAgentToolsMiddleware`/`_NoopSummarizationMiddleware`）转为 `middleware/skeleton.py` 公开导出（去下划线），行为不变。
- `DEEPAGENT_TOOL_NAMES` 与排除件的耦合点随迁至 `middleware/skeleton.py`：启用 deepagents 内置工具仍须同步该集合（task 还需 subagents 非空）。
- 后续接入新能力的落位：MCP → `mcp/`、技能 → `skills/`、长期记忆 → `memory/`、子代理 → `subagents/`；均接入时建目录，不预建。
