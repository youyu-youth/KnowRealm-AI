# 规范：Tauri 2 / Rust 原生层

> 适用范围：`apps/desktop/src-tauri/` 全部 Rust 代码、`capabilities/` 权限配置，以及 React 侧调用 Tauri 的代码（`services/tauri/`）。

## 0. 版本基线

| 依赖 | 基线 |
|---|---|
| Tauri | **2.x**（2024-10 GA，2026 主流） |
| tauri-plugin-sql / fs / dialog | 2.x 配套版 |
| Rust | stable 工具链，`clippy` 零警告 |

## 1. 前后端分工：什么才进 Rust

判定顺序（从上往下，能满足就不往下走）：

1. **纯 UI / 状态** → React（TS）解决；
2. **Web API 能力**（fetch、IndexedDB、MediaRecorder 录音本身）→ WebView 内解决；
3. **文件系统、窗口、系统电源、跨进程集成、性能敏感的本地 IO**（录音分片落盘索引、大文件路径管理）→ **Rust**；
4. **业务逻辑 / 数据计算** → 不进 Rust，下沉到 FastAPI 后端。Rust 层只做"能力"，不做"业务"。

```
React（services/tauri/ 封装 invoke）
   │  invoke("save_recording_chunk", {...})   唯一通道
   ▼
src-tauri/src/commands/  ← 参数校验 + 编排
   ▼
src-tauri/src/services/  ← 原生能力实现（fs、平台 API）
```

规则：**React 不直接调 plugin API 的地方一律经 `services/tauri/` 封装**（类型化 + 统一错误处理），组件里禁止散落裸 `invoke()`。

## 2. Command 规范

```rust
// commands/recording.rs
use serde::{Deserialize, Serialize};

#[derive(Debug, thiserror::Error)]
pub enum CommandError {
    #[error("IO 错误: {0}")]
    Io(#[from] std::io::Error),
}
impl serde::Serialize for CommandError {   // 错误必须可序列化，才能传回前端
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

#[derive(Deserialize)]
pub struct SaveChunkArgs {
    pub record_id: String,
    pub chunk_index: u32,
}

#[derive(Serialize)]
pub struct SaveChunkResult {
    pub saved_path: String,
}

#[tauri::command]
pub async fn save_recording_chunk(
    args: SaveChunkArgs,
    state: tauri::State<'_, crate::state::AppState>,
) -> Result<SaveChunkResult, CommandError> {
    let path = crate::services::recording::save_chunk(&state, &args).await?;
    Ok(SaveChunkResult { saved_path: path })
}
```

```ts
// services/tauri/recording.ts —— 前端侧类型化封装
import { invoke } from "@tauri-apps/api/core";

export async function saveRecordingChunk(args: {
  recordId: string;      // Rust snake_case 字段在 JS 侧自动映射为 camelCase
  chunkIndex: number;
}): Promise<{ savedPath: string }> {
  return invoke("save_recording_chunk", { args });
}
```

- 命令名 `snake_case`；Rust 字段 snake_case，TS 侧 camelCase（Tauri 2 自动转换）。
- 每个命令都要 `Result<T, E>` 返回，错误实现 `serde::Serialize`——**禁止 `unwrap()/expect()`**（panic 会带崩整个应用）。
- 参数多于两个就收拢成 struct（如上 `SaveChunkArgs`），便于校验与扩展。
- 命令注册集中在 `lib.rs` 的 `invoke_handler`，新命令三步走：`commands/` 实现 → `services/` 能力 → `lib.rs` 注册。

## 3. 安全（Tauri 2 的 capabilities 体系）

- **权限最小化**：`capabilities/` 里只声明用到的 permission，逐项评审新增。

```json
// capabilities/default.json —— 示例：录音暂存只需要写 app 数据目录
{
  "identifier": "default",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "sql:default",
    "dialog:default",
    { "identifier": "fs:allow-appdata-read-recursive" },
    { "identifier": "fs:allow-appdata-write-recursive" }
  ]
}
```

- ❌ 禁止：`fs:default` 全开、`allow-write-all`、给整个磁盘开 scope、关闭 CSP。
- `tauri.conf.json` 的 CSP 以 **`default-src 'self'`** 为基线（官方建议）；确需内联脚本用 Tauri 的 hash/nonce 注入，引入远程内容须显式审慎。
- 密钥/敏感配置**不进** Rust 代码与前端，一律后端持有。

## 4. State 与并发

```rust
// state/app_state.rs
#[derive(Default)]
pub struct AppState {
    pub recording: tokio::sync::Mutex<RecordingSession>,  // 异步锁优先，别用 std::Mutex 卡 runtime
}

// lib.rs
.manage(AppState::default())
```

- 共享状态一律 `tauri::State` + 锁（异步路径用 `tokio::sync::Mutex/RwLock`），**禁止全局 `static mut`**。
- 平台差异封装在 `platform/` 模块，用 `#[cfg(target_os = "windows")]` 切换，调用方无感：

```rust
// platform/power.rs —— Windows 防休眠，3 小时长录音依赖
#[cfg(target_os = "windows")]
pub fn keep_awake(on: bool) -> anyhow::Result<()> { /* SetThreadExecutionState */ }

#[cfg(not(target_os = "windows"))]
pub fn keep_awake(_on: bool) -> anyhow::Result<()> { Ok(()) }
```

## 5. 本地 SQLite（tauri-plugin-sql）

定位（对应架构 D1 决策）：**读缓存 + 录音暂存队列索引**。业务写一律在线走 FastAPI，**禁止在本地 SQLite 里积累待同步的业务数据变更**（除录音暂存队列这一个例外，它是上传前的暂存，不是业务编辑）。

```ts
// services/tauri/db.ts —— SQLite 连接与语句集中封装
import Database from "@tauri-apps/plugin-sql";

const db = await Database.load("sqlite:app-cache.db");

// ✅ 参数化查询，禁止字符串拼 SQL
export async function getCachedRecords(courseId: string) {
  return db.select<{ id: string; title: string }[]>(
    "SELECT id, title FROM cached_records WHERE course_id = $1",
    [courseId],
  );
}
```

- SQL 语句集中在 `services/tauri/` 的封装模块里，组件/hooks 里禁止裸写 SQL。
- **表名与结构以数据模型 §5 的十表为准**：`local_record_drafts`（录音草稿）、`local_files`（文件索引+上传队列）、`cached_courses/cached_records/cached_transcripts/cached_transcript_segments/cached_ai_summaries`（只读镜像）、`sync_outbox`（V1 仅文件注册类）、`sync_cursor`、`local_settings`——不自行发明新缓存表，增补须先改数据模型文档。

## 6. 录音链路（项目最关键的原生协同）

```
WebView: getUserMedia → MediaRecorder(webm/opus)
  ├─ 每片 5–10 分钟 stop() → blob → 暂存盘（防中断全损）
  ├─ 启动时 isTypeSupported("audio/webm;codecs=opus") 探测，失败走降级提示
  ├─ 分片索引写入本地 SQLite（record_id / chunk_index / path）
  └─ 后台节流风险：长录音时用 Tauri 防休眠（platform/power.rs）
```

规则：
- 分片上传用 Storage 直传（supabase-js），**不经 FastAPI 转发大文件**；
- 转码在后端 worker 做（前端不做格式转换）：**ffmpeg 转码为 `ogg-opus@16kHz`**（腾讯云 ASR 不支持 webm 容器，功能基线裁决 #5 定稿）；无损 remux（`-c:a copy`）作为 S0 POC 的待验证优化项——若实测识别质量无差异再降级采用并回改文档；
- 录音会话状态（进行中/分片数）在 Zustand，分片文件路径事实在 SQLite（`local_record_drafts` / `local_files`），两边不重复存。

## 7. Rust 代码质量

- `cargo clippy -- -D warnings` 零警告；`cargo fmt` 统一格式。
- 错误类型用 `thiserror` 定义层级，命令层错误统一 `serde::Serialize`。
- 不引入重型 crate 解决小问题（遵循项目"轻量化"定位）。

## 8. 自动更新（updater，Phase 0 后启用）

- 用 `tauri-plugin-updater`，`capabilities/` 中只授 `updater:default` + `allow-check` / `allow-download-and-install`，不放开多余权限。
- **签名密钥管理**：`TAURI_SIGNING_PRIVATE_KEY` / `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` 只存 CI 环境变量，密钥文件与仓库物理分离；构建产物附 `.sig`，无签名更新包一律拒装。
- 更新策略：启动后延时静默 check，下载安装经用户确认（与 Autopilot"只推荐不执行"同哲学）；更新失败降级为提示，不阻塞应用使用。

## 9. 反模式速查

| 禁止 | 用什么代替 |
|---|---|
| 业务逻辑写进 Rust | 下沉 FastAPI；Rust 只做原生能力 |
| 组件里裸 `invoke()` | `services/tauri/` 类型化封装 |
| command 里 `unwrap()/expect()` | `Result` + thiserror |
| 命令参数平铺一大串 | 收拢成 Args struct |
| capabilities 开 `fs:default`/全盘 scope | 最小 permission + appdata scope |
| 关闭 CSP | 保持默认 CSP |
| `static mut` 共享状态 | `tauri::State` + tokio 锁 |
| 前端拼 SQL 字符串 | 参数化查询（`$1` 占位） |
| 本地 SQLite 当业务主库 | 只做缓存 + 录音暂存队列 |
| 大文件走 FastAPI 上传 | Storage 直传 |
| 录音不做分片 / 不探测格式支持 | 5–10 分钟分片 + `isTypeSupported` 兜底 |
