# 今日页暗色设计调整

日期：2026-10-09。本轮按用户新指示使用 impeccable，并读取 DESIGN.md；仅调整今日页暗色，保留上轮布局、功能、亮色与全部未提交修改。未更新 DESIGN.md、PROJECT_PROGRESS.md 或根 AGENTS.md。

## 调整

- theme.css：显式 `.dark` 与系统暗色首帧兜底的九个 today 令牌，改用 DESIGN.md 的冷中性灰阶。面板 `#20242A`、轻表面 `#181B20`、分隔 `#242831`、正文 `#D5D8DE`、元数据 `#9196A1`；主动作浅底深字，选中态、焦点、折线与专注进度取消蓝 / 绿装饰色。
- TodayWorkspace.css：仅 `.dark .today-workspace` 范围内加强标题对比；真实选中记录的边框改用既有 border-strong，避免高亮外框抢占正文。
- 警告、待确认、逾期等必要状态继续使用原有语义色与文字。没有改业务、文案、字号、尺寸、结构、API、Agent 或依赖。
- 亮色 root 声明与修改前备份精确一致，额外工作区规则全部由 `.dark` 限定。

## 已执行

- 4 个相关现有测试文件，21 / 21 通过：TodayStatsBand、TodayTodos、TodayFocus、index。
- `pnpm build`（含双 tsconfig 类型检查）、两份改动 CSS 的 Prettier 检查、git diff --check 通过。CSS 不适用 TS / TSX ESLint，没有新增生产逻辑测试。Impeccable detector 返回空列表。
- 隔离 Chrome 浏览器以当前 App / 组件代码渲染，Tauri IPC 与 API 使用仅存在于浏览器中的替身。视觉检查 1920×1080 / M 暗色、1586×992 / L 暗色、1066×800 / L 暗色、1586×992 / M 亮色、暗色键盘焦点。DPR=1，CSS 缩放=100%，所有场景 body 无横向溢出。
- 正文在面板 / 轻表面对比度 10.92 / 12.09；元数据 5.26 / 5.82，均高于 AA 4.5:1。焦点 outline 为中性灰且 :focus-visible 生效；系统暗色首帧令牌正确。

截图：[暗色](dark.png)、[大字号](dark-large.png)、[窄窗](dark-narrow.png)、[亮色回归](light-regression.png)、[键盘焦点](dark-focus.png)。量测见 matrix.json；测试见 tests.json；构建见 build.log。

## 未执行与限制

本轮真 Tauri 新实例启动未完成：现有桌面程序锁定可执行文件，随后独立实例因数据目录已使用而无法启动 sidecar。没有关闭现有用户程序、改配置或解除数据锁。原生窗口捕获无有效内容，未作为视觉证据；上述截图全部是浏览器替身，不能描述为真机或真实业务数据验收。没有重验真实模型、业务写入、发布安装包、高 DPI / 多显示器或 200% 缩放；本轮没有改变布局与业务。

浏览器中的 __TAURI_INTERNALS__ 由官方 mockIPC 生成，不代表真 Tauri。matrix.json 显式记录 tauri=false、ipc_mock=true 与 visual_mock=true。没有 Git 提交。

隔离预览浏览器已关闭；清理 chrome-profile 临时目录被自动审批检查以 blocked by policy 拒绝，目录保留并由本目录 .gitignore 排除。
