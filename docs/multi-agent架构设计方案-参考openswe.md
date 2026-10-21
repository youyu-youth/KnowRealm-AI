# KnowRealm-AI Multi-Agent 架构重构与实现

你是一名资深的 AI Agent 架构师，请深入审查 KnowRealm-AI 现有代码、技术栈及业务逻辑，基于现有 Agent 系统渐进建立 **LangGraph 驱动的分层混合式 Multi-Agent 架构（Hierarchical Hybrid Multi-Agent Architecture）**。

## 一、目标架构

采用 **独立业务 Agent / Graph + LangGraph 统一运行与按需编排 + 共享 DeepAgents Harness + 按需主从委派 + 既有 Domain Services** 的混合架构。

参考 Open SWE 的独立 Graph 入口、共享 DeepAgents 底座和图内委派方式，运行调度与业务执行继续适配 KnowRealm-AI 现有本地架构。本方案描述目标架构，不代表相关能力已实现或通过验收。

## 二、核心设计

1. **LangGraph**：统一 Agent 图运行与按需协作。显式指定目标的请求直接进入独立 Agent；复杂任务由现有主 Agent 规划，通过 LangGraph 完成委派、等待和结果聚合。不新增所有请求必经的全局 Orchestrator Agent；Checkpoint 只保存图运行态，不替代业务事实。
2. **独立业务 Agent / Graph**：根据真实任务需要划分专业能力，各自拥有独立职责、工具集、上下文及可组合的 Graph。专业 Agent 既可独立接收请求，也可接受主 Agent 委派，两条路径复用同一专业实现；不因存在某个业务模块就强制创建对应 Agent。
3. **LangChain**：负责各业务 Agent 的模型调用、工具集成、Middleware 和结构化输出。
4. **共享 DeepAgents Harness**：复用现有模型工厂、Agent 装配、Middleware、工具注册和上下文治理，隔离各 Agent 的执行状态、任务上下文与权限。首批聊天 Agent 沿用现有 `create_deep_agent` 骨架；确定性工作流直接复用 Service、JobRunner 或必要的 StateGraph，无需强制套用 DeepAgents。Skills 按后续实际需求启用，不作为首期建设内容。
5. **按需主从委派**：主 Agent 负责理解意图、拆解任务、选择委派和最终汇总；专业 Agent 执行明确子任务，返回结构化结论、引用和缺口。复杂任务按需使用受控的 SubAgents / 专业 Graph 委派，首期仅允许一级委派，不新增重复规划的 Deep Task Agent。
6. **Domain Services**：复用现有 Python 业务服务，Agent 必须通过受控 Tools/API 及既有执行入口调用领域能力，不得直接修改数据库。
7. **既有执行治理**：ChatTurn 继续负责回答生成与轮次事件，Run / Operation 继续承载业务执行及操作回执，提案与授权机制继续约束写入；JobRunner 负责后台调度，恢复按既有 Worker 和启动对账机制接线。新增委派只补齐必要的执行身份、等待关系与结果记录，不重复建设审批、任务循环或业务执行账本。

## 三、重构规范

- 简单任务优先使用确定性逻辑；明确指定 Agent 的请求直接分发，不增加前置 LLM 意图分类调用；复杂任务才由主 Agent 按需组织协作。
- Agent 之间通过类型化任务契约及必要的 StateGraph / Subgraphs 协作，明确输入、结果、引用、失败原因和版本，避免共享可变上下文及依赖其他 Agent 的内部状态。
- 保留现有 SQLite 业务事实源、领域模型、RAG 检索约束、权限校验与 HITL 审批机制。
- 授权与确认继续遵循现有三档模式及内容审核、长期记忆和外发同意边界；页面上下文、子 Agent 报告或模型判断不构成授权，子 Agent 不得扩大父任务的资料范围与工具权限。
- 每个委派具有独立、稳定的执行身份和命名空间；不得直接复制父轮次身份，或通过清空轮次身份绕过执行与预算校验。父任务进入等待后释放活动执行额度，子任务完成后经持久结果对账唤醒父任务。
- 父子任务共享并发准入与持久预算，父取消后拒绝新增委派及迟到结果；恢复复用已完成结果与原消费，不重复执行业务操作或重置预算。业务结果、授权与回执以业务 SQLite 为准，不仅保留在 Checkpoint 或 ToolMessage 中。
- 流式进度与输出按执行身份区分来源，复用现有持久事件和查询恢复机制；执行追踪、异常处理、模型输入准入及实际消费计量覆盖直接调用和委派两条路径。

## 四、实施要求

先分析现有架构与代码依赖，明确能力入口、上下文参数、授权、执行流程和状态归属，按仓库的 grill → spec → tickets 流程完善实施规格，再分阶段建设：

1. **独立入口闭环**：首批仅接入现有主 Agent `general` 与只读 Knowledge Agent `knowledge`，Knowledge 复用现有检索能力。交付真实 API 与现有新建对话流程中的最小 Agent 选择入口，会话固定归属一个 Agent，旧入口默认使用主 Agent；资料 scope 与会话 mode 保持独立。
2. **按需协作闭环**：支持不同会话并行执行，保留同会话存在非终态轮次时拒绝新消息的现有行为。主 Agent 可一级委派只读 Knowledge 子任务，交付独立身份、父等待释放额度、共享预算、结果聚合、取消恢复及最小进度展示。
3. **可行性验收**：通过真实 API / SQLite / Worker 验证独立调用与并行委派，覆盖父任务同时等待子任务、部分失败、取消、迟到结果、重放及重启恢复。真实模型验证工具实际调用、引用、实际消费与耗时；自动化、模型替身、浏览器、真实 Tauri/WebView2 和 Windows 系统缩放分别记录，不相互代替。

Canvas、Learning、Document 等 Agent 仅作为后续候选，不纳入首期；动态 Handoffs、嵌套委派、Agent 自由通信、Skills/MCP 平台及 Agent 管理后台也不在本期范围。是否继续扩展以实际实验结果为依据。
