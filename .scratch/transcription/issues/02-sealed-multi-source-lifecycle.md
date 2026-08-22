# 02 — 封口多来源与资产生命周期出口

**What to build:** 用户可以从同一个原生多选入口提交有序的音频、文档或混合资料，也可以接收录音功能交付的已封口 staging；系统把整批作为一次不可追加、不可重排的 Capture Batch 原子受理，每个来源独立处理，全部成功后按选择顺序发布唯一 Transcript。删除、取消、课程归档和进程崩溃都遵守同一资产生命周期，不会遗留可写回的任务、半成品正文或无归属缓存。

**Blocked by:** 01 — 单音频转写与可恢复控制面

**Status:** ready-for-agent

- [ ] 现有顶部导入对话框升级为平台原生多选，接受 MP3、AAC、WAV、M4A、TXT、MD、PDF、DOCX；选择顺序作为请求中唯一的来源顺序，取消或关闭不产生业务数据。
- [ ] `POST /api/capture-batches` 一次接收可空 course_id 和有序来源数组，提交即封口；不持久化 Capture Batch 实体，也不提供提交后追加、移除单个来源或重排接口。
- [ ] 单来源标题取文件名 stem；多来源标题为“首文件 stem + 等 N 个文件”。单一来源沿用 DOCUMENT_IMPORT、AUDIO_IMPORT 或 RECORDING，混合来源使用 MULTI_SOURCE。
- [ ] audio-only 与录音允许 course_id 为空；批次只要含文档就必须绑定 ACTIVE Course。未选课文档、未选课混合来源和 Inbox 归类不在本票据内实现。
- [ ] 整批预校验在正式注册前完成：来源非空、所有格式受支持、音频未损坏、单次录音不超过 3 小时、批次全部音频总时长不超过 5 小时、数据盘可用空间至少为批次全部原件总字节两倍。
- [ ] 任一来源预校验失败都拒绝整批、清理本次临时输入且不创建任何 Record、Record File 或 Processing Job；失败使用规格定义的稳定预注册错误码。
- [ ] 全批通过后在一个事务中创建一个 Record、按 sequence_no=0..N-1 登记全部 Record File，并为每个文档创建 DOCUMENT_PARSE Job、为每个音频创建 AUDIO_TRANSCODE→ASR Job；顺序在同一 Record 内唯一且非负。
- [ ] 每个音频继续复用 01 的随包 ffmpeg、顺序切片、腾讯 ASR、External Processing Consent、等待、检查点和重试合同；每个文档完全复用既有文档解析合同，不复制解析器或任务系统。
- [ ] 03 交付的已封口录音 staging 由本票据合并并转为 Ogg Opus 16kHz；只有最终 AUDIO/RECORDED Record File 原子登记成功后才删除 WebM staging。
- [ ] 导入音频和文档原件作为正式文件保留；录音只保留最终 Ogg。标准化音频、ASR 片和各来源临时正文继续作为可重建 cache。
- [ ] 不创建父/聚合 Job、每片 Job 或切片表；Record 进度由全部 Job progress 简单平均，Job 聚合 API 按来源顺序和执行阶段稳定展示。
- [ ] 同一 Record 中任一 Job 失败后暂停该 Record 的后续 PENDING Job；其他 Record 的可运行 Job 继续处理，不因一个批次失败而阻塞整个 Worker。
- [ ] 每个来源的解析/识别正文先保存在 Record 归属的临时 cache，不提前写用户可见 Transcript；拥有有效 Record File/Job 检查点的临时文件不能被误判为孤儿。
- [ ] 只有全部来源成功时，最终化逻辑才按 sequence_no 使用恰好两个换行连接正文并原子创建唯一 Transcript；不注入文件名、标题、来源标签、Markdown 标题或时间戳。
- [ ] 任一来源失败、正文缺失或音频无语音时不发布部分 Transcript；重复完成通知、Worker 重试和进程重启不得创建第二份 Transcript 或改变合并顺序。
- [ ] 纯音频/录音批次 Transcript language=zh-CN；包含任一文档的文档或混合批次 language=und。V1 不创建 Segment 或持久化腾讯句子时间范围。
- [ ] 课程在内容处理期间归档时，已受理的全部来源继续完成并保留 Transcript，但不得自动创建 Summary Job；最终化时仍为 ACTIVE 才可接续已完成的总结能力。
- [ ] 删除 Record 或取消处理中批次时，在本地事务中把全部非终态 Job 置为 CANCELLED 并阻止后续领取，立即清理该 Record 的可重建 cache；既有正式文件删除继续遵守 Record 资产删除合同。
- [ ] Worker 在转码、解析、远端轮询以及写入片结果、Transcript、Job 或 Record 状态前复核 Record 与 Job 仍可写；删除/取消边界后的迟到结果全部丢弃。
- [ ] 腾讯远端取消只做 best effort；取消失败不回滚本地删除、不恢复 Job，也不允许迟到远端结果重新创建业务产物。
- [ ] sidecar 启动时只清理无法由 Record、Record File 或有效 Job 证明所有权的 staging/cache 临时文件；不得按文件名、年龄或内容哈希猜测并删除活跃资产。
- [ ] 成功最终化后删除全部 ASR 片与来源临时正文，只保留正式文件、Transcript 和最小技术检查点；清理失败可安全重试且不会删除其他 Record 的同名或相同内容文件。
- [ ] 自动化主接缝使用真实 sidecar、SQLite、临时文件系统、Worker 与随包 ffmpeg，覆盖单文档、单音频、多个音频和音频+文档的整批受理、Job 图、进度、顺序合并与失败无部分发布。
- [ ] 原子性与生命周期测试覆盖第一个/中间/最后一个来源预校验失败、数据库提交失败、同 Record Job 失败暂停、其他 Record 继续、处理中删除、迟到结果、远端取消失败、崩溃重启和孤儿清理。
- [ ] 真实录音 staging 样本验证 WebM 合并、最终 Ogg 原子登记和 staging 删除；该证据只验证 03 finalize 之后的交接，不冒充真实麦克风捕获或录音 UI 完成。
- [ ] 前端 Vitest/MSW 覆盖原生多选、选择顺序、课程约束、整批错误、MULTI_SOURCE 标识、聚合进度、多 Job 等待/失败和删除取消；MSW 不冒充 SQLite、文件系统或真实桌面证据。
- [ ] 真实 Tauri Network/渲染检查覆盖多选音频+文档受理、Record 详情 Job 顺序、合并 Transcript、明暗主题、既定桌面尺寸、键盘焦点、长文件列表/错误文本和无整体横向溢出。
- [ ] 静态门禁覆盖后端格式、Lint、严格类型、迁移与测试，桌面 TypeScript、Vitest、Lint、格式、构建，Rust 测试，以及 OpenAPI 生成物无漂移。
- [ ] 完成报告分别列出静态、迁移/SQLite、ASGI、真实 sidecar/socket、真实 ffmpeg、ASR 替身、真实腾讯、录音 staging、桌面组件、真实 Network/渲染和重启持久化；明确麦克风捕获、Inbox、Segment/时间轴、Provider 管理和 MSI 不在本票据范围。
- [ ] 以固定起点完成 Standards 与本 Spec 双轴审查；两轴均通过后同步本 Issue、父规格和对应功能计划的状态/checklist，只勾选实际取得证据的验收项。
