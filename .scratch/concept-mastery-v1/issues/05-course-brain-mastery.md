# 05 — 在 Course Brain 中查看非侵入式 Mastery 状态

**What to build:** 学习者浏览 Course Brain 图谱时，可以在不破坏 Concept/Relation 视觉语义的前提下看到每个 Concept 的 Mastery 状态，并从节点进入已经完成的 Mastery Evidence 详情；亮色、暗色和窄窗口都保持清晰可用。

**Blocked by:** 02 — 让 Concept 作答形成可见的真实 Mastery; 03 — 从 Mastery 下钻到每条 Quiz Evidence.

**Status:** done

- [x] Course Brain 通过现有只读 Mastery 查询组合学习者状态，不扩张知识结构服务的写入职责，也不创建前端第二份持久化状态。
- [x] 图谱节点使用小型状态标记、Tooltip 或辅助信息表达 `NOT_ENOUGH_DATA / WEAK / LEARNING / STABLE`，节点主颜色继续服务于 Concept/Relation 结构。
- [x] 图谱、列表和 Concept 详情对同一 Mastery 状态保持一致；点击入口复用既有 Evidence 详情能力。
- [x] 未构建 Course Brain、零 CONFIRMED Concept、后台 Mastery 尚未形成、查询失败与 Archived Concept 均有诚实降级。
- [x] UI 按 `impeccable` 规范打磨层级、密度、对比度与动效，不引入新图表依赖或脱离设计令牌的颜色。
- [x] 亮色、暗色、窄窗口、键盘操作、Tooltip/详情焦点和 `prefers-reduced-motion` 均可用；固定工作区与局部滚动约束保持不变。
- [x] 前端用户交互测试覆盖状态标记、Tooltip、详情入口、空态和错误态，并证明 Course Brain 原有构建、审核、来源与关系交互零回归。

## 实施备注（2026-09-18）

- **查询层组合（单一数据源）**：`CourseBrainTab` 增 `useCourseMastery(course.id)`（与概览知识 GPS 卡共用同一 queryKey，无新增请求面），派生 `masteryByConceptId` Map 作为图谱、列表、详情三处唯一取值处；零后端改动、零新持久化状态。
- **图谱非侵入标记**：`CourseBrainGraph` 新增可选 `masteryByConceptId`——节点 datum 挂 `masteryStatus`，标签经 ECharts rich text 渲染状态点（`{dot_STABLE|●}` 等），tooltip 追加「掌握状态：{{status}}」文字行；节点主色（重要度灰阶）与边语义零改动。状态点颜色经 `cssVar` 走主题 token 计算值（canvas 读不了 Tailwind 类），映射 `masteryDotCssVars` 落在 `masteryStatus.ts` 与 `masteryDotClassNames` 同源维护。
- **列表与详情**：列表 CONFIRMED 行复用 `ConceptMasteryBadge`（文字徽章）；CANDIDATE 行永不显示（候选不进 Mastery）。详情 aside 掌握行 = Badge + 百分比 + 「掌握详情」按钮，点击打开既有 `ConceptMasteryDetailDialog`（Evidence 下钻、来源跳转零改动复用）。
- **诚实降级矩阵**：未构建/BUILDING/FAILED 相位无工作区即无掌握 UI；mastery 加载中或查询失败 → 三处均无标记（不伪造状态，失败不阻塞 brain 本体功能）；零 CONFIRMED → 既有空态；Archived 概念本就退出 brain 列表与 mastery API，无入口。
- **审查结论（两轴）**：无硬违规、无 scope creep；已修：状态→色映射收敛到 `masteryStatus.ts`（消双份漂移风险）、rich 块由 `masteryStatuses` 派生、Tab 内重复 `get()` 收敛局部量。图谱 canvas 键盘不可达为沿袭既有限制（键盘用户走列表视图，行为等价）。
- **既有覆盖说明**：「后台 Mastery 尚未形成」由列表用例的等待断言覆盖（concepts 与 mastery 两查询并发返回，pending 期间无标记、数据到齐后徽章出现 = spec「允许短暂后台延迟但最终自动出现」）。

## 用户真机验收（不代勾）

- [ ] 图谱节点状态点：亮色/暗色两主题下四态颜色可辨，节点主色仍表达重要度灰阶。
- [ ] 节点 tooltip 含「掌握状态」行；点击节点打开详情面板，「掌握详情」进入 Evidence 弹窗并跳回习题/模拟测试。
- [ ] 列表视图 CONFIRMED 行显示状态徽章（含「数据不足」），候选行无徽章。
- [ ] mastery 查询失败（如临时异常）时图谱/列表可用且无伪造掌握标记。
- [ ] 窄窗口（约 1100px）下图谱/列表 + 详情双栏布局不溢出；`prefers-reduced-motion` 下图谱动画关闭。
- [ ] 键盘路径：Tab 进入列表行 → Enter 打开详情 → 掌握详情按钮可达（canvas 图谱本身不可 Tab 为既有行为）。
