# 票 03 实施与验收记录

日期：2026-10-11。实施基线：`5da4076013a051c3ce9f3f4f0a4b13c6fef8a037`。本记录随实现提交，以提交历史为身份。初始根及 backend 的 AGENTS.md 改动属于用户，保持原样且不纳入提交。

状态：代码已实现；真实 API／迁移 SQLite／JobRunner／领域 worker 与独立 sidecar 进程验收通过；真实 Tauri/WebView2、真实模型和权威文档审批尚未闭环，因此工单保留 ready-for-human。

## 实现

- Tool `wait_for_task` 复用 LangGraph 原生 `interrupt` 和按 interrupt ID 的 `Command(resume=...)`，保持同步 checkpoint。后台等待登记稳定逻辑调用与原 Run／Job／Operation 引用，复用结果，不创建新的来源任务。
- 现有 ChatTurn JobRunner 每两秒周期对账，启动也对账；结果成功、失败、取消或缺失都给结构化状态，未结束保持等待。等待释放槽但占用会话；回写与排队交接处理原 CHAT_TURN job 尚在执行的窗口。
- 创建直执行 Run 同事务登记 EXCLUSIVE；跨轮次引用为 SHARED；明确批准和完成回答的关联 Run 为 INDEPENDENT。停止同事务复用 RunControlService 的取消与推进链，共享和已提交领域 Job 不误取消。
- RunHistoryService 保护非终态轮次引用的终态 Run 和独立 Operation；与等待登记先取得同一 SQLite 写锁，计数和删除保持同一事务；取消／完成后恢复正常清理。已有会话删除冲突和 checkpoint 生命周期保持。
- 终态 compact API 先保存完整公开快照及 done 引用、版本和压缩游标，再删事件。历史消息投影和旧游标 SSE reset 读取该快照，最终消息和业务事实保留。
- 等待卡复用 Button、现有语义样式及关联任务展示；双语状态／原因同步。WAITING_JOB 订阅持续接续；迟到 REST 等待快照不能覆盖较新的生成／完成事件。
- 恢复前置等待与取消同事务串行，取消已提交时直接落 CANCELLED，避免前置检查晚到重新留下活动等待。
- 迁移 0044 仅 DDL；OpenAPI 与 TS 生成契约同步。工具集合变化使图版本从 v1 升 v2，旧图在途轮次按既有版本守卫保守等待。
- 新等待工具同步既有七组 scope/联网挂载矩阵；聊天／研究 prompt 版本升为 v26／v27，保持模型可见工具面的调用日志可追踪。

## 当前门禁

- 新后台套件 `uv run pytest tests/test_chat_turns_background.py -q --tb=short --basetemp=.tmp/pytest-turn03-background-final`：10 passed。
- 原 ChatTurn 套件：21 passed；recovery 与 Run waiting 两套：39 passed（本次合并运行共47项，新增来源失败／清理夹具修正后另跑后台10项）。
- 前端全量 `pnpm test -- --maxWorkers=4`：722 passed、5 failed，79文件。聊天目录、等待卡、迟到快照用例通过；失败来自未触及的 LearningPlanTab 三项、RecordDetail 一项、CommandPalette 一项，单独两槽复跑仍相同五项失败。
- 前端干净基线 `5da4076` 的隔离 worktree 两槽对照：相同三文件、相同五项失败，26 passed／5 failed；复用安装依赖及仓库未跟踪的既有 `src/lib/utils.ts`，没有复制本次改动。隔离 worktree 已移除。
- 后端全量 `uv run pytest -q --tb=short --basetemp=.tmp/pytest-turn03-full`：1159 passed／4 failed／7 warnings，21分35秒。该次收集先于最后夹具与矩阵修正：新增来源失败夹具使用不存在的 `WEB_FETCH_HTTP_ERROR`（已改为真实 `WEB_FETCH_UNREACHABLE`，后台10项通过）；既有scope工具列表未登记新工具（已补齐，挂载矩阵通过）。另外两项是票02已登记的 document_import 私路径日志断言、quizzes 偏好快照增加主题key的遗留失败，保留不扩展修复。最后改动后针对性门禁通过，未再跑第二次全量，不能写成最终全量全绿。
- 后端两项遗留失败在 `5da4076` 隔离 worktree 实际复现：2 failed／13.81秒；原迁移回填夹具遗漏0043表的问题因本票迁移0044必须修正，相关套件已通过。自动化输出摘要保留在 [证据文件](evidence/automated-summary-03.txt)。
- 最后增量：T19并发清理1 passed；原Run清理3 passed；scope/日志相关4 passed及两份prompt回归2 passed；前端等待卡与Hook最终18 passed。
- 后端 Agent 模块与本次测试 Ruff／格式／Pyright，触及前端 ESLint／Prettier、两份 tsc、`pnpm build`、`pnpm --filter @knowrealm/api-types check` 通过。Vite 既有大包提示未处理。
- code-review Standards 轴无须修复发现；Spec 轴指出 T19 缺证，补公开 API 用例并通过后复审无新增发现。静态审查不替代真机验收。

## T01～T23 证据索引

测试路径统一位于 `backend/tests/`，前端路径位于 `apps/desktop/src/`。01／02 的既有证据保留在各票实施记录，基线为上列提交；表中不把模拟重启写成强杀或真机。

| 项 | 实际证据与范围 |
| --- | --- |
| T01 | `test_chat_turns.py::test_t01_switch_to_b_keeps_a_running_and_b_progresses`；公开 API 模拟订阅切换，真实 worker/DB；T16 再证明后台等待时 B 推进。 |
| T02 | 同文件 `test_t02_completion_while_away_shows_final_message`；离开期间完成和历史结果。 |
| T03 | 同文件 `test_t03_resubscribe_with_cursor_no_loss_or_duplicate`；`useChatTurns.test.tsx` 断线基准、revision与reset；T20 旧游标。 |
| T04 | 同文件 `test_t04_request_id_idempotency_and_conflicts`；请求去重、冲突与配置漂移。 |
| T05 | 同文件 `test_t05_normal_proposal_does_not_block_turn_or_next_question`；T16/T19 真正等待与处理／停止。 |
| T06 | 同文件 `test_t06_slot_failure_is_targeted_and_other_slot_continues`、`test_t06_closure_retry_settles_turn_after_job_already_failed`。 |
| T07 | 同文件 `test_startup_recovery_resumes_running_turn` 及票02生命周期重启证据；本次T17强杀证明等待图恢复。模型节点中途强杀的真实桌面证据仍未执行。 |
| T08 | `test_chat_turns_recovery.py::test_t08_business_committed_before_checkpoint_reuses_result`、undo回执接缝；票02公开服务/API写回窗口记录。 |
| T09 | 同文件 `test_t09_multi_effect_third_committed_only_completes_rest`；逐项幂等接缝。 |
| T10 | 同文件 `test_t10_graph_done_assistant_missing_backfills_without_model`；完成图仅补消息。 |
| T11 | `test_chat_turns.py` 三项取消／完成竞态；后台套件专属/共享等待取消与前置等待取消；`test_agent_operations.py` 提交事务取消守卫。停止中强杀真机项待验。 |
| T12 | `test_chat_turn_event_writes.py` 执行身份与单调写；票02恢复用例、`test_agent_operations.py::test_operation_submit_rejected_when_claim_token_stale`。 |
| T13 | `test_agent_auth_mode.py` 恢复档收紧矩阵；票02授权证据及原Service条件重验；临时高权限跨重启真机项待验。 |
| T14 | recovery 的 `test_t14_provider_change_waits_then_resumes`、`test_t14_api_key_rotation_blocks_resume_until_reconsent`；T19再验后台唤醒仍拦供应商变化。 |
| T15 | 票02固化原system/time/已注入快照、领域当前访问与期限重验记录；隔天和来源变化的完整真实桌面矩阵待验，不能以静态代码核对替代。 |
| T16 | 后台套件 `test_t16_wait_releases_slot_and_resumes_original_result` 成功/失败两参数：不发完成通知，周期对账，B推进、同会话冲突、原ID/attempt、结构化结果及对象各一次。 |
| T17 | `test_t17_killed_source_worker_recovers_original_job_and_turn`：真实socket/sidecar进程，WEB_FETCH已RUNNING时kill，重启走原worker恢复，同Job/Record attempt1→2，Transcript/Library/Operation各一条。 |
| T18 | `test_t18_cancel_exclusive_run_keeps_committed_job`、`test_t18_shared_wait_cancel_leaves_source_running` RUN/JOB两参数、`test_t18_completed_answer_leaves_run_under_existing_control`。 |
| T19 | `test_t19_history_preserves_active_dependencies_then_releases`：公开delete409、purge0、取消后Run1/Operation2清理及业务成果保留；原活动会话删除用例保持。 |
| T20 | `test_t20_compaction_old_cursor_resets_authoritative_snapshot`；正文、最终消息、process/revisions、游标幂等及旧SSE reset；前端快照基准替换。 |
| T21 | `test_chat_turns.py::test_t21_migration_constraints_in_real_database`，T16补0044两表CHECK、逻辑调用唯一、控制关系唯一及压缩游标CHECK；公开snapshot与生成类型同源。 |
| T22 | recovery 的 `test_t22_budget_accumulates_across_recovery`、预算满重放Operation/plan原回执及分类计数；wait新调用计预算、同逻辑恢复复用原行。 |
| T23 | 尚未执行本票真实 Tauri/WebView2 故障矩阵和真实模型测试；下方清单保留未勾。真实sidecar强杀不等同于此项。 |

## T17 真实进程身份

环境：Windows x64，Python 3.13.12、deepagents 0.7.13、langgraph 1.2.11、langchain 1.3.18、FastAPI 0.141.1；本机 bundled ffmpeg，模型与网页网络为测试桩。通过受保护真实 socket 使用原生产 app/lifespan/全部 worker；隔离临时数据目录。

- turn：`f9341111-2fb1-4b80-ad22-616d307f7b17`，COMPLETED，attempt 2。
- run：`d95addab-15d8-47ab-b82d-0e2cf80f2ba0`，COMPLETED。
- WEB_FETCH job：`73796044-c766-4f6f-a9c3-e812a027c72f`，RUNNING/attempt1 时强杀；原ID恢复 SUCCEEDED/attempt2。
- record：`4a5c6f51-5a86-40e6-91ce-2d8f92586625`，原来源对象保留。
- operation：`3659160e-b229-4c19-8dd7-d7f78267177b`，SUCCEEDED；Transcript、LibraryItem、等待关系和Operation均为一条。

## Q1～Q5 复核

Q1：普通提案不触发 interrupt；只有明确 `wait_for_task` 且来源未结束才后台等待。Q2：WAITING_USER处理/停止沿原入口，WAITING_JOB自动接续/停止，供应商变化在唤醒时再次拦截。Q3：图resume沿票02原授权重验；专属停止不更改明确批准独立Run的授权。Q4：保存原供应商/模型，当前配置变化等待，不静默替换；本票T19已运行验证。Q5：复用原execution_json的time/system材料快照；新步骤仍走领域访问/版本/期限校验。T13/T15的完整真机矩阵尚未执行，不宣称Q1～Q5全部真实环境验收。

## 真机剩余验收

- [ ] 隔离identifier/data-dir的当前 Tauri＋真实sidecar＋WebView2，A/B切换、离开完成、刷新、断线、隐藏；对照turn/Run/Job/Operation ID。
- [ ] 模型生成中、领域Job执行中、WAITING_USER、WAITING_JOB和停止过程完全退出／强杀重启，验证恢复、版本展示与取消不复活。
- [ ] 专属取消／共享继续／完成回答的独立Run控制，压缩后旧游标正文与引用同步。
- [ ] 真实供应商模型兼容性；Windows系统缩放及多主题下等待卡可访问性。模型桩、jsdom和视口模拟均不代勾。

## 文档与交接

具体权威文档内容见 [增补提案](documentation-proposal-03.md)，未获批准不改权威文件。全量无关失败保留，未补历史覆盖率、未改规范文件、未增调度平台和设置入口；未改变 Windows 宿主生命周期。

本票隔离 worktree、全部 pytest-turn03 basetemp 与临时日志已清理；只保留上列文本摘要与实际测试身份。其他会话的 worktree/数据未动。

## 审查修复：等待接续丢失展示引用（2026-10-11）

- 确认缺陷：`_StreamState` 每次领取重建，提案／直执行回执事件仅在内存聚合；`WAITING_JOB` 返回后，续跑流只发新事件，完成消息锚点与 done 因而遗漏旧引用。违反 spec §5 的真实业务引用保留及 §10 的回执身份保留要求。
- 公开 API＋真实 JobRunner／领域 Service／迁移 SQLite／持久 checkpoint 复现，同进程接续与关闭 lifespan 后重新启动两种场景均失败。修复前数据库实际有 2 条 MEMORY 和 1 条 RESEARCH_INGEST 提案，done 却只有 1 条记忆提案、0 条研究提案、0 条执行回执，assistant 的 `executed_operations_json` 为 NULL。
- 修复：图续跑经公开 `aget_state` 读取已保存 ToolMessage，复用原工具返回解析器重建展示事件；运行中接续与图已完成的补写共用此路径。worker 按 proposal_id／operation_id 聚合，保留等待前后的引用并消除工具重放重复，不重复执行业务写入或放宽授权。
- 回归用例：`tests/test_chat_turns_background.py::test_wait_resume_preserves_proposals_and_execution_anchors[False/True]`，断言等待前提案原 ID、接续新提案、同一调用重放去重、assistant 执行锚点及历史 USER 轮次 result；来源任务通过真实 worker 完成，模型／网页抓取用替身。
- 修复后两场景数据库及 done 均验证：2 条记忆提案、1 条研究提案、1 条操作提案、1 条执行回执，assistant 锚点与 done 一致；提案总数 4、课程／来源资料／等待关系各 1，无重复业务创建。
- 门禁：`uv run pytest tests/test_chat_turns.py tests/test_chat_turns_background.py tests/test_chat_turns_recovery.py tests/test_chat_turn_event_writes.py tests/test_chat_streaming.py --basetemp .tmp/pytest-wait-references-regression -q --tb=short`：133 passed（250.02 秒）；`tests/test_agent_auth_mode.py tests/test_agent_operations.py -k 'operation_execution_event or operation_proposal_event'`：5 passed。触及三个 Python 文件的 Ruff check／format check、Pyright 通过，未扩大为后端全量测试。
- 本次临时目录仍保留在 `backend/.tmp/pytest-wait-references-{repro,fixed,verified,regression}`：路径边界已核对，清理命令被自动审批策略以 `blocked by policy` 拒绝，未执行删除；其他会话数据未动。
- 本次未验证真实供应商模型和 Tauri／WebView2，未自动补写已完成且 checkpoint 已清理的历史轮次；不改变本票剩余验收状态，也未改权威文档和用户已有 AGENTS.md 改动。
