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

## 用户真机验收（不代勾）

1. 对话（帮我批准/完全访问档）说「建一个新课程《XX》并把 https://… 这篇资料导进去」→ 计划卡/直执行后任务面板出现 Run，步骤 1 建课成功、步骤 2 导入后显示「等待任务」状态（等待原因文案「后台任务执行中，完成后将自动继续」）。
2. 等待期间关闭页面/断网重连 → Run 不受影响；后台抓取完成后回到会话，Run 自动接续并完成（导入资料真实归到新建课程，资料库可见）。
3. 抓取失败的 URL（如 404 页）→ 任务面板该步骤显示失败（AGENT_RUN_WAITING_JOB_FAILED 文案），Run 落部分完成；资料库中失败条目可走既有「重试 / 手动粘贴」通道。
4. 等待期间点「取消」→ Run 落已取消、未执行步骤停止、已提交抓取 job 不被杀（资料库可见条目与最终状态）。
5. 等待期间完全退出应用再启动 → 任务自动对账接续（已完成步骤不重做，进度面板如实呈现）。
