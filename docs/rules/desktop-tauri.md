# 规范：Tauri 2 / Rust 原生层

> 适用范围：`apps/desktop/src-tauri/` 全部 Rust 代码、`capabilities/` 权限配置，以及 React 侧调用 Tauri 的代码（`services/tauri/`）。

## 0. 版本基线

| 依赖 | 基线 |
|---|---|
| Tauri | **2.x**（2024-10 GA，2026 主流） |
| tauri-plugin-dialog / global-shortcut / autostart / opener / fs / process / window-state | 2.x 配套版，以 `Cargo.toml` 锁文件为准（opener 只管打开文件/目录；fs 仅壳写 desktop.json；process 仅 relaunch；sidecar 用 `std::process::Command` 拉起与看护） |
| Rust | stable 工具链，`clippy` 零警告 |

## 1. 前后端分工：什么才进 Rust

判定顺序（从上往下，能满足就不往下走）：

1. **纯 UI / 状态** → React（TS）解决；
2. **Web API 能力**（fetch、IndexedDB、MediaRecorder 录音本身）→ WebView 内解决；
3. **窗口、系统电源、进程拉起与看护、需要操作系统权限的能力** → **Rust**；
4. **业务逻辑、数据库与数据目录内的文件生命周期**（包括录音分片落盘、清单与恢复）→ FastAPI sidecar。Rust 层只做系统能力，不做业务或业务文件协调。

```
React（services/tauri/ 封装 invoke）
   │  invoke("set_recording_keep_awake", {...})
   ▼
src-tauri/src/commands/  ← 参数校验 + 编排
   ▼
src-tauri/src/services/  ← 原生能力实现（窗口、进程、平台 API）
```

规则：**React 不直接调 plugin API 的地方一律经 `services/tauri/` 封装**（类型化 + 统一错误处理），组件里禁止散落裸 `invoke()`。

## 2. Command 规范

```rust
// commands/power.rs
use serde::Serialize;

#[derive(Debug, thiserror::Error)]
pub enum CommandError {
    #[error(transparent)]
    Power(#[from] crate::services::power::PowerError),
}
impl serde::Serialize for CommandError {   // 错误必须可序列化，才能传回前端
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

#[tauri::command]
pub fn set_recording_keep_awake(
    enabled: bool,
    state: tauri::State<'_, crate::state::PowerState>,
) -> Result<(), CommandError> {
    crate::services::power::set_keep_awake(&state, enabled)?;
    Ok(())
}
```

```ts
// services/tauri/recording.ts —— 前端侧类型化封装
import { invoke } from "@tauri-apps/api/core";

export function setRecordingKeepAwake(enabled: boolean): Promise<void> {
  return invoke("set_recording_keep_awake", { enabled });
}
```

- 命令名 `snake_case`；Rust 字段 snake_case，TS 侧 camelCase（Tauri 2 自动转换）。
- 每个命令都要 `Result<T, E>` 返回，错误实现 `serde::Serialize`——**禁止 `unwrap()/expect()`**（panic 会带崩整个应用）。
- 参数多于两个就收拢成 struct（如上 `SaveChunkArgs`），便于校验与扩展。
- 命令注册集中在 `lib.rs` 的 `invoke_handler`，新命令三步走：`commands/` 实现 → `services/` 能力 → `lib.rs` 注册。

## 3. 安全（Tauri 2 的 capabilities 体系）

- **权限最小化**：`capabilities/` 里只声明用到的 permission，逐项评审新增。

```json
// capabilities/default.json —— 仅授予当前窗口实际使用的系统能力
{
  "identifier": "default",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "dialog:default",
    "global-shortcut:default",
    "autostart:default",
    "opener:allow-open-path"
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

## 5. 数据目录访问边界（SQLite 唯一事实源在 sidecar）

- **UI 不直连数据库**（不引入 tauri-plugin-sql）：一切业务读写经 localhost sidecar API——sidecar 是 `knowrealm.db` 与数据目录业务文件的唯一协调者。同一数据目录的第二个 sidecar 必须在迁移或 worker 启动前因 OS 排他锁失败而退出；壳把“数据目录正在使用”作为可理解的启动错误展示，不能自动换目录或绕过锁。
- React/Tauri 不直接写数据目录。录音 WebM 分片通过受启动令牌保护的 sidecar 接口写入 `cache/staging/`；sidecar 同时维护 `recording_sessions` 的会话与有序分片清单，前端不维护第二份。
- sidecar 二进制与可审计 LGPL-compatible ffmpeg 经 `externalBin` 随包打进 `.msi`；生产禁止读取系统 PATH。壳用 `std::process::Command` 拉起/看护 sidecar（随机端口经启动参数注入，UI 从壳读取——技术栈 v4.5 §十）。不装 shell 插件：打开文件/目录用 opener，拉进程只留在 Rust 侧。

## 6. 录音链路（项目最关键的原生协同）

```
WebView: getUserMedia → MediaRecorder(webm/opus)
  ├─ 每片 5–10 分钟 stop() → blob → sidecar 安全写入 cache/staging/
  ├─ 启动时 isTypeSupported("audio/webm;codecs=opus") 探测，失败走降级提示
  └─ 后台节流风险：长录音时用 Tauri 防休眠（platform/power.rs）
```

规则：
- 03 只负责 staging 分片、`recording_sessions` 恢复与 finalize；清单封口后不得追加或重排。04 负责合并、ffmpeg 转 `ogg-opus` 16kHz、原子注册最终 `record_file`，成功后才删除 WebM；
- sidecar 接收分片后校验大小、顺序与 SHA-256 幂等性，先写临时文件并原子改名，再更新会话清单；启动恢复只处理本会话目录内的孤儿暂存件；
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
| capabilities 开 `fs:default`/全盘 scope | 只授予实际使用的系统能力 |
| 关闭 CSP | 保持默认 CSP |
| `static mut` 共享状态 | `tauri::State` + tokio 锁 |
| 前端直连数据库 / React 或 Tauri 直接写数据目录 | 一切经 sidecar API（唯一协调者） |
| 录音不做分片 / 不探测格式支持 | 5–10 分钟分片 + `isTypeSupported` 兜底 |
