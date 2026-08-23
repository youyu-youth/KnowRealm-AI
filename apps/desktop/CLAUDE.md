# apps/desktop（@knowrealm/desktop 桌面端）

Tauri 2 壳 + React 19 + Vite 7 + TanStack Router（file-based）+ Tailwind CSS 4 + shadcn/ui（Base UI 底座，style `base-nova`）。业务数据一律经 localhost sidecar API 读写，UI 不直连数据库。

> 编码规范正本是根目录 `.claude/rules/desktop-*.md`（自动加载，本文不重复）。本文件记录本目录的**命令、结构与已验证现状**；rules 部分内容描述的是目标态，差异见文末 Gotchas——**不要为了对齐 rules 而主动重构现有代码**。

## 常用命令

| 命令（本目录内执行）                  | 说明                                                                                                                                                        |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pnpm dev`                            | Vite dev server，端口 1420（strictPort）。仓库根执行用 `pnpm --filter @knowrealm/desktop dev`（无根 package.json，workspace 由 `pnpm-workspace.yaml` 定义） |
| `pnpm build`                          | **类型检查内嵌于此**（双 tsconfig `tsc --noEmit`）+ `vite build`；无独立 typecheck 脚本                                                                     |
| `pnpm lint`                           | `eslint . --max-warnings 0`                                                                                                                                 |
| `pnpm test`                           | `vitest run`（配置内嵌 `vite.config.ts`，无独立配置文件）                                                                                                   |
| `pnpm format:check`                   | `prettier --check .`（覆盖 `.md`；无写入型 format 脚本）                                                                                                    |
| `pnpm tauri dev` / `pnpm tauri build` | 拉起完整壳。`pretauri` 钩子自动跑 `scripts/prepare-ffmpeg.ps1`（固定版本 + SHA256 校验，幂等）；`src-tauri/binaries/` **不入库**，新克隆首次自动下载        |

Rust 侧（`src-tauri/` 内）：`cargo test`（测试内嵌在各文件 `#[cfg(test)]` 模块）/ `cargo clippy -- -D warnings` / `cargo fmt`。

## 目录结构（现状）

```
src/
├── pages/               # TanStack file-based 路由，扁平命名（spaces.index.tsx、records.$recordId.tsx）
├── features/            # 业务功能内聚（组件 + api + 类型）
│   ├── courses/           # 课程 CRUD 闭环（最完整：筛选走 searchParams、编辑、软删）
│   ├── records/           # 记录详情：Summary/Transcript tab、SSE 订阅、转写编辑、删除
│   ├── document-import/   # 「导入资料」对话框，走 POST /api/capture-batches（documentImports.ts 为旧单文档 API）
│   ├── recording/         # 录音完整体验（扁平结构：api.ts + RecordingExperience.tsx）
│   ├── audio-import/      # 仅单音频导入 API 封装，无 UI
│   └── settings/          # 仅腾讯 ASR 外发同意 API
├── components/          # ui/ = shadcn 生成物（勿手改）；common/ = 跨 feature；layout/AppShell.tsx 唯一布局
├── services/http/       # client.ts：统一 base URL、X-KnowRealm-Token（强制覆盖）、ApiError、FormData 边界
├── services/tauri/      # sidecar.ts（getSidecarConfig）、recording.ts（电源/窗口封装，名不副实）
├── app/queryClient.ts   # staleTime 60s / retry 2 / refetchOnWindowFocus false
├── i18n/locales/        # zh.json（V1 唯一语言文件）
├── mocks/               # MSW（仅测试启用）
├── test/                # setup.ts + test-utils.tsx（renderWithQuery）
└── styles/              # tokens / theme / globals / animations 四件套
```

注意：`hooks/`、`stores/`、`charts/` 顶层目录**不存在**；`src/routes/` 是空目录残留；`src/routeTree.gen.ts` 由路由插件生成（勿手改），`.tanstack/` 仅插件缓存。

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

`recordApi.subscribe`（原生 fetch + eventsource-parser 解析）只处理 `invalidate` 事件 → `invalidateQueries` → REST 重取；断线时非终态 Record 每 2 秒条件轮询（ADR-0008）。

## 测试约定

- **无全局 jsdom**：需要 DOM 的测试文件首行写 `// @vitest-environment jsdom`；services 层测试走 node 环境。
- MSW **仅测试启用**：`test/setup.ts` 全局 `server.listen({ onUnhandledRequest: "error" })`；`mocks/handlers.ts` 只有 2 个兜底 handler（courses、recording-sessions 空列表），具体路由在测试内 `server.use(...)` 局部覆盖；无 mockServiceWorker.js，dev 运行不经 MSW。
- 涉及 Tauri 的测试一律 `vi.mock("@/services/tauri/sidecar")`（及 `recording`）桩掉 invoke。
- 组件测试用 `renderWithQuery()`（`test/test-utils.tsx`：retry:false 临时 QueryClient + i18n）。
- eslint 的 `react-refresh/only-export-components` 已豁免 `Route` 导出（file-based 路由必需）。
