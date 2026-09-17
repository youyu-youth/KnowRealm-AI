# 02 — 让 Concept 作答形成可见的真实 Mastery

**What to build:** 学习者完成带主概念的 Quiz 作答后，系统通过既有 Event → Evidence 管道异步形成可重建的 Concept Mastery，并在课程 Knowledge GPS 与概览中展示真实状态、Confidence、证据数量、最近验证时间、覆盖率和状态分布；示意章节数据与课程平均分被移除。

**Blocked by:** 01 — 让习题在作答前绑定一个可信主概念.

**Status:** ready-for-agent

- [ ] 新增每个 Concept 唯一的 Mastery 派生快照，只持久化 V1 真实使用的分数、Confidence、Evidence 计数、最近时间、算法版本与更新时间，不提前加入 Forgetting/Transfer/Reasoning 字段。
- [ ] Evidence Builder 将 Event 中已固化的主概念原样写入 Evidence，禁止在消费或重放时通过 Record 内容猜测 Concept；现有一 Event 一 Evidence 约束保持成立。
- [ ] Mastery V1 只消费带主概念和有效得分的 Quiz Evidence；总结确认、知识点确认、交卷事件和 AI synthesis 不改变 Mastery。
- [ ] 算法严格实现规格中的最近 12 条窗口、四条半衰序位权重、有效计数 Confidence 及 `NOT_ENOUGH_DATA / WEAK / LEARNING / STABLE` 状态规则；不使用墙钟衰减或难度加权。
- [ ] Event/Evidence 成功持久化后由既有 Consumer 异步触发 Concept 全量重算，Quiz 业务服务不直接写 Mastery；最多约 30 秒的最终一致性边界保持可观察且不制造同步旁路。
- [ ] 课程 Mastery 只读 API 返回活跃 CONFIRMED Concept 的覆盖率、四类状态数量、可筛选列表与空状态；不返回课程平均掌握度。
- [ ] 少于 3 条有效 Evidence 的 Concept 返回 `NOT_ENOUGH_DATA` 且分数为空；达到阈值后同时返回数值、Confidence 分档、计数及最近验证时间。
- [ ] Knowledge GPS 改为真实 Concept 列表并支持状态筛选，默认排序优先暴露 WEAK、LEARNING 与数据不足项、稳定项靠后；课程概览改为覆盖率与状态分布，当前章级示意数据和模拟掌握度不再出现在这两个入口。
- [ ] UI 使用现有查询、设计令牌和组件体系，覆盖加载、错误、零 Concept、零 Evidence、数据不足和四类状态；中文与英文文案同步。
- [ ] 算法黄金样本直接验证 3 次全对、4 错后 4 对、4 对后 4 错、8 次交替（交替序列以最新一条为错）与 6 错后 6 对的冻结结果。
- [ ] 最高后端测试接缝通过 HTTP 作答、调用 Consumer 单轮入口、再通过 HTTP 查询 Mastery；前端通过课程详情用户交互测试证明真实数据替换示意数据。

