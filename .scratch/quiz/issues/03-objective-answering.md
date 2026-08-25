# 03 — 客观题作答（选择 / 判断）

**What to build:** 对 ACTIVE 批次的题逐题作答客观题（单选选择题、判断题）：提交即自动判分、展示答案与解析、一题一答锁定、可中断续答；每题在判分时刻与行上作答同事务落一条幂等的 QUIZ_ANSWERED 事件。（契约细节见 `.scratch/quiz/spec.md`）

**Blocked by:** 02 — 批次采纳与重新生成联动

**Status:** completed

- [x] 作答端点：提交选择题 / 判断题作答 → 下标精确匹配判分 → 行上作答三列更新 + QUIZ_ANSWERED **同事务**落表（source_type=QUIZ_QUESTION、source_id=quiz_id、幂等键 `quiz-answered:{quiz_id}`、metadata={batch_id, question_type, generated_from_summary_id}、result 二态、difficulty 从题目行带出、score / duration_ms / concept_id 恒空、**用户所选答案不进事件**）
- [x] 重复提交幂等返回现状，不重复落事件；已答再提交不改变结果
- [x] 一题一答锁定：行上 answered_at 非空即只读；只有 ACTIVE 批次的题可作答（DRAFT / SUPERSEDED 题 409）
- [x] 中断续答：逐题即时落库，重进页面后作答态完整
- [x] 换代场景：转写编辑使旧 Summary 置 SUPERSEDED 后，ACTIVE 批照常作答且事件落表
- [x] 桌面端：单选 radio / 对错二选交互、提交即时判分反馈、已答展示答案与解析的锁定只读态
- [x] 后端 ASGI 全栈测试与桌面 MSW 测试通过（含判分正确性、幂等、锁定、续答、换代可作答）
