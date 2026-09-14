# 02 — 其余四挂点事件写入

**What to build:** 总结确认、知识点批次确认、模拟测试逐题评分完成、交卷完成四个学习行为各自落学习事件；习题/Todo 批次采纳明确不发事件（既定语义）。完成即四事件 MVP 的写入面全部齐备。

**Blocked by:** 01 — learning-evidence 地基 + 逐题作答事件首通。

**Status:** done

- [x] 总结确认端点事务内落 SUMMARY_CONFIRMED（幂等键 `summary-confirmed:{summary_id}`、occurred_at=确认时刻）
- [x] 知识点候选批次确认事务内落 KNOWLEDGE_CONFIRMED（幂等键 `knowledge-confirmed:{batch_id}`、source=批次）
- [x] 测验逐题评分完成：评分 job 写回尾部同事务落 QUIZ_ANSWERED（幂等键 `quiz-answered:test:{item_id}`、score 取逐题评分、difficulty 取习题难度、occurred_at 取该题作答时刻 answered_at）
- [x] 交卷完成（评分落定处）同事务落 QUIZ_TEST_COMPLETED（幂等键 `quiz-test-completed:{test_id}`、score 取卷面总分、occurred_at=完成时刻）
- [x] 批次采纳（习题/Todo）不产生任何事件（负向断言）
- [x] 四域 HTTP/job 级测试扩展：同事务性、键位正确；测验评分沿用既有崩溃恢复与幂等语义（重评不重发事件）
- [x] 门禁：pytest（--basetemp=.pytest-tmp）、ruff、pyright strict 全绿；openapi 逐字零 diff

## 落地备注（2026-09-14）

- 四挂点为基线波次的存量内联写入，本票全部迁移至 `learning.events.write_learning_event`（票 01 统一函数；幂等键预查跳过 + UNIQUE 兜底），键位/字段与 spec 逐字一致；四事件 MVP 写入面至此全部走统一入口。
- 行为修正一处：测验评分路径 QUIZ_ANSWERED 的 `occurred_at` 原取评分落行时刻，现改取 `item.answered_at`（作答时刻，ADR-0021；交卷「全部作答」闸门保证非空，`created_at` 仍为评分时刻）。其余三挂点字段语义原本即正确。
- KP 并发确认的 `except IntegrityError` 读取现状语义保持不变（真并发竞态由幂等键 UNIQUE 兜底）；`_confirm_event` 读侧 helper 因承载业务流判断（404/丢弃守卫）保留原位。
- 测试扩展：summary/KP 域补 metadata/occurred_at/score 字段断言；测验域补 `occurred_at == answered_at`（评分路径）与 `occurred_at == completed_at`（交卷）断言；todo 域补「生成/采纳/手工 CRUD 零事件」负向断言；quiz 批次采纳负向断言已存在（test_quizzes.py `quiz_events == 0`）；「重评不重发」由既有崩溃恢复用例覆盖。
- 双轴审查结论：spec 轴七项全落实、无超纲、五个实现疑点逐一核实无误（answered_at 非空前提、record_test_answer_event 两调用点等价性、finalize 幂等预查、KP IntegrityError 组合、summary 幂等提前返回）；standards 轴无硬违规，遗留小项——summary/KP 的 event_type 裸字符串（"SUMMARY_CONFIRMED"/"KNOWLEDGE_CONFIRMED"）未收敛为 StrEnum（存量原样搬迁，quiz 域已有枚举先例），留待后续统一，不阻塞。
