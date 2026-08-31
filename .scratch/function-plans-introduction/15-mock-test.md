# 15 - 模拟测试

> Wave: B ｜ PRD: §4.4.2 模拟测试行 ｜ 决策引用: #20 #33 #43 #46 #51 ｜ 2026-08-31 grill 定稿（Groundedness 样本拆至 20）

## 功能描述 / 目标

课程级"期末卷"式测验：从课程已采纳（ACTIVE）习题随机抽题组卷，逐题作答、交卷评分、留痕。核心是简答题 AI 语义评分及其可信度边界——**confidence 仅作 UI 复核标记，禁止参与掌握度计算**（#33）。

## 功能范围

**做**：
- 入口：课程详情页第三个 tab「模拟测试」（`courseTabs.ts` 联合类型 + `spaces.$courseId` search 校验 + `spaces.detail.tabs.*` / `spaces.simulations.*` 文案），历史测试列表抄 `CourseRecordsPanel` 骨架
- 组卷：题量 5/10/20 档 + 题型多选（五种，见下），从课程题库随机抽取；存量不足抽全部并提示，存量为零给空态
- **题型五种**：单选、多选、判断、填空、简答（2026-08-31 prototype 二轮定稿，不再受 08 记录习题三型约束）。**题目来源已定稿（A 案）= 08 习题生成直接扩五型**——`question_type` 枚举扩展 + 迁移 CHECK 同步，题库本身富题型，逐题作答模式同步受益；组卷保持纯 DB 抽题不引入 LLM。判分规则：多选全对才得分（1.0/0.0）；填空逐空判分（部分空对=PARTIAL，按空比例计分）；简答 AI 语义评分
- **卷面结构（prototype 二轮定稿）**：独立路由页（`/spaces/$courseId/tests/$testId` 风格），单一卷面内置**三档展示形式随切**（单题=一页一题+键盘←→ / 分段=大题步骤条一屏一段 / 整卷=连续滚动试卷文档），左侧答题卡常驻（跳题/进度/交卷；结果态变成绩摘要），逐题提交一题一答不可改，全部答完才可交卷（确认对话框）；中断重进继续作答；可放弃（ABANDONED，不落事件）
- **前端实现路线（2026-08-31 调查定稿）**：自建编排层 + 复用 shadcn 控件（radio-group/checkbox/input/textarea/tabs/dialog 均已有），题型按 schema 分发渲染（扩展新题型=加分支组件）；不引入外部试卷框架（SurveyJS 调查结论：仅控件观感可经 token 适配器对齐，作答语义/批改层/编排层三处错配，详见对话记录）。重新评估触发条件：矩阵/拖拽排序类题型、或需要用户可视化自建表单设计器
- 客观题提交即判（多选 1.0/0.0、填空按空比例）；简答题 JobRunner 后台评分：一卷一 job，逐题调 LLM
- 简答评分输出 `verdict`（CORRECT/PARTIAL/WRONG）+ `score`（0~1）+ `confidence`（0~1）+ `rationale`，全文存 `ai_grade_json`；pydantic 松一致性校验（WRONG⇒score=0、PARTIAL⇒0<score<1、CORRECT⇒score>0），PARTIAL 仅简答题
- 低置信复核：`confidence < SHORT_ANSWER_REVIEW_THRESHOLD`（模块常量，chat.py 先例；#51 的 .env 意图待配置体系统一后迁移）→ 只读标记"建议人工复核"，不提供人工改判（#20 仅到"标记"）
- 事件：QUIZ_ANSWERED（客观题提交即落、简答题评分成功才落，键 `quiz-answered:test:{item_id}`）+ QUIZ_TEST_COMPLETED（COMPLETED 事务内落，键 `quiz-test-completed:{test_id}`，score/duration_ms/metadata 记题数、题型分布、未计分题数）
- 结果页：得分（0~1 已计分题等权平均，UI ×100 显示）、逐题对错、评分依据展示、低置信标记、"N 题未计分"标注；批改展示随三档形式走
- ARCHIVED 课程护栏三道闸门（read blocked → 开始测试 409 → 评分 job 领取再校验），与 summary/KP/quiz/todo 既有模式一致
- 评分 model 复用 `app.state.quiz_model` 注入与 `call_quiz_model` / `write_llm_call_log` 埋点链路（token/latency/model 照记，prompt 与输出全文不进日志）

**不做**：
- 人工改判/覆盖 AI 分数（数据模型无字段）
- 单题重评（失败题留痕于 `ai_grade_json`，重考新卷即可——模拟测试可反复考）
- 并发进行中测试的限制（允许多张，不加约束）
- 自适应选题（P5，F13）、Transfer Challenge（P5）、错题本自动重练
- Groundedness 评测样本（已拆至 20-quiz-groundedness.md）
- 外部试卷/问卷框架（SurveyJS 等，调查已否决）

## 核心业务流程

课程页模拟测试 tab → 组卷对话框（题量+题型）→ 创建 quiz_test（IN_PROGRESS）→ 独立路由页逐题作答 → 全部答完 → 交卷确认 → 客观题即判 + 简答评分 job（GRADING）→ 评分完成（COMPLETED）→ 结果页 + QUIZ_TEST_COMPLETED 落表

### 状态机

- `IN_PROGRESS → GRADING → COMPLETED`
- `IN_PROGRESS → ABANDONED`（用户放弃，不落事件）
- `GRADING → GRADING_FAILED`（job 崩溃被 `recover_running_to_failed` 回收）→ 重新评分（重建 job，已评成功题跳过，事件幂等键保证不重复）→ `GRADING`

### 关键业务规则

- **测试作答只写 `quiz_test_items`，永不触碰 `quizzes.user_answer_json / answer_result / answered_at` 三列**；已答过的题可再进卷；同课程可多次测试
- 单题评分失败：score/result 留 NULL、`ai_grade_json` 记错误码，不阻塞整卷 COMPLETED；**失败题排除出整卷分母**并在结果页标注
- 简答题评分失败**不落 QUIZ_ANSWERED**（与逐题模式"自评完成才落"同构）；重评成功后再落，键位无冲突
- 抽题仅 `generation_status=ACTIVE`，DRAFT/SUPERSEDED 不进卷
- `quiz_tests.record_id` 恒 NULL（课程级，列留未来形态）

### API 草案

- `POST /api/courses/{course_id}/quiz-tests`（组卷）
- `GET /api/courses/{course_id}/quiz-tests`（列表）
- `GET /api/quiz-tests/{test_id}`（详情+题目）
- `POST /api/quiz-tests/{test_id}/answers`（逐题提交）
- `POST /api/quiz-tests/{test_id}/submit`（交卷→触发评分）
- `POST /api/quiz-tests/{test_id}/abandon`（放弃）
- `POST /api/quiz-tests/{test_id}/regrade`（重新评分，GRADING_FAILED 态）

## 数据与迁移

- 新迁移建 `quiz_tests` + `quiz_test_items`（数据模型 v2.2 P1 补表，当前迁移只到 0011；`(test_id, sequence_no)` 唯一）
- 扩 `ProcessingJobType` 评分枚举 + 同步迁移 0010 的 job_type CHECK（注意顶 6 处 user_version 断言）
- 后端 schema 变更后重跑 `packages/api-types` 类型生成

## 前置依赖

- 08（题库存在，且需增量扩展五型题型生成：`question_type` 枚举 + 生成 prompt/校验 + 迁移 CHECK；作为 15 实现范围的一部分先行落地）

## 原型参考（throwaway）

- `apps/desktop/src/pages/prototype-mock-test.tsx`：卷面二轮原型（三档展示形式 + 五题型作答/批改 + 答题卡 + 入口/组卷对话框），经用户两轮反馈验证后定稿上述结构；实现时按定稿语义重写为正式代码，原型本身不进 main（按 prototype 流程移至 throwaway 分支留档）
- 卷面视觉基调：连续纸面 + 基线分隔（DESIGN.md Zero Card Chrome），答题卡/成绩摘要=左侧常驻栏，批改块用 `*-soft`/`*-foreground` 语义色

## 验收标准（出口线）

- [ ] 课程页 tab 组卷作答交卷 → 客观题自动判分、简答题 AI 评分显示评分依据
- [ ] 人为构造低置信简答 → 出现"建议人工复核"标记（confidence 只读展示，不参与任何计算）
- [ ] QUIZ_TEST_COMPLETED 事件落表且幂等（`quiz-test-completed:{test_id}`）
- [ ] 测验中断后重进继续作答，不产生重复事件
- [ ] 评分失败题不阻塞整卷完成，结果页标注未计分
- [ ] ARCHIVED 课程无法开始模拟测试
- [ ] （用户真机验收）卷面交互与结果页体验
