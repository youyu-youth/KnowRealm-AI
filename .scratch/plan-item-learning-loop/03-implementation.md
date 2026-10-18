# 03 实施与验收

基点：`527a3c6`（分支 `feat/extend-dev-09`）。本票实现首轮计划练习建卷、冻结题面作答、正常评分与人工完成；评分失败重试、安全重练与多轮结果归 04，真实模型与原生桌面验收归 05。

## 2026-10-18：计划结果页隐藏普通重考入口

- 已确认：ResultSummary 原本对 PLAN / MOCK 均无条件显示「再考一张」，父级回调固定返回课程普通模拟测试列表。新增实际 App/Router/Query 页面用例在 PLAN 的 COMPLETED、GRADING_FAILED 状态均因按钮仍存在而失败；同轮 MOCK 导航测试正常。修复前证据：`.pytest-tmp-runs/20261018T014218Z-f8b7d4e0/frontend/`（2 失败、18 通过）。
- 最小修复：仅在共享 ResultSummary 的按钮处增加 mode != PLAN 判断，PLAN 结果页隐藏该动作，继续保留成绩、批改与现有返回计划练习入口；普通 MOCK 的按钮及课程测试列表导航沿用原实现。03 不接入普通 MOCK 作为计划重练，真实安全重练留 04。无新组件、依赖、文案、API 或后端改动。
- PASS：`uv run --frozen --directory backend python -m scripts.run_tests frontend src/features/quiz-tests/components/QuizTestPage.test.tsx`，20 项；新增四项覆盖 PLAN 两种结果状态不显示普通重考、计划返回链接指向当前计划项，以及 MOCK 两种状态的按钮点击均进入课程测试列表。证据：`.pytest-tmp-runs/20261018T014311Z-280cc3ba/frontend/`。替身只在 HTTP 边界，真实 React 页面、Router、Query 和 Button 均参与。
- PASS：本轮两个前端文件 ESLint、Prettier；`pnpm build`（两份 TypeScript 配置 + Vite 生产构建）退出 0。构建仍提示既有测试文件路由发现与大分块警告。样式启发式脚本修复前后均报 no-focus-visible / no-hover-states：其正则只匹配 :focus-visible / :hover，不识别本项目 focus-visible: / hover: Tailwind 类；共享 Button 与页面返回 Link 已有相应样式，本轮只控制原按钮可见性，未扩大为视觉重构。
- NOT_RUN：全量、真实模型、后端（本轮未改）、原生 Tauri/WebView2、屏幕阅读器、主题视觉和 Windows 系统缩放；既有 test_practice_round.py 私有访问类型错误及 PROJECT_PROGRESS.md 的基点格式告警仍保留。桌面待复验：打开同一计划项已完成/评分失败结果，应无「再考一张」且可返回计划练习；打开普通 MOCK 对应结果，两种状态仍可点击「再考一张」回课程模拟测试列表。
- 状态：本轮反馈的五项缺陷已逐项修复并取得定向证据；尚未重新执行整票独立 Code Review 或全量/原生交付验收，不将本次小修视为整票交付认证。

## 2026-10-18：旧模拟测试来源清理兼容修复

- 已确认：无冻结副本的旧 MOCK 试卷在来源 Record 物理删除后，Quiz 随之级联清理，卷面项保留且 quiz_id 置空；详情投影跳过这些题，实际返回 200、items=[]、total_count=0。新增真实 HTTP/完整迁移 SQLite 用例验证该状态，不更改删除规则或回填已丢失题面。
- 修复前实际 App/Router/Query 页面测试 4 项失败，复现单题模式 undefined.id、分段模式 undefined.title，以及刷新后题集缩短使单题索引越界。证据：`.pytest-tmp-runs/20261018T013339Z-af33207d/frontend/`。
- 最小修复：QuizTestPage 在空题集时显示双语说明与返回入口，不挂载作答、交卷或重评界面，动态空态说明通过 status 宣告；普通卷返回课程模拟测试列表，计划卷仍返回计划练习。非空题集刷新后，单题显示索引收敛至有效范围，按钮与键盘翻题使用有效位置。复用现有 Button、Router、Query 和主题语义令牌，无新增依赖、API 或数据库迁移。
- PASS：`uv run --frozen --directory backend python -m scripts.run_tests backend tests/test_quiz_tests.py`，18 项，含真实来源清理新用例及普通模拟测试既有回归。证据：`.pytest-tmp-runs/20261018T013546Z-4cf0ba87/backend/`。
- 前端验证：`uv run --frozen --directory backend python -m scripts.run_tests frontend src/features/quiz-tests/components/QuizTestPage.test.tsx src/i18n/locales.test.ts`；覆盖三种视图的空题集、返回列表、刷新由 3 题缩至 2 题后的翻题及再清空，以及双语一致性。PASS：卷面 16 项、双语 3 项；证据：`.pytest-tmp-runs/20261018T013808Z-cb4900df/frontend/`。
- PASS：改动前端文件 ESLint/Prettier、两份 TypeScript 配置及 Vite 构建；新增后端测试文件 Ruff lint/format、Pyright 0 错。本轮未重跑前几轮未改动的确认卡或计划评分测试，其证据沿用各节记录；既有 test_practice_round.py 私有调用类型错误仍未处理。 文档 Prettier 检查中 PROJECT_PROGRESS.md 仍有格式告警，已对 HEAD 导出文件复现；不为本轮小修重排整张进度表。
- NOT_RUN：全量、真实模型、原生 Tauri/WebView2、屏幕阅读器、主题视觉及 Windows 系统缩放。桌面复验：在隔离数据目录载入无冻结副本的旧 MOCK 试卷，物理清理全部来源后依次用 single/sectioned/full 打开，应显示说明且可返回测试列表；保留部分来源、在末题清理并刷新后，应显示有效题、翻题正常。浏览器 DOM/MSW 测试不代替上述原生验收。
- 后续状态：计划结果页普通重考入口已由最新修复记录覆盖；全量与真实桌面交付验收仍未执行。

## 2026-10-18：评分完整性投影修复

- 已确认并复现：生产 Worker 对单题无效评分输出落 `LLM_OUTPUT_INVALID` 后继续，整卷正常收尾为 COMPLETED；原投影在 14/15 和 0/15 已评分时均误报 `grading_complete=true`。修复前 2 个定向用例均因此失败，证据：`.pytest-tmp-runs/20261018T012753Z-36009f9a/backend/`。
- 最小修复：`round_out` 只在整卷 COMPLETED 且已评分题数等于总题数时返回评分完整。保留执行状态、部分成绩、实际分母、答案及 Worker 收尾语义；HTTP 和 Agent 查询继续共用这一投影，无契约、迁移、权限或前端改动。
- 验收经真实 HTTP 准备 15 题、建卷、保存答案、交卷及生产评分 Worker；只在原有外部模型替身中注入 1 次或 15 次不合规输出，仍经过真实结构化校验、逐题错误落库及完成落账。确认 14/15 和 0/15 时完整性为 false，部分成绩分母 14、零已评分无成绩且无分母；复用既有全部评分成功用例，并补查客观题全部已评分但尚未交卷时完整性仍为 false。
- PASS：`uv run --frozen --directory backend python -m scripts.run_tests backend tests/test_practice_round.py`，23 项，含前两轮修复回归。证据：`.pytest-tmp-runs/20261018T012842Z-52e0ff80/backend/`。
- PASS：本轮两个后端改动文件 Ruff lint/format、生产模块 Pyright；含测试文件的 Pyright 仍只有已在 HEAD 复现的 `_round_conflict` 私有访问错误，不宣称检查全绿。未重跑未改动的普通模拟测试或前端检查。
- NOT_RUN：全量、真实模型、原生桌面与系统缩放。旧 MOCK 空题集及计划结果页普通重考入口已由后续修复覆盖；交付验收边界见最新记录。

## 2026-10-18：评分提交计划约束修复

- 修复范围：旧 `regrade` 入口补齐计划可写性检查；`submit` 与 `regrade` 共用的 `_transition_to_grading` 在创建评分任务的事务内重验计划和课程。计划护栏复用 `practice.lock_item` 取得 SQLite 写锁，再经 `load_context` 校验当前计划版本、目标状态及跳过状态，锁持有至事务结束。继续保持 learning_plan → quiz 的单向依赖，不新增规则、错误码、Schema 或评分引擎。
- 验收路径：真实 HTTP 准备/建卷/保存 15 题答案 → 原供应商配置读取前后，以独立 SQLite 事务使计划换代、目标完结或计划项跳过 → 交卷/旧重评接口返回 `409 PRACTICE_ITEM_UNAVAILABLE` → SQLite 核对零新增评分任务、原答案/试卷状态/学习事件不变。重评的 `GRADING_FAILED` 为明确的 SQL 初始夹具；仅包裹真实配置读取来固定事务间窗口，不替换 Service、事务、迁移或 Worker。另由生产评分 Worker 验证已受理评分在计划换代后仍正常收尾。
- 修复前，9 个失效场景全部复现错误：返回 200 并进入 GRADING。证据：`.pytest-tmp-runs/20261018T012142Z-da943d6e/backend/`。
- PASS：`uv run --frozen --directory backend python -m scripts.run_tests backend tests/test_practice_round.py tests/test_quiz_tests.py`，38 项（轮次 21 + 普通模拟测试 17），含 9 个失效场景及 1 个已受理评分收尾场景。模型为可控外部替身，HTTP/SQLite/迁移/Worker 为生产实现。证据：`.pytest-tmp-runs/20261018T012231Z-dbddfa7f/backend/`。
- PASS：本轮三个后端改动文件 Ruff lint/format；两个生产模块 Pyright 0 错。含测试文件的 Pyright 仍只有上一轮在 HEAD 复现的私有 `_round_conflict` 调用错误，未扩大修改或将检查记成全绿。前端代码未再修改，不重复运行上一轮前端检查。
- NOT_RUN：全量测试、真实模型、原生桌面与系统缩放。其余问题当前状态及交付边界见最新修复记录。

## 2026-10-18：默认授权开始确认闭环修复

- 本次仅修复复核发现的 P1：`OP_PRACTICE_ROUND_START` 未登记聊天确认卡。复用现有卡片注册表、要求参数预览、确认/拒绝 API 与查询恢复；新增专用动作文案、开始影响说明，以及按真实回执展示的轮次、题量、状态、作答和返回计划入口。未改授权档位、领域建卷或答案投影。
- 验证路径：已装配 `start_plan_practice` → REQUEST_APPROVAL 持久 PENDING 提案（核对计划项、要求修订、准备身份及 SQLite 零试卷）→ HTTP 确认 → APPLIED 回执与唯一轮次 → 会话提案查询恢复；另保留 AUTO_APPROVE 回归。前端覆盖显式/默认题集参数、确认、拒绝与评分中持久回执恢复。HTTP/SQLite/准备 Worker 为真实实现，匹配/评分模型为外部替身；前端 API/Router 为组件测试替身。
- PASS：`uv run --frozen --directory backend python -m scripts.run_tests frontend src/features/chat/ChatOperationProposalCard.test.tsx`，52 项（修复前新增 4 项失败、原有 48 项通过；修复后全部通过）。证据：`.pytest-tmp-runs/20261018T011332Z-b234f809/frontend/`。
- PASS：同一测试入口 `backend tests/test_practice_round.py`，11 项，含 REQUEST_APPROVAL/AUTO_APPROVE 两条链。证据：`.pytest-tmp-runs/20261018T011403Z-22917ad3/backend/`。
- PASS：同一测试入口 `frontend src/i18n/locales.test.ts`，3 项。证据：`.pytest-tmp-runs/20261018T011517Z-b47d1264/frontend/`。
- `scripts/check-changed.ps1`：ESLint、Prettier、两份 TypeScript 配置、Vite 构建及 Ruff 检查通过；Pyright 失败 1 项，指向既有并发测试调用私有 `_round_conflict`。将 HEAD 同一文件快照放在 `backend/tests/` 按相同配置复测，同样 1 项错误（基点第 536 行）；临时快照已移除，不修改该无关测试。不能记为范围检查全绿。
- 样式复用 `buttonVariants` 的语义颜色、hover 与 focus-visible；`lint_slop` 不追踪共享 cva 类名，报缺少 hover/focus 的两项为误报，已核对公共按钮定义。本轮未新增设计令牌。
- NOT_RUN：真实模型、浏览器视觉、真实 Tauri/WebView2 与 Windows 缩放；未跑全量测试，未提交临时日志。其余评审问题的当前状态见上方评分提交约束修复记录，不能将整票改判为完成或可交付。下文为首轮实施记录，原初评零遗留结论已被此次复核修正。

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
