# 今日页 UI 重构验收记录

日期：2026-10-09。视觉依据仅为用户附图；未读取或使用 DESIGN.md。用户已授权缺少的图面能力使用假数据，并明确本次不更新 PROJECT_PROGRESS.md。

## 图面与实现

| 图片分区 | 实现 | 数据与取舍 |
| --- | --- | --- |
| 日期、工作台 / 学习轨道 | TodayOverview.tsx | 实际日期；视图写入 URL；Ctrl+1 / Ctrl+2；编辑输入与对话框内不抢快捷键 |
| 左栏待处理 | TodayPending.tsx | 复用 today.pendingSummaries 与 record.inbox；选择总结在右栏预览；原记录详情与收件箱入口保留 |
| 最近资产、学习流程、成就 | TodayAssets.tsx | 保留原示意资产和成就，明确示意；资料库入口与捕获流程展示保留 |
| 学习节奏折线、累计指标 | TodayStatsBand.tsx、StatsTrendChart.tsx、StatsMetrics.tsx | 真实统计与趋势；30 天请求、7 天切片；六项指标在工作台可展开，学习轨道默认展开 |
| 今日行动表格 | TodayActions.tsx、TodayTodos.tsx | 真实计划项；课程筛选、到期 / 时长排序写入 URL；保留目标、课程、预计时长、排期、状态与完成操作 |
| 继续学习、快速开始 | TodayQuickStart.tsx | 原继续学习仍为示意；速记复用 AppShell 的 openQuickNote；AI 对话与课程练习入口可用 |
| 当前专注 | TodayFocus.tsx | 明确本地示意计时；开始、暂停、继续、结束、编辑时长；切换今日视图继续，离开今日页重置 |
| 总结预览、来源、确认 | TodaySummaryPreview.tsx | 读取现有 recordApi.getSummary；来源进入原文；确认进入记录详情的既有审阅与确认流程 |
| 图中没有的四张洞察图 | TodayStatsBand.tsx 的学习轨道 | 保留原雷达、时间分布、专注度、学习趋势，继续明确示意 |

所有新增 UI 文案同步 zh.json / en.json。复用项目 shadcn / Base UI 的 Tabs、Select、Checkbox、Dialog、Button、Collapsible；继续使用现有 ECharts 和 BaseChart，没有增加依赖。颜色集中于 today 语义令牌，未重绘其他页面；BaseChart 增加容器 ResizeObserver，以支持列宽与字号变化。

## 功能与业务保留

- 待确认总结仍来自 `/api/today/pending-summaries`；没有以假数据覆盖真实列表。处理中收件箱记录使用原接口，每 2 秒刷新；发现总结就绪时刷新待确认查询。失败有提示与重试，处理失败记录仍可进入原详情。
- 计划项仍来自 `/api/today/plan-items`，保留当前接口的有效目标 / 计划、排期不晚于今天、未完成范围。完成继续使用 `useCompletePlanItem`，成功使原学习计划与今日缓存失效，失败保留未完成状态并反馈错误。
- 总结确认不在预览栏另建写路径；进入原详情后使用既有受控确认。来源链接仍可定位记录的 transcript 标签页。
- 统计继续使用 `/api/today/stats` 与 `/api/today/stats/trend?days=30`，保留全部六项累计指标、7 / 30 天切换、比较、错误重试和空数据状态。
- 应用壳的导入、录音、粘贴、搜索、导航、原快捷速记功能保留。只增加共享速记打开函数的 Context，未复制捕获逻辑。
- 新增业务写入为零：既有 Agent / API / 领域 Service 与页面共用的入口不变。专注为明示本地示意，无持久化事实，因此本次不增加 Agent Tool。完成列表的真实聚合接口本期未新增。

## 示意范围

原最近资产、继续学习、学习成就、四张洞察图继续为示意。新增已完成列表与专注计时也明确示意；计时不写学习记录与统计。没有真实待办时才展示示例任务，示例复选框禁用；没有待确认总结且查询成功时才展示示例总结，确认按钮禁用。失败状态不会伪装成示例成功结果。

## 已执行检查

| 层次 | 结果与证据 |
| --- | --- |
| 静态 | 改动 TS / TSX ESLint 零警告；改动文件 Prettier 格式化；`pnpm build` 内含两份 TypeScript 配置检查，构建通过；`git diff --check` 通过 |
| 前端替身 | 7 个相关测试文件、33 / 33 用例通过；覆盖计划项完成成功 / 失败与刷新、确认资产化既有流程、统计趋势 / 错误恢复、URL 筛选 / 排序、双语 key、应用壳生命周期、专注墙钟计时 / 暂停 / 恢复 / 结束 / 超时 / 时长校验。记录为 tests.json 与 tests.log |
| 真实桌面 | 本地 Tauri 开发壳 + 原生 WebView2 + 实际 sidecar / 迁移数据库读取真实待确认总结、计划项、统计、趋势和总结内容；`window.__TAURI_INTERNALS__` 为 true，未用普通浏览器替身冒充桌面 |
| 真实交互 | 原生 WebView2 中开始计时、切换学习轨道仍继续、暂停后保持、回工作台继续 / 结束、速记对话框打开 / Escape 关闭、Ctrl+1 / Ctrl+2 切换均通过 |
| 视觉 | 亮 / 暗 M、亮 S / L、窄窗 L 与学习轨道截图；各场景 body 无横向溢出；修复大字号筛选栏高度、真实长标题两行截断与暗色选中态，独立只读复核 disposition: ship |

复跑命令（在 apps/desktop）：

```powershell
pnpm exec vitest run src/features/today/components/TodayTodos.test.tsx src/features/today/components/TodayStatsBand.test.tsx src/features/today/components/TodayFocus.test.tsx src/pages/index.test.tsx src/i18n/locales.test.ts src/components/layout/AppShell.lifecycle.test.tsx src/components/layout/AppShell.lastRoute.test.tsx --maxWorkers=2 --reporter=json
pnpm build
```

截图通过真实 WebView2 的 CDP 模拟 CSS viewport，DPR 约 1、缩放 100%；字号直接施加设置实际使用的根字号 S=15px / M=16px / L=18px，没有修改用户保存的偏好。结束时恢复原主题、字号、viewport 与动效偏好模拟。

| 截图 | CSS viewport | 字号 / 主题 |
| --- | --- | --- |
| [工作台亮色](screenshots/light.png) | 1586 × 992 | M / 亮 |
| [工作台暗色](screenshots/dark.png) | 1586 × 992 | M / 暗 |
| [小字号](screenshots/small.png) | 1586 × 992 | S / 亮 |
| [大字号](screenshots/large.png) | 1586 × 992 | L / 亮 |
| [窄窗大字号](screenshots/narrow-large.png) | 1066 × 800 | L / 亮；两栏，专注与预览移到下方 |
| [学习轨道](screenshots/orbit.png) | 1586 × 992 | M / 亮 |

原始量测：screenshots/matrix.json。交互脚本：check-native.py（由 browser-use 提供 js / cdp / click_at_xy helpers）。构建日志：build.log。

## 差异与未执行项

- 原应用壳、侧栏功能与参考图不同，保持现有实现；没有伪造搜索输入或侧栏能力。真实标题与内容会改变密度，大字号与窄窗通过正常滚动保留全部入口，完整任务标题可悬停查看并进入详情。
- 原四张示意图没有扩展成真实分析能力；已完成列表没有真实跨课程聚合；本地示意专注不能当作持久化学习计时使用。
- 真实桌面使用现有数据完成读取和无持久化的 UI 交互。未在用户真实数据上勾选完成或确认总结，相关写入验收使用现有 MSW 测试，不能等同真实 API + Worker 写入验收。
- 没有新增真实模型调用，没有重跑后端测试或全仓测试，没有执行发布安装包验收或物理窗口多显示器 / 高 DPI 验收。没有独立仪器对比度量测；截图使用 reduced-motion，正常动效代码保留现有组件能力。
- 构建已有大包与测试文件路由提示；一次范围参数为空的 ESLint 调用落到全项目，暴露原 PlanDraftEditor / LearningPlanTab 的 Fast Refresh 警告，未改无关文件。随后改动范围 ESLint 通过。
- 根 AGENTS.md 的外部修改未纳入本次工作、未覆盖。按用户明确选择，PROJECT_PROGRESS.md 不更新。未创建 Git 提交。
