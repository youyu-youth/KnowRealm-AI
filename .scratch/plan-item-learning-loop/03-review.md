# 03 双轴代码评审

固定基点：`527a3c6`。评审范围为本票 WIP（暂存与工作区，含 `git add -N` 新文件），规格为 03 工单、父规格、共用约束及 ADR-0029。按 code-review 技能由两个只读代理分别评审；测试由主会话执行，证据见 [实施记录](./03-implementation.md)。

## Standards

最终结论：通过。初评 2 项硬违规 + 5 项判断性提示，全部处置完毕。

- 模块方向成环（quiz.test_service 反向 import learning_plan.models）→ 改为组合根注入：quiz 暴露 `register_plan_round_guard`，learning_plan.practice_round 注册复用 `load_context` 的实现，依赖恢复 learning_plan → quiz 单向（02 的 authorizer 注册先例），同时消除了与 `load_context` 的重复三态判定。
- `PRACTICE_ITEM_UNAVAILABLE` 归属列失真 → 清单补 quiz。
- 判断性项：`authority` 假参数删除（评审两轴共同指出）；事件 `source_id` 混装实体 id → `FrozenFace` 增加 `quiz_id` 快照，原题物理删除后追溯与事件身份稳定；`? true : false` 与返回链接重复 className 已收敛。`item.quiz_id ?? ""` 空串哨兵保留（planMode 下概念字段只读不消费查询）。

本轴最终未解决项 0。评审代理未运行测试；门禁由主会话执行。

## Spec

最终结论：通过。初评 3 项缺失/部分实现 + 2 项可能有误，处置如下。

- 建卷提交处「执行身份及有效授权」重验：建卷为纯确定性同步事务（题目在 02 已固化），无后台执行与取消窗口可拦截；页面与 Agent 的授权差异由受控 operation 档位在提交处执法（与 02 的 L1 语义一致），假 `authority` 参数已删除并在实施记录声明边界。
- 重放参数变化不拒绝 → 命中 `request_id` 后比对要求修订，不一致返回 `PRACTICE_REQUEST_CONFLICT`（02 同口径）。
- 普通模拟测试列表混入 PLAN 轮次 → `list_for_course` 过滤 `mode != PLAN`，测试断言列表为空。
- 并发双入口「返回同一轮」→ 部分唯一索引拦截的败方在路由层重查返回同一轮（无轮次时如实透出冲突），新增针对性测试；五题型中单选/多选/填空与判断共用同一客观判分函数，由既有 MOCK 回归覆盖，实测以简答（评分链）+ 判断（同步完成链）两型贯通全路径；部分成绩与分母展示已在前端测试覆盖。
- `grading_complete` 把 GRADING_FAILED 判 True 的自相矛盾 → 收敛为仅 COMPLETED（GRADING_FAILED 必有未评分题，配合未评分提示与 04 的重试入口）。
- `plan_item_id` ON DELETE CASCADE 属未声明决策 → 核实 goal/plan 行的物理删除仅课程物理删除链可达，且该链被 `quiz_tests.course_id` 既有 FK 阻塞（历史债，不在本票范围）；软删与计划换代的轮次可见性沿查询期过滤。已在实施记录登记口径。

未揭示答案三处投影（practice 轮次、quiz-tests detail、Agent 回执）均确认不泄露；失效来源标注为纯文本无跳转。

两个轴最终各 0 项未解决问题；没有跨轴合并或以一轴通过代替另一轴。真实模型质量、Tauri/WebView2 与系统缩放仍留 05。
