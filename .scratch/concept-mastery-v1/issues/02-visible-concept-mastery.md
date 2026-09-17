# 02 — 让 Concept 作答形成可见的真实 Mastery

**What to build:** 学习者完成带主概念的 Quiz 作答后，系统通过既有 Event → Evidence 管道异步形成可重建的 Concept Mastery，并在课程 Knowledge GPS 与概览中展示真实状态、Confidence、证据数量、最近验证时间、覆盖率和状态分布；示意章节数据与课程平均分被移除。

**Blocked by:** 01 — 让习题在作答前绑定一个可信主概念.

**Status:** done

- [x] 新增每个 Concept 唯一的 Mastery 派生快照，只持久化 V1 真实使用的分数、Confidence、Evidence 计数、最近时间、算法版本与更新时间，不提前加入 Forgetting/Transfer/Reasoning 字段。（迁移 0025 `user_concept_mastery`：concept_id 唯一 + 级联清理；分数/置信度可空 0~1 CHECK）
- [x] Evidence Builder 将 Event 中已固化的主概念原样写入 Evidence，禁止在消费或重放时通过 Record 内容猜测 Concept；现有一 Event 一 Evidence 约束保持成立。（`consumer._insert_evidence` 复制 `event.concept_id`，无归属仍为空）
- [x] Mastery V1 只消费带主概念和有效得分的 Quiz Evidence；总结确认、知识点确认、交卷事件和 AI synthesis 不改变 Mastery。（引擎过滤 `evidence_type='QUIZ' AND score IS NOT NULL`；`test_mastery_only_consumes_scored_quiz_evidence_of_live_records` 覆盖非 QUIZ/无分数/无归属）
- [x] 算法严格实现规格中的最近 12 条窗口、四条半衰序位权重、有效计数 Confidence 及 `NOT_ENOUGH_DATA / WEAK / LEARNING / STABLE` 状态规则；不使用墙钟衰减或难度加权。（`learning/mastery.py` 纯函数，零 IO/零 LLM/不读当前日期）
- [x] Event/Evidence 成功持久化后由既有 Consumer 异步触发 Concept 全量重算，Quiz 业务服务不直接写 Mastery；最多约 30 秒的最终一致性边界保持可观察且不制造同步旁路。（消费轮内收拢受影响 Concept，单点失败重试后记 MASTERY_RECOMPUTE_FAILED，不回滚证据、不阻塞水位）
- [x] 课程 Mastery 只读 API 返回活跃 CONFIRMED Concept 的覆盖率、四类状态数量、可筛选列表与空状态；不返回课程平均掌握度。（`GET /api/courses/{course_id}/mastery`，无任何写 API）
- [x] 少于 3 条有效 Evidence 的 Concept 返回 `NOT_ENOUGH_DATA` 且分数为空；达到阈值后同时返回数值、Confidence 分档、计数及最近验证时间。
- [x] Knowledge GPS 改为真实 Concept 列表并支持状态筛选，默认排序优先暴露 WEAK、LEARNING 与数据不足项、稳定项靠后；课程概览改为覆盖率与状态分布，当前章级示意数据和模拟掌握度不再出现在这两个入口。（筛选并入 URL `?tab=gps&mastery=` 可恢复；概览卡显示已确认概念数/证据覆盖率/四态分布）
- [x] UI 使用现有查询、设计令牌和组件体系，覆盖加载、错误、零 Concept、零 Evidence、数据不足和四类状态；中文与英文文案同步。
- [x] 算法黄金样本直接验证 3 次全对、4 错后 4 对、4 对后 4 错、8 次交替（交替序列以最新一条为错）与 6 错后 6 对的冻结结果。（`tests/test_mastery.py` 表驱动，含窗口截断/分档边界/排序稳定性）
- [x] 最高后端测试接缝通过 HTTP 作答、调用 Consumer 单轮入口、再通过 HTTP 查询 Mastery；前端通过课程详情用户交互测试证明真实数据替换示意数据。（`test_http_answer_flows_through_consumer_to_course_mastery`；CourseDetail 概览/GPS 交互 + 筛选 + 错误重试 + 空态引导）

## 实施备注

- 迁移 0025 后 13 个测试文件的 `user_version` 断言 24→25 已同步；OpenAPI 契约已 regenerate。
- 快照中的 Evidence 计数为最近 12 条窗口内计数（与工单 03 下钻同口径）；超过 12 条后计数封顶 12。
- 「后台计算中」未单列状态（spec Desktop 段列出该态，本票清单未含）：证据落库与重算在同一消费轮内先后完成，没有独立任务态可供查询；≤30 秒窗口内 UI 呈现上一次快照或「数据不足」，属最终一致性边界，待工单 06 全链路验收复核口径。
- 概览「AI 助手 · 课程洞察」仍使用章级示意名称（非掌握度百分比）；票面「两个入口」指 Knowledge GPS 与掌握度概览卡，洞察卡不在本票范围。
- 真机验收统一收敛在工单 06 的清单，本票不单列。
