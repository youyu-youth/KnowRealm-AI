# Capture Batch 音频导入与转写管线

Status: ready-for-agent

## Problem Statement

KnowRealm 已经具备 Record 工作区、单文件文档导入以及后台 Job/Worker 基础，但用户仍无法把音频或一次选择的多份资料可靠地转成一份 Transcript。现有导入入口一次只能接收一个文档，页面还把单个 Job 标识写入 URL；这不足以表达一个 Record 下包含多个有序来源、多个转码/解析/转写任务以及跨进程恢复的真实状态。

音频处理还包含一组不能靠普通上传覆盖的风险：桌面运行时不能依赖用户系统里的 ffmpeg；腾讯 ASR 对音频片大小有严格限制；提交超时可能已经在远端创建任务，盲目重试会重复计费和产生重复结果；应用重启、断网、缺少凭据或用户尚未同意外发时，任务必须可恢复且不能消耗重试次数。

多来源导入必须是一个封口的 Capture Batch。任何来源在注册前不合法，都不能留下半个 Record、孤立文件或 Job；注册后也不能追加或重排。各来源的中间结果只有全部成功后才能按原始顺序合并并原子发布为唯一 Transcript，不能让用户看到部分正文。

Transcript 发布后还需要安全的编辑与状态刷新合同。并发编辑不能静默覆盖，旧 Summary 不能继续伪装成基于最新正文，Record 详情也不能依赖某个 Job 的 URL 参数或脆弱的单连接事件流。删除或取消处理中的 Record 时，本地任务、缓存和迟到结果必须被一致地隔离。

## Solution

把现有顶部“导入资料”对话框升级为原生多选入口。一次提交形成一个有序且立即封口的 Capture Batch，可包含受支持的音频、文档或两者混合；后端先对整批执行格式、损坏、时长和磁盘空间预校验，全部通过后才在一个事务中注册 Record、Record File 与 Processing Job。Capture Batch 只是一条命令边界，不新增持久化批次实体。

每个音频来源依次经过 AUDIO_TRANSCODE 与 ASR。应用使用随桌面包分发、可审计且 LGPL-compatible 的 ffmpeg，把音频或录音 staging 规范化为 Ogg Opus 16kHz，再切成目标不超过 5 分钟且严格小于 5MB 的本地有序片。一个音频只使用一个 ASR Job，片清单、远端 TaskId、片状态和恢复游标保存在该 Job 的检查点中，并按顺序向腾讯提交和轮询。

第一次发送转码片段前，应用将“原始文件保留在本机，仅转码音频片段发送至腾讯云识别”作为独立的 External Processing Consent 告知用户。配置腾讯凭据不等于同意。未同意、缺少凭据或离线时，Record 继续处于 CONTENT_PROCESSING，ASR Job 保持 PENDING 并显示等待原因；条件满足后复用原 Job 自动继续，不增加 attempts。

文档复用现有解析 Job。所有来源成功后，系统按 `sequence_no` 使用恰好两个换行连接正文，并在一个事务中创建唯一 Transcript；正文不注入文件名、标题或时间戳。任何来源失败或音频没有可识别语音时，不发布部分 Transcript。纯音频 Transcript 标记为 `zh-CN`，包含文档的批次标记为 `und`。

Record 详情通过 Record 级 Job 聚合接口展示进度、等待、失败和重试状态；URL 只保留 Record 标识与当前 tab。受启动令牌保护的 fetch stream 只发送“数据已失效”通知，页面收到事件、连接恢复或窗口重新获得焦点后重新读取 REST；流断开时，仅对非终态 Record 每 2 秒轮询。

用户可在内容处理完成且 Summary 未处理中编辑 Transcript。保存请求携带 `expected_source_version`；版本不匹配返回 409，成功则递增版本、将旧 Summary 标记为 SUPERSEDED，并把 Record 推进到 SUMMARY_PENDING，但不自动重新生成。删除或取消 Record 会立即停止本地任务、清理可重建缓存并丢弃迟到结果；远端取消只做 best effort。

## User Stories

1. As an 学习者, I want to 从现有“导入资料”入口一次选择多份文件, so that 我不需要逐个创建彼此割裂的学习记录。
2. As an 学习者, I want to 使用系统原生文件选择器进行多选, so that 导入行为符合桌面平台习惯且支持键盘操作。
3. As an 学习者, I want to 按我选择文件的顺序处理来源, so that 合并 Transcript 能保留原始资料顺序。
4. As an 学习者, I want to 提交后批次顺序被封口, so that 后台恢复时不会因追加或重排得到不同正文。
5. As an 学习者, I want to 导入 MP3、AAC、WAV 或 M4A 音频, so that 常见课程录音无需预先手工转换。
6. As an 学习者, I want to 把音频和现有支持的 TXT、MD、PDF、DOCX 放在同一批次, so that 一次课程的多种资料可以形成一份 Transcript。
7. As an 学习者, I want to 导入单个来源时自动使用文件名 stem 作为标题, so that 我不用重复输入显而易见的标题。
8. As an 学习者, I want to 导入多个来源时看到“首文件 stem + 等 N 个文件”的标题, so that 列表能简洁表达这是一组资料。
9. As an 学习者, I want to 导入时不再填写标题, so that Capture Batch 保持最小且明确的提交步骤。
10. As an 学习者, I want to 纯音频或录音在未选择课程时也能受理, so that 我可以先捕获内容再由后续 Inbox 流程归类。
11. As an 学习者, I want to 含文档的批次必须绑定 ACTIVE 课程, so that 当前版本不会创建尚无归类出口的文档 Record。
12. As an 学习者, I want to 课程已归档时不能提交含文档批次, so that 新内容不会进入不可继续处理的课程。
13. As an 学习者, I want to 任一文件格式不支持时整批拒绝, so that 我不会得到缺少部分来源的 Record。
14. As an 学习者, I want to 任一音频损坏时整批拒绝, so that 后台不会在处理一半后才暴露可预知错误。
15. As an 学习者, I want to 录音会话超过 3 小时时获得明确错误, so that 产品上限不会被静默截断。
16. As an 学习者, I want to 单批音频总时长超过 5 小时时获得明确错误, so that 一次任务不会超出 V1 的可恢复处理边界。
17. As an 学习者, I want to 可用磁盘不足批次原件总字节两倍时在注册前停止, so that 转码和切片不会耗尽磁盘并留下半成品。
18. As an 学习者, I want to 预校验失败后不留下 Record、文件或 Job, so that 我可以修正问题后干净地重新提交。
19. As an 学习者, I want to 导入成功后原始音频继续作为正式文件保留, so that 可重建缓存被清理后仍保有原始资料。
20. As an 学习者, I want to 录音 staging 成功转码后只注册最终录音文件, so that WebM 分片不会长期占据正式数据目录。
21. As an 学习者, I want to 应用使用随包 ffmpeg 而不是系统 PATH, so that 换一台电脑仍能得到相同的转码行为。
22. As an 学习者, I want to 每个音频先完成转码再进入识别, so that ASR 始终收到统一、可验证的音频格式。
23. As an 学习者, I want to 大音频被切成符合腾讯限制的有序片, so that 不需要上传到公网对象存储也能完成识别。
24. As an 学习者, I want to 音频片按顺序提交, so that V1 的正文顺序可预测且恢复逻辑简单。
25. As an 学习者, I want to 首次发送前看到外部处理告知, so that 我知道哪些派生内容会离开本机以及发送给谁。
26. As an 学习者, I want to 配置腾讯凭据与同意外发是两个独立动作, so that 填写密钥不会被误解为授权发送内容。
27. As an 学习者, I want to 拒绝或尚未作出同意时资料仍被本地受理, so that 我不会因隐私选择丢失已导入内容。
28. As an 学习者, I want to 缺少腾讯凭据时看到明确等待原因, so that 我知道任务未失败而是缺少运行条件。
29. As an 学习者, I want to 离线时看到明确等待原因, so that 网络恢复前任务不会无意义地消耗重试次数。
30. As an 学习者, I want to 同意、凭据和网络补齐后任务自动继续, so that 我不需要重新创建 Record 或重新上传文件。
31. As an 学习者, I want to 临时供应商故障最多自动重试 3 次, so that 短暂错误可恢复且不会无限调用外部服务。
32. As an 学习者, I want to ASR 提交超时且没有 TaskId 时停止自动重提, so that 远端可能已受理的任务不会被重复创建或计费。
33. As an 学习者, I want to 鉴权、配额或输入错误不被自动重试, so that 确定性问题不会制造噪声和额外请求。
34. As an 学习者, I want to 手动重试复用原 ASR Job, so that 任务历史和恢复检查点保持连续。
35. As an 学习者, I want to 手动重试保留已成功片和仍有效的 TaskId, so that 已完成的外部处理不会被重复执行。
36. As an 学习者, I want to 应用重启后从最近检查点继续, so that 长音频无需从第一片重新识别。
37. As an 学习者, I want to 同一 Record 中某个 Job 失败后暂停其后续待处理 Job, so that 失败来源不会与无意义的后续工作交错。
38. As an 学习者, I want to 一个 Record 失败时其他 Record 仍继续处理, so that 单个坏文件不会阻塞整个工作区。
39. As an 学习者, I want to 看到 Record 下全部 Job 的简单平均进度, so that 多来源处理只有一个稳定、可解释的总体进度。
40. As an 学习者, I want to 在 Record 详情查看每个任务的状态和等待原因, so that 我能判断当前正在转码、解析、识别、等待还是失败。
41. As an 学习者, I want to 页面刷新后从 SQLite 恢复任务状态, so that 浏览器内存不会成为处理进度的事实源。
42. As an 学习者, I want to Record 详情地址不包含 Job 标识, so that 一个 Record 的多个任务不会破坏稳定链接。
43. As an 学习者, I want to 处理状态变化时页面及时刷新, so that 我不需要手动重载详情页。
44. As an 学习者, I want to 事件连接断开时非终态 Record 自动轮询, so that 短暂断连不会让进度永久停住。
45. As an 学习者, I want to 已完成或已失败的终态 Record 停止轮询, so that 桌面应用不会产生无意义的后台请求。
46. As an 学习者, I want to 所有来源成功后才看到 Transcript, so that 我不会误把半成品当作完整课程内容。
47. As an 学习者, I want to 合并正文严格遵循来源顺序并用两个换行分隔, so that 多来源文本边界稳定且没有额外装饰。
48. As an 学习者, I want to Transcript 不注入文件名、标题或时间戳, so that 正文保持适合后续总结的纯内容结构。
49. As an 学习者, I want to 音频没有可识别语音时看到明确错误且没有空 Transcript, so that 静音不会被误报为处理成功。
50. As an 学习者, I want to 纯音频 Transcript 标记为中文, so that 后续能力能使用明确语言信息。
51. As an 学习者, I want to 含文档或混合来源的 Transcript 使用未确定语言, so that 系统不会对多语言文档作错误推断。
52. As an 学习者, I want to 内容成功且 Summary 未处理中时编辑 Transcript, so that 我能修正识别或解析错误。
53. As an 学习者, I want to 并发修改时收到 409 冲突而不是覆盖新内容, so that 另一窗口的编辑不会丢失。
54. As an 学习者, I want to 保存 Transcript 后旧 Summary 明确过时, so that 旧摘要不会继续伪装成基于最新正文。
55. As an 学习者, I want to 修改 Transcript 后由我明确触发重新总结, so that 编辑不会自动产生新的外部 AI 调用。
56. As an 学习者, I want to 课程在内容处理期间归档后仍保留已受理 Transcript, so that 进行中的本地工作不会被无故丢弃。
57. As an 学习者, I want to 课程归档后不自动触发 Summary, so that 归档边界能阻止新的下游处理。
58. As an 学习者, I want to 删除处理中 Record 时立即停止本地处理并清理缓存, so that 已删除内容不会继续占用本机资源。
59. As an 学习者, I want to 删除后迟到的 ASR 结果被丢弃, so that 远端响应不能复活已删除 Record。
60. As an 学习者, I want to 远端取消失败不阻塞本地删除, so that 外部服务不可用时我仍能控制本机数据。
61. As an 学习者, I want to 应用启动时清理无归属临时文件, so that 崩溃不会永久留下 staging 或 cache 垃圾。
62. As an 学习者, I want to 成功后删除 ASR 片与临时文本, so that 只保留正式文件、Transcript 和必要技术元数据。
63. As an 使用辅助技术的学习者, I want to 等待、失败、进度和同意步骤具有文字与可访问语义, so that 状态不只依赖颜色或动画表达。
64. As an 开发者, I want to 捕获注册、文件登记和 Job 创建处于同一事务, so that 任一步骤失败都不会留下孤立业务对象。
65. As an 开发者, I want to 非秘密 ASR 配置与秘密凭据分开保存, so that Job 可恢复而密钥不会进入数据库快照。
66. As an 开发者, I want to 日志只包含 Record、Job、片序号、耗时和稳定错误码, so that 转写全文、音频、密钥和 Authorization 不会泄漏。
67. As an 维护者, I want to 真实腾讯 P0 与日常自动化测试分开报告, so that 使用替身的回归测试不会被误报为外部服务端到端成功。
68. As an 维护者, I want to 静态、进程/API、桌面组件、真实 Network、渲染和重启证据分别报告, so that 每项完成声明都能追溯到正确验证层。

## Implementation Decisions

- 本功能复用现有 Record、Record File、Transcript、Processing Job、Worker、随机 localhost sidecar、启动令牌、OpenAPI 类型链、TanStack Query 和 Record 详情宿主；不建立第二套任务系统、上传系统或页面外壳。
- Capture Batch 是一次封口的应用命令，不是持久化领域实体。服务在注册前保留临时输入，预校验全部通过后一次性创建业务数据；提交后不提供追加、删除单个来源或重排接口。
- `POST /api/capture-batches` 接收可空 `course_id` 和有序来源数组。来源顺序就是 `sequence_no=0..N-1` 的唯一来源；服务端不得按文件名、类型或完成时间重新排序。
- Capture Batch 成功注册返回 Record 标识及其当前业务状态。Job 状态统一从 Record 级聚合接口读取，响应和页面跳转不把单个 Job 设为业务入口。
- 保留现有 `POST /api/document-imports` 合同，不把已有单文档调用方强制迁移到 Capture Batch。
- 文件选择器使用平台原生多选能力和明确的 accept 提示，但后端仍是格式与内容可信边界；扩展名或前端 MIME 不能替代服务端探测。
- 支持的音频输入限定为 MP3、AAC、WAV、M4A，以及录音功能交付的已封口 staging；文档格式完全复用既有 TXT、MD、PDF、DOCX 合同。
- 整批预校验在正式注册前完成：来源非空、格式受支持、音频可探测且未损坏、单次录音不超过 3 小时、批次全部音频总时长不超过 5 小时、数据盘可用空间至少为批次原件总字节的两倍（2×）。
- 任一预校验失败都拒绝整批，删除本次临时输入且不创建 Record、Record File 或 Processing Job。错误使用稳定码 `UNSUPPORTED_AUDIO`、`CORRUPT_AUDIO`、`AUDIO_TOO_LONG`、`INSUFFICIENT_DISK`。
- audio-only 与 RECORDING Record 允许 `course_id` 为空；只要批次包含文档就要求非空且指向 ACTIVE Course。未选课文档和未选课混合来源继续由后续 Inbox 计划承接。
- 单来源 Record 的 capture_type 取 DOCUMENT_IMPORT、AUDIO_IMPORT 或 RECORDING；包含多种来源类型的 Record 使用 MULTI_SOURCE。混合类型只描述捕获来源，不新增 Batch 状态机。
- 标题由服务端确定。单来源使用文件名 stem；多来源使用“首文件 stem + 等 N 个文件”；请求不接受自定义标题，避免前后端产生两份标题规则。
- Record File 增加或使用可持久化顺序字段表达 `sequence_no`，并扩展文件类型/来源枚举以区分 DOCUMENT、AUDIO、UPLOADED 与 RECORDED。顺序约束在同一 Record 内唯一且非负。
- 导入音频原件是正式 Record File，保存在正式文件区。标准化音频、ASR 片和临时正文是可重建缓存，只进入 cache；本功能不新增分别配置 `files`、`cache` 或保留标准化 Ogg 的设置。
- 录音功能只负责捕获、staging 和 finalize 交接。转写功能负责合并已封口 WebM staging、执行转码、原子登记最终 AUDIO/RECORDED Record File，并仅在登记成功后删除 WebM staging。
- Tauri 通过 `externalBin` 随包分发固定版本、可审计且 LGPL-compatible 的 ffmpeg。运行时只解析应用资源中的二进制，不探测或回退到系统 PATH。
- 每个音频来源创建一个 AUDIO_TRANSCODE Job 和一个 ASR Job，并保持转码先于识别的依赖。每个文档来源复用既有 DOCUMENT_PARSE Job。
- 不创建 Capture Batch 父 Job、聚合 Job或每片一个 Job。Record 进度由其全部 Job 的 `progress` 简单平均得到；没有额外加权或阶段映射。
- 同一 Record 中任一 Job 失败后，其后续 PENDING Job 保持暂停；其他 Record 的可运行 Job 不受影响。Worker 继续复用现有声明、检查点和重启恢复机制。
- ffmpeg 输出固定为 Ogg Opus 16kHz。转码失败使用 `AUDIO_TRANSCODE_FAILED`，且不得进入 ASR 提交阶段。
- 标准化音频按原始顺序切成目标时长不超过 5 分钟且文件大小严格小于 5MB 的本地片。5MB 是严格上界，不按近似显示值判断。
- 一个音频的全部片由同一个 ASR Job 顺序提交和轮询。V1 不并发提交、不上传 COS/S3、不生成公网 URL，也不建立切片业务表。
- ASR Job 的 `input_json` 固化有序片清单、片校验信息、热词、模型、地域和其他非秘密配置，使重启后的意图稳定。腾讯凭据始终从当前 Provider 配置读取，不进入 Job、日志或数据库快照。
- ASR Job 的 `result_json` 保存每片远端 TaskId、提交/轮询状态、稳定错误码、恢复游标和完成元数据。成功后可删除正文缓存，只保留恢复与审计所需的技术元数据，不保存完整转写正文。
- 腾讯 ASR Provider 在 V1 固定，不新增 Provider 接口、工厂或多供应商抽象。供应商 CRUD 与通用连接测试由账户/档案计划负责；本功能只读取当前腾讯配置并呈现缺失等待态。
- External Processing Consent 独立于 Provider 凭据，授权时间写入本地 `config/settings.json`。首次真实发送前必须展示“原始文件保留在本机，仅转码音频片段发送至腾讯云识别”；未授权不得调用腾讯。
- 本功能提供最小的同意动作和读取合同，不扩建通用设置页。缺少腾讯配置时引导至既定供应商配置能力；在该能力尚未交付的开发/P0 环境中，只能通过受控测试配置提供凭据，不能加入隐藏生产后门。
- 未同意、缺腾讯凭据或离线属于可恢复等待，不属于失败。Record 保持 CONTENT_PROCESSING，ASR Job 保持 PENDING，写入稳定等待原因，`attempts` 不增加；Worker 在条件满足后复用原 Job 继续。
- 自动重试只覆盖确认安全的瞬时轮询失败和供应商临时故障，每轮最多 3 次。等待用户条件的时间不算自动重试。
- 提交请求超时且没有取得 TaskId 时使用 `ASR_SUBMIT_UNKNOWN` 并停止自动重提，因为无法证明远端未创建任务。鉴权、配额和输入错误同样不自动重试。
- 处理阶段稳定错误码包括 `AUDIO_TRANSCODE_FAILED`、`ASR_AUTH_FAILED`、`ASR_QUOTA_EXHAUSTED`、`ASR_TEMPORARY_UNAVAILABLE`、`ASR_SUBMIT_UNKNOWN`、`ASR_RECOGNITION_FAILED`、`ASR_TASK_EXPIRED`、`NO_SPEECH_DETECTED`。
- 手动重试作用于原 ASR Job 和原检查点。成功片保持成功，仍有效 TaskId 继续轮询，只重置失败、已过期或从未提交的片；不得克隆 Job 或重新提交全部片。
- 每个来源的解析/识别正文先作为 Record 归属的临时结果保存在 cache，不提前写入用户可见 Transcript。拥有 Job 检查点的临时文件不能被启动清理误判为孤儿。
- 当且仅当全部来源 Job 成功时，Record 级最终化逻辑按 `sequence_no` 读取来源正文，以恰好两个换行连接，并在一个事务中创建唯一 Transcript、推进 Record。最终化必须可幂等重入，重启或重复通知不能创建第二份 Transcript。
- 合并正文不添加文件名、标题、来源标签、Markdown 标题或时间戳。任一来源失败、缺失正文或音频没有可识别语音时，不创建部分 Transcript。
- 纯音频/录音 Transcript 的 `language` 为 `zh-CN`；包含任一文档的文档或混合批次为 `und`。V1 不持久化腾讯句子时间范围，也不创建 Segment。
- 内容完成后 Record 进入 SUMMARY_PENDING。只有 Course 在最终化时仍为 ACTIVE，已完成的总结功能才可自动接续；处理期间归档的 Course 仍保留 Transcript，但不自动创建 Summary Job。
- `GET /api/records/{record_id}/jobs` 返回该 Record 下按来源顺序和执行阶段稳定排序的 Job 视图，至少包含类型、状态、进度、等待原因、稳定错误码、attempts 以及是否允许手动重试。它是 UI 状态的权威来源。
- Record 详情 URL 只保留 `recordId` 与 tab。移除 `jobId` 搜索参数及其数据依赖；刷新、直达和恢复一律先读 Record，再读 Record 级 Jobs。
- `GET /api/records/{record_id}/events` 是带启动令牌的 authenticated fetch stream；需要请求体的 AI/Chat 命令流继续使用 POST。两类流共用 `EventSourceResponse`，不能使用无法附加自定义头的原生 EventSource。
- Record 事件固定为 `invalidate`，只携带 `record_id`，不承载完整 Record、Job、Transcript 或进度快照；客户端收到事件、重连成功或窗口重新获得焦点后，通过 REST 重新读取权威状态。
- V1 不提供事件序号、Last-Event-ID 或服务端重放。Record 仅在 `CONTENT_PROCESSING` 或 `SUMMARY_PROCESSING` 时保持连接；事件流断开后立即刷新一次 REST，并每 2 秒条件轮询和尝试重连，恢复连接或离开处理态后停止。
- Transcript 编辑使用现有 Record Transcript 接口的 PATCH 语义，请求包含正文和 `expected_source_version`。只有内容已成功且 Summary 不处于处理中时允许保存。
- Transcript 更新在同一事务中比较当前 `source_version`。不匹配返回 409 且不写入；成功时 `source_version + 1`，把现有旧 Summary 标为 SUPERSEDED，并将 Record 设为 SUMMARY_PENDING。
- Transcript 编辑成功不自动触发重新总结。用户必须执行明确的重新生成动作；Summary Worker 在写入前还必须核对绑定的 `transcript_source_version`，过期结果不得覆盖新版本。
- 编辑 Transcript 不删除旧知识点、习题、Todo、回答或 Learning Event；这些下游资产保留原版本事实，后续版本化策略不在本功能内扩展。
- 删除或取消处理中的 Record 时，先在本地持久化取消边界，使 Worker 停止领取/继续对应任务；相关本地 Job 进入 CANCELLED，可重建 cache 立即清理。
- 腾讯远端取消只做 best effort，失败不回滚本地删除。任何在取消边界之后到达的远端结果都必须在写入前复核 Record/Job 状态并丢弃。
- sidecar 启动时清理没有 Record、Record File 或有效 Job 所有权的 staging/cache 临时文件。清理只作用于可重建产物，不删除正式导入原件或最终录音文件。
- Job 成功后删除 ASR 片和临时正文；导入音频原件或录音最终 Ogg、Transcript 以及最小技术检查点继续保留。
- 转写全文、音频内容、腾讯密钥、启动令牌和 Authorization 禁止进入日志。允许记录 `record_id`、`job_id`、片序号、耗时、供应商任务标识的安全摘要和稳定错误码。
- 所有新 API 继续受随机 localhost 启动令牌保护，并由 FastAPI OpenAPI 生成桌面类型；前端不手写第二份 Job、错误码、等待原因或 Transcript 版本联合类型。
- 用户可见的格式错误、等待原因、失败码、同意提示、重试与冲突文案进入中文 i18n；等待、失败和进度必须有文字语义，不能只依赖颜色。
- 桌面端复用现有查询缓存和失效机制，不把 Record/Job/SSE 快照复制到持久化前端状态。事件只是触发失效，REST/SQLite 始终是事实源。

## Testing Decisions

- 测试只断言可观察合同：HTTP 状态与响应、SQLite/文件系统结果、进程重启后的状态、外部调用次数与参数边界、页面可访问行为。不得绑定 Worker 私有函数、组件内部 state、CSS 类名、具体 SQLAlchemy 调用或 JSON 序列化实现。
- 自动化主接缝复用现有真实 sidecar 进程测试：在随机 `127.0.0.1` 端口启动实际进程，使用真实启动令牌、正式迁移、临时数据目录、SQLite、文件系统、Worker 和随包 ffmpeg；只在腾讯 ASR 网络传输边界使用可编程替身。
- 主接缝覆盖 Capture Batch 的整批预校验和原子注册：合法单音频、音频+文档、格式不支持、损坏音频、录音超过 3 小时、批次音频超过 5 小时，以及已执行失败场景均无 Record/File/Job 残留。磁盘不足测试按用户明确决定不执行，产品侧空间校验继续保留。
- 主接缝使用真实 ffmpeg 探测、转码和切片，验证运行时不读取系统 PATH、输出为 Ogg Opus 16kHz、片顺序稳定、目标时长不超过 5 分钟且每片严格小于 5MB。
- ASR 传输替身按真实提交/查询响应形状工作，能够返回 TaskId、处理中、成功、静音、鉴权、配额、临时故障、任务过期和“提交超时但无 TaskId”。测试关注调用次数、顺序和恢复结果，不测试替身内部实现。
- 检查点测试覆盖顺序提交、多片成功、成功片不重提、有效 TaskId 继续轮询、失败/过期/未提交片的手动重试、自动重试最多 3 次，以及 `ASR_SUBMIT_UNKNOWN` 不自动重提。
- 等待态测试覆盖未同意、缺腾讯配置与离线。三者均保持 Record=CONTENT_PROCESSING、Job=PENDING、写入正确等待原因且 attempts 不增加；条件补齐后同一 Job 自动继续。
- External Processing Consent 测试验证凭据存在仍不能绕过同意，授权时间独立持久化，发送内容只包含转码片而非原始音频或 WebM staging。
- 多 Record 调度测试验证一个 Record 失败会暂停自身后续 PENDING Job，但不会阻塞其他 Record；Record 总进度等于其全部 Job progress 的简单平均。
- Transcript 最终化测试覆盖单音频、单文档和音频+文档，断言严格按 `sequence_no` 用两个换行合并、不插入文件名/标题/时间戳、纯音频语言为 `zh-CN`、包含文档时为 `und`。
- 原子发布测试让任一来源失败、正文缺失或返回无语音，确认不存在用户可见 Transcript；重复完成通知和进程重启不得创建重复 Transcript。
- 重启恢复测试在同一临时数据目录重启真实 sidecar，覆盖转码完成后、已有 TaskId 轮询中、部分片成功、等待同意以及最终化前等检查点；成功片不得重复提交。
- 文件生命周期测试验证导入音频原件保留、录音最终 Ogg 原子注册后 WebM staging 删除、成功后切片/临时正文清理、失败检查点仍可恢复、启动时只清理无归属临时文件。
- 删除/取消测试覆盖本地 Job=CANCELLED、cache 立即清理、远端取消失败不阻塞、迟到成功结果不写入，以及正式原件是否删除继续遵循既有 Record 删除合同。
- Course 生命周期测试覆盖只要含文档就必须绑定 ACTIVE Course、audio-only 可为空、处理期间归档仍生成 Transcript 但不创建 Summary Job。
- Transcript 编辑集成测试覆盖允许编辑的状态、Summary 处理中拒绝、正确 `expected_source_version` 成功、陈旧版本返回 409、版本递增、旧 Summary=SUPERSEDED、Record=SUMMARY_PENDING 且不自动生成新 Summary。
- Summary 写入竞争测试验证旧 `transcript_source_version` 的迟到结果不能写成当前 Summary；旧知识点、习题、Todo、回答与 Learning Event 不因编辑被删除。
- Job 聚合 API 测试覆盖稳定排序、进度、等待原因、错误码、attempts、重试能力以及不存在/已删除 Record；缺失或错误启动令牌继续返回 403。
- 事件流进程测试通过真实 socket 和鉴权头连接，验证只发送失效通知、不传输 Transcript/完整 Job、无事件重放，并在 Record 删除或进程退出时正确结束。
- 前端行为接缝复用现有 Vitest、MSW、路由测试与可访问角色查询，覆盖原生多选提交、标题展示、整批错误、等待/失败/进度、手动重试、独立同意、Transcript 编辑冲突和删除状态。
- 前端测试覆盖 URL 不再携带 `jobId`，页面通过 Record 级 Jobs 恢复；事件到达、连接重建和窗口恢复触发 REST 失效重取，断线时仅非终态每 2 秒轮询，终态或重连后停止。
- MSW 只证明桌面组件行为，不作为 ffmpeg、SQLite、真实 socket、启动令牌、腾讯请求或 Tauri Network 的证据。
- 非日常 P0 使用随包 ffmpeg、真实中文音频和真实腾讯账号，验证真实提交/轮询、严格 `<5MB` 切片、片边界正文以及进程重启恢复。该验收单独记录时间、素材、腾讯任务结果和费用，不把网络替身结果替代为 P0。
- 真实 Tauri 验收使用已启动桌面应用检查导入对话框、Record 详情、同意、等待、进度、失败、重试和 Transcript 编辑；Network 证据必须命中随机 localhost 端口并携带启动令牌。
- 渲染与可访问性检查覆盖既定桌面视口、亮色/暗色、键盘焦点、原生文件选择入口、Dialog、进度文字、错误与等待语义、长文件名/长错误信息溢出以及无整体横向滚动。
- 静态门禁覆盖后端格式、Lint、严格类型、迁移与测试，桌面 TypeScript、Vitest、Lint、格式、构建，Rust 测试，以及 OpenAPI 生成物无漂移。
- 完成报告分别列出源码/静态、ASGI/API/SQLite、真实 sidecar socket、真实 ffmpeg、ASR 替身、真实腾讯 P0、桌面组件、真实 Tauri Network/渲染和重启持久化。任何低层证据不能升级表述为更高层通过。
- 实现完成后从固定起点执行 Standards 与本 Spec 双轴审查；只有两个维度均通过，且 P0/手工证据的未验证项被如实标明，才允许关闭后续实现票。

## Out of Scope

- V1 Segment、腾讯句子级时间戳、音频时间轴和音频播放器。
- 英文 ASR、自动语言检测、静音检测增强、重叠切片、片边界文本去重或说话人分离。
- COS、S3、其他对象存储、公网回调 URL或上传原始音频到云端。
- 持久化 Capture Batch、批次管理页面、父/聚合 Job、ASR 切片表和并发提交片。
- 多账户、腾讯之外的 ASR Provider、Provider 抽象层、通用供应商 CRUD 和健康检查面板。
- 新导入页面、重新设计工作台外壳或增加第二套 Record 详情页。
- 录音捕获 UI、麦克风生命周期、录音分片生成与 finalize 之前的恢复；这些由录音计划负责。
- 未选课文档、未选课混合来源、Inbox 归类与批量移动。
- Summary/HITL 的生成实现、知识点、习题、复习资料、Todo、Ask AI 和 Learning Event 新逻辑；这里只维护 Transcript 版本边界。
- Transcript 富文本、多人协作编辑、自动合并冲突、编辑历史浏览或恢复旧版本。
- 取消腾讯远端任务的强一致保证；远端取消只做 best effort。
- 通用事件总线、事件持久化、SSE replay、Last-Event-ID 和跨设备实时同步。
- 自定义标题、提交后追加/移除/重排来源、单来源局部成功发布或从失败批次拆分新 Record。
- `.msi` 首次安装、通用 sidecar 打包验收、自动更新或 CI 发布；但本功能必须提供可供最终发行打包的 ffmpeg `externalBin` 配置与许可材料。

## Further Notes

- 本规格以已完成的 Record 工作区、单文件文档导入和 AI 总结合同为前提。04 的构建依赖只要求 Record 工作区与文档导入基础；完整 Summary/HITL 出口在已完成总结功能存在时集成。
- 供应商管理属于账户/档案计划，服务健康面板属于降级计划。本功能不提前复制这两块 UI，只实现转写必须的当前配置读取、等待原因、独立同意和自动恢复。
- `config/providers.json` 保存腾讯凭据，`config/settings.json` 保存 External Processing Consent；两者都是数据目录内的用户配置事实源。密钥当前为用户可见明文是既有产品决策，本功能不能把它复制进数据库、前端存储或日志。
- 随包 ffmpeg 的版本、来源、构建选项、许可证文本和校验值必须可审计。使用 LGPL-compatible 构建是发行约束，不允许为了方便静态链接进不兼容组件。
- V1 选择顺序切片、无重叠、无去重，是为了保持最小可恢复模型。只有真实 P0 证明片边界存在不可接受丢字后，才另开决策评估重叠或去重。
- `ASR_SUBMIT_UNKNOWN` 是刻意的人工确认边界，不是普通瞬时故障。没有可靠 TaskId 时，宁可停止自动重提，也不能通过猜测制造重复腾讯任务。
- SSE 不是业务事实源。事件只缩短 UI 感知延迟；SQLite、Record API、Job 聚合 API 和 Transcript API 才决定页面状态。
- 本规格不引入新的通用抽象。实现中如果一个固定腾讯客户端、一个 ffmpeg 调用器和现有 Worker 扩展即可完成，不得为假设中的第二供应商或未来并发模式创建工厂、插件系统或编排框架。
