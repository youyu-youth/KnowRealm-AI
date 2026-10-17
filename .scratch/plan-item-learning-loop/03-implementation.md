# 03 实施与验收

基点：`527a3c6`（分支 `feat/extend-dev-09`）。本票实现首轮计划练习建卷、冻结题面作答、正常评分与人工完成；评分失败重试、安全重练与多轮结果归 04，真实模型与原生桌面验收归 05。

## 已实现入口与边界

- 迁移 `0054_plan_practice_rounds.sql`：`quiz_tests` 重建加 `plan_item_id`（FK learning_plan_items CASCADE）/`practice_round_no`/`requirements_id`/`request_id`（UNIQUE），mode CHECK 增 `PLAN`，`UNIQUE(plan_item_id, practice_round_no)`；`quiz_test_items` 重建：`quiz_id` 改可空 + `ON DELETE SET NULL`（原题身份仅追溯，物理删除置空、不阻塞清理），新增 `frozen_json`（CHECK json_valid）。部分唯一索引 `idx_quiz_tests_one_answerable_round`（plan_item_id WHERE mode='PLAN' AND status='IN_PROGRESS'）以数据库约束兜底每项最多一轮可作答。
- 领域 `learning_plan/practice_round.py`：`start_round` 在同一事务内重验要求修订 = 最新、计划正文一致、确认来源归属/有效性/版本（复用 02 的 `require_confirmed_sources`）、准备任务 SUCCEEDED 且 READY、逐题重验 Quiz 身份/ACTIVE/题型/范围内/版本散列；通过后按准备选择顺序建卷并冻结每题题面、判分依据、概念归属、来源标题与版本。已有轮次（任意状态）时普通开始直接返回该轮，不建新轮；`request_id` 重放返回同一轮；并发由部分唯一索引兜底为 409 后重查。
- quiz 域冻结优先改造（普通模拟测试兼容分支）：`test_service`/`grading_worker` 的读题、客观判分、简答评分、交卷统计、完成落账统一改走 `quiz/frozen.py` 的 `FrozenFace`（冻结副本优先，无副本读原题行）；`_detail_out` 改 outerjoin，原题物理删除且无副本的旧卷面题跳过（不猜测回填）；作答期仍不揭示参考答案与解析。`QuizTestItemOut` 新增 `record_title`/`source_valid`（PLAN 轮次按 Record 当前归属与软删事实标注失效）；`QuizTestSummaryOut` 新增 `plan_item_id`/`practice_round_no`。
- 计划约束直连旧作答入口：`answer_item`/`submit` 在 PLAN 轮次先校验计划 ACTIVE、目标 ACTIVE、项未跳过（`PRACTICE_ITEM_UNAVAILABLE`），历史版本仍可查看结果；PLAN 轮次 `abandon` 返回 `PRACTICE_ROUND_OP_UNAVAILABLE`（放弃旧轮属 04 安全重练链）。
- HTTP：`POST /api/plan-items/{item_id}/practice/rounds`（幂等建卷/返回当前轮）；`GET .../practice` 的 `PracticeStateOut` 新增 `round` 投影（已答/已评/未评/总题、成绩与实际分母、评分完整性、来源失效列表、作答入口），永不包含题面或答案。
- Agent：新增受控操作 `start_plan_practice`（L1、`OP_PRACTICE_ROUND_START`）与同名装配工具；`get_plan_practice` 投影自动携带当前轮；完成复用既有 `complete_plan_item`。工具矩阵七档名单与旧库回拨夹具已同步。
- 前端：练习准备页新增 `PracticeRoundCard`（本轮状态/进度/部分成绩与分母/来源失效/继续或查看结果入口）与「开始练习」（READY 后可用，失败重试沿用请求身份）；作答复用 `/spaces/:courseId/tests/:testId` 卷面，PLAN 模式显示「计划练习」徽标与「返回计划练习」入口、概念归属只读、来源失效标注不可跳转、不渲染放弃按钮。zh/en 同步。

## 固定验证路径

真实 HTTP PUT 要求 → POST 准备 → 生产 JobRunner 匹配 → READY → POST rounds 建卷（SQLite 直查 frozen_json 完整性与建卷零学习事件）→ 现有作答端点答 6/15 → 新应用实例重启继续同轮 → 答满交卷 → 生产评分 Worker 逐题评分 → COMPLETED → 轮次投影与事件（15 ANSWERED + 1 TEST_COMPLETED）→ 人工完成保留首次时间戳且零新增事件。

固定数据沿用 02：15 道 Redis 简答（答案含「秘密」标记用于泄漏断言）+ 无关题干扰；客观题路径另用 15 道判断题验证交卷同步落终态。替身仅替换外部匹配/评分推理，不替换 Service、迁移、HTTP、事务或生产 Worker。

## 验证证据

- 后端 `tests/test_practice_round.py` 9 项全过（真实 HTTP/SQLite/生产 Worker）：冻结完整性与零答案外泄、重放/重启/评分中同轮不新建、固定题面穿越原题改写/来源移出课程/软删、失效来源拒新练习（PRACTICE_SOURCE_INVALID）、资料物理删除不被引用阻塞（quiz_id 置空后照常作答评分）、客观题同步完成 + 人工完成首次时间戳保留、旧作答入口计划约束（409）与 PLAN 放弃拒绝、旧库 0053 升级 0054 数据保留与弱引用验证、Agent AUTO_APPROVE 直执行回执无答案。
- 既有回归：`test_practice_preparation.py` 25 项、`test_quiz_tests.py` 17 项（普通模拟测试兼容）全过；装配矩阵 `test_chat_streaming.py -k matrix` 7 档与 `test_tool_budget.py` 旧库回拨 4 项全过。
- 前端：`PracticePreparationPage.test.tsx` 7 项（含开始练习请求身份保留、评分中部分成绩与分母展示）、`QuizTestPage.test.tsx` 12 项、i18n 一致性全过；`npx tsc --noEmit` 零错误。
- 静态：`scripts/check-changed.ps1` 全绿（Ruff/格式/Pyright 改动文件 0 错、ESLint/Prettier/两份 TS 配置、OpenAPI check exit 0）；错误码 `PRACTICE_PREPARATION_STALE`/`PRACTICE_ROUND_CONFLICT`/`PRACTICE_ROUND_OP_UNAVAILABLE` 已三方登记。
- 真实模型、Tauri/WebView2、Windows 系统缩放与屏幕阅读器：NOT_RUN，归 05。

## 设计说明与既有约束处理

- 「不让新增练习引用阻塞资料删除」：`quiz_test_items.quiz_id` 原为 NOT NULL 强外键，原题物理删除（records 级联）会被旧卷面阻塞。本票以迁移改为可空弱引用 + 冻结副本承载题面，旧模拟测试卷面无副本、原题物理删除后该题不再显示（此前该删除本身被 FK 阻塞不可达，属解除既有阻塞而非改变可用行为），不猜测回填。
- 建卷为纯确定性同步事务（题目已在 02 固化为 selected 候选），不新建 ProcessingJob 类型或旁路调度；评分复用既有 QUIZ_GRADING job 与恢复链。同步事务无取消窗口与后台执行身份，页面与 Agent 的授权差异由受控 operation 档位在提交处执法（L1，与 02 的 prepare 同档），不设假 `authority` 参数。
- 「两个并发入口」的同一轮语义：请求重放走 `request_id` 命中（参数变化拒绝，`PRACTICE_REQUEST_CONFLICT`），普通开始走最新轮返回，真并发写入由部分唯一索引拦截、路由层重查后返回同一轮（无轮次时如实透出冲突）。
- `quiz_tests.plan_item_id` ON DELETE CASCADE：计划项行的物理删除仅在课程物理删除链可达，而该链已被 `quiz_tests.course_id` 既有 FK 阻塞（历史债，不在本票范围）；课程软删、计划换代与目标完结的轮次可见性沿查询期过滤与写护栏处理。
- 学习事实：单题事件幂等键 `quiz-answered:test:{item_id}` 天然按轮区分，事件 `source_id` 使用冻结快照中的原题身份（物理删除后不漂移）；交卷事件 `quiz-test-completed:{test_id}` 每轮一次；建卷、要求确认与人工完成零学习事件，掌握度继续只来自真实作答消费链。
- 普通模拟测试列表过滤 `mode != PLAN`，计划练习只经计划项入口进入，统计口径不变。

## 双轴评审修复（2026-10-17）

初评 Standards 2 硬违规 + 5 判断项、Spec 3 缺失 + 2 存疑，全部处置，两轴未解决项归零，明细见 [评审记录](./03-review.md)。要点：模块环依赖改为组合根注入 guard（learning_plan → quiz 单向）、重放参数变化拒绝、列表隔离 PLAN 轮次、并发败方重查返回同一轮（新增针对性测试，最终 10 项轮次测试全过）、`grading_complete` 收敛为仅 COMPLETED、`FrozenFace` 增 `quiz_id` 快照稳定事件身份、前端两处风格收敛。修复后 `scripts/check-changed.ps1` 全绿，后端相关回归 52 项通过。
