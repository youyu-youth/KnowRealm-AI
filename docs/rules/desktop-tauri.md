---
paths:
  - "apps/desktop/src-tauri/**"
  - "apps/desktop/src/services/tauri/**"
---

# 规范：Tauri 2 / Rust 原生层

> 适用范围：`apps/desktop/src-tauri/` Rust 代码、`capabilities/` 权限配置，及 React 侧 `services/tauri/`。Tauri 2.x，版本以 Cargo.lock 为准。

## 1. 前后端分工（自上而下，能满足就不往下）

1. 纯 UI/状态 → React；2. Web API 能力（fetch、MediaRecorder 录音本身）→ WebView；3. 窗口、系统电源、进程拉起看护、需 OS 权限的能力 → Rust；4. 业务逻辑、数据库、数据目录内文件生命周期（含录音分片落盘/清单/恢复）→ FastAPI sidecar。**Rust 只做系统能力，不做业务。**

- React 调 Tauri 一律经 `services/tauri/` 类型化封装，组件禁裸 `invoke()`。

## 2. Command 与状态

- 命令名/字段 snake_case（TS 侧自动转 camelCase）；每个命令返回 `Result<T, E>`，错误用 thiserror 层级并实现 `serde::Serialize`，**禁 `unwrap()/expect()`**（panic 带崩应用）；参数多于两个收拢 struct；新命令三步：`commands/` 实现 → `services/` 能力 → `lib.rs` 的 `invoke_handler` 注册。
- 共享状态 `tauri::State` + 锁（异步路径用 tokio 锁），禁全局 `static mut`；平台差异封装 `platform/` 用 `#[cfg(target_os)]` 切换，调用方无感。

## 3. 安全

- capabilities 权限最小化：只声明用到的 permission，逐项评审新增；禁 `fs:default` 全开、`allow-write-all`、全盘 scope、关闭 CSP；CSP 基线 `default-src 'self'`。
- 密钥/敏感配置存数据目录 `config/providers.json`（sidecar 读取），不进 Rust 代码与前端。
- 插件面：opener 只管打开文件/目录；fs 仅壳写 desktop.json；process 仅 relaunch；不装 shell 插件；sidecar 用 `std::process::Command` 拉起看护（随机端口经启动参数注入）；ffmpeg 经 externalBin 随包 `.msi`，生产禁读系统 PATH。

## 4. 数据目录边界

- UI 不直连数据库（不引入 tauri-plugin-sql）：一切业务读写经 localhost sidecar；第二个 sidecar 必须在迁移/worker 前因 OS 排他锁失败退出，壳把"数据目录正在使用"作为可理解错误展示，不自动换目录。
- 录音 WebM 分片经启动令牌保护的 sidecar 接口写 `cache/staging/`；会话与有序分片清单事实在 sidecar `recording_sessions`，前端不维护第二份；录音 UI 状态在 Zustand，两边不重复存。

## 5. 录音链路

- 前端每片 5–10 分钟 stop() → blob → sidecar 安全写入 staging；启动探测 `isTypeSupported("audio/webm;codecs=opus")`，失败降级提示；长录音用 Rust 防休眠（`platform/power.rs`）。
- sidecar 校验分片大小、顺序与 SHA-256 幂等，先写临时文件原子改名再更新清单；清单封口后不得追加或重排；启动恢复只处理本会话目录内孤儿暂存件。
- 转码在 sidecar worker 内 `create_subprocess_exec` 调随包 ffmpeg（ogg-opus 16kHz），成功注册 `record_file` 后才删 WebM；首次 ASR 外发须独立同意，只发送转码片段。

## 6. 质量

`cargo clippy -- -D warnings` 零警告；`cargo fmt` 统一格式；不引重型 crate 解决小问题。
