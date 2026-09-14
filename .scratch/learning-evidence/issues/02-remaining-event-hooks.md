# 02 — 其余四挂点事件写入

**What to build:** 总结确认、知识点批次确认、模拟测试逐题评分完成、交卷完成四个学习行为各自落学习事件；习题/Todo 批次采纳明确不发事件（既定语义）。完成即四事件 MVP 的写入面全部齐备。

**Blocked by:** 01 — learning-evidence 地基 + 逐题作答事件首通。

**Status:** ready-for-agent

- [ ] 总结确认端点事务内落 SUMMARY_CONFIRMED（幂等键 `summary-confirmed:{summary_id}`、occurred_at=确认时刻）
- [ ] 知识点候选批次确认事务内落 KNOWLEDGE_CONFIRMED（幂等键 `knowledge-confirmed:{batch_id}`、source=批次）
- [ ] 测验逐题评分完成：评分 job 写回尾部同事务落 QUIZ_ANSWERED（幂等键 `quiz-answered:test:{item_id}`、score 取逐题评分、difficulty 取习题难度、occurred_at 取该题作答时刻 answered_at）
- [ ] 交卷完成（评分落定处）同事务落 QUIZ_TEST_COMPLETED（幂等键 `quiz-test-completed:{test_id}`、score 取卷面总分、occurred_at=完成时刻）
- [ ] 批次采纳（习题/Todo）不产生任何事件（负向断言）
- [ ] 四域 HTTP/job 级测试扩展：同事务性、键位正确；测验评分沿用既有崩溃恢复与幂等语义（重评不重发事件）
- [ ] 门禁：pytest（--basetemp=.pytest-tmp）、ruff、pyright strict 全绿；openapi 逐字零 diff
