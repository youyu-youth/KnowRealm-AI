# 录音捕获与恢复

Status: completed

## 目标

在现有 Windows Tauri 工作台中验证并实现真实麦克风捕获：WebView2 使用 `MediaRecorder` 生成独立 WebM/Opus 分片，sidecar 统一负责 staging 落盘、顺序清单和 `recording_sessions` 恢复事实，封口后复用 04 的 Capture Batch 接缝。

## 已确认合同

- 开始前填写可空标题和可选课程；空标题使用本地开始时间生成 `录音 YYYY-MM-DD HH:mm`。
- 同一时刻最多一个 `RECORDING/PAUSED` 会话；`FINALIZING` 不阻塞新录音。
- 暂停立即封口当前片，继续创建新片；三小时上限只累计实际录音时长。
- `chunk_paths` 保持 JSON 有序数组，仅新增 `recorded_duration_ms`，不建分片表。
- 分片通过受启动令牌保护的 localhost multipart 接口交给 sidecar；同序号同 SHA-256 重试幂等，乱序或内容冲突返回 409。
- 开始前按 128kbps 和剩余录音上限校验 2× 预估空间；分片后空间不足则保存当前片并暂停。
- 启动恢复提供继续、结束处理、确认放弃；`FINALIZING` 自动重试 04 交接，失败保留 staging。
- 课程在开始后归档仍完成转写；删除后转入 Inbox。空标题和 Record 时间均以录音开始时刻为准。
- Tauri 只负责防系统休眠和 POC 隐藏窗口验证，不直接写录音分片。

## Q6 POC 边界

- POC 在生产桌面工程内实现，分片间隔临时为 20 秒；正常录制 60 秒可验证三片轮换。
- 真实验收包含两组不超过 60 秒的 Tauri 录音：正常开始/暂停/继续/结束及最小化/隐藏/锁屏；首片落盘后强杀、重启、继续并 finalize。
- POC 只证明短时真实捕获、独立分片、恢复和 03→04 交接；长录音、后台长期节流和生产 5 分钟分片保持未验证。

## 范围外

- WebM 合并、Ogg 转码、正式文件注册、ASR 与 Transcript 实现（复用 04）。
- 课堂标记、麦克风设备选择、波形、电平和 macOS。
