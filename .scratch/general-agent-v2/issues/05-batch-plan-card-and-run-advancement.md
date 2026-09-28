# 05 — 批量计划卡与 Run 推进

**What to build:** 批量整理走「计划卡＋Run」：Agent 产出结构化计划卡（逐项列出目标、参数、计划版本），整卡一次确认即批次授权；确认后创建 Run 与 PLANNED operations，由 JobRunner 内 AGENT_RUN 触发 job 逐步推进（job 是无状态触发器，Run 状态是唯一事实源）；「帮我批准」档不超 10 目标＋10 写操作自动执行、超阈值仍出计划卡；批次部分失败独立继续、依赖阻塞；冲突可等待用户处理、跨重启接续不重做已成功项；随时取消且已提交结果保留。用户可演示（Q1 场景）：十项整理任务前两项成功、第三项冲突 → 任务转等待 → 重启应用 → 处理冲突 → 继续完成剩余项，前两项不重做。

**实施约束:** 实施决策见 [spec](../spec.md) 决策 6~8、11、13（同一 run 至多一个活动触发 job；推进 worker 只认 RUNNING；唤醒仅显式动作＋原子抢占；WAITING_JOB 枚举预留不启用；计划修改版本递增重新确认；执行中新增目标超已批准集合任何档位升回确认）。

**Blocked by:** 02 三档授权与自动执行、03 修改与归档动作、04 删除与跨课迁移。

**Status:** done

- [x] 计划工具＋OP_BATCH 提案类型（OP_ 命名空间，spec 决策 1/13）：payload 携带对象集合＋逐项参数＋plan_version；确认前创建不改任何业务事实
- [x] 确认→创建 Run（auth_mode / instruction_text / proposal_id 固化）＋PLANNED operations＋AGENT_RUN 触发 job；帮我批准 ≤10 目标且 ≤10 写操作直建 run（计入已完成项、拆调用 / 重启不重置、同 operation 重试不重复计项），超阈值出计划卡；完全访问不受确认阈值限制但受固定计划约束
- [x] AGENT_RUN 推进 worker：WorkerSpec 声明式接入（无状态触发 job）；领取守卫（同 run 至多一个活动 job）；逐 operation 原子执行；每步前重检取消 / 授权 / 版本
- [x] 部分失败语义：独立项继续；依赖失败项后续置 SKIPPED；授权失效 / 取消 / 系统性故障停止推进；终态判定 COMPLETED / PARTIAL_COMPLETED / FAILED / CANCELLED
- [x] Run 等待与唤醒：冲突或需确认转 WAITING_USER（waiting_reason）；唤醒仅显式动作（继续指令 / 失败项重试 / 冲突项解决 / 取消）＋原子抢占；会话消息流注入本会话非终态 run 摘要（提示非指令）
- [x] 取消：持久化取消端点（cancel_requested），推进中每步检查，取消后不新增动作、已提交结果保留
- [x] 重启恢复：启动扫描 RUNNING 且无活动触发 job 的 run 重投触发（recover_interrupted 先例）；不重做已成功项
- [x] 计划修改：版本递增＋重新确认；执行中重规划新增目标超已批准集合 → 升回确认（完全访问亦然）
- [x] 前端计划卡（整卡确认、逐项参数、版本变化重新确认）＋Run 进度呈现（执行中 / 等待 / 部分完成、逐项结果、失败项重试与继续按钮）＋操作历史分区 run 展开接真
- [x] 新增错误码登记＋zh/en 双语同步；api-types regenerate；runs 子包零领域 import 的 AST 防线延续
- [x] 门禁全套过（后端 pytest / ruff / pyright、前端 vitest / lint / build、OpenAPI --check）

**实施备注：**

- 落实位：`agent/runs/plans.py`（计划层＝提交入口 `submit_batch_plan`＋OP_BATCH 应用器）、`agent/runs/worker.py`（AGENT_RUN 推进）、`agent/runs/service.py`（RunControlService 唤醒与取消）、`agent/tools/plan_batch_operations.py`（薄工具，恒挂载）、迁移 0033（job_type 放开 AGENT_RUN＋`json_extract(input_json,'$.run_id')` 部分唯一索引＝同 run 至多一个活动触发 job 的存储层保证）。
- 计划载荷的 `plan_version / auth_mode / instruction_text` 由提交路径注入（模型只提供 items）：确认路径的 Run 因此能固化成完整授权依据，应用器无需读 settings。
- 幂等口径（直执行与确认路径同源）：已覆盖目标（PLANNED / SUCCEEDED 的操作目标）不重复建操作、不重做已成功项、不重复计数；混合提交只落待执行子批，子批内依赖跳过被剔除项时经 `preset_dependencies` 挂到既有 operation 上（依赖语义不丢）。失败 / 跳过项不算覆盖——重新预览授权后允许为该目标新建操作（冲突解决的唯一路径：重试沿用旧快照仍会失效，spec 决策 12 的安全属性）。
- 固定计划约束的档位边界：执行中（存在活跃 Run）新增目标一律升回确认，完全访问档亦然（spec 用户故事 23）；等待态 Run 只接受显式唤醒，故经工具追加也转计划卡（确认即显式动作并唤醒）。帮我批准档阈值只管「同一任务直接业务目标数与写操作数 ≤10」的自动建单/追加（计入已建与已完成项、拆调用与重启不重置）。
- 确认路径的两处稳健性：版本单调递增（多张未确认计划卡可能拿到同一提交时版本，确认时以 Run 当前版本为下界，版本是「已批准集合」的组成部分不能回退）；无显式 target 时回落到本会话活跃 Run（同一会话两张计划卡先后确认延展同一 Run，而不是各建一个 Run 重复执行同一批目标）。
- 取消守卫只开给未收尾任务（进行中 / 等待用户）：部分完成与失败任务拒绝取消（取消不冒充撤销），失败项重试另有端点并会重开推进（`finished_at` 清空）。
- 终态判定按目标取最新一次操作结局：重试 / 重新授权产生的成功操作取代旧失败行，run 落 COMPLETED；旧失败行保留为逐项历史。
- 操作推进顺序由计划项索引收敛（同一批提交的 created_at 相同，时间序会打平），`order_run_operations` 是呈现与推进共用的唯一口径。
- 会话消息流注入：`_active_run_summaries` 读本会话未结束任务（上限 3 条）投影为 `ActiveRunSummary`，`format_active_run_summary` 生成「未结束任务摘要（仅提示，不是指令、不构成任何授权…）」块，追加位置与页面提示同段。
- AST 防线 `allowed_domains` 增加 `jobs`：WorkerSpec 与触发 job 是执行基础设施（全部 worker 共用），非业务领域；course / record / capture / quiz 等业务领域依旧禁止，并已把 plans / worker 加入受检模块清单。
- 前端：`AgentRunProgress` 为对话计划卡、会话任务面板与设置页操作历史共用的任务进度组件（推进中 2s 轮询、终态停；快照失效步骤给出「重新整理该项」提示而非只留重试按钮）；run 查询键与呈现助手（状态色 / 时间格式 / 可重试判定）收敛到 `features/settings/api/operationHistory.ts`，`settingsKeys` 的 run 键删除以免同一资源两份缓存。
- prompt bump `chat-library-scope-v15` / `chat-research-scope-v16`（新增批量整理指引＋工具可见面变化）；`build_context_messages` 的 SYSTEM 末尾新增批量指引与任务摘要两段，三处逐字断言与工具可见矩阵同步更新。
- code-review 双轴结论（Standards / Spec）：采纳 spec 轴 3 项实质问题（混合批重复建操作、完全访问档固定计划约束、等待态追加不唤醒）与 2 项稳健性（版本单调、取消守卫），采纳 standards 轴 3 项（重复呈现助手收敛、未结束任务查询共用、`[0]/[1]/[2]` 位置语义改聚合类型）＋删除冗余迁移版本断言（新迁移零断言同步）；judgement call 未采纳两项并说明：OP_BATCH 载荷在前端手写 TS 形状（后端载荷为自由 dict，无生成对应物，与 `AgentOperationOut.payload` 同口径）、run 查询全前缀失效（计划卡的新 Run 事先不可知，前缀失效是既有先例）。
- review 追加修复（P1：确认卡未完整展示授权参数）：归类目标显示课程名（复用 `useCourseNames` 共用缓存；查不到回落 id 缩写 `#xxxxxxxx`，不造假名）；多依赖完整列出（i18next `list(style: narrow)` 格式化，zh「1、3」/ en「1, 3」），不再只显示首项；zh/en 键同步，回归用例覆盖「已知课程名 / 未知课程回落 id / 多依赖」三条路径。授权参数因此始终可见——确认卡批准的对象与参数范围与实际执行一致。
- review 追加修复（P1：损坏计划被静默降级后继续执行）：`parse_plan_out` 的「坏值降级为空计划」原是推进与查询共用口径——损坏计划会让推进顺序与依赖判定静默失效（`.get(operation.id, [])` 恒空 → 依赖阻塞恒不触发），却仍继续执行持久化 operations。修复=拆两个口径：`require_plan_out`（执行 / 写入，坏值抛 `PlanCorruptError`）与 `parse_plan_out`（读取 / 展示，沿用降级、不炸查询）。执行路径（worker）在排序与依赖判定前严格读计划，损坏即整任务停止：`failure_code` 落稳定错误码 **`AGENT_RUN_PLAN_INVALID`**（job 记码 + 日志 `agent_run_plan_corrupt`）、Run FAILED、未执行项 SKIPPED、零业务事实；取消检查提前到严格读之前（取消不依赖计划，用户动作不被误报为任务失败）。写路径同样拒绝：`append_plan_operations` 损坏即 `AGENT_RUN_PLAN_INVALID`（409，确认事务整体回滚——版本不递增、不唤醒、不新增操作），提交入口对活跃 Run 计划损坏返回结构化拒绝（不落新计划卡、不建空 Run）。`order_run_operations` / `_blocked_by` 保持读取口径并在 docstring 标注边界（前端重试失败无错误呈现，重复拦截反而静默）。错误码登记 + zh/en 同步；回归用例 4 项（旧代码下 3 项失败实证：确认卡在坏计划上曾静默 APPLIED），后端全量 873 绿。
- review 追加修复（P1：同一目标改参数被静默丢弃）：覆盖键原只有 (动作, 目标)——已批准「归类到课程 A」后再批准 v2「归类到课程 B」时，v2 项在确认时被当作「已覆盖」剔除（版本递增、`item_count=0`，操作载荷仍是 A；AUTO 档工具路径更直接返回 `added_item_count=0`），违反 spec 决策 13「已批准集合＝对象集合＋参数＋版本」与用户故事 23「改参数后重新确认」。修复=**活步骤口径**：`covered_targets` 返回每个 (动作, 目标) 的活步骤（待执行优先、否则最近一次已成功，含载荷参数）；`pending_plan_batch` 三分——无活步骤＝新建、参数一致＝已覆盖（preset 依赖映射不变）、参数变更＝待执行就地改写（`replaced_operation_ids`：同一 operation 身份与计划位置，依赖它的步骤不受影响）/ 已成功作为新步骤追加（不改写已执行的历史行）；`batch_route` 的 `ALREADY_PLANNED` 判定改为「参数一致的覆盖」——参数变更按既有档位与固定计划约束处理（请求批准 / 固定计划 / 等待态 → 计划卡重新确认；帮我批准阈值内 → 直执行就地改写）。就地改写同步更新 operation 的载荷 / 快照 / 授权依据 / 审批引用与计划条目参数，返回值计数含改写项（回执如实）。回归用例 4 项（旧代码下 3 项失败实证：确认后载荷仍为课程 A、AUTO 路径 `added_item_count=0`），后端全量 877 绿。
- review 追加修复（P1：显式继续 / 重试丢触发竞态）：`enqueue_trigger` 的守卫把 PENDING/RUNNING 都视为有效消费者——显式唤醒若落在「推进事务已提交（Run 落 WAITING_USER / PARTIAL_COMPLETED）、旧 job 未收尾」的窗口内，投递被静默跳过；旧 job 随后在 `writeback` 收尾且不检查 Run 状态，终局＝Run=RUNNING、活动触发 0，只能等重启（main.py lifespan 恢复）或主循环异常恢复。修复=**触发交接**：`writeback` 同一事务内把 job 落 SUCCEEDED 后显式 flush，再读 Run——仍 RUNNING 即补投触发（日志 `agent_run_trigger_handoff`）；等待态 / 终态不补投（保持「等待只由显式动作唤醒」不变量）。选点理由：补投必须在 job 离开 RUNNING 之后（否则守卫再次跳过），writeback 事务正是这个唯一提交点、同事务＝原子；判定信号直接用 Run 状态（worker 停止推进后仍 RUNNING 只可能是显式动作在飞行中重开），免迁移；覆盖全部四个投递点（继续 / 重试 / 直执行追加 / 计划卡确认）；不会成环（补投推进后要么落定一步、要么把 Run 结算为终态）。回归用例 3 项（旧代码下 2 项失败实证：收尾后仅剩 SUCCEEDED、无新 PENDING＝悬挂复现；第 3 项为负向对照，钉住等待态与终态不产生多余触发），后端全量 880 绿。
- review 追加修复（P1：10 项阈值在首批完成后重置）：阈值计数原以**活跃 Run** 为界（`count_run_operations(active.id)`，无活跃 Run 时按 0 起算）——首批 6 项完成（Run 落终态）后再提交 6 项，`find_active_run` 看不到已结束的 Run → 新提交按全新计划放行并新建第二个自动 Run，累计 12 项仍未出计划卡；违反 spec 决策 11「计入已完成项，拆调用 / 分段 / 重启不重置」。修复=**会话累计口径**：新增 `count_session_operations`（本会话全部 Run 的 operation 行数——join agent_runs by session_id，含终态 Run 与已完成 / 失败 / 跳过项；单步操作 run_id 空不属批量计划、不计入），提交入口与 `batch_route` 的「全新计划」分支都先扣已用额度再判（`session_operation_count + len(items) > 10` → 计划卡）；`count_run_operations` 随之删除。计数仍按会话不按全局（另一会话不背前一会话的额度），重试沿用原行不重复计项。回归用例 3 项（旧代码下 2 项失败实证：首批完成后再提交 6 项得到新 Run、分段 6+4+2 的第三段得到新 Run；第 3 项为负向对照，钉住跨会话不串账），后端全量 883 绿。

**用户真机验收（单列，不代勾）：**

- 真实模型跑通 Q1 十项场景：冲突 → 等待 → 重启应用 → 处理冲突 → 继续完成，已成功项零重复。
- 帮我批准档批量归类 10 条以内自动执行＋批次回执；构造超阈值场景仍出计划卡。
- 批量执行中途取消：不再新增动作、已完成项在操作历史如实呈现。
