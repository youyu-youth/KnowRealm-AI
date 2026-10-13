# 全局捕获悬浮工具栏

2026-10-13：将 AppShell 头部的新建速记、粘贴文本、导入资料、开始录音迁移到内容区左下角。默认仅显示一个圆形入口，悬停展开四个竖向 FAB；支持 Tooltip、轻量 Hover、固定定位与拖动。位置只属于当前窗口会话，不写偏好或数据库。其他页面内捕获入口保留。

复用 Button、AppTooltip、原 openCapture 回调和所有现有弹窗；保留 RecordingExperience 的录音控制、恢复、失败反馈及录音期间重复开始的禁用。命令面板/速记快捷键仍走原调用。该改动仅为前端交互布局，无新增 Agent 能力；底层业务/受控执行入口未改。

拖动使用原生 Pointer Capture：位移阈值区分点击，拖动后不误展开；Escape、pointercancel 和失焦取消并恢复原位，lostpointercapture 终止拖动，卸载释放捕获。工作面 ResizeObserver 限制入口边界，扩展区按上下空间选择方向，狭小空间可滚动。Enter/Space 展开、Tab 到操作、方向键移动入口、Escape 收起并归还焦点。隐藏操作为 inert；动作执行前将焦点交还入口，弹窗沿用原焦点保护。使用语义主题及 secondary 变体保证 FAB 背景不透明；减弱动效取消空间位移。

## 自动化证据

- `uv run --frozen --directory backend python -m scripts.run_tests frontend src/App.test.tsx src/pages/inbox.test.tsx src/components/layout/CaptureFloatingToolbar.test.tsx`：40/40，通过；记录 `.pytest-tmp-runs/20261013T095152Z-9c8eba90/frontend/result.json`。API、音频设备与 Tauri 桥使用现有替身，不等同真实录音验收。
- 新增 7 项行为测试覆盖四操作回调、录音禁用、悬停、拖动、误触、键盘、取消与窗口边界。此前独立运行 7/7 通过：`.pytest-tmp-runs/20261013T094851Z-9b2de211/frontend/result.json`。
- 首次扩大回归：61 项中 56 通过、5 失败。四条受迁移影响的旧用例未等待/未展开入口已修正并在上述 40 项中通过；生命周期、侧栏、路由恢复和双语文件在首次运行中通过。记录 `.pytest-tmp-runs/20261013T094652Z-02bc8299/frontend/result.json`。
- 剩余 CommandPalette 用例 `空查询显示三个捕获命令且不发搜索请求，Enter 触发既有入口`：关闭速记后，`closeTopDialog` 全页面查询同名 heading，误命中 TodayQuickStart 的常驻 h3。该标题和断言均在本轮 HEAD 中已存在且未修改；没有执行隔离基点复测，不把它写成已证明的基点测试结果。未扩大本票修复范围。
- 触及 TS/TSX ESLint、Prettier 和 `git diff --check` 通过；最终构建（两套 tsc + Vite）退出码 0，日志：`.scratch/floating-capture-build.log`。既有路由测试文件提示和大 chunk 提示保留。

## 浏览器检查与未验项

- 实际鼠标 hover 展开/Tooltip、将入口从左下角拖到顶部（释放保持收起、向下展开）、键盘 Enter/Tab/Escape 与焦点返回、工作面滚动不改变入口位置均检查通过。
- 检查明亮默认主题、暗黑 Ink 主题和 1099×720 窄视口；无页面横向溢出。暗色背景透明和 Tooltip 截获 Escape 两处在实现中修正。
- 浏览器环境 `prefers-reduced-motion: reduce` 为 true，空间动画关闭；常规动效的真实渲染未验。四项操作的计算尺寸均为 48×48 CSS px。
- 桌面设计取向沿用既有冷中性工作面：仅入口为 primary，操作使用现成 secondary Button；Hover 与焦点反馈由 Button/全局样式提供。`desktop-ui-mastery/scripts/lint_slop.py` 报 no-focus-visible / no-hover-states，但本组件两类 Button 均显式含 `focus-visible:ring-3`，浏览器键盘检查实测 3px 焦点环及 Tooltip；Hover 由 secondary 变体及 `.capture-fab` 媒体查询实现。因此登记为检测器未识别跨文件样式的误报，不为消除报告添加重复样式。
- 本轮浏览器直接访问 Vite，无 Tauri 运行桥，本地业务 API 显示不可用；仅证明布局、指针与键盘行为，业务弹窗/保存链由既有 API 替身回归证明。
- 未验真实 Tauri/WebView2、实际录音设备、Windows 系统缩放、屏幕阅读器及其余主题/字号矩阵。未更改用户现有应用进程和数据。

人工验收：在真实桌面任一页面确认左下角默认仅有加号；悬停逐个检查四项提示，点击确认原弹窗；拖往四边再展开，滚动页面及缩小窗口；开始录音后确认不能重复开始且原暂停/结束控制仍可用；键盘展开和退出；重复检查明暗主题及减弱动效。
