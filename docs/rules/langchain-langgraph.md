---
paths:
  - "backend/**"
---

# 规范：LangChain 1.x + LangGraph（AI 编排层）

> 适用范围：`app/modules/agent/`（对话 Agent 域，ADR-0018/0020）、`summary` 与 `review_material` 工作流及一切 LLM 调用。依赖由 uv 锁定（禁 pre-release）。⚠️ **LangGraph 没有 1.3.x**，官方兼容组合 = langchain 1.3.x + langgraph 1.2.x；deepagents 钉 `>=0.7.x,<0.8`（ADR-0018）。

## 1. 导入与骨架

- 只用拆分包：`langchain`（create_agent/middleware）、`deepagents`（create_deep_agent/BackendProtocol）、`langchain-core`（消息/Runnable/@tool/Document）、`langchain-openai`、`langchain-community`（Loader）、`langgraph`（StateGraph/interrupt/Command/checkpointer）。禁 `AgentExecutor`/`create_react_agent`/0.x chains/`ChatTongyi` 专有集成/向量库集成包。
- chat 系 agent（自由聊天/挂载问答/未来 Tutor 变体）用 `create_deep_agent` 骨架，装配与 `AgentConfig` 变体落 `app/modules/agent/graph.py`；**业务 system 提示必须走 `system_prompt` 参数**（messages 里的 SystemMessage 会被骨架丢弃）。固定流程用 StateGraph。
- 模型实例只在一个工厂创建（`app/modules/llm/service.py` 的 `build_chat_model`），配置来自数据目录 `config/providers.json` 供应商卡（默认预设 DashScope qwen-plus），禁散落硬编码；评测基线只对默认预设负责。
- 工具 docstring 写清"做什么、什么时候用"（LLM 选工具唯一依据）；生产必须传 checkpointer + `thread_id` + `recursion_limit`（防死循环）。

## 2. 结构化输出

AI 产物（知识点/习题/Concept 等）必须 `with_structured_output(Pydantic v2)`，Schema 放域内 `schemas/`，字段带 `description` 与必要约束（`ge/le/max_length`），校验挡在入库之前。

## 3. StateGraph（现役三个：summary、review_material、agent）

- 只有需要状态、暂停恢复、HITL 或 Agent 决策的流程才进 Graph；普通 CRUD 与确定性业务（Course/Quiz/Todo/MasteryEngine 等）写普通确定性 Service，不进 Graph。
- 列表状态字段必须加 reducer（`Annotated[list, operator.add]`），否则节点返回值整个覆盖；节点返回部分更新 dict，不改原 state 不返回整个 state。
- 用了 `Command(goto=...)` 的节点不再挂静态出边（会同时执行）；禁 `add_edge(node, START)`；检查图有到 END 的路径。
- **红线**：节点禁直写 `user_concept_mastery` 等 mastery 表（唯一写入口是 Mastery Engine，节点只发 Learning Event）；AI 产物（确认结果、版本链）必须落业务表，**Checkpoint 只存运行态、不是业务事实**，禁手工查询 langgraph schema。

## 4. HITL 与持久化

- 暂停 `interrupt(payload)`（payload 自带前端渲染所需完整信息，不只传 ID），恢复 `Command(resume=value)`；跨进程/隔天恢复依赖 checkpointer。
- 生产 `AsyncSqliteSaver`（数据目录 `langgraph.db`，`setup()` 仅初始化时执行一次）；单测 `InMemorySaver`；每次 invoke 必传 `thread_id`（放 `config["configurable"]`，业务命名如 `record-{id}`、`chat-{session_id}`）。

## 5. 流式与错误

- SSE 逐 token 用 `stream_mode="messages"`（从 `result["messages"]` 取结果）；节点内非 token 进度用 `get_stream_writer()` + `stream_mode="custom"`。
- 瞬时错误（网络/限流）节点设 `retry_policy`；工具执行失败回给 LLM 自救（ToolMessage）；未知异常直接抛出，由 FastAPI 全局处理器 + loguru 兜底。

## 6. 埋点与隐私

- LLM 调用埋点在统一工厂层（`llm_call_logs`，字段见数据模型 §4.10，embedding 记 `embedding_model`），Graph 节点不手写埋点；**不记 prompt 与输出全文**；埋点失败吞掉记 error code，不影响主流程。

## 7. 检索现状

当前检索走 FTS5（`search` 模块，`search_library`/`search_transcript` 按挂载互斥，ADR-0016）；sqlite-vec 向量检索为**未来候选**（触发条件见扩展文档），未落地前不引入向量库集成包、不建 vec0 表。
