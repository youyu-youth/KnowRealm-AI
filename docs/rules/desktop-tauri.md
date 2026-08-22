# 规范：Tauri 2 / Rust 原生层

> 适用范围：`apps/desktop/src-tauri/` 全部 Rust 代码、`capabilities/` 权限配置，以及 React 侧调用 Tauri 的代码（`services/tauri/`）。

## 0. 版本基线

| 依赖 | 基线 |
|---|---|
| Tauri | **2.x**（2024-10 GA，2026 主流） |
| tauri-plugin-fs / dialog / global-shortcut / autostart / shell | 2.x 配套版（shell 承担 sidecar 拉起与看护） |
| Rust | stable 工具链，`clippy` 零警告 |

## 1. 前后端分工：什么才进 Rust

判定顺序（从上往下，能满足就不往下走）：

1. **纯 UI / 状态** → React（TS）解决；
2. **Web API 能力**（fetch、IndexedDB、MediaRecorder 录音本身）→ WebView 内解决；
3. **文件系统、窗口、系统电源、跨进程集成、性能敏感的本地 IO**（录音分片落盘索引、大文件路径管理）→ **Rust**；
4. **业务逻辑 / 数据计算** → 不进 Rust，下沉到 FastAPI sidecar。Rust 层只做"能力"，不做"业务"。

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
// capabilities/default.json —— 示例：fs 权限收敛到数据目录（首启选定，非 appdata），
// 录音分片仅写 cache/staging/
{
  "identifier": "default",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "dialog:default",
    "global-shortcut:default",
    "autostart:default",
    "shell:default",
    { "identifier": "fs:allow-write-file" },
    { "identifier": "fs:allow-read-file" }
  ]
}
```

- ❌ 禁止：`fs:default` 全开、`allow-write-all`、给整个磁盘开 scope、关闭 CSP。
- `tauri.conf.json` 的 CSP 以 **`default-src 'self'`** 为基线（官方建议）；确需内联脚本用 Tauri 的 hash/nonce 注入，引入远程内容须显式审慎。
- 密钥/敏感配置存数据目录 `config/providers.json`（sidecar 读取），**不进** Rust 代码与前端。

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

## 5. 数据目录访问边界（无本地 SQLite）

- **UI 不直连数据库**（不引入 tauri-plugin-sql）：一切业务读写经 localhost sidecar API——sidecar 是 knowrealm.db 唯一写者（红线 #35，技术栈 v4.3 D1）。同一数据目录的第二个 sidecar 必须在迁移/worker 前因 OS 排他锁失败而退出；壳把“数据目录正在使用”作为可理解的启动错误展示，不能自动换目录或绕过锁。
- React/Tauri 对数据目录的直写**仅限录音分片落盘**（`cache/staging/`，防中断全损的暂存件）——这是唯一例外，且不是业务数据；会话与分片清单事实由 sidecar 写 `recording_sessions`（`chunk_paths`），前端不维护第二份。
- sidecar 二进制与可审计 LGPL-compatible ffmpeg 经 `externalBin` 随包打进 `.msi`；生产禁止读取系统 PATH。壳用 shell 插件拉起/看护 sidecar（随机端口经启动参数注入，UI 从壳读取——技术栈 v4.3 §十）。

## 6. 录音链路（项目最关键的原生协同）

```
WebView: getUserMedia → MediaRecorder(webm/opus)
  ├─ 每片 5–10 分钟 stop() → blob → Rust 写数据目录 cache/staging/（防中断全损）
  ├─ 启动时 isTypeSupported("audio/webm;codecs=opus") 探测，失败走降级提示
  └─ 后台节流风险：长录音时用 Tauri 防休眠（platform/power.rs）
```

规则：
- 03 只负责 staging 分片、`recording_sessions` 恢复与 finalize；清单封口后不得追加或重排。04 负责合并、ffmpeg 转 `ogg-opus` 16kHz、原子注册最终 `record_file`，成功后才删除 WebM；
- 转码在 sidecar worker 内经 `asyncio.create_subprocess_exec` 调用随包 ffmpeg；首次 ASR 外发须独立同意，只发送转码片段，不发送导入原件或录音 WebM；
- 录音 UI 状态在 Zustand；会话与有序分片清单事实在 `recording_sessions`（sidecar 写，数据模型 v2.2 §4.2），两边不重复存。

## 7. Rust 代码质量

- `cargo clippy -- -D warnings` 零警告；`cargo fmt` 统一格式。
- 错误类型用 `thiserror` 定义层级，命令层错误统一 `serde::Serialize`。
- 不引入重型 crate 解决小问题（遵循项目"轻量化"定位）。

## 8. 自动更新（updater，后置启用，#47）

- 用 `tauri-plugin-updater`，`capabilities/` 中只授 `updater:default` + `allow-check` / `allow-download-and-install`，不放开多余权限。
- **签名密钥管理**：`TAURI_SIGNING_PRIVATE_KEY` / `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` 只存 CI 环境变量，密钥文件与仓库物理分离；构建产物附 `.sig`，无签名更新包一律拒装。
- 更新策略：启动后延时静默 check，下载安装经用户确认（与 Autopilot"只推荐不执行"同哲学）；更新失败降级为提示，不阻塞应用使用。

## 9. 反模式速查

| 禁止 | 用什么代替 |
|---|---|
| 业务逻辑写进 Rust | 下沉 FastAPI sidecar；Rust 只做原生能力 |
| 组件里裸 `invoke()` | `services/tauri/` 类型化封装 |
| command 里 `unwrap()/expect()` | `Result` + thiserror |
| 命令参数平铺一大串 | 收拢成 Args struct |
| capabilities 开 `fs:default`/全盘 scope | 最小 permission + 数据目录最小 scope |
| 关闭 CSP | 保持默认 CSP |
| `static mut` 共享状态 | `tauri::State` + tokio 锁 |
| 前端直连数据库 / 直写业务数据 | 一切经 sidecar API（唯一写者） |
| 数据目录直写超出录音分片落盘范围 | 分片只进 cache/staging/，业务数据经 sidecar |
| 录音不做分片 / 不探测格式支持 | 5–10 分钟分片 + `isTypeSupported` 兜底 |
