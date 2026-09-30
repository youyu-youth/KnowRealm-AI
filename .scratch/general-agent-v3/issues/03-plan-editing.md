# 03 — 计划编辑、完成与重生成

**What to build:** 用户对计划获得精细控制：草案确认卡升级为可编辑（改日期、改时长、删项、排序）；落库后的计划项可就地编辑、勾选完成或跳过（每次改动有操作审计）；目标或偏好变化时可要求重新生成——新版本生效、旧版本只读保留，用户手动锁定过的项原样带入不被 AI 重排。

**Blocked by:** 02 — 计划数据与生成确认链路

**Status:** done

- [x] 草案确认卡可编辑：改日期 / 改时长 / 删项 / 排序四操作，确认后按编辑结果落库 ✅ confirm 端点可选 body.payload 携带编辑载荷（`register_draft_edit_validator` 类型专属校验，仅 OP_PLAN_CONFIRM 受理）；前端 PlanDraftEditor 四操作 + 确认携带编辑载荷 + 删光守卫；排期重算比对拆为提交时钩子（确认时不重跑，用户编辑不再要求与确定性铺排逐位一致）
- [x] 项级编辑 Service：就地修改当前版本计划项（日期 / 时长 / 内容）、完成、跳过；每次改动落 Operation 审计；用户手动编辑过的项由 Service 置 user_locked ✅ `PlanItemService` update/complete/skip 核心（HTTP 入口含事务+USER_MANUAL 审计，Agent 应用器复用核心）；页面路径经 `learning_plan/audit.py` 反转钩子落 agent_operations（trigger=USER_MANUAL，USER_UNDO 先例）
- [x] 重生成 Service：新 plan_version、旧版 SUPERSEDED 只读保留、user_locked 项原样带入新版本；历史版本可只读查询（含进度记录） ✅ `regenerate_core`（旧版 SUPERSEDED + effective_to + 新版本 ACTIVE）+ `pack_schedule_with_fixed` 锁定容量感知铺排 + GET /plans 版本列表与版本详情（任意版本只读含进度）
- [x] 完成语义边界：勾选完成不产 learning_event、不直接修改 Concept Mastery（测试断言两表零写入）；学习时长统计由计划项完成时间戳单独承载（今日统计带口径，页面呈现随 04） ✅ 迁移 0036 `completed_at`（DONE 写入 / SKIPPED 清空）；Service / 页面路由 / Agent L1 / AUTO_APPROVE 四路径零写入断言
- [x] Agent 工具：update_plan_item、complete_plan_item（写，确认卡＋授权＋审计）、regenerate_plan（写，确认卡、产新版本） ✅ OP_PLAN_ITEM_UPDATE / OP_PLAN_ITEM_COMPLETE（L1）+ OP_PLAN_REGENERATE（L2）；regenerate_plan 单工具确定性组装换代载荷（锁定项原样复制 + LLM 草案容量感知铺排，不经模型转述）；skip 无 Agent 工具（票面工具清单字面，页面路由承载）
- [x] 测试：编辑 / 完成 / 跳过 / 重生成语义（版本链、user_locked 保留、SUPERSEDED 只读）、learning_events 与 user_concept_mastery 零写入断言、Agent 工具确认与授权行为 ✅ tests/test_plan_editing.py 16 项 + 确认卡编辑交互前端测试
- [x] 门禁全绿：pytest（独立 basetemp）+ ruff + pyright + OpenAPI --check + 前端测试（草案卡编辑交互） ✅ 后端 992+ 全绿、ruff/pyright 0、OpenAPI 与 api-types 同步、前端确认卡 45 绿（全量仅 TodoPanel/CourseBrain 两处已知并发抖动，单跑绿）

参考：[spec.md](../spec.md) 计划执行与调整（User Stories 12~17）、生成确认与版本语义段。

## 实施备注（关键决策与偏差备案）

1. **确认卡可编辑 = confirm 携带编辑载荷**：`ProposalService.confirm(proposal_id, edited_payload?)` 扩展——编辑校验（类型专属校验器）通过后在确认事务内更新提案行再应用，确认卡所见与落库所写同一份；模型原始草案不另行留存（提案是待确认载体非审计事实源，operation 行记录实际确认内容）。编辑边界：schema + 日期 ∈ [今天, 目标期限] + record/concept 可见性；**每日预算一致性不强制**（显式编辑即用户主权）。编辑校验失败（含 PROPOSAL_EDIT_NOT_SUPPORTED）原样透出、提案保持 PENDING 可修正后再确认，不落 FAILED。
2. **排期重算比对拆为提交时钩子**：registry 新增 `submission_validator`（提交与直执行两路执法、确认时不重跑）——02 的模型转述漂移防线行为不变（`test_confirm_plan_submit_rejections` 全绿），用户编辑后的日期不再被确定性铺排比对误伤；确认前目标态变化仍由快照比对覆盖。
3. **页面直改审计的方向反转**：fastapi.md 约束 agent 是下游模块，learning_plan 路由不能直接 import agent 执行机制——`learning_plan/audit.py` 定义钩子、agent 侧 plan_item 操作模块注册 recorder（register_applier 同模式反转），trigger=`USER_MANUAL`（USER_UNDO 先例），action 与 Agent 路径同名（update_plan_item / complete_plan_item / skip_plan_item），页面 / Agent 两路径同一 agent_operations 事实源；每次改动含载荷与执行后投影。
4. **重生成 = 单写工具**（L2 确认卡）：工具读取当前版本 user_locked 项（原样复制，按原阶段分组在前）→ LLM 为其余部分出新草案（生成提示含锁定项清单防重复安排）→ `pack_schedule_with_fixed` 在「每日预算 − 锁定占用」剩余容量内铺排（脚本优先）→ 组装载荷提交确认卡。**载荷不经模型转述**：无 02 的转述漂移防线需求，也无正文 JSON 风险。快照含目标约束字段 + 当前 ACTIVE 计划身份（确认前被并发处理 → 失效重生成）。
5. **锁定项「原样带入」边界**：安排字段（内容 / 日期 / 时长 / 类型 / 引用 / 理由 / 阶段标题）照载荷原样；**状态归 PENDING、completed_at 清空**——进度事实留在 SUPERSEDED 版本只读保留（票面「历史版本可只读查询（含进度记录）」），且避免完成时间戳跨版本重复计数（04 今日统计以 ACTIVE 版本为口径）。`estimated_minutes or 30` / reason 占位是字段损坏的防御兜底（正常不可达：确认落库恒写值）。
6. **完成语义**：complete = 置 DONE + completed_at（首次时间戳幂等保留；跳过后完成补写）；skip = 置 SKIPPED + 清时间戳；无状态机拒绝（勾选语义直白）。完成 / 跳过不产 learning_event、不动 user_concept_mastery、不进学习证据链；学习时长统计由 completed_at 单独承载（04 消费）。
7. **HTTP 端点**（04 计划 Tab 消费面随票落地，避免 04 混入后端）：`GET /api/courses/{cid}/plans?goal_id=`（版本列表，新版本在前）+ `GET .../plans/{pid}`（版本详情，任意版本只读含进度）+ `PATCH .../plans/{pid}/items/{iid}` / `POST .../complete` / `.../skip`（页面直改：归属链 + ACTIVE 版本 + USER_MANUAL 审计全在 Service，薄路由）。编辑 / 完成仅对 ACTIVE 版本开放（PLAN_VERSION_NOT_ACTIVE 409）。
8. **Agent 工具面**：update_plan_item / complete_plan_item（L1，AUTO_APPROVE 直执行）+ regenerate_plan（L2，AUTO_APPROVE 仍落卡）；三者 undo_reason 声明不可撤销（完成是事实记录、编辑可再改回、换代有历史版本）。挂载矩阵 7 处 + prompt 双轨 bump（chat-library-scope-v21 / chat-research-scope-v22）+ CHAT_PLAN_GUIDANCE 计划调整指引。
9. **错误码**：PLAN_NOT_FOUND / PLAN_ITEM_NOT_FOUND / PLAN_VERSION_NOT_ACTIVE / PLAN_REGENERATE_NO_MATERIALS / PROPOSAL_EDIT_NOT_SUPPORTED，zh/en + 后端错误码清单已登记。
10. **双轴 code-review 修复备案**：①路由层编排事务（fastapi.md 薄路由违规）→ 下沉 `PlanItemService.update/complete/skip`（事务 + 审计 + 装载链），路由一行直达；②编辑校验漏引用可见性（直调 API 改坏 record_id 会落 FAILED 而非保持 PENDING）→ `validate_plan_draft_edit` 补 require_records/concepts_visible；③页面 PATCH 显式 null 撞 NOT NULL 500 → update_core 与审计载荷统一滤 None（Agent 工具面滤 None 同口径）；④PROPOSAL_EDIT_NOT_SUPPORTED 未走透传机制（曾落 FAILED）→ 与编辑校验失败同口径；补三回归测试（不支持类型 / 引用越界保持 PENDING / 显式 null）。重复收敛：PLAN_ITEM_TYPE_KEYS 前端抽 `planItemTypes.ts` 共享、`PlanItemUpdatePayload` 继承领域 `PlanItemUpdate`（保留 item_id 感知的「至少一个修改字段」验证器）、`require_active_goal` 收敛四处目标装载。
11. **备案不修项**：PlanDraftEditor 的 Record<string, unknown> 手工收窄（草案载荷是自由 JSON，无生成类型可用）；锁定阶段前置使新版本展示顺序 = 锁定组在前 + 新草案阶段在后（测试固化该设计）；迁移 0036（learning_plan_items.completed_at）随数据模型 v3.1 的 0030~0033 补登提案一并登记（02 备案，待用户批准后动文档）。
12. **重生成 LLM 窗口竞态修复（GPT 审查 P1，09-30）**：载荷派生自 LLM 前读取的状态（目标约束 / ACTIVE 版本 / 锁定项），而授权快照原在提交时（LLM 后）捕获——窗口内锁定新项 / 编辑锁定项 / 目标与版本变更均不被感知，旧载荷可绑定新快照通过确认、静默丢失锁定编辑（违 spec 用户故事 15）；且项级写入只维护 item.updated_at 不触计划头身份字段，快照对项级变更全程不可见（连确认前窗口也漏）。修复双件：① 快照增 `locked_items` 版本戳（item_id + updated_at，项级编辑 / 完成 / 跳过均 bump item.updated_at → 可感）；② `submit_operation` / 直执行两路新增 `basis_json` 派生基线参数——工具 LLM 前经 `build_plan_regenerate_snapshot` 固化快照，提交事务内与当前态比对，偏离即 OPERATION_SNAPSHOT_STALE 拒绝落提案（直执行 FAILED 行快照存基线 → 手动重试重验恒失效、不重放旧载荷）；相等时提案快照即基线，确认比对口径覆盖「派生 → 确认」全窗口。快照 schema 不在 OpenAPI 契约面（提案 snapshot 为泛型 dict）→ 契约零漂移、前端零改动。回归测试 ×3：窗口锁定变异拒绝落提案 / 确认前编辑锁定项确认失效 / FULL_ACCESS 直执行 + 手动重试恒失效（后端 997 绿）。
13. **重生成载荷阶段上限误杀修复（GPT 审查 P1，09-30）**：`PlanRegenerateCore.phases` 原上限 9，但重生成载荷＝「锁定保留组（按原阶段分组，原计划合法 ≤8 阶段、锁定项可分布在每个阶段）＋新草案阶段（≤8）」直接拼接——5+5=10＞9 构造时抛 ValidationError 被工具 `except Exception` 吞成泛化 PLAN_REGENERATE_FAILED，合法多阶段锁定计划无法重生成且无从自纠。修复＝上限 9→16（＝草案 8＋锁定组 8 的拼接上限，注释写明语义）；每阶段 items ≤15 无叠加问题（锁定组 ⊆ 原阶段项）、落库与前端渲染均无阶段数约束、schema 不在 OpenAPI 契约面＝零漂移。回归测试＝5 锁定阶段＋5 草案阶段＝10 阶段端到端（对抗验证：还原旧上限测试确实失败）。顺手修复 test_learning_plans.py::test_generate_tool_paths 日期炸弹（断言硬编码 2026-09-29、跨 UTC 午夜后必炸，对齐 packed_payload 的 TODAY 相对锚——07 先例）。
14. **确认卡编辑换目标未锁死修复（GPT 审查 P2，09-30）**：`validate_plan_draft_edit` 原直接用编辑载荷的 goal_id 装载目标并校验可见性 / 期限，从不与原提案比对（spec 用户故事 9 编辑范围＝改日期 / 时长 / 删项 / 排序，不含换目标）。后果：篡改 goal_id 的编辑按新目标误校验后漏到 applier，被快照比对以误导性 OPERATION_SNAPSHOT_STALE 拦截并把提案污染成 FAILED（违反「编辑非法保持 PENDING」既定语义）；审计行 target_id 取提案行（原目标）而 payload 是新目标＝结构上允许审计与实际写入失真。修复＝编辑校验器在目标装载前比对编辑载荷与原提案载荷的 goal_id，不一致即 PLAN_DRAFT_INVALID（提案保持 PENDING、错误明确可自纠）；校验先于 require_active_goal——目标不可达也以「不能变更学习目标」拒绝。回归测试＝篡改 goal_id 确认拒绝＋PENDING＋原载荷可恢复确认（对抗验证：禁用新校验实际得到 GOAL_NOT_FOUND，证明其为唯一拦截点）。
15. **全 null PATCH 虚假成功审计修复（GPT 审查 P2，09-30）**：`{"estimated_minutes": null}` 经 `exclude_unset` 判非空通过 `_require_any_field`（显式提供的 null 不被 exclude_unset 排除），Service 滤 None 后零改动但 `_apply_manual_change` 无条件落 SUCCEEDED 审计——200＋数据未变＋虚假 USER_MANUAL 审计，违反 spec 用户故事 14「改动立即生效并有审计」成对语义。修复＝验证器排除值为 None 的字段（全 null 与空载荷同拒 422「至少提供一个非空修改字段」）；混合载荷（有效值＋null）忽略 null 行为不变（既有测试覆盖）；Agent 工具面本就滤 None 零影响、`PlanItemUpdatePayload` 继承自动同口径。回归＝路由测试加全 null 422 断言且审计行清单不含该次尝试（对抗验证：还原旧验证器测试确实红＝复现 200 虚假成功）。

## 用户真机验收清单（不代勾）

1. **草案编辑**：对话生成计划草案 → 确认卡上改某项日期与时长、删一项、上下移调整顺序 → 确认 → 对话问「我的计划是什么」核对落库结果与编辑一致。
2. **编辑边界**：把某项日期改到今天之前（或目标期限之后）再确认 → 如实报错且草案卡未失效，修正日期后可正常确认。
3. **Agent 调整**：「把第 X 条改到周五 / 改成 90 分钟」→ update_plan_item 确认卡 before/after 预览 → 确认生效（该项成为用户锁定项）；「这条学完了」→ complete_plan_item 确认 → 完成。
4. **重生成**：先手动编辑锁定 1~2 项 →「重新给我排一份计划」→ 确认卡预览（锁定项带「保留」标记）→ 确认 → 新版本生效；旧版本可只读查询（含此前的完成 / 跳过进度）。
5. **完成零证据**：完成若干项后 DB 直查 `SELECT COUNT(*) FROM learning_events;` 与 `user_concept_mastery;` 均为 0。
6. **审计链**：DB 直查 agent_operations——Agent 路径 trigger=USER_CONFIRMED_PROPOSAL / AUTO_EXECUTED，页面路径（计划 Tab 随工单 04，可先经 API）trigger=USER_MANUAL。
7. **档位行为**：AUTO_APPROVE 下 update / complete（L1）直执行出回执卡、regenerate（L2）仍出确认卡；FULL_ACCESS 三者全直执行；默认档三者均出确认卡。
