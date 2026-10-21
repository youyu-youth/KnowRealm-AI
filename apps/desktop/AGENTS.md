# apps/desktop（@knowrealm/desktop 桌面端）

**开发必读**：开始功能设计、开发和评审前，必须阅读并遵循[根目录 AGENTS.md](../../AGENTS.md)的“Agent 自动执行优先（长期架构原则）”。设计页面操作时同步考虑 AI 对话执行入口、所需上下文、确认交互与结果展示，避免将适合自动执行的能力仅绑定到页面按钮。

Tauri 2 壳 + React 19 + Vite 7 + TanStack Router（file-based）+ Tailwind CSS 4 + shadcn/ui（Base UI 底座，style `base-nova`）。业务数据一律经 localhost sidecar API 读写，UI 不直连数据库。

> 编码规范正本是根目录 `.claude/rules/desktop-*.md`（自动加载，本文不重复）。本文件记录本目录的**命令、结构与已验证现状**；rules 部分内容描述的是目标态，差异见文末 Gotchas——**不要为了对齐 rules 而主动重构现有代码**。

## 常用命令

| 命令（本目录内执行）                  | 说明                                                                                                                                                        |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pnpm dev`                            | Vite dev server，端口 1420（strictPort）。仓库根执行用 `pnpm --filter @knowrealm/desktop dev`（无根 package.json，workspace 由 `pnpm-workspace.yaml` 定义） |
| `pnpm build`                          | **类型检查内嵌于此**（双 tsconfig `tsc --noEmit`）+ `vite build`；无独立 typecheck 脚本                                                                     |
| `pnpm lint`                           | `eslint . --max-warnings 0`                                                                                                                                 |
| `pnpm test`                           | `vitest run --passWithNoTests`（配置内嵌 `vite.config.ts`，无独立配置文件）                                                                                 |
| `pnpm format:check`                   | `prettier --check .`（覆盖 `.md`；无写入型 format 脚本）                                                                                                    |
| `pnpm tauri dev` / `pnpm tauri build` | 拉起完整壳。`pretauri` 钩子自动跑 `scripts/prepare-ffmpeg.ps1`（固定版本 + SHA256 校验，幂等）；`src-tauri/binaries/` **不入库**，新克隆首次自动下载        |

Rust 侧（`src-tauri/` 内）：`cargo test`（测试内嵌在各文件 `#[cfg(test)]` 模块）/ `cargo clippy -- -D warnings` / `cargo fmt`。

## 目录结构（现状）

```
src/
├── pages/               # TanStack file-based 路由，扁平命名（chat.$sessionId、spaces.$courseId_.tests.$testId 等）
├── features/            # 业务功能内聚，惯例为 api/ + components/ 子目录
│   ├── courses  records  recording  quiz-tests      # 课程 / 记录详情（含复习资料、导出）/ 录音 / 模拟测试
│   ├── chat  search  library  inbox  today          # AI 问答 / 全局搜索（Ctrl+K 面板）/ 资产库 / 收件箱 / 今日+学习统计
│   ├── text-capture  document-import  audio-import  # 速记 / 文档导入 / 音频导入
│   └── onboarding  settings                         # 首启向导 / 设置页（偏好·供应商·用量·数据目录）
├── charts/              # echarts 按需注册中枢 + BaseChart + 主题配色（页面不直接 import "echarts"）
├── components/          # ui/ = shadcn 生成物（勿手改，command 来自 @9ui）；common/ = 跨 feature（MarkdownContent 等）；layout/ = AppShell + RootLayout + SidebarUserArea
├── services/http/       # client.ts：统一 base URL、X-KnowRealm-Token、ApiError
├── services/tauri/      # sidecar / recording / lifecycle（退出+托盘）/ onboarding / preferences（关闭行为+快捷键+自启）/ dataDirectory / learningAssetExport
├── services/restartPending.ts  # 「数据目录迁移后必须重启」标记（安全退出据此跳过录音检查）
├── app/queryClient.ts   # staleTime 60s / retry 2 / refetchOnWindowFocus false
├── i18n/                # zh/en 双语（切换逻辑 + locales）
├── mocks/               # MSW（仅测试启用）
├── test/                # setup.ts + test-utils.tsx（renderWithQuery）
└── styles/              # tokens / theme / globals / animations 四件套
```

注意：`hooks/`、`stores/` 顶层目录**不存在**；`src/routeTree.gen.ts` 由路由插件生成（勿手改）。

## 关键机制

### sidecar 启动握手（唯一数据通道）

1. Rust `src-tauri/src/sidecar.rs`：debug 模式拉起 `backend/.venv/Scripts/python.exe -m app.server --port 0 --token <32字节hex> --data-dir %USERPROFILE%\KnowRealm --ffmpeg <随包>`（release 用可执行目录旁的 knowrealm-sidecar）；从 stdout 的 `KNOWREALM_SIDECAR_PORT=<port>` 行解析随机端口，再以带令牌的 `GET /api/health` 探活。
2. 前端 `services/tauri/sidecar.ts` 的 `getSidecarConfig()`（invoke；带失败重置的 Promise 缓存）→ `services/http/client.ts` 统一携带 `X-KnowRealm-Token`。
3. 修改握手协议（stdout 标记行、启动参数）必须同步 `backend/app/server.py`。

### OpenAPI 契约链

API 类型一律 `import ... from "@knowrealm/api-types"`（禁止手写重复定义）；后端 schema 变更后跑 `pnpm --filter @knowrealm/api-types generate`，`check` 校验漂移。

### 录音链路（ADR-0009：sidecar 拥有暂存）

`RecordingExperience.tsx` 常驻 AppShell 顶栏：getUserMedia + MediaRecorder（webm/opus、`isTypeSupported` 探测降级）、暂停/继续、3 小时上限、崩溃恢复（启动时列出未完成会话弹窗：继续/结束/二次确认放弃）。分片经 multipart `POST /api/recording-sessions/{id}/chunks` 直传 sidecar（服务端返回权威 `recorded_duration_ms` 与低磁盘保护），`runExclusive` promise 链串行化保证分片顺序。**当前 PoC 分片间隔 20 秒**（`POC_CHUNK_MS = 20_000`；rules 目标 5–10 分钟）。Rust 侧只做防休眠（power.rs）与隐藏窗口，不落盘分片。

### SSE

`recordApi.subscribe`（原生 fetch + eventsource-parser 解析）只处理 `invalidate` 事件 → `invalidateQueries` → REST 重取；断线时非终态 Record 每 2 秒条件轮询（ADR-0008）。chat 走 `useChatTurns.ts`：POST 提交轮次、GET 订阅持久事件、显式 cancel；切换会话或卸载仅关闭订阅。持久消息与轮次是事实源，完成后失效重取；旧 rules 的 POST 执行流描述以根目录“已核实的规范差异”为准。

### 界面语言（zh/en）

首帧 = localStorage 缓存 ?? 系统语言，后端偏好到达后校正（防闪变）；`applyLanguage` 同时更新 `<html lang>` 与托盘菜单；新增文案 zh/en 两份同交（有一致性测试防线）。

### 首启向导分流

`__root.tsx` beforeLoad 发现未完成向导，一律重定向 `/onboarding`，托盘和快捷键都没有绕过入口。

### 关闭行为

TRAY=隐藏到托盘、EXIT=确认后退出、偏好未载入=直接退出（`mountCloseBehavior`，挂载一次实时读）。

### 图表（echarts）

echarts 按需注册只在 `charts/echarts.ts`，新增图表类型只改这里；配色读语义 token，亮暗主题自动跟随。

### 速记全局快捷键

注册在前端（global-shortcut JS API），Rust 侧无注册逻辑。

## 测试约定

- **无全局 jsdom**：需要 DOM 的测试文件首行写 `// @vitest-environment jsdom`；services 层测试走 node 环境。
- MSW **仅测试启用**：`test/setup.ts` 全局 `server.listen({ onUnhandledRequest: "error" })`；`mocks/handlers.ts` 有 14 个兜底 handler（courses、inbox、chat、providers、preferences、usage、profile、recording-sessions、today 等），具体路由在测试内 `server.use(...)` 局部覆盖；无 mockServiceWorker.js，dev 运行不经 MSW。
- 涉及 Tauri 的测试按需 `vi.mock` 对应 `services/tauri/*` 模块（sidecar、recording、lifecycle、onboarding、preferences 等）。
- 组件测试用 `renderWithQuery()`（`test/test-utils.tsx`：retry:false 临时 QueryClient + i18n）。
- eslint 的 `react-refresh/only-export-components` 已豁免 `Route` 导出（file-based 路由必需）。
