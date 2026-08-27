# 04 - 音频导入与转写管线

> Wave: A ｜ PRD: §4.3.2（音频）/ §4.3.3 / §4.3.4 ｜ 决策引用: #8 #31 #35 #44 #45 #49 #54 #58 ｜ ADR: 0002~0006

> Status: ready-for-human（Issue 01/02 实现与自动化已完成；真实腾讯 P0、真实 Tauri Network/渲染待人工验收）

## 功能描述 / 目标

把一次封口的 Capture Batch（音频、文档或混合来源）可靠地转成一份合并 Transcript，并为音频提供随包 ffmpeg、本地顺序切片、腾讯 ASR 检查点恢复、隐私同意与 Record 级状态通知。复用 05 的 worker / `processing_jobs` / 文档解析基础；完整总结出口由 06 承担。

## 功能范围

**做**：
- 在现有顶部“导入资料”对话框增加原生多选；`POST /api/capture-batches` 一次接收有序来源数组，提交即封口，不持久化 batch 实体；保留 `/api/document-imports`
- 整批预校验格式、损坏、音频总时长和可用磁盘；任一项不合法则整批拒绝、清理临时文件，不创建 Record / File / Job
- 音频格式 MP3 / AAC / WAV / M4A，以及 03 交来的已封口录音 staging；录音会话 ≤3 小时，单批全部音频总时长 ≤5 小时，正式注册前要求至少 2× 批次原件总字节可用空间
- 顺序按选择数组固化为 `sequence_no=0..N-1`；提交后不可追加或重排。单一来源沿用 DOCUMENT_IMPORT / AUDIO_IMPORT / RECORDING，混合来源写 MULTI_SOURCE
- 标题自动生成：单文件取 stem；多文件为“首文件 stem + 等 N 个文件”；不新增标题输入
- 每个音频创建 `AUDIO_TRANSCODE → ASR` 两个 Job；同一 Record 任一 Job 失败后暂停其后续 PENDING Job，其他 Record 继续处理；Record 总进度为全部 Job `progress` 的简单平均
- 03 录音输入由 04 合并并用 Tauri `externalBin` 随包的可审计 LGPL-compatible ffmpeg 转为 Ogg Opus 16kHz；原子注册最终 AUDIO/RECORDED `record_file` 后删除 WebM staging
- 导入音频原件作为正式 `record_file` 保留；标准化音频与 ASR 片位于 cache，可重建
- ASR 将标准化音频切成目标 ≤5 分钟且严格 `<5MB` 的有序本地片；单个 ASR Job 顺序提交，不引入 COS / 公网 URL / 切片表 / 父 Job
- `input_json` 固化片清单、热词、模型、地域等非秘密配置；`result_json` 保存 task id、片状态与恢复游标。凭据始终读取当前配置，不写入 Job
- 首次向腾讯发送转码音频前取得独立 External Processing Consent；配置 key 不等于同意。未同意、缺 key 或离线时 Record 保持 CONTENT_PROCESSING、Job 保持 PENDING 并展示等待原因，不增加 attempts；条件满足后自动继续
- 自动重试仅覆盖安全的瞬时轮询/供应商故障，每轮最多 3 次。提交超时且无 TaskId 记 `ASR_SUBMIT_UNKNOWN`，不得自动重提；鉴权、配额、输入错误不自动重试
- 手动重试复用原 ASR Job 与检查点：保留成功片和仍有效 TaskId，仅重置失败、过期或未提交片
- 全批成功后按 `sequence_no` 用两个换行合并正文并原子创建 Transcript；不注入文件名、时间戳或标题。任一来源失败或音频无语音（`NO_SPEECH_DETECTED`）则不发布部分 Transcript
- 纯音频写 `language=zh-CN`；含文档/混合来源写 `und`。V1 不持久化腾讯句子时间范围，Segment/时间轴留 P2
- Transcript 仅在内容成功且 Summary 未处理时显式保存；PATCH 携带 `expected_source_version`，原子比较失败返回 409。成功后 source_version +1、旧 Summary→SUPERSEDED、Record→SUMMARY_PENDING；重新生成须用户明确触发
- `GET /api/records/{record_id}/jobs` 提供聚合任务状态；页面 URL 只保留 `recordId` 与 tab，不携带 job id
- `/api/records/{record_id}/events` 使用启动令牌的 authenticated fetch-stream，只发送失效通知；收到事件、重连、窗口恢复后 REST 重取。断线时仅非终态 Record 每 2 秒条件轮询，不做事件重放
- 删除/取消立即停止本地任务、丢弃迟到结果并清理 cache；远端取消仅 best effort。启动时清理无归属临时文件；成功后删除 ASR 片与临时文本，仅在 `result_json` 保留技术元数据

**不做**：
- V1 Segment / 句子时间戳 / 音频时间轴、英文 ASR、静音检测增强、重叠切片或文本去重
- COS / S3 / 公网 URL、持久化 Capture Batch、父/聚合 Job、ASR 切片表、并发提交片、多账户或 ASR Provider 抽象
- 新导入页面、录音捕获 UI（03）、文档/混合来源的可选课程与 Inbox 可达性（11）、完整 Summary/HITL（06）、音频播放器

## 核心业务流程

选择有序多来源或接收 03 finalize → 整批预校验 → 原子注册 Record / Files / Jobs → CONTENT_PROCESSING → 文档解析；音频转码/切片 → 等待同意、key 与网络 → 顺序提交/轮询腾讯 ASR → 全部来源成功 → 原子发布合并 Transcript → SUMMARY_PENDING → 仅在课程 ACTIVE 时由 06 自动触发总结。Record 级 SSE 只通知 UI 重新读取 REST。

## 关键业务规则

- audio-only / 录音可不选课；文档/混合批次的课程可选能力由 11 扩展到统一 Capture Batch。无课程批次仍完成内容处理与 Transcript，但不得自动触发 Summary
- 课程在内容处理期间归档：已受理内容继续完成并保留 Transcript，但不得自动触发 Summary
- 一个音频一个 ASR Job，片状态只保存在该 Job JSON；不用“每片一个 Job”或批次父 Job
- 正式文件：导入原件或录音最终 Ogg。缓存：标准化音频、ASR 片、临时文本
- 合并 Transcript 是唯一业务发布点；失败时只保留技术检查点，不暴露半成品正文
- V1 固定时长/体积切片；只有 P0 真实音频证明边界丢字后，才另行评估重叠或去重
- 稳定错误码：预注册通用边界使用 `EMPTY_BATCH` / `EMPTY_SOURCE` / `UNSUPPORTED_SOURCE`，音频边界使用 `UNSUPPORTED_AUDIO` / `CORRUPT_AUDIO` / `AUDIO_TOO_LONG` / `INSUFFICIENT_DISK`；处理后 `AUDIO_TRANSCODE_FAILED` / `ASR_AUTH_FAILED` / `ASR_QUOTA_EXHAUSTED` / `ASR_TEMPORARY_UNAVAILABLE` / `ASR_SUBMIT_UNKNOWN` / `ASR_RECOGNITION_FAILED` / `ASR_TASK_EXPIRED` / `NO_SPEECH_DETECTED`
- 转写全文、音频内容、密钥和 Authorization 禁止进日志；可记录 record_id、job_id、片序号、耗时与稳定错误码

## 前置依赖

- 02（Record 列表/详情、Transcript 页签与删除语义）
- 05（worker、`processing_jobs`、`record_files`、文档解析与条件轮询基础）
- 完整出口集成已完成的 06；04 自身构建依赖只要求 02/05

## 验收标准（出口线）

- [ ] P0 使用随包 ffmpeg、真实中文音频和真实腾讯请求验证转码、严格 `<5MB` 顺序切片、提交/轮询、边界文本、进程重启恢复；运行时不读取系统 PATH
- [ ] 单 MP3 导入后，Record 详情显示不含时间戳的合并正文；导入原件保留，成功缓存已清理
- [ ] 同一批真实挂载音频+文档，按 sequence_no 以两个换行合并；capture_type=MULTI_SOURCE，任一来源失败时无部分 Transcript
- [ ] 整批预校验失败不创建 Record/File/Job；录音 >3h、批次音频 >5h、损坏音频与磁盘不足均有稳定错误码
- [ ] 未同意、缺 key、离线时 Job=PENDING 且 attempts 不增加；补齐条件后自动继续。首次同意明确告知“原件留本地，仅转码片段发送腾讯”
- [ ] ASR 提交超时无 TaskId 时不自动重提；手动重试保留成功片和有效 TaskId；重启不重复成功片
- [ ] Record 级 SSE 只触发 REST 失效重取；断线时非终态 2 秒条件轮询，页面刷新后从 SQLite 恢复且 URL 无 job id
- [ ] Transcript 并发编辑以 expected_source_version 返回 409；成功保存使旧 Summary 过时且不自动重生成
- [ ] 删除处理中 Record 后本地 Job=CANCELLED、cache 立即清理、远端取消 best effort、迟到结果不入库
- [ ] 课程处理期间归档仍完成 Transcript，但不创建 Summary Job；ACTIVE 课程可由已完成的 06 进入完整 Summary/HITL 出口
