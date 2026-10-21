# 02：单 Knowledge 委派的持久协作闭环

Type: task
Status: ready-for-human
Blocked by: 01
实施状态：代码已实现并提交，双轴评审修正复查关闭；联合回归 39、前端全量 871 通过，后端全量 1464 通过、1 项工具名单旧断言失败，修正后定向通过；真实模型、原生桌面与系统缩放待验，见 [实施记录](../02-implementation.md)。
规格：[spec.md](../spec.md) §5～10；Q7～Q9 已确认，本次仅同步四缺口对应条目。

## 用户结果

general 可以按需把一个明确本地知识任务交给与独立入口相同的 knowledge 专业图，显示真实进度；等待时释放执行槽，结果通过持久对账恢复父图汇总。停止、重启与显式重试不越权、不丢消费、不重跑已完成结果。

## 改动边界

以下为实现与双轴静态复核清单；运行证据层级见下方验证及 [02 实施记录](../02-implementation.md)。不代表真实模型或桌面人工验收已通过。

- [x] 新增 agent_delegations 及原请求/预算记录的最小归属扩展；DDL 只追加，不回填业务数据。
- [x] delegate_knowledge(task) 每次仅一个类型化任务，对应一个 delegation/Job/wait/interrupt，不接受模型自定权限/预算根；此票验证单次调用，03 验证两次独立调用并行，接口不改为批量入参。
- [x] 独立子执行 ID/claim/namespace，冻结自己的 system/task/必要消息、父范围/规则及策略版本；同专业图复用 01 的 knowledge 实现，不覆盖父 ChatContextInput/摘要或复制父可变 RuntimeContext。
- [x] 根保持 chat-turn-{turn_id}，子使用稳定 agent-delegation-{execution_id}；线程与工具逻辑 namespace 显式分开传入，领取 attempt/claim 不作为线程或逻辑键。恢复/明确重试优先原线程，已完成图只补业务结果；不能可靠重建时停止或新任务。
- [x] 根预算与执行身份分开；原子准入/输出计量/模型请求/最终子结果提交均验证实际 claim 与根取消状态，禁止 turn_id=None 退化。
- [x] 工具共用根六次限额，委派计次；逐请求用量保留，NULL 不当零；子报告进入父模型再次完整输入准入。
- [x] 两个原 CHAT_TURN 槽共同领取根/子目标，复用 JobRunner；候选、claim、execute、定向失败、启动恢复完整接线，不新增循环或不受限 create_task。
- [x] 委派 Job 的等待资格以父子持久关联证明；保留既有 Run/Job 权限校验，不伪造 Operation。
- [x] 注册、interrupt、WAITING_JOB、释放槽、结果先到、轮询/启动对账与原 checkpoint 唤醒贯通；工具从入口重放时幂等复用原子执行/Job/wait，按原 interrupt ID 恢复，不确定请求不当作普通失败自动唤醒。
- [x] 根取消传播专属子执行，拒绝新增委派、工具请求与迟到结果；原 SHARED/INDEPENDENT Run 行为不变。
- [x] 明确失败按 Q2 汇总结束；请求结果不明则在安全兄弟分支收口后让父进入 WAITING_USER，选择 RETRY_DELEGATIONS 或 ACCEPT_PARTIAL，原 RETRY_AFTER_FIX 不默认授权重发。决定绑定稳定 ID、等待快照、子执行/尝试及不确定请求，并拒绝过期/冲突决定。
- [x] 重试同事务固化决定、只重排选中子执行/Job、清除其 wait.result_json 旧尝试缓存并将父改 WAITING_JOB；保留原 interrupt、成功分支和消费，不先运行主模型或手改 checkpoint。新模型请求关联原请求/本次决定，未知 usage 不归零；旧图版本不兼容走现有安全等待。
- [x] 接受已有结果时未完成子执行按 CANCELLED/用户接受部分结果收口，保留原不确定请求与消费，再让父 QUEUED 汇总；不重新打开最终终态根。子结果先落库再清自己的线程，等待选择时保留，取消/接受部分结果先收口再按精确子 ID 清理，启动补清且不影响父/兄弟图。
- [x] 子状态复用原 ChatTurnEvent/根 seq；同事务校验父子关系、子 claim/attempt 和根取消状态，允许父 WAITING_JOB 时进度写入，子终态事件与子结果/状态一起提交；排队/取消由对应控制路径提交。payload 带 execution_id/agent_id/execution_attempt/status，顶层 attempt/revision 保持根含义；子 token/done 不进入父正文。
- [x] 事件投影、SSE 序列化、background_tasks/快照及压缩投影、前端 Zod/handler/过程区与双语/契约一起适配；沿原订阅和游标恢复，不新增事件表或订阅端点。

## 验证路径

真实 POST turn → general 模型替身发出真实 delegate_knowledge ToolCall → SQLite 委派/Job → 父 WAITING_JOB 返回 → 同槽领取子 claim → 真实 knowledge 图及检索 Tool → 请求/消费/验证后结果落库 → 等待对账 → 原父 checkpoint 续跑 → GET 快照/事件及前端恢复。

模型替身只替换外部 LLM，使用真实 API、迁移 SQLite、JobRunner 和图执行。禁止用直接写终态或跳过 Middleware 冒充委派闭环。

自动化证据使用上述真实生产链和外部模型替身；静态复核单列，不冒充故障注入或真实供应商验收。最终结果与日志见实施记录。

- [x] 单子任务检索/引用/父汇总、父等待时其他会话执行通过；工具白名单复用 01 矩阵，独立冻结输入经双轴静态复核。
- [x] 根 WAITING_JOB 时合法子 claim 可提交；假子身份、失效 claim、错根及缺根预算拒绝（自动化）。
- [x] 重放同逻辑调用不重建子任务、不重复扣准入（故障窗口自动化）；不同参数同身份拒绝经静态复核，未单独注入参数冲突。
- [x] 注册后未停驻、结果先到、结果提交后父未唤醒分别退出/重启对账（公开 checkpoint I/O 停驻，自动化）。
- [x] STARTED 不自动重发；重试/接受已有结果、同决定幂等、连续两次不确定时旧决定不推进新等待、缓存失效及消费保留、供应商变化恢复通过（自动化；外发同意复用既有恢复回归）。
- [x] 根 WAITING_JOB 子状态、快照压缩/恢复身份及 seq、取消后迟到结果不增加事件通过（后端自动化）；断订阅/SSE 解码和等待卡复用前端回归。
- [x] 已完成图只补业务结果不调用模型、结果先提交再清理通过（故障窗口自动化）；独立输入/摘要与精确清理路径经静态复核，未单独故障注入每个清理分支。
- [x] 取消先提交后拒绝子完成且不污染父正文通过；完成先提交的业务事实保留经静态复核，原根轮次先取消/后流结束回归通过。
- [x] 来源删除/排除复用现有检索与引用校验，独立子输入不写父摘要经静态复核；供应商变化有委派重启自动化，外发同意/密钥变化沿原恢复入口回归，未另做全部组合故障注入。
- [x] 复用 test_chat_turns_background.py、test_chat_turns_recovery.py、test_tool_budget.py、test_context_budget.py，相关用例通过；新行为补 test_agent_delegations.py，旧夹具仅随新增列/共享模块归属与工具名单同步，不扩大无关测试。
- [ ] 真实模型与原生桌面另验，不以模型替身或浏览器关闭真实项。

## 桌面重复步骤与证据

准备隔离课程资料 → general 明确要求先检索该课程再汇总 → 观察 knowledge 身份及等待进度 → 切到另一会话发送消息 → 返回检查进度可恢复 → 再分别执行等待时停止与真正退出进程后重启 → 确认取消不回活、完成结果不重跑 → 对不确定请求分别选择重试/接受已有结果，核对仅对应分支推进及原消费保留。

证据：`../02-implementation.md`，记录 root/delegation/job/request/claim 的关联、SQLite 前后查询、槽占用、模型实际调用次数及未知用量，逐项填写证据层级。清理仅限本票隔离资源，保留测试日志，不 add/commit 临时资源。

## 完成定义

单委派具有完整成功/取消/中断/重启证据；不能用“task 工具已开放”或一个 ainvoke 调用当作完成。按批准范围更新进度。
