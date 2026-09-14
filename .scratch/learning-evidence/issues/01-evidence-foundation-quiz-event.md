# 01 — learning_evidence 地基 + 逐题作答事件首通

**What to build:** 学习者每答一道已采纳习题，这个学习行为被同事务记录为一条带幂等键的学习事件（含对错/自评分数、难度、作答时刻）——动作失败不落行、重复触发不重复。同时为后续证据落库建好数据地基。这是 A3 的 tracer bullet 第一发：从答题端点到 learning_events 落行的完整路径。

**Blocked by:** None — can start immediately.

**Status:** done

- [x] 迁移 0021 落地：learning_evidence 表按数据模型 §4.5 字段（event_id 唯一约束、weight/confidence 0~1 CHECK、索引 (concept_id, occurred_at desc)）；user_version 20→21，全部硬编码断言同步（以 grep 实测处数为准）
- [x] 新 learning 域模块就位（feature-first；`__init__` 只写 docstring 落位规则）；learning_events 模型维持 record 域现位不迁移
- [x] learning 域提供统一事件写入函数：传入业务事务会话、幂等键冲突静默跳过、schema_version=1、metadata_json 只记决策性上下文（题型/模式/课程等）
- [x] 逐题模式作答挂点：答题端点成功事务内落 QUIZ_ANSWERED（幂等键 `quiz-answered:{quiz_id}`、score 由 answer_result 映射 1/0 含简答自评、difficulty 取习题难度、occurred_at=作答时刻）
- [x] HTTP 级测试：动作成功才落行、失败/校验拒绝不落行（同事务性）、幂等重放不重复、字段取值正确
- [x] 门禁：pytest（--basetemp=.pytest-tmp）、ruff、pyright strict 全绿；openapi 逐字零 diff

## 落地备注（2026-09-14）

- 逐题作答挂点在基线波次已有内联写入（`_answer_event`），本票将其迁移至 learning 域统一写入函数 `write_learning_event`，并补齐两处行为缺口：score 由 answer_result 映射 1.0/0.0（原为 NULL）；简答自评事件 occurred_at 取 `quiz.answered_at`（作答时刻，与票 02 测验键位语义一致），created_at 仍为自评落行时刻。
- user_version 硬编码断言实测 12 处（含元组式 `== (20,)` 9 处 + `== 20` 3 处），全部同步 21。
- 新增 `tests/test_learning.py`：0021 迁移表结构/索引/无软删列 + weight 越界与 event_id 重复的约束行为；HTTP 级事件断言扩展进既有 `tests/test_quizzes.py` 五个用例（同事务回滚触发器用例原样保留通过）。
- 其余三挂点（总结确认/知识点批次/模拟测试两键位）仍为存量内联写入，票 02 迁移至统一函数。
