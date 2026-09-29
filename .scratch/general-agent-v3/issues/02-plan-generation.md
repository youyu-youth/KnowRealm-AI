# 02 — 计划数据与生成确认链路

**What to build:** AI 生成学习计划并经用户确认落库。用户说"基于这门课的资料生成四周学习计划"，Agent 产出结构化草案（阶段划分、逐项内容、时长、理由）并以只读确认卡呈现（确认 / 放弃 / 重新生成）；确认后计划落库生效。以纯目标为起点（无资料）时返回建议学习内容与资料缺口清单。草案不持久化，关闭即弃。

**Blocked by:** 01 — 学习目标领域与对话制定

**Status:** done

- [x] 迁移 0035 落地 `learning_plans`（(goal_id, plan_version) 唯一、status ACTIVE / SUPERSEDED / COMPLETED、effective_from / effective_to）与 `learning_plan_items`（plan_id、action_type 四类：STUDY_RECORD / PRACTICE_QUIZ / REVIEW_CONCEPT / CUSTOM、concept_id 可空、STUDY_RECORD 目标对象关联、priority、estimated_minutes、scheduled_date 按日、status、user_locked 默认 false、reason_json）
- [x] 生成 Service：LLM 结构化草案（阶段 / 计划项 / 时长估算 / 逐项理由）；日期铺排与预算一致性由确定性校验与修正承担（不超期限、每日总量与 daily_minutes 相容）——脚本优先、LLM 次之
- [x] 草案确认卡（**只读**版）：确认 / 放弃 / 重新生成；确认落库为 ACTIVE 版本（同一目标同时至多一个 ACTIVE 计划）；草案不持久化、learning_plans 仅确认时写入
- [x] 目标起点无资料路径：返回建议学习内容＋资料缺口清单（对话卡呈现，引导补充资料）
- [x] 基于库内资料生成时，复用现有检索把资料内容纳入生成上下文
- [x] Agent 工具：get_plan（只读）、generate_learning_plan（草案，只读不落库）、confirm_plan（草案卡即确认闸门）
- [x] prompt_version bump；计划生成黄金集骨架：评测文档两份 md＋评分脚本＋脱敏占位符＋用户采集流程说明（沿用研究会话模式；回归触发＝prompt 版本或模型变更）
- [x] 测试：Service 生成与落库语义（草案零落库断言、ACTIVE 唯一）、排期确定性修正的黄金样本手算、路由集成测、Agent 工具确认行为；user_version 断言同步
- [x] 门禁全绿：pytest（独立 basetemp）+ ruff + pyright + OpenAPI --check + 前端测试（确认卡组件）

参考：[spec.md](../spec.md) 计划生成与确认（User Stories 7~11）、生成确认与版本语义段。

## 实施备注

1. **草案确认机制＝操作提案复用**：`confirm_plan` 注册为 L2 写操作（OP_PLAN_CONFIRM，0030 CHECK 通配零迁移），提交即落提案＝草案确认卡（只读预览），确认走既有 `/api/proposals/{id}/confirm`。「草案不持久化」语义 = learning_plans / learning_plan_items 仅确认时写入（提案是待确认载体非半成品计划数据，与全部写动作同一机制）；「放弃」= 既有拒绝按钮；「重新生成」= 放弃后在对话中再要求（卡片三按钮中的第三action以 hint 文案承载，可编辑卡随工单 03）。L2 语义下 AUTO_APPROVE 档仍落确认卡（草案卡即确认闸门）、FULL_ACCESS 直执行。
2. **模型转述草案为载荷本体**：generate 返回草案 JSON → 模型原样传给 confirm_plan（载荷=草案全文）。确认卡所见（payload 预览）与落库所写（applier 消费同一载荷）天然一致；模型转述漂移由提交时**排期重算比对**拦截（PLAN_SCHEDULE_INVALID 附期望日期，模型自纠重交），STUDY_RECORD 的 record_id 越界由归属校验拦截（PLAN_DRAFT_INVALID）。
3. **日期不进 LLM 契约**：PlanDraft 只含阶段/项序/时长/理由；日期由 `scheduling.pack_schedule` 纯函数按顺序贪心铺排（每日预算 = 目标 daily_minutes，缺省默认 120；期限容量不足或**单项时长超每日预算**均抛 ScheduleInfeasible → 工具转 PLAN_SCHEDULE_INFEASIBLE 附原因文案，生成 prompt 同时给出容量与单项预算提示引导模型排量）。黄金样本手算测试四例 + 不可行两例。**修复备案（09-29 review）**：原实现「单项超整日预算独占一天为显式豁免」击穿 spec「每日总量与 daily_minutes 相容」（期限当天 + 单项 600 分钟可提交），已改为不可行拒绝，回归测试锚定两复现场景；prompt 版本 bump learning-plan-v2。
4. **无资料路径**：课程可见记录为零时切 PlanSuggestions 输出（建议内容 + 资料缺口），工具返回结构化建议由模型在对话转述并引导补充资料（spec 用户故事 8；「对话卡」以模型转述承载，不新建卡片类型）。
5. **资料上下文复用现有查询**：记录标题 + 已确认总结摘要（ai_summaries CONFIRMED）+ `LibraryRetrievalService.search`（COURSE 范围、目标标题为查询词）逐字引文；LLM 调用期间不持 DB 连接（资料先提取后调用）。
6. **runtime 扩展**：AgentRuntimeContext 新增 llm_provider（accept 时已校验的聊天供应商，与主模型同源）；generate 工具内 LLM 失败复用 StructuredGenerationError 稳定错误码（LLM_OUTPUT_INVALID / PROVIDER_REQUEST_FAILED）。
7. **registry 行为改进（随票）**：submit_operation 的快照拒绝载荷现附带 CodedHTTPException.detail（此前只透出错误码）——PLAN_SCHEDULE_INVALID 需要附期望日期供模型自纠；既有目标动作的中文拒绝理由同步受益（goal 测试两处等值断言改子集断言）。
8. **快照**：PlanConfirmStateSnapshot（updated_at/title/target_date/daily_minutes/course_name）——确认前目标被改（期限/投入变化会让既排日期失真）→ 快照比对失效重新生成。
9. **版本语义**：confirm_core 版本号 = 现有最大版本 + 1（首次恒 1；旧版进终态后递增，重生成 SUPERSEDED 链路随工单 03）。effective_from = 确认落库日（UTC）。
10. **评测骨架**：docs/evaluation/plan-generation-{checklist,samples}.md + backend/scripts/score_plan_generation.py（机械项：排期逐位复算/不超期限/结构完整，与 pack_schedule 同源；人工 rubric：资料贴合度/理由可解释性）；回归触发 = learning-plan-v1（生成 prompt 独立版本串）或模型变更。
11. **prompt 双轨 bump**：chat-library-scope-v18→v19、chat-research-scope-v19→v20（CHAT_PLAN_GUIDANCE 进两模式系统提示）；挂载矩阵 7 处工具列表 + 3 处指引组合断言同步。
12. **真机验收修复（草案 JSON 出现在聊天正文）**：用户真机复现——模型把 confirm_plan 的参数 JSON（草案全文）粘贴到回复正文而非走工具调用（确认卡未出现、正文被截断）。两层修复：①提示词层（chat prompt v20/v21）：generate_learning_plan / confirm_plan 工具指引与 CHAT_PLAN_GUIDANCE 明确「复述草案用简洁中文列表（每行：日期、内容、时长、理由），草案 JSON 只进工具参数、严禁在正文输出 JSON 或代码块」；②前端确定性兜底（不改落库只改展示）：新增 `planDraftJson.ts` 判定（正文整体可解析、顶层非空 phases[].items 专属形状，误伤≈0），命中时 ChatMessageList 以折叠块渲染（摘要行+可展开原始数据+重新发起引导），流式起势（`{`/```json 开头）先收敛为「正在准备结构化数据…」占位；判定与渲染 12 测试。备案：若提示词修复后仍频发，根治架构为服务端草案暂存（confirm_plan 只传 draft_id、模型不再复制大 JSON），属 02 已定案设计变更，届时随工单 03 提请决策。
13. **真机验收二轮修复（前导 JSON + 中文混合形态）**：v20 提示词禁令后模型仍先吐完整草案 JSON 再输出中文复述（构造超长工具参数的底层输出习惯，提示词约束力有限）；且一轮整体判定不命中混合形态、兜底失效。修复升级为**确定性前导剥离**（planDraftJson.ts 重构）：字符串感知括号配平定位顶层对象边界 → 解析 + phases 形状校验 → 剥掉前导 JSON 只渲染剩余中文（含 ```json 围栏前导；JSON 出现在中后段/非草案形状不命中防误伤）；正文整体即 JSON（无中文）保持折叠块；流式统一视图（JSON 未闭合占位 → 闭合后渲染剩余中文打字）。端到端用真实规模复现文本（5 阶段 38 项、8KB）验证剥离正确。
14. **真机验收三轮修复（位置无关全文扫描，定稿）**：三轮形态为「中文在前 + JSON 在后」——二轮的前导剥离（位置锚定）天然不命中；三轮形态演变证明 JSON 位置不固定（独占/前导/后置均出现），按位置锚定是设计错误。定稿重构 planDraftJson.ts 为**按形状锚定**：全文扫描所有平衡闭合顶层 {...} 块（含 ```json 围栏，字符串感知配平），命中草案形状（解析成功且顶层非空 phases[].items）即移除，任意位置多段全剥、剩余中文拼接渲染；防误伤完全由形状保证（普通 JSON 顶层非 phases 结构不命中，用户主动要 JSON 的回答原样保留）；流式统一视图（已闭合段实时移除 + 未闭合开放段从起点截断不透出，闭合且非草案自然恢复）。三轮历史形态回归测试 + 本轮真实形态（19 项 4KB，模型省略可选键兼容）端到端验证。
12. **修复备案（09-29 review）**：确认卡计划项原实现 content 截 60 字且不渲染 reason，违反 spec 用户故事 10（逐项理由可见）与「确认位置核对完整载荷」——已改为内容全文 + 「理由：」次行全文展示（schema 上限 200/300 字有界，无需折叠交互），i18n 双侧补 reasonLabel；阶段标题/目标标题的展示截断维持既有惯例未动。
13. **修复备案（09-29 review）**：第三动作「重新生成」由 hint 文案升级为真按钮（原备注 1 的降级被 review 推翻）——CARD_BY_TYPE 配置表新增 regenerateMessage 声明点（仅 plan 类型），按钮=先 reject 旧草案（REJECTED 终态失效、回执如实呈现「已放弃」）再经父级 onSendMessage 代发「请基于课程资料为目标 {goal_id} 重新生成一份学习计划草案」，Agent 收到后重跑 generate 产新提案卡；未传发送回调（prop 门控）或非 plan 类型不渲染按钮；hint 文案同步更新。

## 用户真机验收清单（不代勾）

1. **核心闭环（有资料）**：配置 LLM → 课程内导入 ≥2 份资料并确认总结 → 对话「为这门课制定目标：四周内学会 X，每天一小时」确认目标 → 「基于这门课的资料生成四周学习计划」→ 出现只读草案确认卡（阶段/逐项日期/时长/类型/排期概览）→ 确认 → 回执「学习计划已生效（第 1 版 · N 项）」+ 打开课程入口。
2. **草案不落库**：再生成一份草案后点放弃（或直接关闭话题）→ 对话问「我现在有什么学习计划」→ 助手答复无生效计划；DB 直查 `SELECT COUNT(*) FROM learning_plans;` 无新增。
3. **无资料路径**：新建空课程 + 目标 → 请求生成计划 → 助手转述建议学习内容与资料缺口、引导补充资料（不编造资料内容）。
4. **排期合规**：目标设短期限 + 小时每日投入（如 7 天 × 30 分钟）请求大量内容 → 助手如实转述「总量超出期限容量」并给建议（不谎称已排出计划）。
5. **查看计划**：确认后对话「我接下来学什么 / 我的计划是什么」→ get_plan 返回逐项内容与日期。
6. **自动档闸门**：切 AUTO_APPROVE 档位后再生成并确认 → 仍出确认卡（L2 草案卡即确认闸门）；FULL_ACCESS 档直执行出回执卡。
7. （可选）机械项评分脚本首跑：按 docs/evaluation/plan-generation-checklist.md §3 采集后 `cd backend && uv run python -m scripts.score_plan_generation <目录>`。
