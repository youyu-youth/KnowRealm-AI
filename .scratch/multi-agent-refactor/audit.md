# Multi-Agent 改造：当前代码核对

日期：2026-10-21。基点：`dd67fcb6d435f67f4b012a459e08495a096ac72f`，分支 `feat/multi-agent-refactor`。
开始调查时工作区干净。本记录是源码与依赖核对，不是功能实现或运行验收。

## 依据及结论

完整阅读设计依据：[multi-agent 架构方案](../../docs/multi-agent架构设计方案-参考openswe.md)。当前进度明确将该能力列为方案阶段（`PROJECT_PROGRESS.md:126`）。

| 核对项 | 当前证据 | 本次改造含义 |
| --- | --- | --- |
| DeepAgents 装配 | `backend/app/modules/agent/graph.py:356-505`，`AgentConfig`、`resolve_agent_config`、`build_agent` | 保留现有工厂；配置组合必须保留 tools/subagents/skills/backend/middleware，不能重建时只保留 tools |
| Agent 归属 | `agent/models.py:11-36`、`schemas.py:53`、`session_service.py:88-205` | 会话尚无 agent_id；需持久归属、API 入参/响应、旧调用默认 general |
| 内置能力隔离 | `agent/middleware/skeleton.py:13-63` | task 与文件/Shell 工具目前均不可见；不能全局开放 task 后让默认 general-purpose 子代理继承写工具 |
| 并发 | `backend/app/main.py:441-461`、`agent/turns/worker.py:162-244` | 已有两个 ChatTurn 执行槽与条件领取；跨会话并行不是待建能力 |
| 释放槽与唤醒 | `agent/turns/background.py:182-289`、`turns/worker.py:541-549,1010-1017` | 已有 WAITING_JOB 停驻、持久结果对账、QUEUED 唤醒；扩展来源校验即可复用 |
| 等待资格 | `turns/background.py:120-164`、`backend/migrations/0044_chat_turn_background.sql` | 仅 RUN/JOB；JOB 目前以已提交 Operation 回执证明归属。Knowledge 不能伪造 Operation 或任意等待 Job |
| 提交身份 | `agent/runtime.py:89-113` | RUNNING + claim_token + 未取消，同事务条件 UPDATE 取得写锁；子任务不能复制或清空父身份 |
| 持久工具预算 | `agent/budget/policy.py:7`、`budget/service.py:47-166` | 当前每轮工具上限 6；消费归属 turn_id，准入和输出都依赖运行身份，需分开根预算和实际执行者 |
| 模型请求事实 | `agent/context_budget/models.py:38-55`、`context_budget/middleware.py:175-279` | 已有逐请求状态、输入估算、usage 和重试关系；扩展子执行归属，不另建模型计次系统 |
| 用量未知 | `context_budget/middleware.py:219-237,277-279` | 失败、取消或供应商无 usage 会留下未知；NULL 不代表零消耗 |
| 运行日志 | `llm/models.py:10-26`、`llm/service.py:322-362`、`agent/graph.py:844-845` | 日志非可靠预算账本；聚合日志不能替代逐请求消费记录 |
| 调度接缝 | `jobs/runner.py:167-196,286-325`；`transcript/audio_worker.py:101-151` | WorkerSpec 可分派多个目标；两个原槽可共同领取根轮次与专业子执行，无须另起循环 |
| 桌面创建 | `apps/desktop/src/features/chat/NewChatButton.tsx:31-98`、`useCreateChatSession.ts:11-30` | 复用现有新建菜单、范围选择、mutation 与路由；补 Agent 选择及固定身份展示 |
| 数据迁移 | 最新迁移 `0055_practice_recovery.sql` | 新增迁移顺序接续；旧会话用 ADD COLUMN DEFAULT general，不用 UPDATE 回填 |

## 已有恢复机制的边界

现有父轮次停驻 WAITING_JOB 后，不再满足 `turn_write_allowed()`；子执行如果继续使用父 claim，预算和输出提交会被拒绝。清空 turn_id 则退回内存计数，不能作为实现方案。

当前启动恢复会处理旧 RUNNING 轮次，并非天然符合本次 Q3 的“结果不明请求不自动重发”。需要以逐请求事实与 checkpoint 共同裁决：已完成结果直接复用；确实尚未发出的步骤继续；已发出而无可靠结果进入显式重试分支。不能只看 Job 是否 RUNNING。

现有回归入口：`test_chat_turns.py`、`test_chat_turns_background.py`、`test_chat_turns_recovery.py`、`test_tool_budget.py`、`test_context_budget.py`、`test_chat_sessions.py`、`test_chat_streaming.py`。本轮未运行这些测试；其存在不代表本次验收通过。

## 官方能力核对

本地 `uv run --frozen python` 读取依赖版本与公开签名：deepagents **0.7.13**、langchain **1.3.18**、langgraph **1.2.11**。

- [Deep Agents Subagents](https://docs.langchain.com/oss/python/deepagents/subagents)：专业可编译图可以复用；本地已安装实现的 task 内部直接 await 子图，不会自动完成 KnowRealm 的业务等待/释放槽/消费记账。
- 本地 `deepagents.middleware.async_subagents.AsyncSubAgent` 定义明确依赖 Agent Protocol 服务。不能为此引入额外服务、部署或账号。
- [Open SWE 官方仓库](https://github.com/langchain-ai/open-swe)：借鉴 DeepAgents Harness 与业务工具/中间件分离；其沙箱、外部集成和服务部署不属于本地桌面首期。
- 最新文档中的 HarnessProfile 等行为必须与锁定版本核对，不能用最新示例推断本地默认子代理、工具继承和权限已经安全。

## 权威约束

保留 ADR-0026 三档授权、长期 Memory/内容采纳/外发确认，以及 ADR-0028 的最终完整输入准入、业务事实与 checkpoint 分离。

ADR-0018/0028 仍记录内置子代理隔离；ADR-0026 的后果段及通用 Agent 设计-4 有本期不做 Multi-Agent 的阶段性表述。本次是用户明确要求的能力演进，需在实施前按[具体文档提案](documentation-proposal.md)登记阶段差异，不能默默改写旧 ADR，也不修改 `.claude/rules/`。

## 本轮证据范围

已完成：方案/项目进度/相关 ADR/代码调用链/现有测试入口/锁定依赖与安装源码核对。

未执行：模型替身回归、真实 API/SQLite/Worker 场景、真实模型请求、浏览器、Tauri/WebView2、Windows 系统缩放。未修改生产代码、数据库或用户设置，未请求或读取供应商密钥。
