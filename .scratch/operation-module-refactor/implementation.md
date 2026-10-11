# Operation module 实施与验收

日期：2026-10-12。基线：`74eb87a5866d7966b44908089b4f949039dca6e8`。

## 当前实现

`operations/execution.py` 的 `_execute` 共用准备、类型化动作应用、结果校验与成功记账；四个私有 adapter 保留确认、自动执行、Run、手动 Retry 的差异。所有事务仍由原入口持有，执行核心不 begin/commit；自动入口的重试循环与独立失败事务整体迁入 execution，不更改其 guard。

`OperationSpec[P, R]` 把 payload schema、应用器载荷及结果类型绑定。全部 22 个动作的应用器接收具体 Pydantic payload 与后端 execution_id；不构造临时 Proposal。确认使用原 Proposal ID，自动/Run/手动 Retry 每次尝试使用新 UUID，草案 Job 保留原来源语义，不迁移成真实 Operation ID。

`runs/bindings.py` 原样承接 Run 的载荷解析、输出引用解析；Operation 的 Run adapter 在原授权检查之后调用。引用模型、计划依赖、Run/Job 生命周期仍属于 Run。

## 调用关系与职责对照

| 原入口 | 重构前 | 重构后保留的责任 | 移入 Operation module 的知识 |
|---|---|---|---|
| ProposalService.confirm → 注册确认应用器 | 注册闭包解析/比较快照、调用 ORM 应用器、校验结果、写成功 Operation | Proposal 条件抢占、编辑校验、显式确认、APPLIED/FAILED 与 HTTP 包装 | execute_confirmed_operation → _ConfirmedExecution → _execute；字符串快照比较、动作应用与成功事实 |
| submit_operation → 自动执行 | registry 自行编排首次/派生快照、提交校验、伪 Proposal 应用、结果校验、成功 Operation/effect | Tools 分流、预算、prepare_effect、提案提交；自动入口保留业务事务、重试和独立失败协议 | execute_direct_operation → _DirectExecution → _execute；基线比较、提交校验、成功 Operation、工具回执/effect 同事务投影 |
| advance_step | worker 重验授权、解析引用/补快照、比较快照、调用伪 Proposal 应用器、序列化并写成功 Operation | 事务内持久取消、计划/依赖/待执行项、结果驱动 Job 等待、Run 收尾/恢复及独立失败记账 | execute_run_operation 接收真实 Run/Operation/plan；授权依据、调用 Run 引用绑定、空快照固化、结构比较与成功记账 |
| retry_standalone_operation | 原身份条件抢占后重复快照/应用/成功编排 | 原 Operation 身份、条件抢占、并发输家投影、回滚后失败事务 | execute_retry_operation → _RetryExecution → _execute；结构比较、应用、结果与 attempts 成功更新 |

`RunOperationBlocked` 表示原事务内的执行前拒绝，worker 就地落 FAILED/SKIPPED/WAITING_USER；领域编码异常仍走原回滚与独立失败事务。没有把快照拒绝改成另一种事务语义。

Undo 的应用器签名未受影响：继续读取原 Operation 的 payload/snapshot/result，经原补偿器和版本校验执行。仅相关 Retry 调用适配；Undo 全部既有行为断言保留。

## 行为验收映射

| 标准 | 现有原入口证据与核对点 |
|---|---|
| A01 | test_agent_auth_mode 的授权矩阵、非 Operation memory 提案；test_agent_operations 的公开工具/提案投影；OpenAPI --check |
| A02 | test_agent_operations 的并发 confirm、确认失败与重试；test_agent_modify_actions 的旧快照失效；test_plan_editing 的卡片合法编辑 |
| A03 | test_agent_auth_mode 的业务/系统失败回执；test_agent_undo_retry 的写后崩溃回滚；test_chat_turns_recovery 的提交后 effect 恢复 |
| A04 | test_agent_operations 的取消后提案/直执行拒绝及提交交错；test_agent_batch_run 的取消保留成功项；独立失败事务逐分支与基线对照，保留原 guard 缺口 |
| A05 | test_agent_modify_actions、test_plan_editing、test_agent_undo_retry 的派生基线/锁竞争目标变化；test_agent_run_waiting 的引用注入、完整快照及 Undo |
| A06 | test_agent_batch_run 的 live downgrade、resume 不绕过授权、已确认计划继续；test_agent_multi_source_run 的 L2 批次批准 |
| A07 | test_chat_turns_recovery 的指纹冲突、预算满重放、业务先提交后 checkpoint 恢复、Undo 原回执恢复 |
| A08 | test_agent_batch_run 的独立步骤继续、依赖跳过、真实 JobRunner 重启；test_agent_run_waiting 的等待/唤醒/失败/取消/重启不重复；test_agent_multi_source_run 的多来源与草案恢复 |
| A09 | test_agent_undo_retry 的补偿版本/同值回改、原身份手动 Retry、attempts 历史与并发抢占；test_agent_batch_run 的步骤失败重试 |
| A10 | 所有已注册动作签名与 ORM 使用静态盘点；上述职责对照；Standards/Spec 两轴独立审查 |

新增的必要回归限定在身份契约：确认/自动草案 Job 标识两例；既有 Run 草案失败重试用例补断言“每次新 UUID、不替换成 Operation ID”。故障注入跟随共享应用接缝迁移，原业务断言保留；并发 Retry 暂停注入放在失败回执准备之后。

## 验证记录

在 `backend/` 执行，所有 pytest 使用本轮独立 basetemp。

1. 修改前相关基线：`uv run pytest tests/test_agent_operations.py tests/test_agent_auth_mode.py tests/test_agent_modify_actions.py tests/test_agent_delete_and_move.py tests/test_agent_batch_run.py tests/test_agent_undo_retry.py tests/test_agent_runs.py tests/test_agent_run_waiting.py tests/test_agent_multi_source_run.py tests/test_plan_editing.py --basetemp=.tmp/pytest-operation-baseline -q`：**265 passed**；3 条既有 aiosqlite named-parameter 弃用警告。
2. 新身份回归：`uv run pytest tests/test_agent_multi_source_run.py -k 'execution_identity or job_failure_then_retry' --basetemp=.tmp/pytest-operation-identities -q`：**3 passed**。
3. 并发 Retry：`uv run pytest tests/test_agent_undo_retry.py -k concurrent_manual_retry --basetemp=.tmp/pytest-operation-retry-claim -q`：**1 passed**。
4. 全量测试：`uv run pytest --basetemp=.tmp/pytest-operation-full -q`：**1167 passed、2 failed、7 warnings，1286.16s**。本票相关 10 文件 267 用例均通过。此前两轮相关批跑因迁移后的并发测试注入时点不当被中止，不作为通过证据。
5. 触及文件 Ruff check/format、范围 Pyright、OpenAPI check 已通过。Pyright 范围为 `app/modules/agent/operations app/modules/agent/runs tests/test_agent_undo_retry.py tests/test_agent_multi_source_run.py`。
6. 全量 `uv run pyright`：**6 个既有错误**，test_chat_turns.py:1043/1055/1107 的 5 个未使用变量，以及 test_error_code_guard.py:52 的部分未知类型。对基线原始两文件的隔离检查复现同 6 条；未修改这些文件，也未降低检查规则。

全量失败已在未改动的基准代码副本复现：用 `git archive 74eb87a5866d7966b44908089b4f949039dca6e8 backend` 提取完整 backend，使用相同 `.venv/Scripts/python.exe -m pytest` 在副本内单跑两项，**2 failed，14.14s**，断言完全一致：

- `test_document_import.py::test_unexpected_io_and_parser_errors_are_not_retryable_or_logged`：JobRunner 的异常 traceback 含测试私有字符串；断言失败于 765 行。此日志隐私问题位于未触及的模块。
- `test_quizzes.py::test_quiz_last_count_preference_round_trip[asyncio]`：原断言遗漏现有 `light_theme_id` / `dark_theme_id` 字段，失败于 1017 行。

未修复上述历史失败，也未删改其断言；全量门禁仍非全绿。

## Review

### Standards

0 项可操作问题。新增 adapter 各自承载实际入口差异，复用原领域 Service；类型化 schema 与应用器绑定，未引入无需求配置、依赖或跨业务域反向依赖。最终结构调整后增量复核无新增问题。

### Spec

0 项未解决发现。发现的 Run interface 缺少真实 Run 上下文已修复；授权检查仍先于载荷与引用绑定，失败拒绝保留原事务语义，身份与取消协议保持。

两轴均为独立只读静态审查，运行证据以上述实测为准。

## 验证级别与限制

- 自动化涉及真实迁移 SQLite、原 Proposal/Tools/API/Run/JobRunner 入口与持久结果，包括并发、提交回滚、等待与重启；全量还覆盖真实 sidecar 子进程恢复测试。网络、LLM、锁故障等使用既有替身；不宣称使用真实模型。
- 未运行真实模型与真实 Tauri/WebView2 验收；本票未改变前端、公开 schema、Tools、HTTP/SSE、数据库或 checkpoint 格式。
- 草案 Job 的标识关联问题保留待独立复现；本票只维持其原来源。自动入口独立 FAILED 回执事务的既有取消 guard 行为也按规格保留。
- 不增加依赖、迁移、策略开关、通用 action 工具、重试/Undo 能力或其他历史修复。
