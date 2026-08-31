# 04 — 交卷评分链路与结果页完整闭环

**What to build:** 测验的最后一段：显式交卷（确认对话框）→ 客观题已判 + 简答题后台 AI 评分（一卷一评分 job、逐题调 LLM）→ 评分完成出结果页——得分（×100）、逐题对错、简答评分依据与置信度展示、低置信"建议人工复核"只读标记、评分失败题"未计分"标注（排除出分母）、填空逐空对错、成绩摘要侧栏（对/错/半对/未计分/待复核），批改展示在三档形式下均可渲染；支持重新评分（GRADING_FAILED）与再考一张。15 号功能的验收线在本票全绿。

**Blocked by:** 03（作答闭环与交卷前置）。

**Status:** done

**深度参考:** `.scratch/function-plans-introduction/15-mock-test.md`（状态机、评分 schema、事件键位、失败语义、配置常量）；原型 `apps/desktop/src/pages/prototype-mock-test.tsx`（结果页批改块/摘要侧栏形态基线）

- [x] 交卷 API：全部已作答才可交（409 否则）→ 状态 IN_PROGRESS→GRADING；无简答题时同步判分直达 COMPLETED
- [x] 简答评分 job：一卷一 job、逐题 LLM 评分；`ai_grade_json` 必存 verdict（CORRECT/PARTIAL/WRONG）+ score（0~1）+ confidence（0~1）+ rationale；pydantic 松一致性校验（WRONG⇒0、PARTIAL⇒开区间、CORRECT⇒>0）；PARTIAL 仅简答
- [x] 单题评分失败：错误码入 `ai_grade_json`、score/result 留 NULL、整卷照常 COMPLETED、**排除出整卷分母**（结果页标注 N 题未计分）、该题不落 QUIZ_ANSWERED
- [x] `QUIZ_TEST_COMPLETED` 事件：键 `quiz-test-completed:{test_id}`、COMPLETED 事务内落、score/duration_ms/metadata（题数、题型分布、未计分数）、幂等
- [x] job 崩溃 → GRADING_FAILED，可重新评分（已评成功题跳过、事件键保证不重复）
- [x] 前端：交卷确认、评分中轮询态、结果页完整批改（上述全部标记与摘要侧栏）、三档形式下批改渲染、放弃态灰显、再考一张
- [x] 低置信阈值 `SHORT_ANSWER_REVIEW_THRESHOLD` 为模块常量（chat.py 先例，注释标 #51 待配置体系统一后迁 .env），不进用户 UI
- [x] 评分 model 复用 quiz 域注入与埋点链路：prompt 与输出全文不进日志，token/latency/model 照记
- [x] 整卷分 = 已计分题等权平均（0~1 入库，UI ×100 显示）
- [x] 15 工单验收线逐条自验（自动化门禁内）；**用户真机验收清单单列于此票，回写时不代勾**
- [x] pytest（评分 job/失败语义/事件/重评）与前端 MSW（评分中/结果批改/低置信标记）双侧绿

## 实现备注（2026-08-31 关票）

- **评分 model 注入**：`call_quiz_model` 硬编码 QuizBatch 输出 schema，无法字面复用；按同一模式新增 `ShortAnswerGrade` schema + `OpenAiCompatibleQuizGradingModel` + `call_quiz_grading_model`（graph_name=quiz / graph_node=grade，底层共用 `_call_structured_model` 与 `write_llm_call_log` 埋点），`create_app(quiz_grading_model=...)` 注入与 quiz_model 同构。
- **JobRunner 放行课程级 job**：`claim_one` 原只领取 `record_id` 非空的 job；QUIZ_GRADING job 天然无 record 主体（`record_id` NULL、test_id 走 input_json），runner 侧 record 坐标对无 record 任务传空串，ctx 的 `record_id` 承载 test_id。record 域 worker 候选恒有 record_id，行为不变。
- **答案揭示门控**：`correct_answer` / `explanation` 仅在 COMPLETED / GRADING_FAILED 揭示（作答期与 GRADING 期恒 null，防泄漏未来卷——同题可再抽入新卷）；ABANDONED 亦不揭示。
- **归档第三道闸门语义**：评分 job 领取时课程已归档/卷面失效/供应商指纹变化 → job 静默 CANCELLED 且卷面翻 GRADING_FAILED（归档期读卷面本就 409，未来解档后可重新评分出分）。
- **单题落库粒度**：一题一事务（崩溃后已落题不重评）；QUIZ_ANSWERED 与题目评分同事务落（天然幂等）；重评只评 `result IS NULL` 的简答题。
- **前端轮询**：GRADING 态 useQuery `refetchInterval` 1.5s，其余状态停轮；离开作答态同步课程页列表缓存。

## 用户真机验收（不代勾）

- [ ] 交卷确认对话框 → 评分中轮询 → 结果页出现的完整链路体感（简答评分完成的等待时长）
- [ ] 结果页批改阅读体验：三档形式下批改块、成绩摘要侧栏、简答评分依据/置信度、低置信"建议人工复核"标记观感
- [ ] 评分失败题"未计分"标注与整卷得分（已计分题平均 ×100）是否符合预期
- [ ] 重新评分（人为断网构造 GRADING_FAILED）与"再考一张"流程
