# 06 — 首启三步向导

**What to build:** 壳读 desktop.json 判定首启（文件缺失或 `onboarded=false`）→ 首路由 `/onboarding`（AppShell 外，托盘/快捷键不绕过）。三步**全可跳过**：①数据目录——默认 `~/KnowRealm` 展示（"使用默认目录开始"=跳过）、"更改位置"（复用 03 的空目录选择）、"从导出包导入"（选 zip → spawn sidecar 带 `--import-archive`，失败向导内报错可重试）、OneDrive 检测（路径含 OneDrive 组件或 `%OneDrive%` 前缀 → 黄字警告不阻断）；②供应商卡——复用 02 卡组件，"稍后在设置中配置"=跳过（降级 #38 由空态引导兜底）；③角色卡——四选一+自我介绍，跳过=不建档（chat 中性默认已有）。完成（含全部跳过）：完成页提示"所有设置可稍后在设置页修改" → 写 `onboarded=true` → 进首页，向导永不再现、无"重新运行"入口。向导期间不记 last_route（13 号豁免扩展为"设置页与首启向导除外"）。

**Blocked by:** 02 — 供应商分区；03 — 数据目录分区、desktop.json 与打开目录；05 — 全量导出/导入与滚动备份

**Status:** done（真机项待用户验收）

- [x] 首启判定：壳读 desktop.json → 路由分流；托盘/快捷键不绕过向导
- [x] 向导①：目录默认/更改/从导出包导入分支（--import-archive 接线+失败可重试）/OneDrive 检测警告
- [x] 向导②③：复用供应商卡与角色表单；跳过语义落地（接受默认/不建档）
- [x] 完成：写 `onboarded`（经壳）→ 进首页；向导路由不写 last_route
- [x] 前端测试（三步跳过/导入失败重试/完成态/last_route 豁免/非首启不出现）；pyright/tsc/prettier 全绿
- [x] 真机人工验收（用户执行）：全新数据目录首启走完三步（含全跳过）后永不再现；OneDrive 路径出警告；导入恢复后②③显示已配置/已建档

> **实现注记（2026-08-31）**：
> - **首启分流**：根路由 `beforeLoad` 每次导航询问壳 command `get_onboarding_state`（desktop.json 缺失/损坏经 `load_or_repair` 回退即 `onboarded=false`）；结果在 `services/tauri/onboarding.ts` 会话内缓存（onboarded 只 false→true 翻转），`complete_onboarding` 写盘并同步翻转缓存。`/onboarding` 路由反向守卫：已完成者直达一律回首页（无重跑入口）。向导期间 AppShell 不挂载（`RootLayout` 按路径条件渲染），侧栏/捕获入口/速记快捷键/last_route 写入结构性不存在——托盘"显示"只能看到向导本身。
> - **①目录**：与设置页共用迁移/导入链路——抽 `useDataDirectoryFlows`（`useDataDirectoryChange` + `useArchiveImport`），设置页 `DataDirectorySection` 与向导 `DirectoryStep` 同源消费；弹窗（Change/Import）与 restartPending + 生产 relaunch / 开发 manualRestart 语义全部复用。OneDrive 检测为纯函数（路径分段以 onedrive 开头或含 %onedrive%），当前目录黄字警示、更改所选目标在确认弹窗内就地警示（ChangeDialog 新增可选 `warning` prop）。
> - **②③**：`LlmProviderCard`/`TencentAsrCard` 从 ProvidersSection 导出直接复用；③按工单只收角色+自我介绍（昵称/头像不收集），保存保留服务端已有 nickname 防静默清空，跳过零请求；导入恢复场景已有档案回填并提示"检测到已有档案"。角色枚举抽 `features/settings/roles.ts` 单一来源。
> - **已知边界**：导入校验失败（版本过新/包损坏）发生在 relaunch 后 sidecar 启动期（05 票注记既有行为）：进程非零退出、错误码进 backend.log、pending-import 已消费，再次启动回到向导①可重选——向导内报错可重试覆盖的是 command 同步失败与弹窗失败态。完成页若不点"进入"直接退出应用，下次启动向导从①重放（三步可跳过，代价 3 次点击），故在按钮点击时写 onboarded。
> - **连带修复**：`warning-foreground/soft`、`success-foreground` 三 token 按 DESIGN.md 补齐 theme.css/tokens.css——此前 KnowledgePointPanel/QuizPanel 使用的同名工具类在构建产物中不存在（静默无色），本次起真实生效。
> - **门禁实测（2026-08-31）**：cargo test 21 过 + clippy -D warnings 零告警；tsc 双配置零错；prettier（改动文件）净；eslint 仅剩基线既有 PreferencesSection:45 一条 react-refresh 警告（stash 对照确认非本票引入）；前端全量 276/277（唯一失败为 TodoPanel 既有全量抖动，单跑 8/8 过）；后端零改动。
