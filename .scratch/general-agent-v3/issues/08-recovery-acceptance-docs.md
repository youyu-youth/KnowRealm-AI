# 08 — 长任务恢复核验与必要文档收口

**What to build:** 复用 06、07 已完成的实现、测试与真机清单，集中核验中途退出恢复和真实模型端到端链路；修复实际发现的恢复缺陷，核对业务数据、操作历史与界面展示一致，并同步必要文档。此票是验收与缺陷收口，不重新开发多资料编排。

**Blocked by:** 07 — 多资料建课编排（代码已完成，执行前复核当前状态）

**Status:** done（2026-10-06，自动化门禁全绿；真实模型端到端与真机退出恢复**待用户验证**〔见文末〕）

## 执行边界

- 能力入口沿用现有计划卡、Run 继续 / 失败步骤重试 / 取消端点与领域 Service；Agent 与页面共用受控执行路径。本票不新增工具体系、恢复平台或任务调度框架。
- 授权沿用 ADR-0026：固定来源清单、建课与目标参数、计划生成意图；恢复不扩大批准范围，权限变化和快照失效仍走既有检查。学习计划草案确认是 Run 之外的人工闸门。
- 应用隐藏且 sidecar 存活时继续执行；完全退出期间不执行，下次启动对账恢复；已完成步骤不重做，取消不冒充撤销。
- 原 spec 的自动续跑要求保留。发现中断 Job 只能落失败、需手动重试时，登记为恢复缺口；不得仅修改文案或降低验收要求关票。若修复必须改变既定授权 / 重试语义或架构，提出具体决策提案，继续完成不依赖该决策的核验。
- 优先运行相关现有测试；仅为本票实际发现且现有测试未覆盖的行为新增最小回归测试，不补历史覆盖率。

## 1. 复用已有证据

- [x] 阅读 PROJECT_PROGRESS、[spec](../spec.md)、[06](06-run-waiting-binding.md)、[07](07-multi-source-course-run.md)，固定验收 commit（b5a0972；07 之后另有 e75481a 修复提交十轮 codex 审查项），记录工作区已有改动（本工单文件自身重写，随收口一并提交）。
- [x] 运行并记录 `backend/tests/test_agent_run_waiting.py`（21 用例）、`test_agent_multi_source_run.py`（12 用例）基线全绿——等待接续（唤醒完成不重做/未终态持续等待）、部分失败（两份一成一败 PARTIAL + 依赖 SKIPPED）、单步重试（URL 幂等复用/本地文档原地重置/草案重投）与取消行为（等待中取消保留 job/竞态兜底）均有既有覆盖。
- [x] 部分失败覆盖检查：既有用例证明「失败步骤的**依赖者** SKIPPED + 课程与成功导入保留 + 单步重试收敛」，但**失败步骤之后的独立步骤照常执行**未覆盖（既有用例的失败步骤排在末段）→ 补最小用例「五份独立导入第三份失败」：其余四份仍完成（推进不因单点失败停止）、课程保留、失败步骤重试成功后 Run 收敛 COMPLETED、五份条目恰好五条（重试不重复入库）。

## 2. 核验并修复中途退出恢复

**执行前复核的已知缺口（2026-10-05 代码核对）：** `agent/runs/worker.py` 会重投 RUNNING / WAITING_JOB Run 的触发并核对等待 Job；`capture/web_fetch_worker.py` 和 `agent/operations/plan_draft.py` 的恢复会把正在运行的来源 Job / 草案 Job 标记为失败，随后等待步骤走失败分流。已有 `test_restart_reconcile_waiting_run_without_redo` 先把来源 Job 置为 SUCCEEDED，再调用 Run 恢复；它证明已完成 Job 的接续，不证明执行中 Job 的自动恢复。执行时同时核查 DOCUMENT_PARSE 的实际恢复策略。

- [x] 调用链核验（`main.py` lifespan → worker_factories 表序逐 worker `recover_interrupted`：document → summary → review_material → … → web_fetch → agent_run → plan_draft）：**AGENT_RUN 触发 job** 是无状态触发器（中断翻 FAILED 后 Run 对账重投即恢复）；**DOCUMENT_PARSE**（`document_worker.recover_running`）本就是正解形态——`attempts < max_attempts` 回 PENDING 带退避自动重投（max_attempts=3）、耗尽才翻 FAILED；**WEB_FETCH 与 PLAN_DRAFT** 恢复一律翻终态 FAILED（WORKER_INTERRUPTED）且 job 创建 `max_attempts=1`——即使恢复想重投也无预算，中断即终态失败需手动重试，**确认为恢复缺口**（spec US32「应用重启后未完成的长任务自动对账恢复继续」被这两类打断）。
- [x] 按下表核验（自动化经对应来源 worker 的真实恢复与写回链路，非改 Job 状态替代）：

| 退出时点 | 验收结果 | 证据 |
| --- | --- | --- |
| 来源 Job 已成功，Run 尚未接续 | 启动后继续后续步骤；建课、资料导入等成功步骤不重做 | 既有 `test_restart_reconcile_waiting_run_without_redo`（06，attempts 恒 1 断言）复用 |
| WEB_FETCH / DOCUMENT_PARSE 已领取、尚未完成 | 启动后按既有通道安全恢复并接续；来源对象不重复、Transcript / 索引 / Record 状态一致 | **修复后**新增 `test_interrupted_web_fetch_requeues_and_completes`（真实 recover → 回 PENDING、Record 维持 CONTENT_PROCESSING → 真实 worker 写回〔Transcript 落库 + Record 推进 SUMMARY_PENDING〕→ Run 对账唤醒 COMPLETED、步骤 attempts 恒 1、单条目单记录）；DOCUMENT_PARSE 既有通道代码核验 + `test_document_import` 重启用例族 |
| PLAN_DRAFT 正在生成，尚未落确认卡 | 启动后恢复生成并产出确认卡；用户确认前不落 learning_plans，成功落卡后不重复生成卡 | **修复后**新增 `test_interrupted_plan_draft_requeues_and_completes`（真实 recover 回 PENDING → 真实 worker 全链生成+写回草案卡 → Run 对账 COMPLETED；断言草案卡恰 1、learning_plans 零行） |
| Run 已取消或等待用户确认 | 启动不复活已取消任务，不绕过用户确认；已提交 Job 的结果与回执仍可查询 | 既有 `test_cancel_waiting_run_settles_and_keeps_submitted_job` + recover 只扫 RUNNING/WAITING_JOB（WAITING_USER 不投递）代码核验 |

- [x] 修复缺陷：`web_fetch_worker.recover_running` 与 `plan_draft` 的 recover 对齐 DOCUMENT_PARSE 形态——`attempts < max_attempts` 回 PENDING 带退避（2^attempts 秒）自动重投、耗尽才翻终态 FAILED；WEB_FETCH 预算内 Record 维持 CONTENT_PROCESSING（find_candidate 照常命中）。配套 `create_web_ingest_rows` 与 PLAN_DRAFT job 创建 `max_attempts` 1→3（**业务失败仍一次性终态**：两类 apply_failure 均走 mark_failed 不看预算，中断≠业务失败）。修复不改变授权（来源 job 续跑不涉授权面）、不改变重试架构（attempts 预算/手动重试通道/部分唯一索引全部沿用）、复用 DOCUMENT_PARSE 既有先例，故无需决策提案。
- [x] 幂等与边界检查：恢复重复调用幂等（只扫 RUNNING，二次调用无 RUNNING 零操作；0033/0039 部分唯一索引保证回 PENDING 后不重复占位）；已提交结果（终态 job/回执）不被恢复触碰；LLM 重投仍经执行期 validate_claim 二次确认与 provider 检查（PLAN_DRAFT 既有稳定失败码路径不变）；预算耗尽落 FAILED 交 Run 失败分流（`test_interrupted_web_fetch_budget_exhausted_fails`：PARTIAL_COMPLETED、保留手动重试）。红验证：撤掉产品修复后两个 requeues 用例如期转红。

## 3. 真实环境验收

- [ ] 配置真实模型，在 Tauri + sidecar 中执行一次「多资料建课 → 资料处理与挂课 → 目标 → 草案确认卡 → 用户确认计划」；来源与操作步骤沿用 [07 真机清单](07-multi-source-course-run.md#用户真机验收清单不代勾)。**待用户真机验证**（自动化侧无真实模型/真机条件，不以 mock 代勾）。
- [ ] 在真实环境核验应用隐藏、完全退出后重启，以及等待期间取消；重点复核第 2 节执行中 Job 的退出时点。**待用户真机验证**——本票新增最小复核项：Run 等待 WEB_FETCH / PLAN_DRAFT 期间**完全退出**应用 → 重启后来源 job 自动重投续跑至完成（修复前该场景会呈现失败步骤、需手动重试）。
- [ ] 用同一 run_id 对照课程 / 资料 / 目标 / 计划数据、agent_operations 的逐项状态与回执、聊天任务面板与草案卡。**界面呈现待用户**；数据/操作行一致性已由自动化断言（新用例断言业务事实与 operation 行状态/错误码/attempts）。
- [x] 记录环境、commit、结果：自动化环境 = commit b5a0972 + 本票工作树（Windows/uv/py312）；证据脱敏不记录 API key；真实环境证据（模型、run_id、退出时点快照）待用户回填。

用户验收沿用 [06 清单](06-run-waiting-binding.md#用户真机验收不代勾)、[07 清单](07-multi-source-course-run.md#用户真机验收清单不代勾)；M1 日常学习计划与共享引用沿用 01~05 各票清单。本票仅补充执行中 Job 退出恢复的证据，用户项目由用户确认，不再复制整套清单。

## 4. 必要文档与门禁收口

- [x] 整理数据模型升版提案：实际缺登范围为 **0027~0039 共 13 个迁移**（工单预估 0030~0039，执行核对 0027 研究会话/0028~0029 通用 Agent 一阶段同样晚于 v3.1 定稿日）；登记新表 7 张（agent_runs / agent_operations / agent_activity / learning_goals / learning_plans / learning_plan_items / course_shared_refs，已实施 31→38、设计 44→47）、存量表变更 8 项、learning_goals.course_id 对 P6 原设计的显式修正；learning_agent_actions / learning_agent_feedback / teach_back_attempts 维持 deferred 并登记启用条件。提案落盘 [data-model-upgrade-proposal.md](../data-model-upgrade-proposal.md)，**待用户批准**。
- [x] 提案列明拟修改的权威文档（数据模型升 v3.2 重命名 + PRD/技术栈/扩展设计头部交叉引用 + PROJECT_PROGRESS 标记翻转）、升版与交叉引用范围；未批准前不动任何权威文档，本工单更新不视为批准。
- [x] 权威文档零修改（核验结论）：恢复行为是 JobRunner 内部机制，对外 API/SSE/prompt 契约零变化（prompt 未 bump、OpenAPI 零 diff）；扩展文档 §44 对恢复仅有概括性表述（「JobRunner 自研队列带崩溃恢复」）与本票修复方向一致、无相悖旧口径；`recover_running_to_failed` 仍是 LLM 四域等 22 个 worker 的默认通道（未漂移）；CONTEXT 学习目标/计划/计划项/共享引用词条随 01/02/03/05 已落。PROJECT_PROGRESS 已更新（见下）。
- [x] PROJECT_PROGRESS 收口：删除重复的 2026-09-29 旧「最后更新」头；§3 表 06 行「修复中」改 done（审查修复 10-02 已落地）；补 07/08 两行；§5「第三阶段进行中」更新为八工单全部完结；§6 迁移清单 0038→0039；186 行保持 200 行内。
- [x] 门禁：修复了产品代码 → 收口全量重跑。后端全量 pytest **1083 passed**（含 4 项新回归；独立 `.pytest-tmp` 测后已清理）+ ruff check/format（触及文件）+ pyright **0 errors** + OpenAPI `--check` 零 diff。前端零改动（恢复为后端内部机制，i18n/契约零变化）→ 引用 07 验收 commit 既有前端全量证据，不重复跑。
- [x] 在本票追加执行记录（下节）。

参考：[spec.md](../spec.md) M2 执行闭环、Testing Decisions、Further Notes；[06](06-run-waiting-binding.md)；[07](07-multi-source-course-run.md)。

## 执行记录（2026-10-06 备案）

**已复用证据**：06/07 既有测试 33 用例基线全绿（§1 清单）；重启对账「成」分支、等待中取消、job 缺失保守失败等 21+12 用例直接引用，未重复实现。

**发现与修复的缺陷**：
1. **恢复缺口（本票主缺陷）**：WEB_FETCH / PLAN_DRAFT 中断恢复一律翻终态 FAILED + `max_attempts=1` 双重锁死自动续跑（对照 DOCUMENT_PARSE 既有 attempts 预算形态）→ 修复为预算内回 PENDING 带退避自动重投（耗尽才 FAILED）+ max_attempts 1→3；业务失败语义不变（apply_failure 一次性终态）。
2. **搭车修复一（测试日期锚凌晨错位，非本票引入）**：`test_plan_editing.py` / `test_learning_plans.py` 的 `TODAY = datetime.now(UTC).date()` 与产品排期锚 `local_today()` 在本地凌晨 0~8 点差一天 → 「起点回挪」防线误拒全部提交（全量 11 failed 的根因；白天跑绿掩盖）。修复：TODAY 改 local_today 同源；`effective_from/to` 断言分锚 `LANDED`（产品定稿 UTC 落库日，service._next_version 注释明示，凌晨差一天无逻辑破坏、本票不改产品语义）。
3. **搭车修复二（e75481a 遗留 pyright 4 错）**：`lambda _data_dir: provider` 两处裸 lambda（partial unknown）→ 换带注解 def（07 同款处理）。
4. **搭车修复三（既有 TOCTOU 测试稳定化，产品不动）**：`test_text_capture_enqueues_backfill` 撞 capture 入队钩子与回填 worker 完结写回的固有竞态窗口（钩子读 RUNNING 不投 + worker 完结时新记录未提交不可见 → 撞窗记录成孤儿直到下一次捕获钩子补扫自愈，生产影响=条目延迟建立；干净 HEAD 同样红、诊断脚本实证双窗口时序）→ 用例先等启动回填落定再捕获，专测「入队钩子 → worker 真实运行」链路。**竞态本身登记为资料库域已知问题**（PROJECT_PROGRESS §7 已登记；有自愈路径，修复属独立工单范围）。

**审查备案（code-review 双轴，2026-10-06）**：Standards 轴无硬违规——「中断恢复预算分支」形状现散在 document/web_fetch/plan_draft 三处内联副本，**收敛提案登记**（与退避公式统一、job-runner issue 01 一并处理，见 PROJECT_PROGRESS §7；本次不抽共享 helper＝document 公式明文冻结保真，抽统一即动雷、超票面）；测试 helper 命名对齐同文件惯例（`interrupt_mid_fetch`）。Spec 轴无确证违规（四时点证据逐格核实、范围无蔓延、文档数据与迁移目录实核一致）；恢复幂等与 PLAN_DRAFT 重投后 goal 终态两处无恢复期专测＝同一执行路径既有用例已盖，按工单「不为完整度扩测试」不补。

**追加修复（2026-10-06，codex 审查发现的存量缺口，属实已修）**：恢复预算 1→3 只落在新建路径（`create_web_ingest_rows` / `apply_plan_draft_generate`），**升级前已落库的 WEB_FETCH 未终态任务仍为 max_attempts=1**——抢占已 attempts+1，重启恢复 `attempts(1) < max(1)` 不成立、直接翻终态 FAILED，违反 spec US32（重启不分版本；DOCUMENT_PARSE 无此问题＝其创建路径从诞生即 max=3）。修复＝新增迁移 **0040** 纯数据回填（0022 先例）：WEB_FETCH/PLAN_DRAFT 的 PENDING/RUNNING 行 max_attempts<3 → 3（终态史实与其余 22 个 worker 的 max=1 刻意合同不触碰；迁移先于 worker 恢复执行，回填后 recover 预算内回 PENDING）。不改 recover 逻辑（`max_attempts` 落库值为创建时合同，recover 擅自提预算会偏离 DOCUMENT_PARSE 对齐形态）。新增回归 `test_upgrade_migration_backfills_legacy_recovery_budget`（真实链路造中断瞬间 → 模拟升级前预算=1 + 版本回拨 0039 → 重放迁移链 → 断言回填后 recover 回 PENDING）+ 红验证（撤 0040 转红）；`test_plan_editing.py` user_version 断言 39→40；数据模型提案补登范围更新为 0027~0040（14 个）。

**自动化结果**：后端全量 1083 绿（4 项新回归 + 红验证：撤产品修复两个 requeues 用例转红、存修复全绿）+ ruff + pyright 0 错 + OpenAPI --check；前端零改动引用 07 证据。

**真实环境证据**：无（自动化环境无真实模型与真机条件，如实缺省，不以 mock 代勾）。

**待用户项**：
- 真机验收：07 清单 7 项 + 06 清单 + 本票 §3 新增「执行中 Job 完全退出自动续跑」最小复核项。
- 待批准：数据模型 0027~0039 补登提案（批准后升版 v3.2 并同步交叉引用，见 [data-model-upgrade-proposal.md](../data-model-upgrade-proposal.md)）。
- 已知问题登记：资料库 backfill 入队钩子 TOCTOU（延迟建立、有自愈，见搭车修复三）。
