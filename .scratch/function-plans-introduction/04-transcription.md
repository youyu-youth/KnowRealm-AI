# 04 - 音频导入与转写管线

> Wave: A ｜ PRD: §4.3.2（音频）/ §4.3.3 ｜ 决策引用: #31 #33→#43 #44 #49 #54

## 功能描述 / 目标

音频（导入 + 录音共用）→ 带时间戳转写全文的完整后端管线，并引入 sidecar SSE 状态推送与 processing_jobs 技术任务态——状态机真正"动起来"的第一环。

## 功能范围

**做**：
- 音频导入入口：MP3 / AAC / WAV / M4A（+录音产生 webm / ogg-opus）；导入时长 ≤5h（对齐 ASR 供应商上限，#44）；无体积硬限，仅磁盘剩余空间防呆（≥2× 预估体积，不足提示）
- record_files 按导入先后自动定序；CONTENT_PROCESSING 开始后不可重排（要改顺序=删除重导，#54）
- worker 统一转码：全部音频 ffmpeg → ogg-opus@16kHz（#31，不可省略）
- 腾讯云录音文件识别（标准版）：句子级时间戳、热词取课程设置（01 维护的 ≤100 词）
- Transcript 持久化（V1 整段合并文本，快速展示用）；转写文本编辑与保存
- processing_jobs 技术任务态（业务态不混写）；sidecar 进程内事件（SSE）推送 records 状态变更（UI 轮询兜底，#8）
- 失败 → FAILED + 可重试；content_hash 落盘校验；处理中删除竞态（每步写前校验 deleted_at，软删即终止丢弃产物，#54）

**不做**：
- Segment 句子级持久化（P2）、英文 ASR（P2）、音频文件本身的前端预览播放

## 核心业务流程

导入音频 / 收到录音分片 → 注册 record_files → CONTENT_PROCESSING（worker 本地 ffmpeg 转码 + ASR 提交/轮询，多文件并行按序合并）→ Transcript 落库 → 已选课自动触发 06 / 未选课停 SUMMARY_PENDING → sidecar SSE 推送状态

## 关键业务规则

- V1 仅普通话语音；英文文本处理见 05（#45）
- 转写全文禁止进日志（隐私红线）；可记录 record_id / latency / error code
- 后台任务可重试且幂等（idempotency_key）
- 导入原件经 API 原样保留 files/（可逆性优先），转码产物放 cache/（可清可重建）；ASR SDK 仅在 worker 任务内使用（R9）

## 前置依赖

- 02（记录详情展示转写）
- P0-07（进程内 asyncio worker 骨架）

## 验收标准（出口线）

- [ ] 导入 1 个 MP3 → 状态流转可见（SSE 推送）→ 详情页看到带时间戳转写全文
- [ ] 已选课自动进入总结触发；未选课停 SUMMARY_PENDING
- [ ] ASR 失败 → FAILED → 重试成功
- [ ] 删除处理中记录 → 链路终止、无产物入库
- [ ] 超 5h 音频被拒收；磁盘空间不足时给出明确提示
