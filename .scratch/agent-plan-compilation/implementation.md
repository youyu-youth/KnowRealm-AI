# 工单 01 实施与验收

日期：2026-10-12。范围：内部计划编译与延展重构；外部协议和批准规则保持。源码基点 `0a70b051fc7be6a2dde343e19a8a4f13c4116878`，主实现提交 `55dfaf0`，最终覆盖读取顺序调整提交 `1f3f70b`。

## 实际改动

仅修改 `backend/app/modules/agent/runs/plans.py`，251 行新增、365 行删除，净减少 114 行。

- `_PlanStep` 将原提交索引、请求项、OperationSpec、判别参数与快照绑定为一个内部步骤记录。
- `_CompiledPlan.compile/from_proposal` 复用原动作登记、schema 投影与引用延期校验；`capture_snapshots` 保持已有目标快照和未创建引用目标的跳过策略。
- `route` 内部读取会话累计数与活步骤，保留三档、阈值、固定计划及等待态分流。入口不再配对请求项与解析列表。
- `persist` 内部完成覆盖复用、待执行修订、成功后追加、确认快照重验、依赖与引用编号映射、Operation/计划投影写入；返回实际生效项数。
- 删除 `resolve_plan_items`、`capture_plan_snapshots`、`verify_plan_snapshots`、`pending_plan_batch`、`append_plan_operations`、`batch_route` 的旧平行序列接口，两条入口不再拆装六元组。
- 入口继续拥有事务、目标 Run 选择、授权上下文、轮次绑定、触发 Job 和成功 Effect/Proposal 回执；共享 implementation 只读取、写入和 flush。
- 最后核对时移除自动入口额外的覆盖查询：compiler 复用分流阶段读到的覆盖事实，确认入口仍在原位置读取，保持原编排读取顺序。该补充后再次运行相关六文件及触及类型/规范检查。

动作白名单及外部扁平字段仍由原枚举/schema 维护；未增加通用 catalog、协议版本、迁移、Prompt、Tool、SSE 或 UI 变更。原 `_concrete_payload`、延期错误条件和最终执行端完整校验未改。

## 两条入口代码证据

源码均指向最终实现提交 `1f3f70b`：

| 阶段 | 自动提交 | 计划卡确认 |
| --- | --- | --- |
| 解析 | `submit_batch_plan` 调用 `_CompiledPlan.compile` | `apply_batch_plan` 调用 `_CompiledPlan.from_proposal` |
| 快照 | 调用 `capture_snapshots`，保留目标不可达结构化返回 | `from_proposal` 读取旧持久格式，`persist` 重验实际待执行项 |
| 编译与落库 | 调用同一个 `persist`，只消费新增/修订数量 | 调用同一个 `persist`，只消费新增/修订数量 |
| 控制绑定 | 新 Run 为 EXCLUSIVE，延展为 SHARED | 确认为 INDEPENDENT，保留原轮次定位 |
| 事务回执 | `session.begin` 内绑定/触发/Effect 成功同事务 | ProposalService 确认事务内绑定/触发/Proposal 成功，失败诊断仍由框架独立记账 |

原 `pending_plan_batch` 六元组、子批快照/解析对齐、preset/replaced/提交索引参数已从两个入口删除。覆盖及序号字典仅存在于共享 `persist` 内部。

## 持久行为验收映射

| 保证 | 本轮实际运行的既有公开入口用例 |
| --- | --- |
| 三档与累计阈值、原 AUTO_APPROVE 延展 | `test_agent_batch_run.py` 的三档、拆调用、完成后累计、按会话计数、改参用例 |
| 提案确认前零业务事实、快照失效回滚 | 同文件 `test_request_approval_creates_plan_card_without_business_fact`、`test_confirm_plan_after_target_changed_is_stale` |
| 混合覆盖/新项、待执行身份与位置、成功历史追加 | 同文件 `test_mixed_batch_only_appends_pending_targets`、三个 `test_replan_changed_params*` 用例 |
| 原依赖与追加批引用编号 | `test_confirm_plan_carries_dependencies_between_steps`；`test_agent_run_waiting.py::test_appended_batch_refs_bind_to_own_steps` |
| 含引用已有目标快照、执行前重验与 Undo | 等待文件 `test_ref_update_step_snapshot_stale_blocks_overwrite`、`test_ref_update_step_snapshot_complete_and_undoable` |
| 损坏计划拒绝且不覆盖 | 批量文件 `test_corrupt_plan_rejects_plan_append`、`test_corrupt_plan_confirmation_fails_and_keeps_run_unchanged` |
| 旧卡合入活跃 Run、版本不回退 | 批量文件 `test_second_plan_card_confirmed_extends_first_run`；快照/Run JSON 沿用旧形状 |
| WAITING_JOB/WAITING_USER、失败/跳过与原身份重试 | 批量/等待/多资料文件中的推进、唤醒、冲突等待、部分失败、失败重试用例 |
| 重启不重做成功项、保留 Job 等待链 | 等待文件 `test_restart_reconcile_waiting_run_without_redo` 与中断 web fetch；多资料中断 plan draft；批量中途崩溃恢复用例 |
| Effect 成功重放先于预算、无重复 Run/Job | `test_chat_turns_recovery.py::test_plan_replay_at_budget_limit_returns_original_receipt` 及多效果恢复用例 |
| 持久取消、轮次身份和绑定语义 | `test_chat_turns_background.py` 中独占/共享/独立 Run、取消、等待与恢复；预算文件取消和身份校验用例 |
| 前端既有消费兼容 | `ChatBatchPlanCard.test.tsx`、`ChatBatchRunCard.test.tsx`、`useChatTurns.test.tsx`；TypeScript 与 OpenAPI 检查 |

上述用例保留原行为断言，没有为内部类型增加镜像测试，也没有修改任何测试。

## 已执行检查

- 原基点相关四文件：99 passed，70.35s。
- 首轮重构相关四文件：99 passed，65.97s。
- 主实现六文件（上述四文件 + `test_chat_turns_background.py` + `test_tool_budget.py`）：136 passed，212.90s。覆盖读取顺序调整后，同六文件最终补跑 **136 passed，151.21s**，触及 Pyright/Ruff 再验通过。最终独立 basetemp 为 `.tmp/pytest-plan-compiler-query-order`。
- 前端上述三文件：29 passed；两个 TypeScript 配置检查通过。
- 触及文件 Pyright 0 errors；Ruff check/format、OpenAPI check、`git diff --check` 通过。
- 静态 AST 自检：9 个既有函数（字段投影、延期错误条件、部分载荷、快照读取、目标选择及错误投影）与原基点完全一致。
- 全量 Pyright：未修改的 `test_chat_turns.py` 五个未使用变量和 `test_error_code_guard.py` 一个 Unknown 类型，共 6 项；从原基点 git archive 导出的隔离 backend、同一解释器再次复现同 6 项。
- 原基点隔离复验：`test_unexpected_io_and_parser_errors_are_not_retryable_or_logged`、`test_quiz_last_count_preference_round_trip` 均失败（2 failed，14.03s），分别为异常日志私有字符串与设置返回新增主题字段的旧断言。
- 后端全量 pytest（主实现 `55dfaf0` 快照）：1192 passed、2 failed、7 warnings，1332.43s。两个失败与原基点隔离复验一致，未扩大修复历史问题；最后的覆盖读取顺序调整后，上述相关六文件再次全部通过；未将先前全量结果描述为最终补丁后的全量重跑。

## 双轴审查

按 `code-review` 技能由两名独立只读子代理审查本次源码 diff：Standards 0 项，Spec 0 项，无未解决的新问题。固定范围为 `git diff 0a70b051fc7be6a2dde343e19a8a4f13c4116878...1f3f70b -- backend/app/modules/agent/runs/plans.py`；最后 4 行覆盖事实复用调整已由两轴追加复审，均无发现；审查不替代运行验收。

## 保留差异与验收边界

- AUTO_APPROVE 的未确认活跃 Run 可在原阈值内自动延展/修订；旧卡可合入当前活跃 Run，目标终态后可另建 Run。本票保持这些现状，未修正授权规则。
- 待执行修订继续保留原 Operation 身份/位置及依赖；混合修订与追加沿用原 `base_index + 待执行枚举序号` 规则，编号可有间隙，本票未引入基础版本 CAS 或新编号/依赖编辑策略。
- 本轮运行真实迁移、SQLite、ProposalService、Operation/Run Worker、JobRunner、公开 API 和 checkpoint 恢复路径。模型及网络使用现有受控替身；部分等待用例显式设置 Job 终态，不能视为真实网络或模型验收。
- 真实模型、外部网络和 Tauri/WebView2 未执行。浏览器/jsdom 消费测试不代表原生桌面验收。
- 未实施 ADR-0027 完整协议/审批升级，后续目标仍在 `upgrade-spec.md` 与 deferred 工单中。
- 本次测试使用独立 `backend/.tmp/pytest-plan-compiler-*` 和原基点隔离副本；临时目录清理命令被环境策略拒绝（`blocked by policy`），因此目录保留。没有扩大清理范围或改动用户原有测试文件删除。
