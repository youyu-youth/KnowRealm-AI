# 06 — Run 等待与结果绑定

**What to build:** Run 状态机补齐长任务两块拼图。其一：步骤提交后台 job 后 Run 进入 WAITING_JOB 等待，job 完成后自动接续推进（另设启动对账兜底——重启后扫描等待中的 Run、核对所等待 job 的终态决定续跑 / 失败 / 部分成功）；其二：前一步骤的输出（如新建课程的 id）可绑定为后续步骤的参数。以最小场景（单资料导入 → 建课）验证机制。

**Blocked by:** None — can start immediately（与 M1 并行）

**Status:** done（2026-10-01；代码与自动化门禁完结，剩用户真机验收〔清单见下〕）

- [x] Run 计划契约扩展：步骤输出按字段路径引用（如新建课程 id）注入后续步骤参数；依赖仍只表达先后与成功
- [x] WAITING_JOB 激活：步骤提交 job 后 Run 置 WAITING_JOB（该状态此前仅预留零写入者）；job 完成主动触发 Run 推进（与现有 AGENT_RUN 无状态触发 job 联动）
- [x] 启动对账兜底：扫描 WAITING_JOB 的 Run、核对等待 job 终态决定续 / 败 / 部分成功（掌握度 consumer 自愈同模式）；对账幂等
- [x] 等待中取消：未提交步骤停止、已提交 job 保留回执；断开 SSE 不当作业务取消（沿用二阶段语义）
- [x] 最小验证场景：单资料导入 → 建课 Run 全链（等待 → 唤醒 → 结果绑定 → 完成），聊天卡呈现等待状态
- [x] 测试：job 终态注入（成功 / 失败 / 部分失败）、重启重放对账（WAITING_JOB 恢复正确分流、已完成步骤不重做）、等待中取消、结果绑定注入正确性
- [x] 门禁全绿：pytest（独立 basetemp）+ ruff + pyright + OpenAPI --check

参考：[spec.md](../spec.md) M2 执行闭环段（User Stories 30~32 部分）、多资料长任务前置机制。

## 实施记录

- **迁移 0038**：`agent_runs.waiting_job_id`（可空列；WAITING_JOB 的核对对象，唤醒与终态清列）；RunStatus.WAITING_JOB 从预留转正（零 CHECK 变更）。user_version 断言 37→38（test_plan_editing）。
- **计划契约扩展（结果绑定）**：`StepOutputRef(step, field)` 点路径引用；BatchPlanItemPayload 的 item_id 转可选（创建类步骤无既有目标）＋course_id 允许引用＋新增 name/learning_context/education_stage/depth/description/url 扁平列；**引用即依赖**（payload 结构校验自动并入 depends_on，越界引用提交时结构化拒绝）；重复目标检查只对 item_id 非空项。BatchPlanAction +CREATE_COURSE/INGEST_LIBRARY_ITEM（映射进 plans.BATCH_PLAN_ACTIONS——create_course 复用既有注册项零新代码）。提交期判别校验剔除引用字段（引用值执行时才有；引用字段必填的动作保守拒绝）；引用项快照跳过（state 空），执行时解析引用后**现固化**快照＋回填事实参数到 payload_json（重试与普通步骤同口径）；目标定位（target_resolver）对引用字段同样剔除后判别。
- **新动作 `ingest_library_item`**（operations/library_item_ingest.py，OP_ 通配零迁移）：L1 创建类、无独立薄工具（仅计划内步骤，07 多资料 Run 地基）；应用器复用 `create_web_ingest_rows` 事务内核心（Record+条目+WEB_FETCH job 同事务）；result 含 awaited_job_id。**重试边界备案（07 收口）**：抓取失败后条目已在库（同 URL 内容指纹），步骤重试命中重复拒绝——失败条目走资料库既有重试/手动粘贴通道。
- **OperationSpec +waits_for_job 声明字段**：声明该动作的应用器提交后台 job 且 result 含 awaited_job_id。
- **WAITING_JOB 激活与唤醒**（worker.py）：推进成功落定后 spec.waits_for_job → Run 置 WAITING_JOB＋waiting_job_id（步骤提交即成功，result 留回执）；**运行期核对＝触发 job 的领取闸门**——validate_claim 对等待 Run 调 resolve_waiting 核对 job 终态：未终态 WaitingClaim（不消费触发、0.25s 轮询再核）＝「job 完成主动触发」的载体；SUCCEEDED 唤醒（清等待字段）；FAILED/CANCELLED/缺失 → 等待步骤翻 FAILED（AGENT_RUN_WAITING_JOB_FAILED，attempts 留痕）后唤醒，SKIPPED/终态判定交还推进循环既有口径＝零特判。writeback 对 WAITING_JOB 补投触发（等待核对轮询）；**取消竞态兜底**：核对读 cancel_requested 即按取消收尾＋触发 CancelClaim（不复活已取消 Run）。**启动对账＝recover 扫描 WAITING_JOB 重投触发**（幂等：活动触发守卫＋0033 部分唯一索引），与运行期核对共用 resolve_waiting（掌握度 consumer 自愈同模式）。
- **等待中取消**（service.py）：守卫与就地收尾分支扩 WAITING_JOB——未执行步骤置 CANCELLED、已提交 WEB_FETCH job 保留回执（不杀）、PENDING 触发静默作废；断开 SSE/关页面不是业务取消（推进独立于连接）。retry/resume 唤醒 UPDATE 补 waiting_job_id=None（口径对称防御）。
- **提示词**：CHAT_RUN_BINDING_GUIDANCE（创建类步骤＋引用语法＋等待如实转述）；prompt chat-library-scope-v24 / chat-research-scope-v25；plan_batch_operations 工具 docstring 与宽松参数列同步。
- **前端**：零组件改动——runStatus.WAITING_JOB 文案既有预留，waiting_reason 渲染既有机制；errors 两码（AGENT_RUN_WAITING_JOB_PENDING/FAILED）＋action.ingest_library_item zh/en；api-types regenerate（ProposalType +1）。
- **测试**（tests/test_agent_run_waiting.py 15 用例）：绑定注入回填与真实归类／计划卡确认路径携带等待步骤／越界引用拒绝／引用不可解析防御 SKIPPED／缺必填结构化拒绝（含模型级 detail 转述）／job 成功唤醒完成不重做／未终态持续等待不消费触发／job 失败翻 FAILED+可重试／两份导入一成一败 PARTIAL（唤醒后再等待链）／取消竞态兜底／重启对账续跑+失败两分支幂等／等待取消保留 job／job 缺失保守失败／resolve_waiting 直连口径。既有跟进：chat_streaming 指引断言×3+import+版本断言、research 版本断言、plan_editing 版本断言。
- **门禁**：后端全量 1054 绿＋ruff＋pyright 0 错＋OpenAPI regenerate/--check（ProposalType 枚举唯一实质变化）；前端 i18n 防线＋tsc 0＋Run 卡相关 12 用例绿。
- **双轴 review 采纳修复**：唤醒取消竞态兜底（validate_claim 后置状态检查）、retry 清列对称、部分失败链测试、重启败分支测试、注册项重试边界备案、工具 title 描述对齐。不采纳（备案）：concrete 参数剔除三处收拢（形状同语义异）、工具 Args 手抄（宽松声明先例）。
- **P1 修复（10-02，GPT 审查实锤）**：等待领取路径违反 processing_jobs.waiting_reason 的 0004 CHECK（值域仅 audio 三态 CONSENT_REQUIRED/ASR_KEY_REQUIRED/OFFLINE）——validate_claim 返回 WaitingClaim("waiting_job") 后 JobRunner.\_mark_waiting 写库即 IntegrityError，等待期每轮轮询反复错误恢复；既有测试直接调 validate_claim 绕过了该写库路径故未拦截。修复＝WorkerSpec 加 write_waiting_reason 开关（默认 True、audio 等现有 worker 行为零变化），AGENT_RUN spec 置 False 只取「不消费触发」协议语义——Agent 等待语义由 agent_runs.waiting_reason=AGENT_RUN_WAITING_JOB_PENDING 承载，processing_jobs 侧该列对 AGENT_RUN job 无消费者（读路径 ProcessingJobOut 枚举值域亦不含）。新增回归测试走完整 JobRunner.claim_one（真实迁移库 CHECK 生效），对抗性验证：撤开关即红（IntegrityError 复现）、带开关绿；全量 1061 绿＋ruff＋pyright 0 错。
- **P1 修复 2（10-02，GPT 审查实锤）**：追加批次的输出引用错绑旧步骤——append_plan_operations 步骤编号换算全局（index=base_index+n、depends_on 经 dependency_ids 映射 operation id），但 params 里的 StepOutputRef.step 保留本批局部索引原样落库，解析器 \_resolve_step_refs 按 plan 全局编号取结果：等待期批准第二批「建课 B＋导入 URL2 引用本批第 0 步」时 step=0 绑到第一批建课 A（URL2 归 A、B 留空；实测复现同）。修复＝构造「原始提交索引 → 全局编号」映射（preset=既有条目编号／replaced=被改写条目编号／新建=base_index+序数，三类覆盖全部索引；结构校验保证引用只指本批更早项故映射必全），\_\_remap_step_refs 在写入操作载荷与计划投影前统一换算。新增两批引用回归测试（URL2 归课程 B 断言＋执行回填后不残留引用对象），对抗性验证：撤重映射即红（URL2 错绑课程 A id 复现）；全量 1062 绿＋ruff＋pyright 0 错。
- **P1 修复 3（10-02，GPT 审查实锤）**：含引用的修改类步骤绕过对象版本检查且未固化有效快照——capture/verify 对含引用项整体跳过（plans.py 旧条件），即使目标 item 既有（引用的只是 course_id 参数字段，定位不依赖它）；worker 现固化兜底判 `snapshot_json is None` 而落库恒 "{}"（死代码），stale 检查经 elif 被引用分支短路：批准后用户改条目标题，Agent 直接覆盖并报完成；空快照 Undo 即 OPERATION_UNDO_CONFLICT（工单宣称的「现固化快照」未实现）。修复＝①capture_plan_snapshots 含引用时剔除引用字段照常抓目标快照（创建类 capture_state 为 None 天然无快照）；②verify_plan_snapshots 同口径重验；③worker 引用分支：空快照（None 或 "{}"）现固化兜底（服务存量数据），回填后与普通步骤同口径走 stale 检查（elif 改统一 if）。连带修复既有潜伏笔误：stale 分支 error_code=OPERATION_SNAPSHOT_STALE 为未导入裸名（原 elif 分支从未被测试执行故未炸，触发即 NameError 炸推进循环）。新增两测试：中途改条目标题→步骤 FAILED(OPERATION_SNAPSHOT_STALE)＋用户值不被覆盖（撤修复即 Run COMPLETED 直接覆盖复现）；正常执行→快照完整固化＋UndoService.undo_operation 恢复 before 值。全量 1063 绿（test_library 单项失败系全量运行中途对抗验证切码的伪失败，单跑绿）＋ruff＋pyright 0 错。
- **P2 修复 4（10-02，GPT 审查实锤）**：等待中的 Run 阻塞其他独立 Run——find_candidate 按 created_at 取最早 PENDING 触发，等待触发 WaitingClaim 原样保留（PENDING、next_run_at 空、零字段变更）恒居队头，后续 Run 的触发领取不到：Run A 等待抓取期间独立会话的 Run B 恒 PLANNED 不被推进（等待全程饿死，慢抓取/重试时分钟级）。唤醒链无 job 完成侧联动投递（enqueue_trigger 全在 agent/runs 域内），不能在候选层排除等待触发（断唤醒）；修复＝validate_claim 等待分支对触发 job 置短退避 next_run_at=now+0.25s（WAITING_RECHECK_BACKOFF_SECONDS，与 poll_interval 同节奏）让出下一调度窗口，核对频率≈0.5s/次、唤醒延迟增量≤一拍，audio 的 WaitingClaim 语义零影响（退避在 AGENT_RUN 侧 validate_claim 内、非 runner 骨架）。新增调度 fairness 测试（A 等待期间 B 经 process_one 完整推进 COMPLETED、A 不受影响、退避留痕），对抗性验证：撤退避即红（next_run_at=None＋B 不被推进）；既有 claim_waiting 辅助改 ORM 加载与生产同形态（SQL Row 不可赋值暴露）。全量 1065 绿＋ruff＋pyright 0 错。
- **P2 修复 5（10-04，GPT 审查实锤）**：仅通过引用归类资料的合法计划被拒——「建课 → 既有资料归到新课」只传 item_id＋course_id 引用时，\_plan\_item_params 剔除引用字段后 model_validate 撞上 update 的「至少一个修改字段」model 级校验返回 PROPOSAL_PAYLOAD_INVALID（工单备案「引用消费方 course_id 均可选＝保守拒绝」的论断漏了存在性条件校验：引用被剔除后等同零修改字段）。修复＝新增 \_concrete_payload helper 收拢四处剔除点（\_plan_item_params 判别／capture 快照／verify 重验／target_resolver 定位——推翻工单备案「concrete 剔除不收拢」，第四处出现后同形状语义已实质收拢）：仅剩 model 级条件校验失败（errors 全无字段路径）且存在引用字段时放行（model_construct 构造，字段级校验已过；引用即修改意图），字段级失败照常拒绝。新增纯引用归类回归测试（提交 ok→COMPLETED→条目真实归入新课→快照完整固化），对抗性验证：撤放行即红（提交被拒无 run 键）。全量 1066 绿＋ruff＋pyright 0 错。

## 用户真机验收（不代勾）

1. 对话（帮我批准/完全访问档）说「建一个新课程《XX》并把 https://… 这篇资料导进去」→ 计划卡/直执行后任务面板出现 Run，步骤 1 建课成功、步骤 2 导入后显示「等待任务」状态（等待原因文案「后台任务执行中，完成后将自动继续」）。
2. 等待期间关闭页面/断网重连 → Run 不受影响；后台抓取完成后回到会话，Run 自动接续并完成（导入资料真实归到新建课程，资料库可见）。
3. 抓取失败的 URL（如 404 页）→ 任务面板该步骤显示失败（AGENT_RUN_WAITING_JOB_FAILED 文案），Run 落部分完成；资料库中失败条目可走既有「重试 / 手动粘贴」通道。
4. 等待期间点「取消」→ Run 落已取消、未执行步骤停止、已提交抓取 job 不被杀（资料库可见条目与最终状态）。
5. 等待期间完全退出应用再启动 → 任务自动对账接续（已完成步骤不重做，进度面板如实呈现）。
