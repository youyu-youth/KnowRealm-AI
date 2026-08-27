# 轻捕获与收件箱

Status: ready-for-agent

## Problem Statement

KnowRealm 已经能够通过录音、音频和文档形成 Record、Transcript 与后续学习资产，但顶部捕获栏中的速记仍是禁用占位，左栏 Inbox 也没有真实路由。用户想到一句话、拿到一段较长文本，或者暂时不知道素材属于哪门课程时，仍然无法先把内容可靠地保存到本地，再在合适的时候整理。

现有导入链路还把“是否选择课程”与“是否允许处理内容”绑在一起：统一 Capture Batch 已支持纯文档、多文档、纯音频和音频与文档混合来源，但只要批次包含文档就会强制要求 ACTIVE 课程。这使用户无法把尚未归类的文档留在 Inbox，也与已经允许未选课录音、音频的 Record 模型不一致。数据库和领域模型实际上已经允许 `course_id` 为空，当前限制来自导入服务和 UI，而不是数据结构。

“先捕获后整理”还存在 AI 费用与状态语义风险。Inbox 是 `course_id` 为空的 Record 集合，不是新的业务状态；速记和未选课粘贴使用 NOTE，而文档和录音必须继续表达 CONTENT_PROCESSING、SUMMARY_PENDING 或 FAILED 等真实生命周期。如果简单地把所有 Inbox 内容改成 NOTE，会抹掉解析、转写和失败事实；如果归类时直接复用当前内容完成器的自动总结行为，又可能在用户只想整理归属时调用 LLM。

最后，真正的全局速记依赖桌面应用在关窗后继续驻留。当前工程虽然已经安装全局快捷键与自启动相关依赖，但尚未注册固定快捷键、系统托盘或关闭窗口拦截。只做 React 弹窗无法满足“任意界面唤起”，而托盘退出若不考虑活动录音和未保存文本，又可能造成数据丢失。

## Solution

交付五级捕获中的轻文本端和 Inbox Wave A 闭环。顶部捕获栏增加明确分开的“速记”和“粘贴文本”入口，两者复用同一个文本捕获组件但写入不同 Capture Type。速记固定保存为无课程 QUICK_NOTE；粘贴使用 PASTE，并允许用户显式选择 ACTIVE 课程或保持“暂不归类”。文本在一次本地事务中创建 Record 与 Transcript，不伪造来源文件，也不因为 Provider、网络或外部处理同意不可用而丢失。

Inbox 成为真实的 `/inbox` 页面，展示所有未软删且 `course_id` 为空的 Record，并保留各来源的真实业务状态。用户可以删除内容；对已经具备 Transcript 的 NOTE 或 SUMMARY_PENDING Record，可以纯归类到 ACTIVE 课程而不触发 AI，也可以通过“升级”在一次操作中选择课程、完成归类并进入现有 Summary/HITL 管线。纯归类后的 Record 在详情 Summary 页仍可后续升级，避免离开 Inbox 后形成死路。

统一导入入口中的所有来源组合都允许不选择课程。文档继续立即执行本地解析，音频继续遵守既有 ASR 同意、凭据和恢复合同；全部来源完成后发布 Transcript，未选课 Record 停在 SUMMARY_PENDING，不创建 Summary Job。旧单文件文档导入接口同步接受可空课程，避免两个公开入口出现不同语义。

Tauri 注册固定 `Ctrl+Alt+N` 全局快捷键，并提供最小系统托盘“显示/退出”。关闭主窗口只隐藏应用；快捷键或托盘显示会恢复、聚焦主窗口并打开唯一速记框。快捷键冲突不会阻止应用启动。托盘退出在存在活动录音或未保存文本时先显示主窗口并要求确认，只有安全状态或用户明确确认后才停止 sidecar 并退出。

## User Stories

1. As an 学习者, I want to 从任意界面快速打开速记框, so that 我不会因为寻找课程或页面而丢失刚产生的想法。
2. As an 学习者, I want to 使用固定的 Ctrl+Alt+N 唤起速记, so that 我可以形成稳定的肌肉记忆。
3. As an 学习者, I want to 关掉主窗口后仍能使用全局速记, so that 应用可以作为长期驻留的学习工具。
4. As an 学习者, I want to 从顶部捕获栏点击速记, so that 快捷键不可用时仍有完整入口。
5. As an 学习者, I want to 从顶部捕获栏点击粘贴文本, so that 较长纯文本不会与速记入口混淆。
6. As an 学习者, I want to 速记和粘贴使用明确的不同类型, so that 系统不需要按字数或粘贴事件猜测我的意图。
7. As an 学习者, I want to 速记不要求选择课程, so that 捕获动作保持足够轻。
8. As an 学习者, I want to 粘贴文本时可以暂不选择课程, so that 我可以先保存再整理。
9. As an 学习者, I want to 粘贴文本时可以明确选择 ACTIVE 课程, so that 已知归属的内容能直接进入该课程的总结流程。
10. As an 学习者, I want to 课程选择器默认“暂不归类”, so that 系统不会因为当前页面上下文而静默触发 AI。
11. As an 学习者, I want to 从课程页面打开粘贴或文档导入时仍不自动预选课程, so that AI 资格始终来自我的明确选择。
12. As an 学习者, I want to 空白文本不能保存, so that Inbox 不会积累没有内容的 Record。
13. As an 学习者, I want to 过大的纯文本被提示改用 TXT 或 MD 导入, so that 应用不会在 JSON 请求和文本框中处理无界输入。
14. As an 学习者, I want to 文本捕获保留我的正文, so that 换行和段落不会因为保存而丢失。
15. As an 学习者, I want to 标题自动取第一条非空行, so that 快速捕获不需要额外填写标题。
16. As an 学习者, I want to 很长的首行得到稳定的短标题, so that Inbox 与 Record 列表保持可读。
17. As an 学习者, I want to 文本捕获成功后继续留在原工作上下文, so that 速记不会打断当前阅读或学习。
18. As an 学习者, I want to 保存成功后得到明确反馈, so that 我知道内容已经真实写入本地。
19. As an 学习者, I want to 重复点击保存不会创建多条 Record, so that 网络或界面延迟不会制造明显重复内容。
20. As an 本地优先用户, I want to Provider 缺失时仍能保存速记和粘贴, so that 本地捕获不依赖外部服务。
21. As an 本地优先用户, I want to 未同意外部处理时仍能保存和归类文本, so that 隐私选择不会阻断本地数据。
22. As an 离线用户, I want to 无外网时仍能完成速记、粘贴和 Inbox 整理, so that 捕获能力不依赖网络。
23. As an 学习者, I want to 从左栏进入真实 Inbox, so that 所有未归类 Record 都有统一入口。
24. As an 学习者, I want to Inbox 只包含 course_id 为空的 Record, so that 它准确表达未归属集合而不是另一套状态机。
25. As an 学习者, I want to Inbox 按创建时间倒序显示, so that 最新捕获的内容最容易找到。
26. As an 学习者, I want to Inbox 使用 Record 的真实标题、来源、状态和时间, so that 页面不会伪造第二套展示模型。
27. As an 学习者, I want to 速记和未选课粘贴显示 NOTE, so that 我知道它们只是纯存储文本。
28. As an 学习者, I want to 未选课文档显示 CONTENT_PROCESSING 或 SUMMARY_PENDING, so that 本地解析进度不会被伪装成 NOTE。
29. As an 学习者, I want to 未选课录音显示真实转写状态, so that ASR 等待、处理和失败仍可理解。
30. As an 学习者, I want to 失败的未归类来源显示 FAILED 与真实恢复入口, so that 失败不会从 Inbox 消失。
31. As an 学习者, I want to 软删除 Record 不再出现在 Inbox, so that 删除与现有 Record 语义一致。
32. As an 学习者, I want to Inbox 没有内容时看到真实空态, so that 页面不会用示例数据伪装成功。
33. As an 学习者, I want to 处理中记录自动刷新状态并在终态停止轮询, so that 页面既及时又不持续浪费资源。
34. As an 学习者, I want to 点击 Inbox 项进入 Transcript, so that 我优先看到刚捕获或解析的原始内容。
35. As an 学习者, I want to 无课程 Record 的详情返回 Inbox, so that 返回操作不会错误跳到知识空间首页。
36. As an 学习者, I want to 有课程 Record 的详情继续返回对应课程, so that 既有导航语义不被破坏。
37. As an 学习者, I want to 无课程 Summary 显示“请先归类并升级”, so that 我不会把缺少课程误解成课程已归档。
38. As an 学习者, I want to 在 Inbox 为可处理 Record 选择 ACTIVE 课程并归类, so that 它能进入正确的知识空间。
39. As an 学习者, I want to 纯归类不调用 LLM, so that 整理动作不会产生未授权费用。
40. As an 学习者, I want to 纯归类后继续停留在 Inbox 页面, so that 我可以连续整理其他内容。
41. As an 学习者, I want to 归类成功的行立即从 Inbox 消失, so that 页面与 course_id 的最新事实一致。
42. As an 学习者, I want to 看到 Record 被归到哪门课程, so that 行移除后仍有明确结果。
43. As an 学习者, I want to 对同一课程重复归类得到成功结果, so that 响应丢失后的安全重试不会变成错误。
44. As an 学习者, I want to 已归到另一课程的 Record 拒绝再次归类, so that 本功能不会暗中提供重新归类能力。
45. As an 学习者, I want to 处理中或失败的 Record 暂不能归类, so that 内容完成器不会把纯归类误当成 AI 请求。
46. As an 学习者, I want to 对 NOTE 或 SUMMARY_PENDING Record 执行升级, so that 已准备好的内容可以进入总结管线。
47. As an 学习者, I want to 在 Inbox 一次完成选择课程和升级, so that Record 不会先消失再让我寻找第二个操作入口。
48. As an 学习者, I want to 升级成功后进入 Summary 页, so that 我可以继续配置 Provider、授权、生成和 HITL。
49. As an 学习者, I want to 纯归类的 NOTE 在 Record 详情仍可升级, so that 稍后处理不会形成死路。
50. As an 学习者, I want to 已归类 SUMMARY_PENDING Record 从详情继续生成总结, so that 归类和 AI 可以分时完成。
51. As an 学习者, I want to Provider 未配置时升级仍保存归类和状态, so that 外部配置问题不会回滚本地整理结果。
52. As an 学习者, I want to 未同意发送 Transcript 时升级不创建 Summary Job, so that 同意边界继续有效。
53. As an 学习者, I want to 入队临时失败时 Record 仍停在可继续状态, so that 我不用重新捕获或重新归类。
54. As an 学习者, I want to 重复升级复用已有活动 Summary Job, so that 不会产生双重 token 消费。
55. As an 学习者, I want to 总结已经进入后续状态后重复升级成为安全空操作, so that 重试不会倒退 Record 状态。
56. As an 学习者, I want to 编辑 NOTE 后仍保持 NOTE, so that 修改本地正文不会自动升级或调用 AI。
57. As an 学习者, I want to 编辑 NOTE 不自动改变标题, so that Record 在列表中的身份保持稳定。
58. As an 学习者, I want to 升级时才把 NOTE 推进到 SUMMARY_PENDING, so that 状态变化准确表达我的意图。
59. As an 学习者, I want to 导入纯文档时可以不选择课程, so that 暂未归类的资料仍能立即保存和解析。
60. As an 学习者, I want to 导入多个文档时可以不选择课程, so that 一次学习会话的资料可以整体进入 Inbox。
61. As an 学习者, I want to 导入音频与文档混合批次时可以不选择课程, so that 多来源 Record 不被迫提前归类。
62. As an 学习者, I want to 未选课文档仍立即本地解析, so that 损坏、密码保护或无文本问题可以尽早发现。
63. As an 学习者, I want to 未选课文档解析完成后停在 SUMMARY_PENDING, so that 它保留真实内容状态但不生成总结。
64. As an 学习者, I want to 未选课音频继续遵守 ASR 同意与凭据规则, so that Inbox 不会绕过既有隐私边界。
65. As an 学习者, I want to 未选课音频完成转写后不调用 LLM, so that ASR 和 Summary 两种外部处理不会被混为一谈。
66. As an 学习者, I want to 已选 ACTIVE 课程的批次继续自动尝试总结, so that 现有直接进入学习链的体验不倒退。
67. As an 学习者, I want to 已归档课程不能接受新的捕获、归类或升级, so that AI 上下文不会绑定失效课程。
68. As an 学习者, I want to 课程在内容处理期间归档后仍保留 Transcript, so that 已受理来源不会因归档丢失。
69. As an 学习者, I want to 课程在总结入队前被再次校验, so that 归档竞态不会触发新的 LLM 调用。
70. As an 学习者, I want to 关闭窗口只隐藏应用, so that 全局快捷键和后台任务继续工作。
71. As an 学习者, I want to 从托盘重新显示并聚焦主窗口, so that 隐藏后的应用可被重新发现。
72. As an 学习者, I want to 快捷键重复触发时只保留一个速记框, so that 输入不会分散到叠加弹窗。
73. As an 学习者, I want to 快捷键被其他程序占用时应用仍能启动, so that 一个系统冲突不会阻断全部学习数据。
74. As an 学习者, I want to 快捷键冲突得到一次明确提示, so that 我知道应改用应用内入口。
75. As an 学习者, I want to 托盘提供明确的显示和退出命令, so that 关窗驻留不会让应用无法真正退出。
76. As an 学习者, I want to 活动录音时退出前得到警告, so that 我知道最新未落盘分片可能丢失。
77. As an 学习者, I want to 存在未保存速记或粘贴时退出前得到警告, so that 临时正文不会无提示消失。
78. As an 学习者, I want to 安全状态下托盘退出直接生效, so that 正常退出不需要多余确认。
79. As an 学习者, I want to 明确确认风险后仍能退出, so that 应用不会在我决定放弃内容时阻止操作。
80. As an 学习者, I want to 真正退出时 sidecar 一并停止, so that 后台进程不会残留。
81. As an 键盘用户, I want to 操作文本捕获、课程选择、Inbox 和确认对话框, so that 不使用鼠标也能完成闭环。
82. As an 键盘用户, I want to 所有焦点状态和禁用原因清晰可见, so that 我能理解哪些状态暂不可操作。
83. As an 使用窄窗口的学习者, I want to Inbox 与捕获栏没有整体横向滚动, so that 1099×720 仍可正常整理内容。
84. As an 深色主题用户, I want to 捕获和 Inbox 沿用现有连续工作面, so that 新功能不会退回卡片化或低对比界面。
85. As an 维护者, I want to SQLite 与 REST 继续作为业务事实源, so that 前端缓存和原生事件不会发展成第二套状态。
86. As an 维护者, I want to 不新增 Inbox 实体或业务状态, so that 归属和生命周期保持正交。
87. As an 维护者, I want to 文本捕获不创建虚假的 record_files, so that 来源文件与直接文本不会共享错误生命周期。
88. As an 维护者, I want to Wave A 不提前加入分页、筛选和批量归类, so that 当前实现保持最小且可验证。

## Implementation Decisions

### 领域模型与状态边界

- Inbox 的唯一成员条件是 Record 未软删且 `course_id` 为空。Inbox 不是持久化实体、标签、文件夹或新的 Record Status。
- NOTE 只用于无需后台内容处理的 QUICK_NOTE 和未选课 PASTE。文档、音频、录音和混合来源继续使用 CONTENT_PROCESSING、SUMMARY_PENDING、FAILED 等现有业务状态。
- 归类只改变课程归属，不触发 LLM，不产生 learning_events，也不把 NOTE 自动推进到 SUMMARY_PENDING。
- 升级表达用户请求进入 Summary/HITL：NOTE 在升级时推进到 SUMMARY_PENDING；已经处于 SUMMARY_PENDING 的 Record 保持该状态并尝试入队。
- “未归类不耗 token”精确解释为未归类不创建 LLM Summary Job。未选课音频仍可在用户已同意并配置 ASR 后执行腾讯转写，其费用和隐私合同继续由音频管线负责。
- 不新增数据库表、Record Status、Capture Type 或索引。现有可空 `course_id`、QUICK_NOTE、PASTE、Transcript 唯一关系和 `(course_id, created_at DESC)` 索引足以承载本功能。

### 文本捕获合同

- 顶部捕获栏提供独立“速记”和“粘贴文本”入口；两者复用同一个文本捕获组件，但由显式入口决定 QUICK_NOTE 或 PASTE，不按字数、键盘输入方式或浏览器 paste 事件推断。
- QUICK_NOTE 不显示课程选择器并固定 `course_id=null`、status=NOTE。PASTE 显示可选 ACTIVE 课程选择器，默认始终为“暂不归类”，不会根据当前路由预选。
- PASTE 未选课时 status=NOTE；选择 ACTIVE 课程时 status=SUMMARY_PENDING，并在本地事务提交后尝试复用现有 Summary 入队能力。
- 文本创建在一个 SQLite 事务中写入 Record 和 Transcript。两者任一写入失败都不得留下半条 Record；成功后再执行可恢复的 Summary 入队，不把外部能力加入本地事务。
- 文本捕获不创建 Record File、Processing Job 或来源文件。Transcript 初始 `language=und`、`source_version=1`、`edited_by_user=false`；用户之后保存修改时才置 `edited_by_user=true`。
- 正文以 UTF-8 字节数为边界，最大 1 MiB；后端是最终校验者，前端可做相同的提前提示。超过边界提示改用 TXT/MD 文档导入，不能静默截断。
- 只包含 Unicode 空白的正文返回 422，不创建 Record 或 Transcript。正文保留用户可见段落并统一换行为 LF；空白判断和标题生成使用清理后的视图，不用标题处理重写正文。
- Record 标题取正文第一条非空行去除首尾空白后的前 100 个 Unicode 字符。文本正文非空保证标题有来源；不增加独立标题输入或自动时间标题。
- 创建成功后关闭文本捕获框并保持用户当前页面，显示可访问的本地保存成功反馈，同时使 Inbox 查询失效；若用户本来位于 Inbox，新行立即出现。已选课 PASTE 进入对应 Record 的 Summary 页。
- 提交期间禁用重复保存；成功、失败或取消后恢复。取消关闭不创建任何业务事实。

### Capture Batch 与文档课程可选

- 当前桌面导入入口已经统一使用 Capture Batch，它是本功能的真实扩展接缝。纯文档、多文档、纯音频和音频+文档混合批次都允许 `course_id` 为空。
- 提供课程时仍必须在受理前验证课程存在、未软删且为 ACTIVE；无课程不是错误。旧的“批次包含文档就必须选择课程”规则被本规格取代。
- 旧单文件文档导入公开接口同步把课程参数改为可空，并复用相同的 ACTIVE 校验，避免同一产品中两个文档入口语义冲突。
- 文档无论是否选课都立即创建 DOCUMENT_PARSE Job 并本地解析；不新增“等待归类后解析”状态或启动命令。
- 音频和录音继续遵守封口批次、正式来源文件、处理缓存、ASR 同意、凭据、离线等待、检查点和恢复合同。本功能不改写 ASR 状态机。
- 全部来源成功后继续原子发布一份完整 Transcript。若 Record 无课程，发布后停在 SUMMARY_PENDING，Summary 自动入队资格检查返回无任务；若 Record 有 ACTIVE 课程，则沿用既有条件入队。
- 内容处理中课程被归档时仍完成内容处理并保留 Transcript；Summary 入队前必须重新读取并验证课程仍为 ACTIVE。
- Capture Batch 仍是一次性封口命令，不新增持久化批次实体，也不允许处理开始后追加或重排来源。

### API 合同

- `POST /api/text-captures` 接收显式 Capture Type、正文和可空课程。只允许 QUICK_NOTE/PASTE；QUICK_NOTE 携带课程或 PASTE 携带无效课程均返回可理解的 4xx。
- 文本捕获响应包含 `record_id` 与可空 `summary_job_id`。`summary_job_id=null` 表示本地捕获成功但当前没有启动 Summary，不是捕获失败。
- `GET /api/inbox` 返回全部未软删且 `course_id` 为空的 Record，按 `created_at DESC` 稳定排序；同时间使用 Record ID 作为稳定次序。Wave A 不增加分页、搜索、类型筛选或批量字段。
- `POST /api/records/{record_id}/classification` 接收目标课程，返回最新 Record。目标必须为 ACTIVE；Record 必须具备 NOTE 或 SUMMARY_PENDING 且尚未归类。
- 同一 Record 已归到同一课程时，重复归类返回当前 Record 作为幂等成功；已归到其他课程返回 409。不存在、已软删或父课程已删除按现有 Record 语义返回 404。
- `POST /api/records/{record_id}/upgrade` 接收可空目标课程并返回最新 Record 与可空 `summary_job_id`。未归类 Record 必须提供 ACTIVE 课程；已归类 Record 缺省使用当前课程；请求中的不同课程返回 409。
- NOTE 和 SUMMARY_PENDING 可以首次升级。若同一 Record 已有活动 Summary Job，重复升级返回该 Job；若状态已推进到 SUMMARY_PROCESSING、SUMMARY_READY 或 COMPLETED，重复升级返回当前事实且不倒退状态、不创建 Job。
- CONTENT_PROCESSING 与 FAILED 不接受归类或升级。处理中继续等待既有 Job；失败记录继续使用已有重试或删除出口，避免在 Transcript 尚不可用时混入 AI 意图。
- 删除继续复用现有 Record 软删除接口和 Job 取消语义，不新增 Inbox 专用删除端点。
- 所有端点继续受 localhost 启动令牌保护，使用生成的 OpenAPI 类型；前端不得直读 SQLite 或数据目录。

### 本地提交、Summary 入队与失败恢复

- 文本捕获和升级先提交本地 Record、Transcript、course_id 与 status，再尝试创建 Summary Job。外部 Provider、同意、网络或入队故障不能回滚已经成功的本地事务。
- 缺少 LLM Provider 或当前供应商同意时不创建 Summary Job，返回可空 Job ID，并由现有 Summary 读取合同展示配置或授权动作。
- 入队阶段发生意外故障时记录不含正文的结构化错误日志，响应仍保留本地成功事实；Record 停在 SUMMARY_PENDING，用户可从 Summary 页再次继续。
- Summary 入队继续校验 ACTIVE 课程、Transcript 存在、Record 状态、活动 Job 和当前 Transcript Source Version。不得为 Inbox 建立批量扫描待总结 Record 的后台任务。
- 现有活动 Summary Job 是重复升级的幂等事实；不得以再次点击为由创建第二个活动 Job。
- Summary Job 创建后的生成、失败、调整、确认、版本链、外部同意和 learning event 全部复用 06，不在本功能复制状态机。
- 编辑 NOTE 时更新 Transcript 版本和 `edited_by_user`，但 Record 保持 NOTE，不自动重算标题、不标记既有 Summary，也不调用 LLM。非 NOTE Transcript 编辑继续遵守既有版本和 Summary SUPERSEDED 合同。

### Inbox 页面与 Record 详情

- 左栏 Inbox 从禁用占位变成 `/inbox` 真实路由，复用现有 Application Shell、Record 展示语义、状态标签、加载/错误/空态和全局 Record 详情路由。
- 页面是按时间倒序的连续列表，不绘制装饰性时间轴、不把每条 Record 包成卡片。只有可导航行和真实动作显示 hover、pointer 与键盘焦点。
- 每行显示面向人的标题、Capture Type、Record Status 与创建时间。长标题单行截断并保留完整可访问文本。
- 页面存在 CONTENT_PROCESSING Record 时每 2 秒条件轮询 Inbox；没有处理中 Record、离开页面或请求失败进入稳定错误态时停止。不得为列表同时建立多个 Record SSE 连接。
- NOTE 和 SUMMARY_PENDING 行提供归类、升级、删除；CONTENT_PROCESSING 提供查看和删除，恢复动作沿用详情；FAILED 提供查看、已有 Job 重试和删除，不显示不可执行的归类/升级。
- 纯归类成功后使 Inbox 与目标课程 Record 列表失效，留在 Inbox 并移除该行，同时显示“已归类到 {课程}”的可访问页内反馈。
- 升级成功后使 Inbox、目标课程列表、Record 详情和 Summary 查询失效，并进入该 Record 的 Summary 页。可空 Job ID 不改变导航结果。
- Inbox 点击 Record 默认打开 Transcript Tab。无课程 Record 的返回链接指向 Inbox；有课程 Record 继续返回对应课程 Records。
- 无课程 Summary 使用新的 `COURSE_REQUIRED` 阻塞原因和“请先归类并升级”文案，与“课程已归档”严格区分。
- 无课程 Record 的 Summary 页提供带 ACTIVE 课程选择器的升级入口；已归类 NOTE/SUMMARY_PENDING 的 Summary 页提供不重复选择课程的升级入口。课程列表页不再复制升级按钮。
- 课程选择器只展示 ACTIVE 课程；加载失败、没有 ACTIVE 课程、提交中、409 冲突和本地成功但未入队都必须有诚实且可恢复的界面状态。
- Query cache 只提供即时反馈；SQLite/REST 始终是事实源。成功 mutation 精确失效 Inbox、课程列表、Record 详情与 Summary，不建立第二份业务 store。

### 全局快捷键、托盘与应用生命周期

- 本功能交付固定 `Ctrl+Alt+N`，不读取或写入偏好配置。快捷键自定义、开机自启与其他本机偏好由 13 在此能力之上实现。
- 初始化已经安装的全局快捷键插件；若系统注册失败，应用与 sidecar 继续启动，应用内速记入口保持可用，并在当前应用会话显示一次明确错误。
- 全局快捷键事件由 Tauri 负责接收，随后显示并聚焦主窗口，再向前端发送打开 QUICK_NOTE 模式的单一事件。前端已有速记框时只聚焦现有输入，不叠加 Dialog。
- 主窗口 CloseRequested 被阻止并转换为隐藏；隐藏不停止 sidecar、worker、录音恢复事实或快捷键注册。
- 系统托盘最小菜单只有“显示”和“退出”。显示动作恢复并聚焦主窗口；不增加设置、最近内容或捕获子菜单。
- 托盘退出先向前端发出退出请求。不存在活动 RECORDING/PAUSED 会话且文本捕获框没有未保存正文时，前端确认安全并执行真正退出。
- 存在活动录音时显示主窗口并提示最新尚未提交的内存分片可能丢失、已提交分片可在重启后恢复；存在未保存文本时明确提示正文将丢失。两种风险可在同一确认对话框合并呈现。
- 用户取消退出后应用保持运行、窗口可见且数据不变；用户明确确认后执行 Tauri 退出，沿用现有 RunEvent Exit 清理 sidecar。
- 不为托盘状态新增数据库或设置文件。未保存文本属于前端临时 UI 状态；录音业务事实继续来自现有 recording sessions Query，而不是原生层缓存。
- 实现优先复用现有 Tauri 与已安装插件；如托盘 API 需要启用现有 Tauri feature，只修改现有依赖声明，不安装新的第三方包或引入常驻辅助进程。

### 桌面体验、可访问性与视觉边界

- 新页面和弹窗遵循 Continuous Work Surface、Zero Card Chrome、既有 Noto Sans SC、语义色、shadcn/Base UI 原语和 i18n，不建立独立视觉系统。
- 顶部捕获栏保持录音为主按钮，速记、粘贴和导入使用次级/ghost 语法；窄屏可隐藏文字但保留可访问名称。
- Dialog 初始焦点进入正文；课程选择、保存、取消、归类、升级、删除与退出确认均可通过键盘完成，`focus-visible` 清晰可见。
- 仅以颜色区分状态不合格；所有处理中、失败、待归类、未入队和快捷键冲突都必须有文字。
- 提交中禁用重复动作但不隐藏当前输入；失败后保留正文和课程选择，允许修正或重试。
- 页面验证 1440×900、1280×800 和 1099×720，包含亮色/深色、长中文标题、1 MiB 边界提示、焦点、hover 和无整体横向溢出。

## Testing Decisions

- 好测试只断言外部行为：HTTP 响应、SQLite/文件系统持久事实、Provider 调用次数、页面可见状态、Tauri 窗口与进程结果。不断言 SQLAlchemy 内部调用顺序、React state 形状、Query cache 实现细节或辅助函数拆分。
- 第一条且最高的自动化接缝是 sidecar API 配合真实临时 SQLite、真实临时数据目录和可观测 fake Provider。沿用现有 Capture Batch、文档导入、Summary、Record 与 server-process 测试先例，不为标题、UTF-8 长度或状态判断分别建立碎片化测试文件。
- 文本捕获覆盖 QUICK_NOTE 与 PASTE、有/无 ACTIVE 课程、Record+Transcript 原子性、无 record_files、`language=und`、source version、编辑标志、首个非空行标题、100 字符边界、空白、恰好 1 MiB 与超过 1 MiB、不支持 Capture Type，以及失败时无半条业务数据。
- Capture Batch 覆盖无课程纯文档、多文档、纯音频和混合来源的受理；有 ACTIVE 课程继续成功；归档、删除或不存在课程继续拒绝。文档立即解析，完成后无课程 Record 为 SUMMARY_PENDING 且 fake Summary Provider 调用次数为零。
- Inbox 查询覆盖只返回 `course_id` 为空且未软删的 Record、全部 Capture Type/Status 的保留、稳定倒序、软删过滤与重启后同样结果。
- 归类覆盖 NOTE/SUMMARY_PENDING 成功、同课程幂等、跨课程 409、CONTENT_PROCESSING/FAILED 拒绝、ACTIVE 校验、删除竞态与 SQLite 最终事实；断言纯归类的 fake Provider 调用次数保持零。
- 升级覆盖无课程时选择课程、已归类时复用课程、NOTE→SUMMARY_PENDING、SUMMARY_PENDING 保持、已有活动 Job 复用、后续 Summary 状态重复命令不倒退、跨课程冲突，以及 Provider 缺失/未同意/入队异常时本地结果不回滚。
- NOTE Transcript 编辑覆盖版本递增、正文更新、`edited_by_user=true`、Record 仍为 NOTE、标题不变和零 Summary 调用；非 NOTE 编辑继续由既有 Transcript 控制面测试承担。
- 使用一次真实 localhost socket 冒烟验证启动令牌、文本捕获→Inbox→归类/升级请求形状和重启持久化。ASGI/应用内 HTTP 测试与真实 socket 证据必须分开报告。
- 第二条自动化接缝是桌面路由级渲染配合 MSW。沿用现有 AppShell、Record Detail、课程页面和 HTTP client 测试模式，渲染真实路由与 Query 交互，只 mock localhost 和 Tauri 原生边界。
- 桌面测试覆盖：左栏 Inbox 启用与路由；真实空态、加载、错误和重试；两种文本入口；课程默认不选；正文保留；提交中防重复；成功/失败/取消；Inbox 条件轮询；行导航；按状态显示动作；归类留在页面；升级进入 Summary；精确缓存失效；COURSE_REQUIRED；无课程返回 Inbox；NOTE 编辑仍为 NOTE。
- 桌面测试覆盖键盘操作、焦点回归、可访问名称、aria-live 结果、禁用原因和错误保留正文；不通过快照测试代替交互断言。
- Tauri/Rust 层只为可独立表达的外部策略留下最小测试，例如关闭转换为隐藏、退出请求的安全/需确认结果和重复快捷键事件不会制造第二个前端打开请求。若为测试需要复杂的新抽象，应改用更高层验收而不是搭建原生状态框架。
- Rust 格式、静态检查、桌面 lint/test/build、OpenAPI 生成一致性、Python Ruff/Pyright/pytest 和 `git diff --check` 是实现门禁，但它们不证明 OS 快捷键、托盘或真实窗口行为。
- 第三条接缝是真实 Windows/Tauri 验收：关窗后进程仍在；隐藏状态按 Ctrl+Alt+N 能显示、聚焦并打开一个速记框；重复按键不叠加；模拟快捷键冲突时应用仍启动且应用内入口可用；托盘显示恢复窗口。
- 真实 Tauri 验收还覆盖无风险退出直接停止 sidecar、活动录音退出警告、未保存文本退出警告、取消后继续运行、确认后退出，以及重启后已提交录音分片仍可恢复。必须核对实际进程与窗口，不把 Vite 页面当成 Tauri 证据。
- UI 实际渲染检查覆盖 1440×900、1280×800、1099×720、亮色/深色、长标题、hover、focus 和横向溢出；构建成功不能替代渲染证据。
- 本规格不要求重新发起真实腾讯 ASR 或真实外部 LLM 请求。11 只证明与既有 04/06 接缝正确；未归类零 Summary 调用和升级单次调用使用可观测 fake Provider，真实供应商证据继续归各自功能所有。

## Out of Scope

- Wave B 的批量归类和按类型筛选。
- Inbox 分页、游标、虚拟滚动、全文搜索或排序配置；真实规模证明全量读取不足时再增加。
- 已归类 Record 的重新归类、移动课程或批量移动。
- 快捷键自定义、快捷键录制控件、开机自启、主题、字体、时区和其他偏好设置。
- 自动归类建议、AI 课程推荐、速记直接生成知识点或批量扫描待总结 Record。
- 网页剪藏、浏览器扩展、OCR、PPT/PPTX、图片文字识别或新导入格式。
- 新的 LLM/ASR Provider、真实供应商重新验收、供应商健康面板或费用统计。
- 为文本捕获创建 Record File、原始 `.txt` 文件、处理 Job、来源锚点或 Transcript 历史表。
- 新 Record Status、Inbox 表、Inbox 标签、持久化 Capture Batch 或 AI 请求意图字段。
- 通用 Record POST/PATCH、通用搜索接口或从前端直写 SQLite。
- 为本功能新增 toast 框架、系统通知、多个窗口、托盘捕获子菜单或后台辅助进程。
- macOS/Linux 的全局快捷键与托盘验收；当前出口是 Windows Tauri Desktop。
- 本轮生成 issues 或实现代码；issues 由后续 `to-tickets` 基于本规格生成。

## Further Notes

- 本规格综合了 11 功能计划的五轮 grilling 共识，并使用 CONTEXT 中的 Capture、Quick Note、Paste、Inbox、File、Upgrade、Record 与业务态语言。
- 当前生产桌面导入已经使用统一 Capture Batch；旧单文件文档接口仍同步课程可空，只为保持公开契约一致，不重新建设第二套 UI。
- 本功能复用本地优先、封口 Capture Batch、Summary 绑定 Transcript Version、云 ASR/LLM 独立同意、Record File/Processing Cache 分离、Record SSE 仅失效通知和 sidecar 统一拥有录音 staging 等既有 ADR，不新增 ADR。
- 计划中的最小实现顺序由后续 `to-tickets` 固化为三张纵向票：文本/可选课程导入到 Inbox；归类/升级到既有 Summary/HITL；全局快捷键/托盘/安全退出与 Wave A 总验收。
- `ready-for-agent` 表示需求、接口与测试策略已经足以拆票，不表示代码、OpenAPI、Tauri 托盘或真实 Windows 验收已经完成。
