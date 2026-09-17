# 05 — 在 Course Brain 中查看非侵入式 Mastery 状态

**What to build:** 学习者浏览 Course Brain 图谱时，可以在不破坏 Concept/Relation 视觉语义的前提下看到每个 Concept 的 Mastery 状态，并从节点进入已经完成的 Mastery Evidence 详情；亮色、暗色和窄窗口都保持清晰可用。

**Blocked by:** 02 — 让 Concept 作答形成可见的真实 Mastery; 03 — 从 Mastery 下钻到每条 Quiz Evidence.

**Status:** ready-for-agent

- [ ] Course Brain 通过现有只读 Mastery 查询组合学习者状态，不扩张知识结构服务的写入职责，也不创建前端第二份持久化状态。
- [ ] 图谱节点使用小型状态标记、Tooltip 或辅助信息表达 `NOT_ENOUGH_DATA / WEAK / LEARNING / STABLE`，节点主颜色继续服务于 Concept/Relation 结构。
- [ ] 图谱、列表和 Concept 详情对同一 Mastery 状态保持一致；点击入口复用既有 Evidence 详情能力。
- [ ] 未构建 Course Brain、零 CONFIRMED Concept、后台 Mastery 尚未形成、查询失败与 Archived Concept 均有诚实降级。
- [ ] UI 按 `impeccable` 规范打磨层级、密度、对比度与动效，不引入新图表依赖或脱离设计令牌的颜色。
- [ ] 亮色、暗色、窄窗口、键盘操作、Tooltip/详情焦点和 `prefers-reduced-motion` 均可用；固定工作区与局部滚动约束保持不变。
- [ ] 前端用户交互测试覆盖状态标记、Tooltip、详情入口、空态和错误态，并证明 Course Brain 原有构建、审核、来源与关系交互零回归。

