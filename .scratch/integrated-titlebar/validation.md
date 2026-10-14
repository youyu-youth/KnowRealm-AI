# 集成标题栏视觉修正（2026-10-14）

本次将标题栏与侧栏视作同一外围色面，复用 `bg-sidebar`；移除标题栏底部横线，保留主工作面圆角及边框，以内容边界承担层次。仅修改 WindowTitleBar 和 AppShell 两处 className，无交互、数据、API 或原生窗口代码变化。纯前端布局无需 Agent Tool。

- PASS：现有标题栏、侧栏、生命周期和上次路由测试共 21 项，四个文件全部通过。日志及机器结果：`.pytest-tmp-runs/20261014T070953Z-e36c8124/frontend/`。
- PASS：`pwsh -NoProfile -File scripts/check-changed.ps1`，触及文件 ESLint、Prettier、两份 TypeScript 检查及 Vite 生产构建通过。构建仍提示原有路由测试文件及大 chunk 警告。
- PASS：`git diff --check`。
- PASS：独立本地 Edge 浏览器访问生产前端 `/library`，四套主题 × 1440/1099 CSS 视口共八组。标题栏底边宽度 0px，标题栏/侧栏/外围底色相同，无页面横向溢出。见 `visual-check.json`。
- PASS：鼠标点击侧栏 Toggle 折叠/恢复，折叠后宽度 0 且 inert；Tab 可进入控件并匹配 focus-visible。见 `interaction-check.json`。
- PASS：目检 `light.png`、`dark.png`，标题栏与侧栏连续，主工作面边界保留。浏览器无 Tauri IPC/后端连接，资料区域处于加载态，未验证业务数据。
- NOT_RUN：真实 Tauri/WebView2、窗口拖动、Windows 系统缩放、全量前后端测试。原生窗口动作由现有替身回归覆盖，不作为真机证明。

Desktop UI Mastery 的 lint_slop 在改动前后均报告两处 no-focus-visible。该扫描器未识别文件中已有 Tailwind `focus-visible:*` 与 Button 的焦点样式，属于既有误报；本次未为清除误报扩大改动。

人工复验：启动桌面端，分别切换亮/暗及非默认主题，确认横线消失；拖宽、折叠及恢复侧栏；检查标题栏拖动和最大化、最小化、关闭仍正常。系统缩放需真实 Windows 设置验收。

本次自建的隐藏 Edge 预览进程已停止；现有 1420 开发服务未停止。预览用户目录位于系统临时目录 `knowrealm-integrated-titlebar-20261014`，作为本地调试缓存保留。
