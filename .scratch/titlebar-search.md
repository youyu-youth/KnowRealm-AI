# 搜索入口迁移至自定义标题栏

2026-10-13：将原 AppShell 工作面顶部的搜索按钮迁移至自定义标题栏右上角、最小化按钮左侧（8px 间隔）。按钮外观、双语文案、Ctrl+K、查询清空及原命令面板保持。

标题栏通过 ref 提供 DOM 槽位，App 用 Context 将槽位传给 AppShell；AppShell 用 React createPortal 渲染原按钮，仍拥有唯一的 paletteOpen 和原业务回调。未使用全局事件或新增 UI 状态存储，无后端/Agent/原生权限变更。引导流程未挂载 AppShell 时不显示搜索按钮。标题栏拖动区域仍沿用原实现，按钮和图标不添加 data-tauri-drag-region。

沿用 impeccable 及既有 shadcn Button 与主题；不新增动效或依赖。全局固定空白头部已按后续要求移除，原录音控制按内容显示，空态不占空间。

验证：

- 既有命令面板两个相关用例通过：Ctrl+K/Escape/Alt 修饰/清空查询，以及搜索按钮位于标题栏、最小化之前且原位置不再存在，点击唤起同一面板。`pnpm exec vitest run src/features/search/components/CommandPalette.test.tsx --maxWorkers=1 -t 'Ctrl\+K 唤起|标题栏搜索按钮'`，2 通过、10 未选择；日志 `.scratch/titlebar-search-tests.log`。未复跑上一轮登记的无关同名标题断言失败。
- `uv run --frozen --directory backend python -m scripts.run_tests frontend src/components/layout/WindowTitleBar.test.tsx`：8/8，通过；窗口 API 使用现有替身。证据 `.pytest-tmp-runs/20261013T100807Z-c38d08e6/frontend/result.json`。
- 浏览器 Vite 检查：只有一个搜索按钮，处于窗口标题栏，最小化左侧；原头部入口消失；实际鼠标点击、Ctrl+K、Escape 及关闭后焦点返回通过。明亮默认主题 1102×724、暗黑默认主题 902×722 CSS viewport 均无页面横向溢出；搜索按钮为 96×28 CSS px，与最小化相隔 8px。浏览器无 Tauri 桥，真实本地业务请求不可用。
- 当前已运行的真实 Tauri 窗口通过只读 PrintWindow 截图确认搜索位于最小化左侧、旧位置移除；截图 `.scratch/titlebar-search-native.png`，原生外框 1938×1098 栅格 px，GetDpiForWindow=120（125%）。截图时用户所在知识空间页面未被改变；没有执行原生鼠标点击或拖动。
- 触及文件 ESLint/Prettier、构建（内嵌两套 tsc）与 `git diff --check` 均通过；构建退出码 0，日志 `.scratch/titlebar-search-build.log`。既有路由测试文件提示及大 chunk 提示保留。

未验真实 Tauri 窗口拖动/双击最大化与 Windows 系统缩放；未运行无关全量测试。原窗口控制的自动化回归不等同原生验收。

## 全局空白头部移除

2026-10-13 后续修改：移除 AppShell 固定 52px 捕获 header，RecordingExperience 常驻于 `empty:hidden` 内容容器，空态不占高度；录音控制和错误仍按实际内容显示，原弹窗/恢复链保持。所有 AppShell 页面共享该修改，无逐页删除或后端/Agent 能力变更。

现有 FINALIZING 失败反馈、录音暂停/继续/分片交接，以及标题栏搜索/旧 header 不存在的三个用例均通过（API/音频设备替身）：`.scratch/shell-empty-header-tests.log`，3 通过、16 未选择。触及文件 ESLint 与 Prettier、diff 检查及构建均通过；构建退出码 0，日志 `.scratch/shell-empty-header-build.log`。

真实 Tauri 当前今日页面只读截图确认空白条消失，未改变用户路由或数据；原生外框 1938×1098 栅格 px，DPI 120（125%），截图 `.scratch/shell-empty-header-native.png`。未验真实录音设备及其余页面逐页操作，其他页面共享同一 AppShell 容器。未运行无关全量测试。
