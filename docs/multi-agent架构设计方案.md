# KnowRealm-AI Multi-Agent 架构设计与实现

你是一名资深的 **AI Agent 系统架构师**，请结合 KnowRealm-AI 现有代码、技术栈和业务需求，参考 **Open SWE 的独立 Agent Graph、共享 Agent Harness 与确定性工作流设计**，设计并实现 **LangGraph 驱动的分层混合式 Multi-Agent 架构（Hierarchical Hybrid Multi-Agent Architecture）**。

> open-swe地址: https://github.com/langchain-ai/open-swe
> open-swe代码位置：E:\workspace\project\agent-project\open-swe

## 一、核心架构

- 采用 **LangGraph Orchestrator + 独立业务 Agent + Shared Agent Harness（按需 DeepAgents）+ Domain Services** 的分层混合架构。
- **LangGraph**：作为核心编排与状态运行引擎，负责跨领域任务路由、并行协作、动态 Handoffs、Checkpoint 和 HITL；单领域简单任务无需强制经过 Orchestrator。
- **LangChain**：负责独立 Agent 构建、模型调用、Tools、Middleware、结构化输出及上下文管理。
- **Shared Agent Harness / DeepAgents**：参考 Open SWE，统一封装 Agent Runtime、Skills、工具注册、状态持久化、流式执行和追踪；仅按需使用 DeepAgents 处理复杂长任务、多阶段规划及深度研究，不作为所有 Agent 的强制基类。
- **Domain Services**：统一处理确定性业务逻辑、权限校验、数据读写和持久化，Agent 必须通过受控 Tools/API 调用，不得直接操作业务数据库。

## 二、Multi-Agent 分工

- **Orchestrator**：仅协调需要跨业务领域协作的复杂任务，负责任务规划、Agent 路由、状态管理及结果聚合。
- **Canvas Agent**：知识画布节点创建、编辑、关系建立、知识结构调整及智能布局。
- **Course / Learning Agents**：分别负责课程管理、学习路径、智能辅导、学习建议及学习证据分析。
- **Library / Document Agents**：分别负责资料资产管理、文档解析、内容摘要、知识提取及文档关联。
- **Knowledge Agent**：负责 RAG 检索、知识理解、概念提取、跨资料关联及来源验证。
- **Deep Task Agent**：按需基于 DeepAgents 执行跨模块、多阶段、长周期复杂任务，支持专业 Subagents 协作。

## 三、架构规范与约束

- 参考 Open SWE 的独立 Graph 入口设计，各业务 Agent 按需采用独立 LangGraph Graph/Subgraph 或 LangChain Agent，通过 Router、Handoffs 和类型化任务契约协作，避免全部依赖主 Agent 的 Subagents 机制。
- 统一复用 Shared Agent Harness，隔离各 Agent 的专业上下文、状态和工具权限；避免重复实现基础设施、无序通信和上下文污染。
- 优先采用确定性 Python 逻辑及轻量工作流处理简单任务，不强制每个功能都创建 Agent、StateGraph 或调用 LLM。
- Agent 修改知识画布、课程或其他业务数据时，必须通过 **Tools → Domain Services** 执行，涉及高风险或重要变更时实施 HITL 审批。
- 保持 **SQLite 为唯一业务事实源**，严格遵循现有课程、资料、知识、学习事件、证据及掌握度的数据模型与业务规则。
- 支持任务异步执行、并行调度、中断恢复、取消、流式进度、执行追踪、权限隔离、异常处理和 Token 成本控制。
- 优先复用现有 **FastAPI + Tauri 2 + React + Python Sidecar** 架构，采用模块化单体设计，避免不必要的微服务化、过度抽象和重复建设。

## 四、实施要求

先全面审查现有 Agent 代码、业务服务和数据依赖，识别可复用模块并制定渐进式重构方案；明确 Orchestrator、独立 Agent、Shared Agent Harness 与 Domain Services 的职责边界、目录结构、状态模型和接口契约。优先实现 **Orchestrator + Canvas Agent + Knowledge Agent + Domain Services** 核心闭环，再逐步扩展其他业务 Agent、异步任务及 DeepAgents 能力；补充单元测试、集成测试与端到端测试，确保架构可维护、可扩展、可观测，不破坏现有功能。