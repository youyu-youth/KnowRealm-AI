# 学习统计

Status: ready-for-agent

## Problem Statement

KnowRealm 的学习闭环已经能捕获、转写、总结、练题、问答，但用户看不到自己的学习全貌：学了多少小时、攒了多少记录和课程、AI 帮我做了多少事、练了多少题、问了多少问题——这些数字散在各业务表里，UI 上没有任何聚合展示。PRD §4.1（#54）为此规划了「今日」页底部统计卡片区（Wave B）。

2026-09-07 grill 定稿两处与此前的差异：**七项指标口径全部定死**（含"删除后回落"的一致性原则）；**趋势图表从「不做」拉进本票且直接用真数据**（按捕获日聚合的学习时长趋势，数据源今天就存在，否决了"假数据先行"方案）。完整决策见 `.scratch/function-plans-introduction/17-learning-stats.md` 与本 spec。

## Solution

今日页底部新增**统计带**（一条分节，非卡片仪表盘）：上半是「学习趋势」折线面积图（echarts，近 7 天 / 近 30 天切换，按捕获日聚合音频时长），下半是六格指标带（单行、细分隔线相隔）：累计学习时长 / 记录数 / 课程数 / AI 总结次数 / 习题（已作答 / 生成）/ 问答轮次。

全部数字由业务表实时聚合（不建事实表、不缓存），打开应用即见、无需主动刷新。删除记录或课程后，其名下指标同步回落；空库显示全 0 与平线，不空白不说谎。

## User Stories

1. As an 学习者, I want to 打开今日页就在底部看到统计带, so that 无需任何点击即了解自己的学习全貌。
2. As an 学习者, I want to 看到累计学习时长（X 小时 Y 分）, so that 知道自己在这些课上投入了多少时间。
3. As an 学习者, I want to 看到学习记录总数, so that 感知积累的厚度。
4. As an 学习者, I want to 看到课程总数（含已归档）, so that 归档的课不算没学过。
5. As an 学习者, I want to 看到 AI 总结次数（含重新生成版本）, so that 知道 AI 帮我消化了多少次内容。
6. As an 学习者, I want to 看到习题已作答与已生成的双数, so that 一眼看出练习进度（80 / 120）。
7. As an 学习者, I want to 看到问答轮次, so that 知道自己向 AI 提了多少问题。
8. As an 学习者, I want to 看到近 7 天学习时长趋势折线, so that 回顾最近一周的学习节奏。
9. As an 学习者, I want to 切换查看近 30 天趋势, so that 拉长周期看趋势。
10. As an 学习者, I want to 没有学习的日子趋势如实为 0, so that 图表不粉饰、可信。
11. As an 学习者, I want to 删除一条记录后其名下指标同步回落, so that 统计与实际资产一致、不留幽灵数字。
12. As an 学习者, I want to 删除课程后其记录与相关指标整体回落, so that 删得干净、算得干净。
13. As an 学习者, I want to 重新生成总结后 AI 总结次数 +1, so that 每次生成都被如实计数（#54 口径）。
14. As an 学习者, I want to 收件箱里未归类的记录也计入统计, so that 捕获了就算数。
15. As an 学习者, I want to 处理失败的记录也计入记录数, so that 失败的学习尝试不被抹掉。
16. As an 学习者, I want to 删除聊天会话后问答轮次回落, so that 删掉的对话不算数。
17. As an 学习者, I want to 新库（全 0）也显示六格与平线图表, so that 首次打开不空白、有成长起点感。
18. As an 学习者, I want to 统计带加载时今日页其余部分不被阻塞, so that 待办确认永远优先可见。
19. As an 学习者, I want to 统计加载失败时看到可重试的错误区, so that sidecar 抖动不变成永久空白。
20. As an 学习者, I want to 窄窗口下指标带折行为两行三列, so that 小窗口不挤压变形。
21. As an 学习者, I want to 暗色主题下统计带与图表配色正确, so that 夜间学习不刺眼。
22. As an 学习者, I want to 所有数字都来自真实业务数据, so that 统计没有假数据和估算。
23. As an 本地用户, I want to 聚合查询全部在本地 SQLite 完成, so that 学习数据不出本机。
24. As an 本地用户, I want to 统计查询不拖慢今日页, so that 打开应用依然轻快。

## Implementation Decisions

### 统计口径（七项，全部定死）

- **累计学习时长**：`SUM(records.duration_ms)`，records 软删过滤。仅音频类捕获（录音/音频导入/含音频的多来源）贡献时长；文档/粘贴/速记无时长自然计 0；处理中未封口（duration_ms 为空）不计——属预期，不估算不补。
- **记录数**：records 软删外**全量**——含 FAILED、NOTE（速记）、收件箱未归类。课程软删已级联记录软删，无需 JOIN 课程。
- **课程数**：courses 软删外全量，**含 ARCHIVED**（归档是"不再活跃"不是"没学过"）。
- **AI 总结次数**：ai_summaries 行数（含重新生成版本，即 GENERATED/CONFIRMED/SUPERSEDED 全状态），**JOIN records 过滤已删记录**（记录软删不级联 ai_summaries 行，靠 JOIN 回落）。
- **习题生成次数**：quizzes 行数（含 DRAFT/SUPERSEDED 历史批次），软删过滤 + JOIN records；与 AI 总结口径同构。
- **习题完成次数**：quizzes.answered_at 非空行数（软删过滤 + JOIN records）——逐题作答口径，**模拟测试交卷作答不计**（其作答写在 quiz_test_items，不回写 quizzes）。
- **问答轮次**：chat_messages 中 role='USER' 的行数，JOIN chat_sessions 过滤软删会话（chat_messages 本身追加型无软删列）。
- **一致性原则**：删除记录/课程后，其名下所有指标同步回落——record 域指标一律 JOIN records 软删过滤，不依赖子表自身 deleted_at。

### API 契约（today 模块扩展，不新建 stats 模块）

- `GET /api/today/stats` → 七字段单对象：

```json
{
  "total_learning_ms": 123456789,
  "record_count": 42,
  "course_count": 5,
  "ai_summary_count": 30,
  "quiz_generated_count": 120,
  "quiz_answered_count": 80,
  "chat_turn_count": 200
}
```

- `GET /api/today/stats/trend?days=7|30` → 按捕获日（date(created_at)）聚合 duration_ms 的序列，软删过滤，**后端补零**（缺天补 total_ms=0，序列连续无空洞）：

```json
[{ "date": "2026-09-01", "total_ms": 5400000 }, { "date": "2026-09-02", "total_ms": 0 }]
```

- days 查询参数白名单 7/30，非法值 422。
- 纯只读、无 Job/worker、无缓存（SQLite 本地单用户量级毫秒级）；launch token 鉴权与 today 既有端点一致。
- OpenAPI 是前端类型唯一契约：schema 先落再生成 api-types。

### 桌面端（今日页底部统计带）

- **容器（DESIGN.md 规范）**：统计带是今日页一个分节，与待确认总结区同构（上边线分节、留白节奏一致）；border: 0 增量、无圆角、无外框、无阴影——不是一组等权卡片，DESIGN.md「底部统计带」形态。
- **结构**：上「学习趋势」图表、下六格指标带；标题「学习趋势」（不叫"本周"——有 30 天档）。
- **趋势图表**：echarts 模块化引入（echarts/core + LineChart 按需注册 + **SVGRenderer**，休眠依赖转正、零新增包）；折线 + 渐变面积填充；y 轴学习时长（小时）、x 轴日期；右上近 7 天 / 近 30 天分段切换控件（切换即重取对应 days）；空白天 0 值如实平线，不做平滑；配色走语义 token（线色 foreground 系、面积为主色低透明度渐变），亮暗主题随 CSS 变量生效。
- **六格指标带**：单行 6 格、格间细分隔线（非独立卡片边框）；每格 = 图标（中性浅底圆角 chip，暗色走 surface-subtle 系 token）+ 小标签 + 大数值（单位小号内联浅色）；习题合一格显示双数「已作答 80 / 生成 120」；不做趋势副文案槽；窄窗折行 3+3（折行处不留悬空竖线，分隔线只在水平相邻格之间）。
- **时长格式化**：不足 1 小时显示「X 分钟」，≥1 小时显示「X 小时 Y 分」（整小时省分钟）——不用小数。
- **状态与空态**：加载态沿今日页既有行内 Spinner 模式且不阻塞待办区；错误态沿既有 alert 分节 + 重试按钮；空库全 0 照常渲染六格 + 平线图表（不做引导卡——空态引导是 #42 按域做的，统计区全 0 无歧义）。
- 文案全走 i18n（zh/en）；交互组件沿用现有 shadcn/ui + Base UI 体系；图标 lucide 线性图标。
- 前端落位 features/today 既有目录（api/keys + 组件），不新建 feature 或路由。

### 性能与依赖

- 无新表、无迁移、无 Job——七条聚合直查业务表。
- 数据来源表（records / courses / ai_summaries / quizzes / chat_messages / chat_sessions）均已就绪（Wave A + B 已交付功能产生），无前置代码依赖。
- 依赖变更：无新增（echarts 已在依赖清单，源码零使用状态转正）。

## Testing Decisions

- 好测试只断言外部行为：HTTP 响应数字与序列、UI 可见文本与请求行为；不断言 SQL 写法、echarts 内部渲染细节与像素。
- **后端缝（既有，零新缝）**：today 测试族模式——create_app 应用工厂 + 真实迁移库 + httpx ASGITransport 全栈驱动，经真实 HTTP 端点造数（建课/捕获/软删/总结确认/答题/聊天）后断言两个新端点。口径断言全在这条缝。
- **前端缝（既有，零新缝）**：今日页测试模式——MSW mock 两个新端点 + 渲染真实 App，断言六格数值文本、时长格式化（分钟/小时分钟两档）、习题双数格、加载/错误态、7↔30 切换触发重取（断言请求参数）；echarts 用 SVGRenderer 故 jsdom 可渲染，图表只断言容器存在与请求行为。
- 必测场景：空库全 0；七口径各自命中（含 FAILED/NOTE/收件箱计入、ARCHIVED 课程计入）；删记录后 ai_summary/quiz 指标回落而记录数同步 -1；删课程后全链回落；重新生成总结 +1；模拟测试交卷不增加完成数；删会话后轮次回落；趋势补零（中间空白天 total_ms=0 且日期连续）；days 白名单 422；纯文档记录时长为 0。
- 本机 pytest 必须加 `--basetemp=.pytest-tmp`。
- **真机项单列「用户真机验收」清单，agent 不验证不代勾**：统计带视觉形态（对照参考图）、渐变面积与亮暗双主题效果、窄窗折行手感、图表切换流畅度。

## Out of Scope

- 按周 / 月维度报表、任意维度切片（趋势图仅 7/30 天两档）。
- token 用量统计（归 19 服务与用量）。
- 模拟测试参与度 / 成绩维度统计（P7 学习画像的家）。
- 掌握度 / 遗忘曲线 / 学习画像域（P4/P7）。
- learning_events 写入（#43 事件集不扩，纯读聚合不发事件）。
- 聚合缓存层 / 物化（性能需要时再说，当前量级直查）。
- 柱状图、热力图等其他图表形态。
- 左栏新增入口（#54 定死入口在今日页底部）。

## Further Notes

- 决策源：2026-09-07 学习统计 grill 共识（三轮，含参考图定 UI 形态）；工单见 `.scratch/function-plans-introduction/17-learning-stats.md`；术语见 CONTEXT.md。
- **范围修订记录**：原工单与 PRD v2.4 均写「趋势图表 Wave B 出口线之外，后续可加」——本次 grill 裁决拉进本票，且用真数据（否决假数据先行：真数据源今天即存在，假数据上线即误导且需返工）。**PRD「学习统计」行需随本功能交付同步升版**（补趋势图与七口径），升版时按文档惯例改版本号并同步全部交叉引用。
- 参考图：统计带内部结构（单行指标 + 格间细分隔线 + 图标/标签/大数值）严格照用户提供的参考图；外层容器按 DESIGN.md 无卡片化规范执行（grill Q9 裁决，参考图的白色圆角面板不采纳）。
- 拆票建议（供 /to-tickets 起步）：①后端两端点 + 口径测试 → ②前端统计带（图表 + 六格）+ 测试；①为 ② 的 blocking edge。规模较 16 小，不建议拆更细。
