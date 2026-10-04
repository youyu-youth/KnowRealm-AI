# 07 — 多资料建课编排

**What to build:** 目标场景跑通："把这五篇论文整理到新的课程中，并生成学习计划。"Agent 给出一张计划卡（来源清单四类＋建课参数＋计划生成意图），一次批准绑定整个 Run 后自动执行：逐份导入解析（提交现有后台 job，WAITING_JOB 接续）→ 建课（课程 id 结果绑定注入后续步骤）→ 资料挂课（改归属或建共享引用）→ 最后一步产出计划草案卡（确认是 Run 之外的人工闸门）。部分资料失败不回滚已完成部分，失败步骤可单独重试。

**Blocked by:** 02 — 计划数据与生成确认链路；05 — 共享来源引用；06 — Run 等待与结果绑定

**Status:** done（2026-10-04，自动化门禁全绿，剩用户真机验收〔清单见文末〕）

- [x] 多资料建课计划卡：固定来源清单（库内资料 / 本地文档 / URL / 粘贴文本四类，全部走现有导入管线）＋建课参数＋计划生成意图；一次批准绑定（计划版本、固定对象集合；执行中重规划新增目标升回确认，完全访问档亦然）
- [x] 步骤编排：逐份导入解析（每份提交现有 job、Run 进 WAITING_JOB 自动接续）→ 建课 → 资料挂课（改归属或建共享引用，两种路径）→ 计划草案产出（Run 末步产草案卡，草案确认不算 Run 步骤）
- [x] 授权与审计：每步落 Operation 审计；总结与学习资产原有采纳审核不被批次授权跳过（测试断言）
- [x] 部分成功：单项失败不回滚已完成步骤与已建课程，Run 标记部分成功，失败步骤可单独重试
- [x] 等待与执行状态在聊天卡可见（等待资料解析 / 进行中 / 部分成功 / 完成）
- [x] 大 PDF 仍按整本一条记录处理（按章拆分属书籍拆章波次，不引入临时解析路径）
- [x] 测试：编排全链（含结果绑定链）、部分成功与单独重试、重规划升回确认、计划卡授权语义
- [x] 门禁全绿：pytest（独立 basetemp）+ ruff + pyright + OpenAPI --check + 前端测试（计划卡 / 等待状态呈现）

参考：[spec.md](../spec.md) 多资料长任务（User Stories 29~34）、M2 执行闭环段。

## 实施记录（2026-10-04 备案）

- **动作面扩展（BATCH_PLAN_ACTIONS +5）**：`ingest_local_document`（新操作 L1，本地文档来源）/ `add_text_record_to_course`（既有 TEXT_RECORD_ADD，粘贴文本来源）/ `add_shared_ref`（既有 OP_SHARED_REF_ADD，库内资料挂课路径二）/ `create_goal`（既有 OP_GOAL_CREATE，计划卡确认即 AI_INFERRED 目标的用户确认）/ `generate_plan_draft`（新操作 L2，末步计划生成意图）。`BatchPlanItemPayload` 新扁平列：path / content / library_item_id / goal_type / target_date / daily_minutes / target_score / goal_id（`str | StepOutputRef`，与 course_id 同款引用注入——建目标步骤输出注入末步）。
- **ingest_local_document**（operations/local_document_ingest.py）：document import 核心抽取共用——`create_document_ingest_rows`（只读算指纹→幂等预查→复制落 files/→事务内建行 Record+RecordFile+DOCUMENT_PARSE job+索引+回填，HTTP 上传路径改经同一 `_ingest_document_rows` 事务体，行为逐行等价）。waits_for_job=True → Run 等 DOCUMENT_PARSE。重试幂等＝同课程同 content_hash 复用既有导入；上次解析失败则新投任务并把 Record 置回 CONTENT_PROCESSING（document worker 候选按状态过滤，不重置则永不被领取——jobs 重试通道同先例）。路径来自用户对话明确提供（扩展名白名单+is_file+空文件+占用转 DOCUMENT_FILE_UNREADABLE 结构化失败；读本地路径不触红线，红线仅禁任意路径写）。
- **generate_plan_draft**（operations/plan_draft.py，操作+PLAN_DRAFT job worker 一体）：应用器提交 PLAN_DRAFT job 即成功（waits_for_job=True）；job worker 复用 `PlanGenerationService.generate`（LLM 调用不占推进事务、执行期读当前活跃 provider），完成时在写回事务落 **OP_PLAN_CONFIRM 草案确认卡**（快照同口径固化、session 归属经 operation→run 反查——弃置语义与工具路径同口径）——**草案确认是 Run 之外的人工闸门**：learning_plans 仅用户确认时写入（测试断言 Run 完成后零计划落库、ai_summaries 无 CONFIRMED、knowledge_points 零行）。无资料路径（SUGGESTIONS）落稳定失败码 PLAN_DRAFT_NO_MATERIALS（不静默成功）；LLM 未配置 / 目标不可用 / 排期不可行各有稳定码（PLAN_DRAFT_LLM_UNCONFIGURED / PLAN_DRAFT_GOAL_UNAVAILABLE / PLAN_SCHEDULE_INFEASIBLE），等待步骤翻 FAILED 后可单独重试（重试新投 job 成功产卡，测试覆盖）。
- **迁移 0039**：processing_jobs.job_type CHECK 增 'PLAN_DRAFT'（0033 先例整表重建，11 索引全量保留）+ 同目标至多一个活动草案任务部分唯一索引（json_extract goal_id 表达式索引，AGENT_RUN 同先例）。user_version 断言全库已收敛 supported_user_version()（C2 成果），仅 test_plan_editing 一处 ==38 跟进 ==39。
- **快照规则补全（plans.py）**：`_skip_item_snapshot`——创建类（item_id 空）含输出引用跳过提交期快照（引用对象在前序步骤产出、提交/确认时不存在，照常 capture 会误拒整卡：create_goal 的单 ACTIVE 快照、add_shared_ref 的 validate_add 都依赖 course_id）；执行期 worker 现固化兜底（06 既有机制）。修改类含引用维持 06 修复 3 的「剔除引用照常固化」。`_only_deferred_errors` 引用放行规则扩展：必填引用消费方（create_goal / add_text_record / add_shared_ref 的 course_id）剔除后 missing 属预期放行（06 时引用消费方全可选的前提被 07 打破）；`_plan_item_params` 放行分支直接 dict 投影（construct 实例 dump 对 str 枚举告警）；target_resolver 仅 item_id 非空项调用（创建类无既有目标可定位）。
- **ingest_library_item 重试幂等收口（06 备案落地）**：同 URL 且**同归类**的在库存活条目（ACTIVE、未软删）复用直接成功——活动抓取任务仍等待、终态失败不再等待（条目处置走资料库既有通道）；归类 / 存活不匹配不复用，交 create_web_ingest_rows 重复拒绝如实失败（模型可改用 update_library_item / add_shared_ref，与本地文档侧谓词对称）。
- **装配与 prompt**：main.py 新增 plan_draft worker（第 10 个 JobRunner）；CHAT_RUN_BINDING_GUIDANCE 扩展多资料编排段（四类来源动作、建目标、末步草案卡、失败可重试、草案确认前不声称已生成）；prompt 双轨 bump v24→v25 / v25→v26；plan_batch_operations 工具 docstring 与 args 同步新动作参数；三处既有版本断言跟进。
- **前端**：ChatBatchPlanCard 渲染新动作与授权参数（action 翻译 +4、paramPath/paramContent/paramGoal、目标参数含 target_score、goal 引用「第 N 步的输出」）；错误码翻译 +5（DOCUMENT_FILE_UNREADABLE / DATA_DIR_UNBOUND / PLAN_DRAFT_LLM_UNCONFIGURED / PLAN_DRAFT_GOAL_UNAVAILABLE / PLAN_DRAFT_NO_MATERIALS）；api-types regenerate（ProposalType +2、ProcessingJobType +1）。等待/执行/部分成功/完成状态呈现复用 06 既有（WAITING_JOB 文案 + AgentRunProgress），零新状态组件。
- **测试**（tests/test_agent_multi_source_run.py 9 用例）：编排全链（计划卡确认→建课→建目标（引用+快照跳过）→URL 导入等待唤醒→本地文档等待唤醒→粘贴/归类/共享引用→末步草案 job→草案卡落库→Run COMPLETED→用户确认草案落 ACTIVE；含授权语义三断言与整本一条记录断言）/ 部分成功不回滚（课程与首份导入保留、依赖步骤 SKIPPED）/ URL 导入重试幂等复用（同 URL 单条目）/ 本地文档解析失败重试（复用行+新投任务+置回状态）/ 草案 job 失败重试成功 / LLM 未配置稳定码 / 无资料稳定码 / 等待中追加升回计划卡（FULL_ACCESS）/ L2 末步 AUTO_APPROVE 出卡确认后 Run 内照常执行。前端计划卡组件 +1 用例（四类来源与目标参数、引用注入可见）。
- **code-review 修复（对抗性审查）**：P0＝本地文档重试重投不重置 Record 状态致永久悬挂（已修，见上）；P1×3＝URL 复用谓词缺课程/存活匹配（已修）、SUGGESTIONS 静默成功死胡同（已修，稳定失败码）、前端 target_score 不渲染（已修）；P2＝ScheduleInfeasible 落 INTERNAL_ERROR（已修同码）、源文件 Windows 占用穿透为 Run 级失败（已修结构化）、valid_course 双份（已收敛 document_import 正本 + ingest re-export）。备案不修：引用放行路径绕过 model 级校验（model_construct 同不跑 model validator，06 修复 5 同口径，执行期 payload 判别兜底＝步骤级失败）；同目标双活动 PLAN_DRAFT 撞部分唯一索引（单 worker 串行 + 跨 Run 罕见，系统性失败可诊断）。
- **遗留提请**：数据模型 v3.1 的 0039 迁移登记随既有 0030~0038 补登提案一并向用户提请（升版先提案经批准再动文档）。

## 用户真机验收清单（不代勾）

1. 配置 LLM → 对话说「把这五篇论文整理到新课程《XX》并生成学习计划」（给出 URL / 本地文档路径 / 粘贴文本，或既有资料条目）→ 出计划卡（逐项列四类来源、建课参数、目标参数、末步「生成学习计划草案」步骤）→ 一次确认。
2. 任务面板：建课成功 → 各导入步骤显示「等待任务」→ 后台解析完成后自动接续 → 粘贴/归类/共享引用瞬时完成 → 末步草案生成（等待）→ Run 完成后对话出现学习计划草案确认卡。
3. 草案确认卡确认 → 计划落库生效（课程计划 Tab 可见）；Run 完成时未确认前 DB 无 learning_plans 行。
4. 部分失败：混入一个 404 URL → 该步骤失败、Run 部分完成、新课程与已导入资料保留；失败步骤单独重试成功（条目不重复入库）。
5. 本地文档：对话给出本机 PDF 路径（Tauri 应用可见的路径）→ 整本一条记录进入新课程；文件被占用时失败提示可读。
6. 等待期间关闭页面/重启应用 → Run 对账接续不重做已完成步骤。
7. 执行中再追加新目标（完全访问档）→ 仍出计划卡需确认。
