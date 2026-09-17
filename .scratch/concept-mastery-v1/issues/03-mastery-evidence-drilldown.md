# 03 — 从 Mastery 下钻到每条 Quiz Evidence

**What to build:** 学习者打开某个 Concept 的 Mastery 详情时，可以看到当前算法实际采用的普通 Quiz 与模拟测试逐题 Evidence、得分、发生时间和来源，并跳回相应学习资产；无效、已删除或不参与当前窗口的证据不会冒充计算依据。

**Blocked by:** 02 — 让 Concept 作答形成可见的真实 Mastery.

**Status:** ready-for-agent

- [ ] Concept Mastery 只读详情返回快照、状态、Confidence 分档以及当前算法版本实际采用的有效 Evidence。
- [ ] Evidence 按发生时间倒序，区分普通 Quiz 与模拟测试逐题来源，并提供前端可消费的业务定位信息。
- [ ] 关联软删除 Record、课程不匹配、无主概念、非 Quiz 类型或落在最近 12 条窗口之外的 Evidence 不出现在“参与计算”列表。
- [ ] Concept 已确认但尚无快照时返回 `NOT_ENOUGH_DATA` 空详情，不伪装成 404 或 0%。
- [ ] Knowledge GPS 的 Concept 行可打开详情；详情展示分数、Confidence、Evidence 数量、最近验证时间和 Evidence 列表。
- [ ] 学习者可从 Evidence 跳转到对应普通 Quiz 或模拟测试结果；定位能力不足时保留来源说明和时间，不生成假链接。
- [ ] 已删除来源有明确降级语义，历史事实不被删除或改写，但不参与当前 Mastery。
- [ ] 中文与英文文案、键盘焦点、Dialog/Sheet 滚动边界和空态符合现有桌面组件规范。
- [ ] API 测试覆盖来源类型、排序、窗口截断、删除过滤、跨课程防护和空详情；前端测试通过用户点击完成详情与跳转闭环。

