# Chat Agent 骨架：deepagents 为主、严格空骨架迁移

---
Status: accepted（2026-09-13，grill 三轮五+三+一问定稿）
---

Chat Agent（`backend/app/modules/chat/graph.py`）原以 LangChain `create_agent` 裸循环运行（决策 #53，tools 空置预留检索）。Agent 运行时选型调研（docs/本地Agent运行时选型调研报告.md）定稿主推 deepagents 后，本次将 chat 的骨架替换为 `deepagents.create_deep_agent`（钉 0.7.13，社区钉法 `>=0.7.x,<0.8`，与 LangChain 官方生产参考 open-swe 同版），**为 Tools、Skills、Memory、RAG、任务规划等后续 Agent 能力提前建立官方推荐的架构入口**。本次只做迁移：模型可见面（工具列表、提示组装、流式路径）与迁移前严格一致，不引入任何新功能。

**决定**：

- **主骨架 = `create_deep_agent`，严格空骨架**：内置工具（`ls`/`read_file`/`write_file`/`edit_file`/`delete`/`glob`/`grep`/`execute`/`task`）全部对模型不可见，默认 SummarizationMiddleware 原位禁用。实现走**公开 API 组合**（非 beta HarnessProfile）：自写排除中间件（同步/异步 `wrap_model_call` 双实现，从 `request.tools` 移除 `DEEPAGENT_TOOL_NAMES`）+ no-op 件同名替换摘要件（`create_agent` 拒绝重名 → 同名原位替换）。已核实 0.7.13：FilesystemMiddleware 默认不注入提示词、子代理信息只随 task 工具描述出现，故工具名移除后内置能力对模型完全不可见。
- **system 提示注入通道变更**：deepagents 会把组装结果（哪怕空串）传给 `create_agent` 的 `system_prompt` 参数，输入 messages 里的 SystemMessage 被覆盖丢弃（实测）。业务 system 提示（挂载指令/角色快照）因此从 `messages[0]` 拆出、经 `system_prompt=SystemMessage` 参数注入；模型收到的 system 内容语义等价。`build_context_messages` 及预算计量不动。
- **扩展入口 = 轻形态配置对象**：`AgentConfig` frozen dataclass（tools/subagents/skills/backend/middleware 五扩展点）+ `build_agent(config, model, checkpointer, system_prompt)` + 模块常量 `CHAT_AGENT_CONFIG`，全部留在 `modules/chat/graph.py`。新变体（Tutor 等）= 新增常量实例，不建工厂类/注册表；summary/review 两 graph 迁移不迁移由各自需求驱动，届时若共享装配再上提（不为一次性迁移造跨模块抽象）。
- **每轮重建上下文 + checkpoint 只承载当轮的既有语义不变**：不启用 deepagents 的跨 thread 持久记忆；长期记忆仍归业务表。
- **依赖引入**：`deepagents>=0.7.13,<0.8`。uv 解析顺带升级 langchain 1.3.16→1.3.18、langchain-core 1.6.0→1.6.3、langsmith 0.11.1→0.12.4（同主版本内，423 项全量测试验证无破坏）；deepagents 传递带入 langchain-anthropic、langchain-google-genai、google-genai、cryptography 等，本地 sidecar 形态可接受。

## Considered Options

| 方案 | 结论 |
|------|------|
| **A. create_deep_agent + 公开 API 空骨架 + AgentConfig 轻工厂** | **采纳**——确定性强（不依赖运行期 provider 推断）、单栈官方推荐形态、扩展面完整 |
| B. 继续裸 create_agent，到 A1/A2 再换 | 否决——检索工具工单同时改骨架与功能，回归面更大；骨架先行让功能工单变小 |
| C. HarnessProfile beta（excluded_tools/excluded_middleware/GP disabled） | 否决——beta API 且按 provider key 从模型实例推断匹配，存在"注册了不生效"已知失败模式（0.7.13 源码自认），恰在本地单测最难暴露 |
| D. 温和骨架（保留默认件、不配 backend，工具调用即报错） | 否决——工具看得见摸不着，诱导失败调用 |
| E. 保留默认文件工具（StateBackend 虚拟文件立即生效） | 否决——行为变化违背本次"只迁移"目标；工具面开放属 A1/A2 工单，届时配好 backend 与提示词约定再逐个开 |

## Consequences

- 后端新增 deepagents 依赖树（含若干 provider 包），安装体积增大；.msi 打包体积影响在发布验证时观测。
- 未来启用内置工具 = 从 `DEEPAGENT_TOOL_NAMES` 移除对应名（task 还需 subagents 非空）；此耦合已写入 `AgentConfig` docstring 与本 ADR。
- 空骨架等价由 `TestDeepagentsEmptySkeleton`（断言模型可见工具面为空 + system 提示经参数注入到达）兼作 deepagents 升级回归闸门；升级 0.8+ 前须重验内置工具名与 SystemMessage 处理（同名替换/排除机制可能演进）。
- `stream_chat_reply` 输入侧多了 SystemMessage 拆分一步；引用解析、token 埋点、409/中断语义零改动（34 项 chat 测试 + 423 全量验证）。
- summary/review 两 graph 维持裸 LangGraph/create_agent 形态，形成"chat=deepagents、其余=裸 graph"的过渡期双骨架——由本 ADR 记录缘由，避免未来读者困惑；单栈原则不变（deepagents 返回的就是 LangGraph 图，tools 即 langchain 工具）。
