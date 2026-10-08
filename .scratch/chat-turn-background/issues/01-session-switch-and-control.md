# 01：切换会话与持久控制

**What to build:** 用户在会话 A 发起回答后，可以切换到 B、进入其他页面、刷新或重连，A 仍由后端继续执行；返回时看到持久输出和离开期间完成的最终回答。停止通过明确的后端指令落实，而不是关闭连接。

**Blocked by:** 无，可立即开始

**Status:** ready-for-agent（本次 P1 取消竞态已修复；独立 FAILED 回执事务取消守卫及其他复核问题待修，真机验收未执行）

## 规格与交付边界

- 依据父规格的职责、受理、输出、调度、停止和前端观察决策；覆盖用户故事 1～8、12～15、21～24、42～44，并建立故事 45 的证据记录方式。
- 复用现有 Deep Agents／LangGraph、WorkerSpec／JobRunner、Tool、领域 Service、Proposal／Run／Operation；新建 ChatTurn 表示回答生成，不合并业务任务事实。
- 普通提案可以独立待确认，回答正常完成，不把所有确认卡转换为轮次等待。真正的 WAITING_USER 恢复入口由 02 交付，WAITING_JOB 和专属子 Run 控制传播由 03 交付。
- 本票只交付持续执行与持久观察。重启后的 INTERRUPTED 保留内容、可显式停止，但禁止自动或手动不安全重放；不要显示可用的继续按钮或宣称安全自动续跑。
- 当前轮次停止禁止其新增副作用，已创建独立任务沿既有契约管理；专属子 Run 的持久控制传播在 03 补齐，不把停止回答解释为所有关联业务任务均已停止。
- 既有历史消息和过程展示保持可读，不借机重设计工作区或修改无关 worker。

## 验收标准

- [x] 在迁移后的真实数据库中实现 ChatTurn、持久输出事件及 CHAT_TURN 调度；同会话最多一个非终态轮次，事件序号与受理身份有数据库唯一约束，CHECK／ORM／公开 schema 一致。
- [x] 提交在同一事务保存用户消息、轮次和 job，立即返回 202 及实际状态，不等待生成；事务失败不残留部分对象。
- [x] request_id 在网络重试中稳定：同请求返回原轮次；同身份不同内容、范围、联网、页面或授权参数返回冲突；全局配置变化不改变原请求指纹；重复和并发提交只有一组用户消息／轮次／job。
- [x] 同会话新请求遇到未结束轮次明确冲突，不建隐藏输入队列，不覆盖已有 USER 消息；终态后的新问题创建新轮次。
- [x] 复用两个独立 JobRunner 执行槽，以数据库条件领取、执行身份和 attempt 防重复；A／B 独立推进，网络等待不持有写事务。
- [x] checkpoint 归属独立轮次，不再在另一个会话或新轮次开始时删除活动轮次运行态；本票不启用重放。
- [x] 正文与事件先同事务持久化再通知／发送，含 seq、attempt、output_revision、segment_id／tool_call_id；可展示过程不包含模型私有思维链。
- [x] 快照及 last_seq 来自一致视图；补发只读已提交事件，重复忽略、缺口补拉、通知丢失能自行同步，慢客户端不阻塞生成。
- [x] 最终 assistant、引用、终态及完成事件原子提交，轮次只有一条最终消息；前端完成时使用权威正文，不仅拼接 token。
- [x] 所有聊天发起入口改用提交和订阅契约；卸载、切换及刷新只关闭订阅，AbortController 不作为业务停止依据。旧执行入口迁移期间共享占用约束，调用迁移后移除双执行路径。
- [x] 返回会话读取历史消息和轮次，包括离开期间已完成的轮次；以轮次／最终消息引用合并，回答不漏、不重复，部分输出仍可看。
- [x] 普通确认卡不会让轮次长期占用会话；Agent 可完成回答，用户可以下一轮提问，提案和 Run 的独立确认入口仍有效。
- [x] 停止持久写入 cancel_requested，在模型前、工具前、Job 提交前及业务提交处检查；排队、生成和工具调用期间均可控制，不依赖下一个 token。
- [x] 完成／取消竞态只有一个有效终态；取消先提交后无新副作用，已提交结果和回执保留；不可立即中断时显示“正在停止”，不提前写 CANCELLED。
- [x] 一个槽执行或写回异常仅收口对应轮次／job，其他槽继续；不能以启动全局恢复重置所有 RUNNING。暂时写库失败后恢复可写能针对性收口，不能永久占用会话。
- [x] 启动时遗留执行标记 INTERRUPTED 并保留已保存内容，禁止不安全续跑；原会话可查看原因并停止，后续新问不改写旧轮次。
- [x] 有非终态轮次的会话删除返回冲突并提供先停止入口，不隐式取消，也不删除独立业务历史。
- [x] 复用现有聊天布局、过程与确认组件和 shadcn 控件；新增状态、错误和停止文案同步中英文，按钮有可访问名称，屏幕阅读器不逐 token 播报。
- [x] 业务回执及最终写回走既有缓存失效路径，相关页面能看到真实业务变化；日志关联轮次、job、attempt 和错误码，不记录凭据。
- [x] OpenAPI 和生成类型同步，相关后端／前端测试、类型检查、lint 及触及文件格式检查通过；不补无关测试覆盖率。

## 验收证据

- 以公开 API＋真实 JobRunner＋迁移后的临时 SQLite 验证 T01～T04、T06，以及 T05 的普通提案、T11 的当前轮次取消、T19 的活动删除、T21 的本票迁移。模型／网络可控替身不替代业务写入。
- 前端复用既有 chat 集成接缝，证明切换后后台仍运行、离开期间完成的结果合并、刷新重连和持久停止；记录实际通过的测试和命令。
- [ ] 真实 Tauri＋sidecar＋WebView2 完成 A→B→A、离开期间完成、刷新和隐藏窗口验收；真实模型证据与模型桩证据分开记录。
- [x] 记录实现提交、环境、turn_id 及真实结果；测试数据与用户数据隔离，临时目录在验证后删除；尚未执行的真机项保留未勾选。

## 实施记录（2026-10-07）

- 后端：迁移 0042（chat_turns/chat_turn_events + processing_jobs 整表重建放开 CHAT_TURN job_type，0039 先例）；`agent/turns/` 新子包（models/schemas/projection/service/worker/routes/runtime）；双执行槽 `chat_turn_0/1` 装配（`validate_claim` 纯读 + `on_preempted` 换执行身份——双槽同 job 竞争时落败槽不得有副作用）；取消=独立轮询观察器（0.4s，不依赖下一条 token）+ `cancel_turn` 直收口分支（QUEUED/INTERRUPTED/无在途执行 RUNNING）；启动对账一次性闸门（RUNNING→INTERRUPTED 保留内容，双槽只跑一次防误伤）；`on_loop_failure` 针对性收口（双槽禁全局恢复）；`stream_chat_reply` 增 `thread_id`（`chat-turn-{turn_id}`，每轮独立 checkpoint）；旧 POST /messages 端点与 `accept`/`stream_events`/`ChatStreamRegistry` 移除，过程视图由轮次事件投影（`process_out_for`，历史 REST 与 SSE 同一规则）。
- 前端：`useChatTurns`（提交 202→快照游标订阅→done 权威正文→断线快照对账重连 ≤8 次；打开会话恢复活动轮次部分输出；停止=POST cancel「正在停止」；切换/卸载只 abort 订阅连接）；`chatApi.submitTurn/activeTurn/getTurn/cancelTurn/turnEvents`；`ChatComposer` stopping 态；MSW 默认 handlers 盖 turns 列表；zh/en 同步（chat.turn.* + 六错误码）；api-types regenerate。
- 顺带修复（迁移链连坐，均为预置失败、HEAD worktree 复核属实）：test_agent_run_waiting 升级回拨模拟补摘 0041/0042 新表（0041 加入时未同步）；test_plan_editing 硬编码 user_version==40 改跟随 `supported_user_version()`。
- 自动化证据：后端新增 `tests/test_chat_turns.py` 11 用例（T01 A/B 并发、T02 离开期间完成、T03 游标补发、T04 幂等/指纹/配置漂移/并发、T05 普通提案不阻塞、T06 单槽写回故障针对性收口、T11 取消与完成竞态×2、T19 活动删除冲突、T21 迁移约束、启动对账 INTERRUPTED）+ 既有七测试文件迁移到轮次契约；前端 `useChatTurns.test.tsx` 6 用例（订阅/失效/停止/会话恢复）+ chatSessions.test 轮次契约重写 + chat.test.tsx 39 用例全绿；模型/网络替身=GatedReply/StubChatModel，数据库写入/领取/回执真实。
- 未提交前临时目录（.tmp 冒烟脚本与 pytest basetemp）已删除；真机验收清单（A→B→A、离开期间完成、刷新、隐藏窗口）保留未勾，由用户执行。
- 双轴 review 修复（2026-10-08，全部落地并复验）：①返回会话部分输出——active_only 列表带事件投影（list_session_turn_outs），前端恢复可见已生成正文；②取消检查点——新增 TurnCancelGuardMiddleware（abefore_model/awrap_tool_call 副作用前闸门，cancel_check 经 stream_chat_reply 注入）；③INTERRUPTED 原因展示——hook 消费 chat.turn.interrupted；④断线重连正文缺口——重连以服务端快照 output_text 重置本地拼接再从 last_seq 续订；⑤request_id 保留——仅网络失败（非 ApiError）保留身份重试，服务端裁决即清除；⑥针对性收口退避重试 ≤2 次（写库暂时不可写场景，规格 §6）；⑦审查附带收敛——游标错误 422→400、iso_utc 公开复用、last_claim 改 _ClaimedTurn、job 收口三元组助手 close_job、on_loop_failure 复用 finalize_terminal、routes 去 Any、删 TurnEventPayloads 死导出、错误码清单登记六码、abefore_model 签名对齐框架（state, runtime）。
- 取消业务守卫（2026-10-09，规格 §2/§11/§14）：AgentRuntimeContext 的 turn_id/turn_claim_token 由 worker 填入；turn_write_allowed 通过条件 UPDATE 校验 RUNNING＋身份匹配＋未取消，并持有 SQLite 写锁至业务事务结束，修复原 SELECT 放行到首个业务写入之间取消仍能抢先提交的竞态。复用已有接入点：submit_operation 提案/直执行、propose_memory、propose_ingest 逐条、submit_undo 两分支、submit_batch_plan。取消先提交则拒绝；业务先取得锁则先完成提交，取消等待后落库，保留真实结果。独立 FAILED 回执事务仍遗漏守卫，本次未修，不能据此宣称全部业务副作用已受控。
- 本次验收：新增参数化双连接竞态用例覆盖提案与直执行，在旧 SELECT 实现上均失败；修复后证明校验放行后取消不能抢先写入、业务事务结束后取消可提交、随后工具调用拒绝且不增加提案/回执。`uv run pytest tests/test_agent_operations.py tests/test_chat_turns.py tests/test_research_session.py tests/test_learner_memory.py --basetemp .tmp/pytest-fix-turn-atomic-regression -p no:cacheprovider -q`：110 passed；触及 Python 文件 ruff、格式检查、pyright 通过。另以公开 API＋真实 JobRunner＋迁移数据库，在提案首个写入前挂起并发起取消，验证取消等待业务提交后返回 200，已提交 COURSE_CREATE/PENDING 保留一条；仅模型为桩，临时数据库已清理。未执行全量后端/前端及真机验收。

## 执行注意

开始前复核当前实现、工作区改动、最新迁移编号和项目进度。前端与后端在本票形成一个可演示闭环；不得将后端门禁通过等同于会话切换能力已交付。权威文档只先形成提案，未经批准不修改。

## Parent

[切换会话不中断任务与安全恢复规格](../spec.md)
