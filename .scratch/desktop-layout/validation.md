# Desktop 布局设置验收（2026-10-14）

功能代码已实现；原生桌面及真实系统缩放验收未完成。

设计采用标题栏下独立导航行，沿用侧栏底色与既有工作面边界。主要导航共享定义；按实际文字尺寸预留更多按钮空间，不按固定窗口断点假设英文或大字号宽度。近期课程收进菜单，档案及设置常驻，禁用的学习画像保持禁用。页面、弹窗、录音组件不因切换布局而换树，侧栏内容保持挂载但在顶部模式隐藏且 inert。

持久化继续由 sidecar 唯一写入数据目录 `config/settings.json`，新增 `layout_mode`，SIDEBAR 为默认，TOP 为顶部模式；非法请求或显式 null 拒绝，损坏存量读回侧栏且不改写文件。默认值删除对应键，保留其他偏好与未知键，无数据库迁移。主入口继续先经 prepareAppearance 读偏好再挂载工作区。布局使用已确认的 Query 事实，不另建持久缓存或 Zustand 副本；保存失败沿用既有读回、报错与重试。

## 已通过

- 后端：`uv run --frozen --directory backend python -m scripts.run_tests backend tests/test_preferences.py`，70 passed；包含布局保存、真实文件内容、重新构建应用后恢复、重置默认及坏值回退。记录 `.pytest-tmp-runs/20261014T073724Z-079df031/backend/`。
- 前端最终：`uv run --frozen --directory backend python -m scripts.run_tests frontend src/components/layout/AppShell.layout.test.tsx src/components/layout/AppShell.sidebar.test.tsx src/components/layout/WindowTitleBar.test.tsx src/components/layout/SidebarUserArea.test.tsx src/components/layout/AppShell.lifecycle.test.tsx src/features/settings/useSavePreference.test.tsx src/features/settings/appearanceCache.test.tsx src/pages/settings.test.tsx src/i18n/locales.test.ts`，9 文件、70 passed。记录 `.pytest-tmp-runs/20261014T080156Z-b4a051ba/frontend/`。
- `pwsh -NoProfile -File scripts/check-changed.ps1` 通过：范围 ESLint、Prettier、两份 TypeScript 检查、生产构建、Ruff/格式与 Pyright（0 errors/warnings）。日志 `check-changed.log`。
- `pnpm --filter @knowrealm/api-types check` 通过；`git diff --check` 通过。
- 真实隔离 sidecar（43339 端口，仅本次 data 目录）＋Chrome 浏览器：设置保存、顶部/侧栏互切、资产库及溢出 AI Chat 导航、近期课程进入 `13d66c0e-0c61-48da-844d-025f66515330`、浏览器刷新恢复顶部通过。IPC 配置桥为替身，API/设置文件及课程数据为真实隔离服务；未使用正式用户库。
- 中文/英文 × 四套主题 × 1440/1099/800/600 CSS 视口，16/18px 两档字号，共 32 组无页面横向溢出且导航项未越界；`evidence/matrix.json` 为每组记录，PNG 已目检。字体/视口/焦点为 CDP 模拟，不能当作系统缩放验收。
- 溢出按钮 Tab 可达，Enter 打开、方向键进入菜单、Esc 关闭并返回可见焦点，见 `evidence/keyboard.json`。

## 调试与边界

初轮新测试的路由记忆 PUT 替身返回默认布局，已改为保留完整事实；过长的跨页面场景被拆为草稿保持与恢复侧栏两个用例，未增加 5 秒超时。最终 70 项已通过。既有设置/资料夹具仍有未匹配 MSW 请求诊断输出，本次不扩大无关业务夹具；构建仍提示既有路由测试文件及大 chunk 警告。

独立 Edge 预览进程启动被自动审批拒绝，未换命令绕过。改用已连接浏览器；后台页的动画帧与 ResizeObserver 被暂停，使用 CDP 焦点模拟后重跑完整矩阵。初次后台页面的未完成矩阵不计通过。浏览器测试脚本为 `check-browser.py`。

复用已安装的 shadcn/Base UI 菜单及 RadioGroup，文档参考 [Base UI Menu](https://base-ui.com/react/components/menu)；Context7 查询因月额度耗尽未返回文档，采用官方文档与本地组件/API 为依据。Desktop UI Mastery lint_slop 对 Tailwind/复用组件的 focus-visible 与 hover 报误报，源码已有语义样式，并以键盘实测核对。

未执行：全量前后端测试、真实 Tauri/WebView2、真实 Windows 系统缩放、真实桌面进程退出与重启、活动录音/真实模型执行中切换布局。现有生命周期回归为替身；真实模型不涉及本票确定性配置实现。

人工步骤见 `issues/01-layout-settings.md`；原生未验项保持未勾选。本期没有 Agent 自动修改外观入口，原因及范围见 spec.md。

收尾：本次预览浏览器页、隔离 sidecar 和本次自建 Vite 服务已关闭，保留截图、日志及隔离数据目录作为证据。未清理用户已有 baseline 或上轮改动，未提交 Git。
