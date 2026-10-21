# 四个架构缺口的收敛记录

日期：2026-10-21。
Status: accepted（Q7～Q9 用户均已明确确认，2026-10-21）
范围：本记录登记 Q7～Q9 设计收敛与获批 ADR 细化；规格和对应工单现已回写。01 独立入口实施及验收见 [实施记录](01-implementation.md)，02～04 尚未实现。
依据：[原方案](../../docs/multi-agent架构设计方案-参考openswe.md)、[现有规格草案](spec.md)、[既有决定](grill.md)。Q1～Q4 和 Q6 保留；不重开已有产品范围、并发或预算决定。

## 1. 已确认决定

### Q7：成功分支保留，结果不明时等待用户选择

用户明确选择：等待选择“仅重试 B”或“接受部分结果”。

场景：A 成功、B 已发模型请求但崩溃后无可靠结果。父轮次不提前 COMPLETED；等待所有仍可安全执行的兄弟分支收口后，进入 WAITING_USER，展示成功与中断事实，释放活动槽。

- 仅重试 B：保留 A、原根预算、B 的稳定执行身份及原请求记录；只对 B 的不确定请求给予本次显式重试许可。
- 接受已有结果：明确放弃本次等待中的未完成部分，恢复父图以成功结果及缺口完成回答；不把 B 的原不确定请求改写为成功或零消耗。
- 未选择前不自动重发；停止仍走持久取消，并拒绝后续迟到结果。
- 单个分支不确定时，不直接停止仍可安全推进的兄弟任务，也不让根持续占用运行槽。

### Q8：每次 Tool 调用只委派一个子任务

用户明确选择：`delegate_knowledge(task)`，一次调用一个子任务；允许 general 同轮输出两个独立 ToolCall 并行委派。

每个 ToolCall 对应一个 delegation、ProcessingJob、wait 和 interrupt。原根预算合计仍为六次，两个委派调用合计占两次，其他父子工具合计剩四次；根累计最多两个子任务，全局仍为原两个执行槽。

不新增批量等待表、聚合 Job、全局 Orchestrator 或自建并行循环。模型实际是否发出两个并行 ToolCall 需真实模型验收；不能仅凭工具接口可调用宣称真实并行已验证。

## 2. 已核实的代码与框架事实

| 缺口 | 当前事实与接缝 | 收敛方向 |
| --- | --- | --- |
| 批量等待 | `turns/models.py:64-82` 一次逻辑调用仅一个 wait；`background.py:30-38,182-206,237-289` 已支持多 interrupt、多 wait 和全部就绪后唤醒 | 采用已确认 Q8，以两次独立调用复用原等待机制 |
| 显式重试 | `turns/service.py:796-867` 目前只处理根 WAITING_USER/INTERRUPTED；`background.py:270-274` 不覆盖已有结果缓存 | 给本期等待原因增加类型化决定，原子重排选中子任务并失效对应缓存 |
| 子进度 | `turns/service.py:946-990` 仅根 RUNNING+claim 可写；`routes.py:66-145` 重建固定 SSE 字段；前端 Zod/handler 无子身份 | 原事件表、根 seq 与订阅不变，增加受控子状态入口及端到端类型化投影 |
| 图隔离 | `graph.py:819,829-849` 已支持显式 thread_id 和 resume；`:871-876` 工具 namespace 当前与 thread 绑定 | 稳定独立子线程，逻辑 namespace 明确派生，逐次 claim 不作为线程或逻辑键 |
| 子输入 | `context_budget/models.py:23-35` 仅根 turn_id 主键；父输入冻结在 `turns/worker.py:595-627`；输入 Middleware 会读父 pins/摘要并使用父 claim | 子输入冻结在 delegation，不覆盖父 ChatContextInput；复用估算/外发/请求记录接缝而非原样套父上下文 |

锁定依赖：deepagents 0.7.13、langchain 1.3.18、langgraph 1.2.11、langgraph-prebuilt 1.1.0。

已安装 `langchain/agents/factory.py:1957-1968` 将每个未完成 ToolCall 分别 Send 到工具任务；`tool_node.py:1120-1129` 向上传递 GraphInterrupt，Pregel 汇集多中断。无需把两个调用改成一个自行 gather 的中断节点。

官方依据：[多 interrupt 按 ID 恢复](https://docs.langchain.com/oss/python/langgraph/interrupts#handling-multiple-interrupts)、[节点恢复重执行与幂等](https://docs.langchain.com/oss/python/langgraph/graph-api#re-execution-and-idempotency)。以本地锁定版本的实际机制为准，不引入最新版本专属 API。

### Q9：四项机制与文档细化已确认

用户明确选择“确认本轮收敛并批准 ADR 细化”，批准本文件第 3～5 节及 ADR-0030 中对应四点增补。明确失败按 Q2 汇总并结束；仅不确定请求进入本轮显式重试选择。本次确认只结束设计收敛阶段，规格/工单正式回写及生产实现分别进入后续阶段。

## 3. 已确认的等待和重试闭环

### 父子状态

| 子任务集合的事实 | 父状态/行为 |
| --- | --- |
| 仍有 QUEUED/RUNNING 子任务 | WAITING_JOB，释放槽；已完成分支保持原结果 |
| 均已有可靠结果，含明确 FAILED/PARTIAL | 自动唤醒原父图，按 Q2 汇总可靠结果并披露缺口；全部失败则说明失败 |
| 所有可安全推进分支收口，至少一个请求结果不明 | WAITING_USER，要求本次类型化决定，不把中断结果当普通失败自动汇总 |
| 用户仅重试选中不确定分支 | 根回 WAITING_JOB，选中子任务回 QUEUED；不先运行主模型、不重跑成功分支 |
| 用户接受已有结果 | 未完成子执行以 CANCELLED/用户接受部分结果收口，原不确定请求历史不改写；根 QUEUED，原 interrupt 按原 ID 恢复，父图汇总后正常终态 |
| 用户停止 | 持久取消根及其专属子执行，拒绝新增调用/迟到结果，不启动汇总 |

明确失败的分支按 Q9 对 Q2 的细化结束汇总；本期原根内的显式重试处理不确定请求。完成最终回答后不重新打开终态根；后续请求是新的用户任务。不提供“任何失败都保留原轮次重试”的含混行为。

### 类型化决定与缓存

复用现有根 resume 资源，增加专门等待原因与 `RETRY_DELEGATIONS` / `ACCEPT_PARTIAL` 决定；既有 `RETRY_AFTER_FIX` 不默认授予未知模型请求重发许可。

决定绑定 root turn、等待快照版本、明确的子执行 ID/当前尝试和不确定请求 ID；客户端提供稳定决定 ID，服务端拒绝同 ID 不同参数及过期等待决定。身份、范围、供应商、外发同意、图版本及原消费均须重验。

重试受理同事务完成：取得根写锁/校验等待快照 → 固化决定 → 只更新选中子任务 → 清除其业务 wait.result_json 旧尝试缓存 → 确保该子 Job 可领取 → 根改 WAITING_JOB。保留原 interrupt 绑定，不手工改写 LangGraph checkpoint；不得清除成功分支、原工具消费或模型请求历史。

原根 ToolCall/interrupt ID 保留；对账只消费当前子执行尝试的有效结果。明确选择部分结束后，子执行与等待结果记录 CANCELLED 及“用户接受部分结果”的原因，不伪造成功；原不确定模型请求和实际消费继续保留。并发决定仅一方生效；旧决定不能作用于下一次 WAITING_USER。

实际重发产生新的模型请求记录，关联原不确定请求与本次显式决定；原 usage 仍未知时保持未知。工具准入逻辑键不因显式重试变化；若确实又产生新的工具输出，沿原输出规则记实际消费，不把新消费藏进重放。

## 4. 已确认的进度持久化闭环

保留原根事件入口，在同一事件 Service 增加子状态写入接缝，不新增事件表、独立 SSE 或第二套订阅游标。

- Worker 持久化子状态及对应事件时，在同一事务取得根写锁，检查持久父子关系、当前子 claim/attempt、根未取消及合法父状态；子终态事件与子结果/状态同事务提交，避免终态后再因 RUNNING 校验失败丢事件。
- queued/running/completed/partial/failed/interrupted/cancelled 状态由 Service/Worker 写入，不由模型自行报告权威状态。排队事件校验父注册身份或用户决定；运行事件校验子身份；取消事件由已持久取消的控制路径写入。
- 事件继续使用根 last_seq；payload 明确 `execution_id / agent_id / execution_attempt / status`。事件顶层 attempt/output_revision 保持根含义，不冒充子 attempt。
- 父 WAITING_JOB 时允许合法子状态提交；根 WAITING_USER 只在安全兄弟已收口后进入，避免活跃子任务还要依赖等待用户的根状态。
- 子 token/done 禁止进入根正文投影，子过程不展示私有思维链；首期提供状态和必要的工具进度。
- 后端枚举/事件投影/SSE 序列化/快照/background_tasks/压缩投影、OpenAPI 与前端 Zod/handler/过程组件一起适配。只塞 JSON 不算完成。
- 子状态和最后结果以原 delegation 事实为准；断订阅、快照压缩及重启仍可从原根事件和查询恢复。

## 5. 已确认的 checkpoint 与输入隔离

| 对象 | checkpoint thread | 工具逻辑 namespace | 输入与清理归属 |
| --- | --- | --- | --- |
| 根轮次 | 原 `chat-turn-{turn_id}` | 原根稳定 namespace | 原 ChatContextInput；只由根业务收口及根恢复清理 |
| 委派执行 | `agent-delegation-{execution_id}` | 独立派生的稳定子 namespace | delegation 冻结 system/task/约束/策略版本及必要消息；子 Service 独立收口/清理 |

二者通过明确参数传入 Harness，不隐式继承父 thread/context。工具 namespace 与线程参数分开表达，不使用可变化的领取 attempt/claim 作为逻辑键。

普通恢复与用户明确重试优先续用同一子线程，从未完成节点继续；不得默认 `resume=False` 清线程后重跑。已经保存工具结果的节点不因重试重复消费；副作用登记仍需业务幂等，以覆盖 checkpoint 未提交窗口。

子图已完成但业务结果未提交时先从原图状态验证并补投影，不再请求模型。checkpoint 缺失时先核对持久结果与逐请求输入；无法可靠重建则明确停止/新任务，不静默从头重发不确定请求。

子成功先提交结果再清理自己的线程；不确定中断或等待用户决定时保留子线程和输入。父接受部分结果、取消或不可恢复收口后，先持久处理相关子状态/迟到防线，再按确切子 ID 清理；启动对账补清未完成清理。禁止按会话前缀批量删除父/兄弟图。

子完整输入准入复用现有估算、外发校验、请求事实和输出限制，但不能读写父 ChatContextInput/摘要/固定项选择状态。父规则中应继承的范围、排除项与必要约束须先冻结进子输入，执行端继续校验来源有效性。

## 6. 已执行机制实验及未验边界

只在内存使用 StateGraph + ToolNode + InMemorySaver，按 create_agent 实际的逐 ToolCall Send 方式执行，复用生产 ToolCallIdentityMiddleware / interrupt_bindings。无供应商模型、网络或仓库代码写入。

| 场景 | 初次 interrupt | 工具函数总进入次数 | 稳定登记数 | 结果 |
| --- | --- | --- | --- | --- |
| 两调用都等待 | 两个不同 ID | A=2，B=2 | 2 | 各自按 ID 恢复，PASS |
| A 完成、B 等待 | 一个 ID | A=1，B=2 | 2 | A 不重跑，PASS |
| 两调用等待，恢复前结果都已就绪 | 两个不同 ID | A=2，B=2 | 2 | 重放读取原结果直接返回，PASS |

这证明所选框架接缝可用，不证明真实 API/SQLite/Worker、真实模型/计量或原生桌面闭环已通过。

后续工单必须补齐：两个父同时等待仍可推进；等待前注册的崩溃窗口；取消先提交后拒绝迟到事件/结果；重试只处理选中分支及旧决定拒绝；等待缓存按尝试失效；根/子线程互不覆盖；子输入不改根摘要；快照/事件压缩/断订阅/重启恢复一致；所有实际请求和原预算保留。

## 7. 文档同步边界

本文件及 grill.md 保存本轮事实和 Q7～Q9 已确认决定；spec 与四张工单尚待正式回写，不得以其旧批量入参/重试描述覆盖本记录与新 ADR 细化。未修改生产代码。

Q9 已批准并登记到 ADR-0030 的精确增补：每次 ToolCall 一个子任务；未知请求先等待类型化选择；根事件流接纳经子身份校验的状态；独立稳定子线程与独立输入、按业务终态清理。它们细化原 ADR 的既有边界，不增加新 Agent、预算或执行服务。

三个已定义领域术语继续使用，不为 thread、claim、attempt 等一般实现概念新增术语。规格和工单的正式修订留待后续 to-spec / to-tickets 阶段。
