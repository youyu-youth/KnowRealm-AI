# 01 — 学习目标领域与对话制定

**What to build:** 学习目标成为真实业务数据。用户通过对话让 Agent 为知识空间制定学习目标（"为这门课定个目标：四周内学会 Agent 工程，每天一小时"），Agent 追问缺失的期限或投入、无知识空间时先确认建新空间；AI 推断的目标范围必须经用户确认才生效；目标可编辑、标记完成、归档；同一空间同时最多一个进行中目标，跨空间不受限。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 迁移 0034 落地 `learning_goals`：course_id 必填外键、goal_type、title、target_date、daily_minutes、target_score（可选）、scope_source（USER_CONFIRMED / COURSE_SELECTION / AI_INFERRED）、scope_confirmed、status（ACTIVE / COMPLETED / ARCHIVED）；单空间单 ACTIVE 用部分唯一索引（UNIQUE(course_id) WHERE status='ACTIVE'，工单内核实 SQLite 支持）✅ SQLite 部分索引支持已核实（0010/0026/0033 先例），迁移结构测试 + 存储层行为测试双覆盖（终态不占名额、跨空间不受限）
- [x] 领域 Service：创建（单 ACTIVE 校验、AI_INFERRED 未确认不能生效）、编辑（期限/每日投入）、完成、归档；换新 ACTIVE 目标时明确提示先完成或归档旧目标（新错误码登记 zh/en）✅ `learning_plan/` 模块（工单 02 计划域后续同入）；`GoalCreateCore` schema 执法 AI_INFERRED+未确认拒绝（用户故事 6 不变量）；错误码 GOAL_ACTIVE_EXISTS / GOAL_NOT_ACTIVE / GOAL_NOT_FOUND zh/en 已登记
- [x] 课程软删后目标查询不可见（查询期过滤，不写级联）、恢复课程目标即恢复——与 Record 同模式 ✅ GoalService.get / list_for_course JOIN courses 查询期过滤（复用 CourseService.get），测试覆盖软删→不可见→恢复→可见
- [x] API：课程嵌套目标端点（列表/创建/修改状态），OpenAPI 重新生成 --check 通过 ✅ GET/POST `/api/courses/{id}/goals` + PATCH `.../goals/{goal_id}` + POST `.../complete` / `.../archive`（course 归档/恢复端点先例）；api-types 已 regenerate
- [x] Agent 工具：list_goals / get_goal（只读）、create_goal / update_goal（写，走确认卡＋三档授权＋Operation 审计，ADR-0026）✅ OP_GOAL_CREATE / OP_GOAL_UPDATE 进注册表（均 L1，OP_ 通配零迁移）；确认与直执行路径同事务回接 operation 行；只读工具复用 listing.py 统一 limit 形态与预算；恒挂载全部会话类型
- [x] 前端：目标制定 / 编辑走现有聊天确认卡呈现（复用二阶段通用操作卡，无新增页面；确认卡对目标字段预览的适配随票完成，api-types 重新生成）✅ CARD_BY_TYPE +2（goalFields 共用字段标签块 + 类型枚举翻译；创建卡=课程/类型/标题/期限/投入+单 ACTIVE 提示、更新卡=before/after+状态流转终态提示；回执创建卡带课程入口跳转）
- [x] chat prompt 更新：目标制定引导（追问缺失项、无空间先建、范围确认话术）、prompt_version bump ✅ CHAT_GOAL_GUIDANCE 进 SYSTEM 末尾指引段（chat-library-scope-v18 / chat-research-scope-v19）
- [x] 测试：Service 单 ACTIVE 与 scope 确认语义、路由集成测、Agent 工具确认卡与授权行为；新迁移同步全部 user_version 断言 ✅ tests/test_learning_goals.py 18 项；user_version 断言全库已收敛 supported_user_version()（C2 先例）自动跟随迁移发现，无需手改
- [x] 门禁全绿：pytest（独立 basetemp）+ ruff + pyright + OpenAPI --check + 前端测试

## 实施备注（关键决策与偏差备案）

1. **单 ACTIVE 冲突在提交时拒绝（对 create_course 先例的有理由偏离）**：创建类动作通常无 capture_state（课程创建无状态），但目标创建是状态依赖约束（单空间单 ACTIVE）。`capture_goal_create_state` 读取器让 GOAL_ACTIVE_EXISTS / COURSE_NOT_FOUND 在**提交时**以结构化错误返回（零提案，模型即时转述「先完成或归档旧目标」——精确服务用户故事 3 的对话时体验）；确认前课程被改 → 快照比对失效重确认；领域核心 + 部分唯一索引仍是存储层兜底。
2. **Agent 创建的目标 scope 固化 AI_INFERRED + scope_confirmed=True**：确认卡即用户确认（spec 用户故事 6）；HTTP 页面入口恒 USER_CONFIRMED。两路径共用 GoalCreateCore（领域核心参数显式承载 scope 语义）。
3. **update_goal 单动作覆盖编辑与状态流转**（票面四工具定案）：payload 可选字段 + 可选 status（COMPLETED/ARCHIVED 终态单向）；编辑与流转均仅对 ACTIVE 开放（GOAL_NOT_ACTIVE 单码覆盖编辑/完成/归档三种非 ACTIVE 拒绝，少登两个幂等码）。
4. **goal_type 枚举**：数据模型 P6 原设计未列值域，落 SKILL / EXAM / PROJECT / READING / CUSTOM 五类；exam_scope_json 不随票（票面字段集）。
5. **撤销不在本票范围**：两注册项声明 undo_reason（补偿器留后续票）；UI 经既有 ProposalUndoEntry 就地呈现原因。
6. **公共流程 1 词修复**：`submit_operation` 与 `ProposalService.create_core` 的载荷清洗 `model_dump()` → `model_dump(mode="json")`——date 类型进 payload_json TEXT 列的序列化缺口在两处单点修复（既有动作字段为 str/枚举，输出逐字等价，全量测试佐证）。
7. **测试常量坑**：UUID pattern 是十六进制校验，goal 测试 id 用 `g` 前缀会被拒（`c` 是合法 hex）；同仓惯例 `9` 前缀。
8. **双轴 code-review 修复（已并入）**：①错误码清单 docs/后端错误码清单.md 补登三码（ADR-0017 权威清单，随票登记惯例）；②嵌套路由归属校验——PATCH/complete/archive 的路径 course_id 与目标实际归属错配按 404 GOAL_NOT_FOUND 处理（GoalService.update/set_status 增 expected_course_id 可选参数，Agent 路径按 goal_id 直达不传），补跨课错配测试；③单 ACTIVE 校验提取 GoalService.require_no_active 唯一入口（创建核心与 Agent 提交期检查共用）；④clean_goal_title 共享验证器收敛四处重复。
9. **review 备案不修项**：COURSE_SELECTION 暂无生产者（spec 值域原文保留，未来课程选择推荐入口可用）；编辑字段含 title/target_score（US5「目标可编辑」泛指＋计划 Tab 展示需要，票面括号举例非穷尽）；GoalStateSnapshot.status 用 str 与 CourseStateSnapshot 先例一致；直执行档 scope_confirmed=True＝三档预授权口径（注释已备案，确认事实由 authorization_json 承载）。

## 用户真机验收清单（不代勾）

- [ ] 对话制定目标：说「为 XX 课程定个目标：四周内学会 YY，每天一小时」→ 确认卡预览（课程/类型/标题/期限/投入）→ 确认后目标生效，回执卡可跳课程
- [ ] 追问体验：缺期限或每日投入时 Agent 先追问；没有课程时先确认建新课程
- [ ] 单 ACTIVE 体验：已有进行中目标再定新目标时，对话中即时得到「先完成或归档旧目标」提示
- [ ] 目标调整：改期限/投入的 before/after 预览与确认；「这个目标完成了」走状态流转确认（终态提示如实）
- [ ] 授权档位：AUTO_APPROVE 下创建/更新目标直执行出回执卡；FULL_ACCESS 同；默认档恒出确认卡
- [ ] 课程软删后 GET 课程目标 404、恢复课程后目标回归

参考：[spec.md](../spec.md) 目标制定（User Stories 1~6）、Implementation Decisions 领域模型段。
