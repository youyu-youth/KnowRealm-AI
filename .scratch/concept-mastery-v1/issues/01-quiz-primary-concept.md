# 01 — 让习题在作答前绑定一个可信主概念

**What to build:** 学习者生成或查看习题时，可以看到系统从同课程已确认 Concept 中建议的唯一主概念，并能在首次作答前修改或清空；首次作答后归属固定。没有 Course Brain、没有已确认 Concept 或无法可靠归属时，习题保持可正常使用但不产生 Concept Mastery，已作答历史题不被自动猜测回填。

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Quiz 持久化可空的唯一主概念；存量行保持为空，不新增多对多表或自动回填任务。（迁移 0024 `quizzes.concept_id` 纯 ADD COLUMN + SET NULL 外键，无回填）
- [x] 生成流程只允许从当前 Record 所属课程的 CONFIRMED Concept 中建议主概念，模型结果经过服务端课程、状态与存在性校验。（worker claim 时加载概念清单进 prompt，writeback 事务内按 id+course+CONFIRMED 复核，无效 id 落空、批次照常发布；prompt 升 `quiz_v2`）
- [x] 无 Course Brain、零 CONFIRMED Concept、模型未选择或校验失败时，生成与作答行为保持现有语义且主概念为空。（无概念时 prompt 不含建议段；`test_generation_without_confirmed_concept_keeps_concept_empty`）
- [x] 学习者可在首次作答前通过真实 API 修改或清空主概念；跨课程、Candidate、Archived 或不存在的 Concept 被拒绝。（`PUT /api/records/{record_id}/quizzes/{quiz_id}/concept`；409 QUIZ_CONCEPT_INVALID / 404 COURSE_BRAIN_CONCEPT_NOT_FOUND 复用）
- [x] 普通 Quiz 或模拟测试题一旦首次作答，主概念不可再静默修改。（锁= `quizzes.answered_at` OR 存在已作答 `quiz_test_items` 行；模拟测试作答不写 quizzes.answered_at，故后者必需）
- [x] 已作答且无主概念的历史 Quiz 保持未归属；未作答旧题可在首次作答前选择主概念。
- [x] 普通 Quiz 与模拟测试逐题写入 Learning Event 时固化主概念；无主概念的 Event 仍正常记录。（`write_learning_event` 增 concept_id 参数，两条作答路径传入）
- [x] Desktop 在习题生成/采用与作答前界面展示可访问的主概念选择器（含模拟测试逐题作答前的修改入口），作答后展示只读归属；中文与英文文案同步。（新 `QuizConceptField` 共用组件：QuizPanel 候选/已采纳列表 + TestQuestionCard 题位；zh/en `record.detail.quiz.concept.*` + 2 错误码）
- [x] 现有无 Concept 的 Quiz 生成、采用、作答和模拟测试流程零回归。（后端全量 559 绿、前端全量 464 绿）
- [x] HTTP 级测试覆盖建议、修改、清空、锁定、跨课程防护、历史题和无 Course Brain 场景；前端用户交互测试覆盖可编辑与只读两态。（test_quizzes 4 新 + test_quiz_tests 1 新；QuizPanel 2 新 + QuizTestPage 1 新）

## 实施备注

- api-types 已 regenerate；错误码已登记 `docs/后端错误码清单.md`。
- 已知口径边缘（评审记录，不改）：已交卷/放弃测试中从未作答的题位，后端仍接受设置（该题永远不会再产生 Event，无证据路径）；前端此时已整体只读。
- 概念在「生成后、作答前」被归档的时效性过滤属工单 04（Mastery 活跃性过滤）范畴。
- 真机验收统一收敛在工单 06 的清单，本票不单列。
