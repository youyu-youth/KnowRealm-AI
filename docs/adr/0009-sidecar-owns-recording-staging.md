# Sidecar 统一拥有录音暂存

MediaRecorder 产生的 WebM 分片通过受启动令牌保护的 localhost 接口交给 sidecar，由 sidecar 协调安全落盘、顺序校验与 `recording_sessions` 清单更新；Tauri 仅保留防休眠等系统能力，不直接拥有录音文件清单。这样文件与恢复事实只有一个协调者，可缩小“文件已写但清单未登记”的崩溃窗口，并避免向 WebView 开放数据目录文件权限。
