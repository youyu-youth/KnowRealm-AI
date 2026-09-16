# CB-10 — Course Brain 真实页面：替换 mock（map Tab 主页面 + 概览玫瑰图）

**What to build:** map Tab 升级为 Course Brain 主页面（状态栏 + 图谱/列表双视图 + 概念详情面板 + 来源列表 + 来源类型筛选 + 重建入口 + 空态/失败态/过期态）；概览玫瑰图吃真实 Concept Top 分布；`courseDetailInsights.ts` mock 模块整体删除。UI 设计遵循 impeccable skill + DESIGN.md。

**Blocked by:** CB-09。

**Status:** done（2026-09-16，33c12ec）

**前端**

- [x] 状态栏：六态文案 + 构建进度 + 重建按钮（STALE 提示内容已变化）+ 失败重试
  - 实施备注：构建进度=阶段表达（BUILDING 显示「构建中…」+Spinner+禁用按钮）；快照无进度百分比/开始时间字段，按 DESIGN.md「进度不可知时禁止假百分比」降级为阶段名。
- [x] 图谱/列表双视图：ECharts 封装复用（BaseChart/echarts.ts/token.ts），关系图节点=Concept（大小=evidence_count、色=status/importance）、边=CONFIRMED relation；列表视图含出现次数/来源类型徽章
  - 实施备注：节点大小按 schema 注释用 record_count（BrainGraphNodeOut 明文「record_count=图谱节点大小映射」；Concept 无 evidence_count 字段，工单括号系笔误）；色=importance 灰阶（CONFIRMED-only 图内 status 恒同、无信息量）；边宽=evidence_count、stale 边虚线。列表行徽章=候选状态/stale_archivable + AI 提取/用户确认/系统来源徽章。
- [x] 概念详情面板：名称/描述/类型/重要度/出现记录数 + 来源列表（Transcript 时间 mm:ss / Document 页码 / KP / Chat 四类）+ 来源类型筛选
  - 实施备注：concept_type 为自由字符串，常见五值（TERM/PROCESS/PRINCIPLE/METHOD/TOOL）走 i18n，未知值 defaultValue 回落原文。
- [x] 来源跳转（grill Q7 裁决含定位）：Transcript→`/records/$recordId?tab=transcript` 定位 segment（TranscriptPanel 定位增强）；Document→记录文档视图+页码（视图不支持则来源行文本标注页码降级）；KP→知识点面板锚点；Chat→`/chat/$sessionId`
  - 实施备注：TranscriptPanel 的 quote 高亮定位机制原样复用、零改动（工单允许「可扩展则复用」），quote 走 URL highlight 参数定位滚动；无 quote 锚点降级为仅打开转写 tab；KP 为 tab 级跳转（KnowledgePointPanel 无面板内定位机制，本票未新增）；USER_NOTE 锚点同转写降级处理。
- [x] 概览 Tab 玫瑰图：真实 Concept Top 分布（importance/evidence_count 排序）；两处未构建均显示构建引导空态
  - 实施备注：Top 8，importance desc + occurrence_count desc 前端 tiebreak；value=occurrence_count（概念粒度的证据计数，schema 注释同）。
- [x] 删除 mockCourseKnowledgePoints/aggregateCourseKnowledgePoints/buildCourseKnowledgeRelations 及其测试与 i18n mock key（`spaces.courseDetail.mock.*`）
  - 实施备注：mock.* 仅删 nodes 段（唯一活消费者是被删函数链）；chapters/goals/subjects/points 仍被 GPS 卡/信息面板/洞察卡消费、保留。连带删除：translateNodeName（唯一消费者 CourseKnowledgeGraph 已删）、mockKnowledgeNodes（既无消费者的死代码且引用已删 mock.nodes key 成为悬空）+ KnowledgeNode 类型与对应测试；被删组件独占的 i18n `spaces.courseDetail.graph.*`、`spaces.courseDetail.map.*` 段同步清理。
- [x] TranscriptPanel 定位增强（segment 高亮滚动，若 quote 高亮机制可扩展则复用）
  - 实施备注：复用既有机制零改动；formatTimelineTimestamp 抽到 recordPresentation.ts 供来源行复用（TranscriptPanel 本地删除）。
- [x] 亮/暗/窄窗/减少动效验收；组件测试（BaseChart mock 惯例 + MSW）
  - 实施备注：图表色全部经 chartPalette() 读语义 token（亮暗随动）、动效经 prefersReducedMotion、窄窗经 @container 断点；BaseChart 增 onItemSelect 点击回调（off/on 成对清理）；测试 6 用例（六态/双视图/详情/跳转 href/筛选参数/玫瑰图）。

**门禁**

- [x] pnpm test / lint / Prettier / build；提交：`feat(desktop): Course Brain 真实页面替换 mock 图谱（F4 CB-10）`
  - 451/451 全绿（TodoPanel/QuizTests 曾两轮间歇超时，单跑复绿=既有抖动）；code-review 双轴（Standards/Spec）过审：ToggleChip 抽取（chip 类名三处复制硬违规）、STATUS_TONES 穷举键类型、loading 文案纠偏、confirmed 查询 limit 200（图谱节点映射兜底）等 6 项采纳修复。真机验收（亮/暗/窄窗实机观感）留用户侧。
