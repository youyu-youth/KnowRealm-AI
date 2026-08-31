# 04 — 交卷评分链路与结果页完整闭环

**What to build:** 测验的最后一段：显式交卷（确认对话框）→ 客观题已判 + 简答题后台 AI 评分（一卷一评分 job、逐题调 LLM）→ 评分完成出结果页——得分（×100）、逐题对错、简答评分依据与置信度展示、低置信"建议人工复核"只读标记、评分失败题"未计分"标注（排除出分母）、填空逐空对错、成绩摘要侧栏（对/错/半对/未计分/待复核），批改展示在三档形式下均可渲染；支持重新评分（GRADING_FAILED）与再考一张。15 号功能的验收线在本票全绿。

**Blocked by:** 03（作答闭环与交卷前置）。

**Status:** ready-for-agent

**深度参考:** `.scratch/function-plans-introduction/15-mock-test.md`（状态机、评分 schema、事件键位、失败语义、配置常量）；原型 `apps/desktop/src/pages/prototype-mock-test.tsx`（结果页批改块/摘要侧栏形态基线）

- [ ] 交卷 API：全部已作答才可交（409 否则）→ 状态 IN_PROGRESS→GRADING；无简答题时同步判分直达 COMPLETED
- [ ] 简答评分 job：一卷一 job、逐题 LLM 评分；`ai_grade_json` 必存 verdict（CORRECT/PARTIAL/WRONG）+ score（0~1）+ confidence（0~1）+ rationale；pydantic 松一致性校验（WRONG⇒0、PARTIAL⇒开区间、CORRECT⇒>0）；PARTIAL 仅简答
- [ ] 单题评分失败：错误码入 `ai_grade_json`、score/result 留 NULL、整卷照常 COMPLETED、**排除出整卷分母**（结果页标注 N 题未计分）、该题不落 QUIZ_ANSWERED
- [ ] `QUIZ_TEST_COMPLETED` 事件：键 `quiz-test-completed:{test_id}`、COMPLETED 事务内落、score/duration_ms/metadata（题数、题型分布、未计分数）、幂等
- [ ] job 崩溃 → GRADING_FAILED，可重新评分（已评成功题跳过、事件键保证不重复）
- [ ] 前端：交卷确认、评分中轮询态、结果页完整批改（上述全部标记与摘要侧栏）、三档形式下批改渲染、放弃态灰显、再考一张
- [ ] 低置信阈值 `SHORT_ANSWER_REVIEW_THRESHOLD` 为模块常量（chat.py 先例，注释标 #51 待配置体系统一后迁 .env），不进用户 UI
- [ ] 评分 model 复用 quiz 域注入与埋点链路：prompt 与输出全文不进日志，token/latency/model 照记
- [ ] 整卷分 = 已计分题等权平均（0~1 入库，UI ×100 显示）
- [ ] 15 工单验收线逐条自验（自动化门禁内）；**用户真机验收清单单列于此票，回写时不代勾**
- [ ] pytest（评分 job/失败语义/事件/重评）与前端 MSW（评分中/结果批改/低置信标记）双侧绿
