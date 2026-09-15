# CB-10 — Course Brain 真实页面：替换 mock（map Tab 主页面 + 概览玫瑰图）

**What to build:** map Tab 升级为 Course Brain 主页面（状态栏 + 图谱/列表双视图 + 概念详情面板 + 来源列表 + 来源类型筛选 + 重建入口 + 空态/失败态/过期态）；概览玫瑰图吃真实 Concept Top 分布；`courseDetailInsights.ts` mock 模块整体删除。UI 设计遵循 impeccable skill + DESIGN.md。

**Blocked by:** CB-09。

**Status:** todo

**前端**

- [ ] 状态栏：六态文案 + 构建进度 + 重建按钮（STALE 提示内容已变化）+ 失败重试
- [ ] 图谱/列表双视图：ECharts 封装复用（BaseChart/echarts.ts/token.ts），关系图节点=Concept（大小=evidence_count、色=status/importance）、边=CONFIRMED relation；列表视图含出现次数/来源类型徽章
- [ ] 概念详情面板：名称/描述/类型/重要度/出现记录数 + 来源列表（Transcript 时间 mm:ss / Document 页码 / KP / Chat 四类）+ 来源类型筛选
- [ ] 来源跳转（grill Q7 裁决含定位）：Transcript→`/records/$recordId?tab=transcript` 定位 segment（TranscriptPanel 定位增强）；Document→记录文档视图+页码（视图不支持则来源行文本标注页码降级）；KP→知识点面板锚点；Chat→`/chat/$sessionId`
- [ ] 概览 Tab 玫瑰图：真实 Concept Top 分布（importance/evidence_count 排序）；两处未构建均显示构建引导空态
- [ ] 删除 mockCourseKnowledgePoints/aggregateCourseKnowledgePoints/buildCourseKnowledgeRelations 及其测试与 i18n mock key（`spaces.courseDetail.mock.*`）
- [ ] TranscriptPanel 定位增强（segment 高亮滚动，若 quote 高亮机制可扩展则复用）
- [ ] 亮/暗/窄窗/减少动效验收；组件测试（BaseChart mock 惯例 + MSW）

**门禁**

- [ ] pnpm test / lint / Prettier / build；提交：`feat(desktop): Course Brain 真实页面替换 mock 图谱（F4 CB-10）`
