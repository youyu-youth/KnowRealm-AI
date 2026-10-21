# 有界专业 Agent 与持久委派

Status: accepted（2026-10-21，Q1～Q4/Q6 原决定及 Q7～Q9 四缺口细化均获用户明确批准；设计已收敛，规格与工单待正式回写，尚未实现）

KnowRealm 从现有单一聊天 Agent 演进为 general 与本地只读 knowledge 两个专业入口，复杂任务才由 general 按需一级委派。采用独立业务 Agent/Graph、共享 DeepAgents Harness、LangGraph 图内等待及现有领域 Service/JobRunner 的分层混合架构，复用本地执行与恢复基础，避免新增所有请求必经的编排 Agent、服务部署或第二套执行系统。

设计依据：[用户指定方案](../multi-agent架构设计方案-参考openswe.md)；[当前事实核对](../../.scratch/multi-agent-refactor/audit.md)、[用户决策](../../.scratch/multi-agent-refactor/grill.md)、[四缺口收敛记录](../../.scratch/multi-agent-refactor/architecture-gaps.md)、[待回写的实施规格草案](../../.scratch/multi-agent-refactor/spec.md)。本 ADR 记录已批准决定，不代表任何功能已通过验收。

## 决定

1. **独立入口与固定归属**：显式选择 Agent 的请求确定性直达。聊天会话固定 general/knowledge；旧会话及未指定入口默认 general。Agent 身份、ChatScope 与 ChatMode 独立，不增加前置 LLM 分类调用或动态 Agent 管理平台。
2. **复用专业实现**：独立 knowledge 与被委派 knowledge 使用同一专业图/工具白名单及现有模型工厂、AgentConfig、build_agent。组合配置不得丢失现有工具、子代理、技能源、后端或中间件扩展点。确定性业务仍由领域 Service 与 JobRunner 执行。
3. **首期 knowledge 本地只读**：仅访问冻结的有效资料范围，返回经过验证的结论、引用和缺口。不联网检索、不生成记忆/入库提案、不拥有业务写工具、不继续委派。FREE 不扩大到 ALL。调用外部模型仍受原外发同意与供应商身份约束。
4. **受控委派与状态归属**：general 按需调用受控委派 Tool；子执行有独立稳定身份、claim、命名空间和冻结输入。LangGraph interrupt/checkpoint 承载图内等待与恢复；业务 SQLite 保存委派结果与消费，不凭 ToolMessage 或模型判断授权。
5. **复用双槽与持久等待**：根与子共用现有两个活动执行槽，父停驻 WAITING_JOB 后释放槽。现有 CHAT_TURN Job 输入显式区分根轮次与子执行，由原 WorkerSpec/JobRunner 分派；JOB 等待须以持久父子关系证明资格，不伪造 Operation，不增加新任务循环。
6. **执行身份与根预算分离**：根任务最多两个 knowledge 子任务，父子合计六次工具准入，委派 Tool 也计次；重放复用原逻辑消费。每个实际模型请求沿现有请求事实记录根/子身份、输入准入、实际用量及失败。未知 usage 保留未知，不充当零消耗或精确金额；不增加可调并发或金额预算。
7. **原授权边界保持**：业务写入继续复用三档、Operation/提案/Run 和领域 Service；Memory、内容采纳与外发确认规则不变。子执行不得扩大父资料范围或工具权限；页面、来源文本、子报告及 checkpoint 均不构成授权。准入与结果写事务均校验实际 claim 和根取消状态，不通过清空 turn_id 绕过校验。
8. **失败、取消与恢复**：部分成功时允许父汇总成功证据并披露缺口；全部失败不得伪造结论。父取消后拒绝新增委派与迟到结果。已完成结果和原消费优先复用；已发出但无可靠结果的模型请求不自动重发，进入显式重试，提示可能重复计费。尚未发出的安全步骤可以按原预算继续。

## 四个架构缺口的细化（Q7～Q9 已批准）

1. **一调用一委派**：`delegate_knowledge(task)` 一次仅登记一个专业子执行，对应一个 Job、wait 和 interrupt。两个独立任务可由 general 同轮输出两个 ToolCall，使用框架原有逐调用 Send/interrupt 及现有多等待对账。不增加批量等待表、聚合 Job 或自建并行循环。两次委派各计一次根工具准入，原六次额度和最多两子任务不变。
2. **不确定请求的显式选择**：明确失败按既定部分成功规则汇总并结束；当请求结果不明时，保留成功分支，待其余可安全执行分支收口后让根进入 WAITING_USER。用户可选择仅重试选中中断分支，或接受已有结果结束。决定绑定等待快照、子执行/尝试及不确定请求，使用稳定决定身份和条件提交；旧决定不得作用于后续等待。重试同事务重排选中子 Job、清除对应业务 wait 缓存并让父回 WAITING_JOB，不重跑成功分支、不先调用主模型、不重置原消费、不手工改写 checkpoint。新模型请求关联原不确定请求及显式决定。接受部分结果时，未完成子执行按用户决定取消收口，原不确定请求和用量历史保留，再唤醒父图汇总；最终终态根不重新打开。
3. **原事件流中的子进度**：子状态复用原 ChatTurnEvent、根 seq、订阅与快照，新增受控写入接缝并端到端适配类型和投影。执行状态/终态事件与子事实同事务提交；校验持久父子关系、实际子 claim/attempt 和根取消状态，允许父 WAITING_JOB 期间的合法子进度。排队、取消等控制事件由对应已授权的 Service/Worker 路径提交。payload 明确子 execution_id、agent_id、execution_attempt 与状态，根事件顶层 attempt/output_revision 保留根含义。子 token/done 不进入父正文；无第二套事件表或独立订阅端点。
4. **图与输入的隔离**：根继续使用 `chat-turn-{turn_id}`，子使用稳定 `agent-delegation-{execution_id}`；工具逻辑 namespace 独立表达，不以变化的 claim/领取 attempt 替代。子输入单独冻结在委派事实中，不覆盖根 ChatContextInput 或会话摘要；完整请求估算、外发校验和逐请求记录复用现有接缝并按实际身份提交。恢复与显式重试优先原子线程续跑，图已完成则仅验证并补写业务结果；不能可靠恢复时明确停止/新任务，不默认清图从头重发。子结果先持久提交再清自己的线程；等待用户期间保留所需图与输入，取消/接受部分结果后先收口再清理，启动按精确身份对账，禁止清理父/兄弟图。

详细状态转换、等待缓存/决定幂等、事件消费链及机制实验边界见[收敛记录](../../.scratch/multi-agent-refactor/architecture-gaps.md)。框架内存实验已验证双 ToolCall 中断与按 ID 恢复，不等同生产 API/SQLite/Worker、真实模型或桌面验收。

## 与已有决策的阶段差异

本决定在本期有界知识协作范围内演进 ADR-0018/0028 的子代理工具隔离，以及 ADR-0026 后果段、通用 Agent 设计-4 中暂不做 Multi-Agent 的阶段范围；不改写旧决策和当时验收事实。内置默认 general-purpose、文件/Shell、自由通信、嵌套委派、动态 Handoffs、Skills/MCP 平台及额外专业 Agent 仍不开放。

不是仅从 task 黑名单中移除工具：原内置同步 task 不提供 KnowRealm 的持久父等待、槽释放、独立提交身份及根预算关系；Agent Protocol 异步子代理又会引入额外服务。因此使用必要的受控图适配与原本地运行机制，并保留原最终模型输入准入和摘要治理。

## 代价与验证

专业协作增加模型请求、延迟及持久身份/恢复复杂度，不预设比单 Agent 更快或更省 Token。必须验证直接调用与委派的工具面/范围一致，两个根同时等待无死锁，预算最后额度原子裁决、部分失败、取消与迟到、重放及真正重启恢复。

真实 API/SQLite/Worker、模型替身、真实模型与实际 usage、浏览器、Tauri/WebView2、Windows 系统缩放分别留证。当前均未执行本功能验收；后续进度以实际工单结果为准。
