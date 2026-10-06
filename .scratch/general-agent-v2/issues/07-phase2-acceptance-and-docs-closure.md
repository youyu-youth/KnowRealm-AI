# 07 — 第二阶段综合验收与文档收口

**What to build:** 对 01~06 已交付机制补齐故障与回归场景（阶段一 04 票模式），收口权威文档与项目进度。自动化验收覆盖：降档中途行为、超阈值、旧提案不进自动执行、清理降级占位、崩溃对账、重启续跑回归、三档越权尝试拒绝、重规划不偷加对象；真机验收清单单列（真实模型、真实 Tauri / WebView2、重启场景）。文档同步把「编排型 Job＋batch_id」的历史表述统一改为 Run 推进，消除设计-4 / 开发计划 / 扩展文档三处口径漂移。

**实施约束:** 验收对照开发计划第七节门禁表（授权 / 目标 / 幂等 / 一致性 / 取消与撤销 / 长任务 / 产品回归 / 扩展性 / 兼容性）；真机项不代勾；不新建评测资产（沿用门禁与既有评测惯例）。

**Blocked by:** 01~06 全部。

**Status:** done

- [x] 故障场景测试补齐：执行中崩溃后重启对账（operation 行＝事实锚点）；直执行超时后查询不重复执行；SSE 断开后 run / operation 状态经持久查询恢复一致
- [x] 授权边界回归：默认档未确认零写入；三档越权尝试拒绝（含 FULL_ACCESS 固定计划外新增目标升回确认）；降档后剩余动作不沿用旧自动授权；升档不扫执行旧提案
- [x] 兼容性回归：旧待确认提案（ORGANIZE 等）沿用现行确认路径、不进自动执行；既有成功回执可查；PENDING 提案跨重启保留
- [x] 产品回归：普通问答、研究提案、RAG 引用、Learner Memory、总结审核、全局搜索在全部档位保持原有约束
- [x] 扩展性验证：03 / 04 / 05 新动作接入对 operations 注册表与 runs 子包零领域分支（AST 防线）；公共流程无领域专属判断
- [x] i18n 一致性防线、api-types regenerate、后端与前端全量门禁绿（既有抖动口径：失败文件单跑绿）
- [x] 文档同步：设计-4 §7（V1 最小形态→Run/Operation 已启用、触发条件已兑现）；开发计划第二 / 三阶段（「编排型 Job＋batch_id」→ Run 推进）与状态行；扩展文档 §44.3；GLOSSARY.md 词条（Run / 计划卡 / 执行前快照 / 操作历史 / 跨课迁移）
- [x] PROJECT_PROGRESS 回写（≤200 行，只保留当前有效信息）；工单逐条勾选并置 done

## 实施备注（2026-09-29）

- **验收方式**＝阶段一 04 票模式：先逐项盘点 01~06+08 既有测试对开发计划第七节门禁表的覆盖，只对真实缺口新增测试，除门禁归零外零生产代码改动。既有覆盖佐证（本票引用不重写）：授权矩阵与三档 dispatch（test_should_execute_directly_matrix / test_delete_and_move_auth_mode_dispatch / test_full_access_ignores_threshold_but_keeps_fixed_plan / test_approved_plan_run_replan_requires_confirmation）、默认档零写入（test_request_approval_defaults_to_proposal 等）、降档三路（跨轮 test_downgrade_rechecks_authorization_next_turn / 流中 test_mid_stream_downgrade_constrains_current_turn / 运行中步骤 test_live_downgrade_*）、升档不扫执行旧提案（test_global_auth_mode_switch :519-525）、超阈值与拆调用累计（test_auto_approve_* 族六例）、Q1 冲突等待重启接续（test_q1_conflict_wait_restart_resolve_and_continue）、重启重投（test_recovery_requeues_running_run_without_active_trigger）、交错手动重试恰好一次（test_concurrent_manual_retry_executes_business_once）、崩溃行不在=未发生（test_applier_crash_leaves_no_operation_or_business_write）、存量提案现行路径（test_organize_legacy_proposal_without_snapshot_still_applies）、批次撤销逆序与取消不补偿（test_run_batch_undo_* / test_cancel_keeps_completed_without_compensation）、快照失效族（modify/delete 各 stale 用例）。
- **新增测试 5 项**（各对应工单条目真实缺口）：
  1. `test_agent_batch_run.py::test_crash_mid_run_restart_reconciles_and_resumes_without_redo`——执行中崩溃（首步已提交、后两步 PLANNED、触发 job 翻 FAILED）→ 重启对账（operation 行如实分布＋业务事实一致＝事实锚点口径）→ recover_interrupted 重投 → 续跑 COMPLETED 且三行 attempts 恒 1（既有 Q1 覆盖等待态接续、recovery 覆盖未推进崩溃，本用例钉死「推进中途崩溃」精确组合）。
  2. `test_chat_streaming.py::test_interrupted_stream_keeps_direct_execution_recoverable`——AUTO_APPROVE 直执行收到 tool_result 后 aclose() 断流：operation 行 SUCCEEDED 恰一条（恰一次）、课程恰一门、零提案、assistant 不落库，经 GET /api/agent/operations 会话过滤持久恢复一致（授权依据含档位）。「直执行超时后查询不重复执行」由本例（恰一行）＋06 交错重试恰好一次＋崩溃对账（行不在=未发生可安全重试）三测试合围覆盖；对照一阶段提案版中断测试（提案保留待决 vs 操作已发生可查）。**run 侧恢复**（checklist「SSE 断开后 run 状态经持久查询恢复一致」）由既有覆盖佐证：`test_active_run_summary_reads_nonterminal_runs_only`（会话消息流读非终态 Run 投影，05 票）＋05 票 review 修复「终态保留为批次回执：终态任务经同一 Run 查询恢复为回执（跨重启成立）」前端 3 用例（ChatBatchRunCard）——本票直执行测试钉 operation 侧、run 侧引用既有，不重复建。
  3. `test_library_lifecycle.py::test_organize_stays_on_confirmation_path_under_auto_mode`——全局 AUTO_APPROVE 生效下 ORGANIZE 提案仍落 PENDING、切档不触碰既有待决行、确认沿用现行路径（APPLIED＋before/after 投影）且恒零 operation 行（不经注册表＝不在直执行通道；RESEARCH_INGEST 同构引用结构保证）。
  4. `test_agent_auth_mode.py` Memory 测试参数化 [AUTO_APPROVE, FULL_ACCESS]——修正测试名/docstring 与实际钉档位（原只钉 FULL_ACCESS）的事实漂移，「任何档位」两自动档齐备。
  5. `test_agent_operations.py` AST 防线受检清单补 `runs/undo.py`＋`runs/retry.py`（06 票新增子模块遗漏入清单，补入后通过＝两文件零领域 import 实证）。
- **门禁归零（既有债务修复）**：HEAD 基线 pyright 存在 4 错（06 票末尾修复提交引入未复跑）——`runs/retry.py` rowcount 类型收窄改 proposals.py 同款 `isinstance(claim, CursorResult)` 判定（零行为变化）、`test_agent_undo_retry.py` OptionalCall 补 assert / 私有引用补 `# pyright: ignore[reportPrivateUsage]`（test_agent_auth_mode.py:31 先例）。触及文件 ruff format；存量 6 个 format 不符文件（course/service.py 等 03/04 票遗留）按「format 只跑改动文件」纪律不动。
- **文档口径统一**：设计-4 §7 两处（V1 最小形态段改「Run／Operation 独立表已启用（触发条件兑现）」＋事实源分工表 Operation 行）、开发计划四处（头部状态行升二阶段收口、§四 07 行与「必须注意」存储条、§五第三阶段存储段改 Run 推进已启用）、扩展文档 §44.3 三处（Run 表述＋头部「能力未上线」过期句＋Mastery 收拢兑现）；全库 grep 确认「编排型 Job＋batch_id」仅存于设计-3（落选方案史实）与被取代说明句。GLOSSARY.md「操作／操作回执」词条更新＋新增 Run／计划卡／执行前快照／操作历史／跨课迁移五词条。
- **产品回归口径**：普通问答/研究提案/RAG 引用/总结审核/全局搜索与档位无共享代码路径（02 票结构论证），全量 pytest 938 绿＋前端 vitest 全绿＝零回归；Learner Memory 两自动档由参数化测试钉住；L0 读取恒自动（test_read_tools_unaffected_by_auto_mode）。
- **兼容性佐证补引**：「既有成功回执可查」=test_migration_0030_new_epoch_and_op_prefix（存量 APPLIED 不回填、旧回执经既有提案查询仍可达）＋test_proposal_list_filters_by_session_across_statuses（全状态列表过滤）；「PENDING 提案跨重启保留」=提案 SQLite 持久化行（跨进程重启天然保留，一阶段 04 已真机验收「重启后提案状态与界面一致」＋前端 APPLIED/FAILED/REJECTED 恢复测试），二阶段 operation 纪元不改变该存储事实。
- **review 处置记录（双轴 code-review 2026-09-29）**：Standards 无硬违规——断流测试与提案版中断测试 ~30 行同构骨架（两处属提取下限，不提取）、runs_package 变量收敛（无碍）两条判断性提示维持现状；「lifecycle SQL 拼接被改单行」经核实为 ruff format 对触及文件的必然改写（ruff 会合并合并后 ≤100 字符的隐式拼接，还原反而制造 format 永远想改的抖动点），保留合规形态并在此披露。Spec 轴采纳 2 项：run 侧恢复与兼容性两子项的既有佐证测试名补进上文（避免「勾选无据」）；崩溃测试重投断言偏弱属既有 recovery 测试职责分工，维持。
- **⚠️ 发现待用户拍板**：数据模型 v3.1 未登记 0030~0033 迁移（agent_runs/agent_operations/agent_activity 三表、agent_proposals.snapshot_json、chat_messages.executed_operations_json、processing_jobs job_type AGENT_RUN）——权威文档升版须走提案流程，本票未擅动。
- **门禁**：后端 pytest 全量 938 passed＋1 既有抖动（test_quizzes 客观题作答，单跑绿，quizzes 域与本票零关联）＋ruff check 全绿＋触及文件 format＋pyright 0 错＋OpenAPI --check 零 diff＋api-types regenerate 零 diff（零 schema 变更）；前端 vitest 全量 exit 0（含 i18n 一致性防线 locales.test）＋lint 0 错＋build 通过（chunk 体积警告为既有）。

**用户真机验收（单列，不代勾，阶段汇总清单）：**

- 真实模型三档全流程走查：默认档创建 / 修改 / 批量整理；帮我批准自动执行＋超阈值计划卡；完全访问批量执行＋计划外目标升回确认。
- Q1 十项冲突场景真机复跑（含应用完全退出后重启接续）。
- 跨课迁移 + 历史回看 + 撤销链真机验证。
- 操作历史分区：run 展开、模式切换审计、清理入口与「历史已清理」降级占位。
- 删除聊天会话后任务历史仍可达。
