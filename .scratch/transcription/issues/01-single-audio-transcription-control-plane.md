# 01 — 单音频转写与可恢复控制面

**What to build:** 用户可以从现有顶部“导入资料”入口提交一个 MP3、AAC、WAV 或 M4A 音频，由应用使用随包 ffmpeg 在本机规范化和顺序切片，在取得独立 External Processing Consent 后通过腾讯 ASR 生成真实 Transcript。Record 详情以 Record 为入口展示全部任务、等待、进度、失败和重试状态；断网、缺凭据、提交状态未知、进程重启和 Transcript 并发编辑都不会造成重复外部任务、部分正文或静默覆盖。

**Blocked by:** None — can start immediately

**Status:** completed

- [x] 现有顶部导入对话框在本票据支持一次选择一个 MP3、AAC、WAV 或 M4A；纯音频可不选课程，也可绑定 ACTIVE 课程，取消或关闭不创建业务数据，多来源选择留给 02。
- [x] 单音频 Record 标题由服务端取文件名 stem，capture_type=AUDIO_IMPORT，来源顺序固定为 sequence_no=0；请求不新增标题输入或自定义排序。
- [x] 后端在正式注册前验证来源非空、音频格式与内容匹配、音频未损坏、时长不超过 5 小时且数据盘可用空间至少为原件字节两倍；失败使用稳定错误码并清理本次临时输入。
- [x] 任一预校验失败都不创建 Record、Record File 或 Processing Job；数据库注册失败会补偿本次文件落位，不留下孤立正式文件。
- [x] 成功受理在一个事务中注册 CONTENT_PROCESSING Record、正式 AUDIO/UPLOADED Record File、AUDIO_TRANSCODE Job 和依赖它的 ASR Job；Capture Batch 不持久化为实体。
- [x] 导入音频原件通过受控相对路径保存在正式文件区；客户端文件名不能目录穿越、覆盖其他资产或泄漏完整本机路径。
- [x] 桌面包声明固定版本、可审计且 LGPL-compatible 的 ffmpeg `externalBin`，附来源、构建选项、许可证与校验值；运行时只使用应用资源中的二进制，不读取或回退到系统 PATH。
- [x] AUDIO_TRANSCODE 把输入规范化为 Ogg Opus 16kHz；标准化音频、ASR 片和临时正文只进入 cache，转码失败使用 `AUDIO_TRANSCODE_FAILED` 且不提交 ASR。
- [x] 标准化音频被切成目标时长不超过 5 分钟且每片严格小于 5MB 的有序本地片；V1 不使用 COS/S3、公网 URL、重叠切片、文本去重、并发提交或每片一个 Job。
- [x] V1 使用固定腾讯 ASR 客户端，不引入 Provider 接口、工厂或多供应商抽象；腾讯凭据只从当前 Provider 配置读取，不写入数据库、前端状态、Job 或日志。
- [x] 首次真实发送前独立展示“原始文件保留在本机，仅转码音频片段发送至腾讯云识别”；配置凭据不等于授权，授权时间写入本地 settings 配置。
- [x] 未同意、缺腾讯凭据或离线时，Record 保持 CONTENT_PROCESSING、ASR Job 保持 PENDING 并返回明确等待原因，attempts 不增加；条件补齐后同一 Job 自动继续。
- [x] ASR Job 的输入检查点固化有序片清单、校验信息、热词、模型、地域等非秘密配置；结果检查点保存每片 TaskId、状态、稳定错误码和恢复游标，不保存完整转写正文。
- [x] 一个音频只使用一个 ASR Job，并按片顺序提交和轮询；片成功后推进持久化恢复游标，进程重启不得重复提交已成功片。
- [x] 自动重试只覆盖确认安全的瞬时轮询或供应商临时故障，每轮最多 3 次且首次执行计入；鉴权、配额、输入错误不自动重试。
- [x] 提交超时且没有取得 TaskId 时使用 `ASR_SUBMIT_UNKNOWN`，立即停止自动重提并提供人工可理解的处理状态，避免创建重复腾讯任务。
- [x] 手动重试复用原 Record、原音频、原 ASR Job 和原检查点；成功片保持成功、有效 TaskId 继续轮询，只重置失败、过期或未提交片。
- [x] sidecar 重启时恢复遗留 RUNNING 转码/ASR Job 与下一恢复游标；等待同意、缺凭据和离线状态继续等待，不依赖前端内存。
- [x] 音频全部识别成功后，在一个事务中创建唯一 Transcript、将 ASR Job 置为 SUCCEEDED 并推进 Record；重复完成通知或重启不得创建第二份 Transcript。
- [x] Transcript 正文不包含文件名、标题或时间戳；纯音频 language=zh-CN。没有可识别语音时返回 `NO_SPEECH_DETECTED`，不得创建空 Transcript。
- [x] 成功后删除标准化音频片和临时正文，保留导入原件、Transcript 与最小技术元数据；处理中删除 Record 会取消本地 Job、清理相关 cache 并拒绝迟到结果写回。
- [x] 课程在音频处理期间归档时，已受理内容继续生成 Transcript，但不得自动创建新的 Summary Job；ACTIVE 课程可接续已完成的总结能力。
- [x] `GET /api/records/{record_id}/jobs` 返回该 Record 的稳定排序任务视图，包含类型、状态、进度、等待原因、稳定错误码、attempts 和是否允许手动重试；Record 总进度是其全部 Job progress 的简单平均。
- [x] Record 详情 URL 只保留 Record 标识与 tab，不再携带或依赖 job id；刷新和直达均从 Record、Record 级 Jobs 与 Transcript API 恢复。
- [x] Record 级 authenticated fetch stream 携带启动令牌且只发送数据失效通知；收到事件、连接恢复或窗口重新获得焦点后重新读取 REST，不通过事件传输完整 Job 或 Transcript。
- [x] 事件流断开时仅非终态 Record 每 2 秒条件轮询；重连或进入终态后停止轮询。V1 不实现事件持久化、重放或 Last-Event-ID。
- [x] Transcript 仅在内容成功且 Summary 未处理中允许显式保存；PATCH 携带 `expected_source_version`，陈旧版本返回 409 且不发生部分写入。
- [x] Transcript 保存成功时 source_version 原子递增，旧 Summary 标为 SUPERSEDED，Record 进入 SUMMARY_PENDING；不自动重新生成 Summary，Summary 写入前拒绝过期 transcript_source_version。
- [x] Transcript 编辑不删除旧知识点、习题、Todo、回答或 Learning Event；这些既有资产继续保留其历史事实。
- [x] 所有新增 API 受随机 localhost 启动令牌保护并进入 OpenAPI 生成链；桌面端不复制 Job、等待原因、错误码或 Transcript 版本类型。
- [x] 转写全文、音频内容、腾讯密钥、启动令牌和 Authorization 不进入日志；仅记录 Record、Job、片序号、耗时与稳定错误码等最小元数据。
- [x] 自动化主接缝启动真实 sidecar 进程，使用随机端口、启动令牌、正式迁移、临时数据目录、SQLite、文件系统、Worker 和随包 ffmpeg；只在腾讯网络传输边界使用可编程替身。
- [x] 真实进程测试覆盖原子受理、格式/损坏/时长、转码、严格 `<5MB` 切片、等待条件、顺序提交、有限重试、`ASR_SUBMIT_UNKNOWN`、手动重试、删除竞态、Transcript 原子发布和重启恢复；磁盘不足场景按用户明确决定不执行测试。
- [ ] 非日常 P0 使用随包 ffmpeg、真实中文音频和真实腾讯请求验证提交/轮询、片边界正文与重启恢复；运行时不读取系统 PATH，证据与 ASR 替身测试分开报告。
- [x] 桌面 Vitest/MSW 覆盖单音频提交、等待/失败/进度、独立同意、手动重试、SSE 失效与轮询降级、URL 无 job id、Transcript 409 冲突和成功保存；MSW 不冒充真实 sidecar 或腾讯证据。
- [ ] 真实 Tauri Network/渲染检查覆盖随机 localhost 请求、启动令牌、明暗主题、既定桌面尺寸、键盘焦点、长文件名/错误文案、进度和等待的非颜色语义以及无整体横向溢出。
- [x] 完成报告分开列出静态、迁移/SQLite、ASGI、真实 sidecar/socket、真实 ffmpeg、ASR 替身、真实腾讯 P0、桌面组件、真实 Network/渲染和重启持久化；明确多来源、录音 staging 与批次级孤儿清理由 02 承接。
- [x] 以固定起点完成 Standards 与本 Spec 双轴审查；两轴均通过后同步本 Issue 的 Status 与已验证 checklist，不把未执行的真实腾讯或渲染证据标为完成。

## 完成证据（2026-08-22）

- 静态与契约：Ruff、Pyright strict、ESLint、前端构建、OpenAPI check、`git diff --check` 通过。
- 迁移 / SQLite / ASGI：后端完整自动化 77/77 通过。
- 真实 sidecar / socket / ffmpeg / 重启持久化：真实进程自动化通过；腾讯只在 HTTP transport 边界使用官方响应形状替身。
- 桌面组件：Vitest/MSW 39/39、Cargo 4/4 通过。
- 双轴审查：固定起点 `3702706`，Standards PASS，Spec PASS。
- 人工验收：用户在真实 Tauri 中确认录音文件可正常导入，并通过真实腾讯 ASR 生成 Transcript；据此明确接受并关闭 01。
- 未单独验证：真实腾讯任务中途重启恢复与片边界正文、Tauri DevTools 启动令牌证据及完整主题/焦点/溢出专项检查；这些未验证边界不冒充为已完成 checklist。
- 磁盘不足场景按用户明确决定不测试。
- 02 承接：多来源、录音 staging 与批次级孤儿清理。
