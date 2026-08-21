# 单文件文档导入与本地解析

Status: ready-for-agent

## Problem Statement

KnowRealm 已经能够持久化并展示 Record，但用户仍无法通过产品入口创建一条真实的学习记录。顶部快速捕获栏中的文档入口尚不可用，Record 详情的 Transcript 页签也没有真实内容来源。用户手中的 TXT、Markdown、PDF 或 DOCX 课件因此无法进入自己的数据目录，更不能在本地解析后成为后续总结功能可消费的 Transcript。

文档导入还首次引入文件资产与后台任务。如果上传、解析、Record 业务状态和任务技术状态混在一起，短暂故障会被错误地当成业务失败，重启后任务也无法恢复；如果原件、数据库行和解析结果分别提交，任一中途失败都可能留下不可发现的文件或没有原件的 Record。多个 sidecar 同时操作同一数据目录还会破坏 SQLite 单写者和文件一致性。

本功能需要交付一个最小且真实的单文件纵切：用户选择一个 ACTIVE 课程和一个支持的文档，原件进入本地数据目录，sidecar 内的单并发 worker 解析全文，Record 从 CONTENT_PROCESSING 推进到 SUMMARY_PENDING，并在 Transcript 页签显示结果。该纵切必须诚实处理可恢复故障、确定性失败、删除竞态、进程中断和 30 天清理，但不得提前引入多文件、Inbox、SSE、OCR 或 AI 总结。

## Solution

在现有顶部快速捕获栏启用“导入文档”。用户通过原生单文件选择器选择 TXT、MD、PDF 或 DOCX，并从已有课程中选择一个 ACTIVE 课程。桌面端使用 multipart 请求把文件交给受启动令牌保护的 localhost API；浏览器只负责选择与传输，所有信任边界校验、路径生成和落盘都由 sidecar 完成。

API 在创建任何业务数据前拒绝未选课程、不可用课程、空文件、不支持扩展名和磁盘空间不足。通过边界校验后，原件原样写入数据目录，并注册 DOCUMENT_IMPORT Record、record_files 关联和 DOCUMENT_PARSE Job。成功受理返回 202，桌面端立即进入该 Record 的 Transcript 页签。

sidecar 在持有数据目录操作系统排他锁后启动迁移和并发度为 1 的 asyncio worker。worker 从 processing_jobs 领取任务，按格式提取正文，将源文本写成 language=und 的 Transcript，再把任务置为 SUCCEEDED、Record 置为 SUMMARY_PENDING。处理期间 UI 每 2 秒查询任务状态；终态立即停止。解析成功不调用 Provider，不生成 Summary。

临时 I/O、SQLite busy 和 worker 意外中断每轮最多尝试 3 次；额度耗尽后用户可以手动开启新一轮。损坏、密码保护、格式伪装、纯图片或无可提取文本属于确定性失败，不允许对同一文件重试，只提供删除并重新选择。删除处理中 Record 会取消非终态 Job，worker 必须在每次写入前再次检查删除状态并丢弃后续产物。

## User Stories

1. As a 学习者, I want to 从顶部快速捕获栏发起文档导入, so that 我可以在工作台任意位置捕获课件。
2. As a 学习者, I want to 使用系统原生文件选择器选择一个文档, so that 我能沿用熟悉且可访问的桌面操作。
3. As a 学习者, I want to 一次只选择一个文件, so that 当前流程的进度、失败和归属保持清晰。
4. As a 学习者, I want to 导入 TXT 文件, so that 纯文本资料可以形成学习记录。
5. As a 学习者, I want to 导入 Markdown 文件, so that 带结构标记的笔记可以保留原貌。
6. As a 学习者, I want to 导入带文本层的 PDF, so that 常见电子课件可以被本地提取。
7. As a 学习者, I want to 导入 DOCX, so that Word 课件正文和表格可以成为 Transcript。
8. As a 学习者, I want to 在提交前选择课程, so that 后续 Transcript 和总结拥有明确的学习上下文。
9. As a 学习者, I want to 只能选择未删除且 ACTIVE 的课程, so that 新记录不会进入已经归档或不可见的知识空间。
10. As a 学习者, I want to 未选择课程时无法提交, so that 文档不会成为当前产品中无法重新发现的 Inbox Record。
11. As a 学习者, I want to 课程在提交前被归档时得到明确拒绝, so that 界面缓存不会绕过后端事实。
12. As a 学习者, I want to 看到已选文件名和目标课程, so that 提交前可以核对导入对象。
13. As a 学习者, I want to 可以取消选择或关闭导入对话框, so that 未提交操作不会产生文件或 Record。
14. As a 学习者, I want to 空文件在创建 Record 前被拒绝, so that 列表中不会出现没有可处理内容的记录。
15. As a 学习者, I want to 不支持的扩展名在创建 Record 前被拒绝, so that DOC、PPT 或其他格式不会进入错误的解析器。
16. As a 学习者, I want to 磁盘空间不足时在落盘前得到明确提示, so that 导入不会因写满数据目录而损坏。
17. As a 学习者, I want to 文档没有人为设置的体积上限, so that 本地优先产品不会套用云存储限制。
18. As a 学习者, I want to 导入后的标题默认取文件名去掉扩展名, so that 新 Record 容易识别。
19. As a 学习者, I want to 原始文件原样保存在数据目录, so that 解析结果之外仍有可逆的事实来源。
20. As a 学习者, I want to 相同文件可以重复导入, so that 不同学习会话不会被内容哈希错误合并。
21. As a 学习者, I want to 每次重复导入都得到独立 Record 和原件, so that 删除或处理其中一次不会影响另一次。
22. As a 学习者, I want to 文件受理后立即进入 Record 的 Transcript 页签, so that 我能看到当前处理状态而不是失去上下文。
23. As a 学习者, I want to 处理中看到明确状态, so that 我知道本地解析尚未完成。
24. As a 学习者, I want to 刷新应用后继续看到同一处理状态, so that 页面状态不依赖前端内存。
25. As a 学习者, I want to 处理期间获得适度更新, so that 进度可见又不会持续制造无意义请求。
26. As a 学习者, I want to 任务结束后停止轮询, so that 成功或失败页面不会继续请求后台。
27. As a 学习者, I want to TXT 和 MD 的 UTF-8 BOM 被正确处理, so that 文件开头不会出现多余字符。
28. As a 学习者, I want to TXT 和 MD 的换行统一显示, so that 不同平台生成的文本拥有稳定 Transcript。
29. As a 学习者, I want to Markdown 标记原样保留, so that 标题、列表和代码围栏不会在解析阶段丢失。
30. As a 学习者, I want to PDF 内容按页面顺序出现, so that Transcript 保持原课件阅读次序。
31. As a 学习者, I want to PDF 非空页之间用空行分隔, so that 页面边界可读但不插入虚构页码。
32. As a 学习者, I want to PDF 页眉页脚不被启发式删除, so that 解析器不会误删真实内容。
33. As a 学习者, I want to DOCX 正文段落和表格按文档顺序出现, so that 表格不会被集中到正文末尾。
34. As a 学习者, I want to DOCX 页眉、页脚、脚注、批注和嵌入对象不进入 Transcript, so that 当前能力边界清晰且结果可预测。
35. As a 学习者, I want to 文档原文不被翻译或改写, so that Transcript 是来源事实而不是 AI 产物。
36. As a 学习者, I want to 文档 Transcript 不猜测语言, so that 未实现的检测不会产生错误元数据。
37. As a 学习者, I want to 解析成功后看到完整 Transcript, so that 我能确认导入内容是否正确。
38. As a 学习者, I want to 解析成功后的 Record 停在等待生成总结, so that 下一阶段可以从明确状态接管。
39. As a 学习者, I want to 文档导入本身不消耗 AI 额度, so that 捕获和总结是可区分的阶段。
40. As a 学习者, I want to 临时故障被有限次数自动重试, so that 短暂 I/O 或数据库争用不要求人工介入。
41. As a 学习者, I want to 自动重试耗尽后看到可手动重试动作, so that 可恢复任务不必删除原件重新开始。
42. As a 学习者, I want to 手动重试开启完整的新一轮额度, so that 上一轮失败次数不会立即耗尽新尝试。
43. As a 学习者, I want to 手动重试复用原 Record、文件和 Job, so that 页面不会产生重复记录或丢失历史归属。
44. As a 学习者, I want to 损坏或密码保护的文件得到可理解的失败说明, so that 我知道需要换一个可读取文件。
45. As a 学习者, I want to 纯图片 PDF 或无可提取文本的文档保留为 FAILED Record, so that 已受理的失败不会从历史中悄悄消失。
46. As a 学习者, I want to 格式伪装文件被确定性拒绝处理, so that 扩展名不能欺骗解析器。
47. As a 学习者, I want to 确定性失败不显示同文件重试, so that 我不会反复执行注定失败的任务。
48. As a 学习者, I want to 确定性失败提供删除并重选文件的路径, so that 恢复动作与真实可行方案一致。
49. As a 学习者, I want to 在处理中删除 Record, so that 我可以撤销不再需要的导入。
50. As a 学习者, I want to 删除后后台停止为该 Record 写入产物, so that 已删除内容不会重新出现。
51. As a 学习者, I want to 已归档课程中的已受理文档仍完成解析, so that 提交后的课程竞态不会损坏本地事实。
52. As a 学习者, I want to 已归档课程的文档不自动进入 AI 总结, so that 后续 token 消费仍遵守 ACTIVE 课程边界。
53. As a 学习者, I want to sidecar 意外退出后任务可以恢复, so that 重启应用不会永久卡在处理中。
54. As a 学习者, I want to 同一数据目录不能被两个 sidecar 同时写入, so that SQLite 与原始文件保持一致。
55. As a 学习者, I want to 首个 sidecar 退出后可以再次打开数据目录, so that 操作系统锁不会形成永久阻塞。
56. As a 学习者, I want to 软删除满 30 天的文档原件和阶段业务数据被物理清理, so that 已删除内容不会无限占用磁盘。
57. As a 学习者, I want to 未满 30 天的墓碑仍保留, so that 清理任务不会提前破坏既定删除窗口。
58. As a 键盘用户, I want to 完成文件选择、课程选择、提交、取消和重试, so that 文档导入不依赖鼠标。
59. As a 使用辅助技术的学习者, I want to 上传、处理、成功和失败状态由文字与语义表达, so that 状态不只依赖颜色或动画。
60. As a 开发者, I want to Record 业务态与 Job 技术态分开存储, so that 多种后台任务不会污染用户可理解的状态机。
61. As a 开发者, I want to processing_jobs 成为技术任务状态唯一事实源, so that record_files 不会产生第二份进度状态。
62. As a 开发者, I want to 文件、Record、文件关联和 Job 的创建具有补偿边界, so that 任一步失败都不会留下不可发现的孤儿。
63. As a 开发者, I want to 所有路径由 sidecar 生成并限制在数据目录内, so that 原始文件名不能造成目录穿越或覆盖。
64. As a 开发者, I want to 日志和错误不包含文档正文或启动令牌, so that 本地敏感学习内容不会泄漏到诊断输出。
65. As a 开发者, I want to 导入和状态合同由 OpenAPI 生成前端类型, so that 前后端不会维护第二份手写协议。
66. As a 维护者, I want to 验收证据区分组件模拟、ASGI 集成、真实 socket、文件系统与桌面渲染, so that 低层通过不会被误报为完整桌面链路。

## Implementation Decisions

- 本功能扩展现有 Record 纵切和工作台外壳，不建立第二套文档工作区，不引入通用 Loader 框架、消息队列服务、Repository 接口或事件总线。
- 桌面入口复用顶部快速捕获栏和现有 Dialog、课程查询、Record 详情路由、TanStack Query、错误状态及 i18n。导入对话框只包含单文件选择、课程选择、取消和提交。
- 文件选择使用原生单文件 input。桌面端用 FormData 提交，不通过 Tauri/Rust 文件 API 读取或转存内容；统一 localhost 客户端遇到 FormData 时不得强制设置 JSON Content-Type，由浏览器生成 multipart boundary。
- 提交必须携带一个 course_id 和一个 file。后端以数据库当前值校验 Course 存在、未软删且 status=ACTIVE；前端禁用或隐藏不可用课程只是体验优化，不能代替后端校验。
- 新增受启动令牌保护的文档导入端点。成功受理返回 202 以及 record_id、job_id，客户端据此进入全局 Record 详情的 Transcript 页签。请求未进入后台队列前的校验错误使用现有统一错误响应。
- 新增按 job_id 查询单个 processing job 的受保护端点，作为 05 阶段轮询入口；响应提供 status、progress、attempts、max_attempts、稳定 error_code、面向 UI 的 retryable 和相关 record_id，不返回文档正文、内部路径或原始异常堆栈。
- 新增受保护的手动重试命令，仅接受 FAILED 且 retryable 的 DOCUMENT_PARSE Job。成功返回 202；命令复用原 Job，并在一个事务内将 Record 置为 CONTENT_PROCESSING、Job 置为 PENDING，attempts 归零并清除上一轮进度、错误和执行时间。
- 新增 Record Transcript 读取合同。可见 Record 有 Transcript 时返回 language、content、source_version、edited_by_user 和更新时间；尚未生成时返回明确的未就绪结果，不以空字符串冒充成功内容。
- FastAPI OpenAPI 仍是前后端合同唯一来源。新增请求、响应、枚举和错误结构必须重新生成类型包；桌面端不得复制 ProcessingJobStatus、错误码或 Transcript 类型。
- API 在创建 Record 前拒绝：缺失文件、缺失课程、Course 不存在/已删除/非 ACTIVE、0 字节、扩展名不在 TXT/MD/PDF/DOCX，以及可用空间小于文件体积两倍。文件无硬性体积上限。
- 扩展名比较不区分大小写。原始文件名只用于展示和 Record 标题；存储路径由服务端生成的 Record 与 file UUID 组成，不能采用客户端绝对路径、相对路径片段或未经净化的文件名。
- Record 的 capture_type 固定为 DOCUMENT_IMPORT，初始业务状态为 CONTENT_PROCESSING，title 取去掉最后一个扩展名后的原始文件名；空白结果使用现有未命名 Record 回退语义，不额外引入标题编辑。
- record_files 写入 file_type=DOCUMENT、source_type=UPLOADED、数据目录相对路径、原始文件名、可信的 MIME 描述、实际字节数、sequence_no=0 和内容哈希。content_hash 不设唯一约束，不参与去重短路或物理文件复用。
- 原件存放在 Record 与 file 标识组成的 files 子目录中并保持字节不变。上传先写同一目标文件系统中的临时文件，在完整写入、同步并完成空间检查后原子改名；数据库注册失败必须补偿删除本次文件，补偿失败由孤儿清理再次处理。
- 文件落盘、Record、record_files 和 DOCUMENT_PARSE Job 以“可补偿的文件操作 + 单个数据库事务”形成一致性边界。API 只在文件已就位且数据库事务提交后返回 202；任何较早失败不得暴露 Record。
- 本功能通过正式迁移新增 record_files、transcripts 和 processing_jobs 及必要的约束、索引和外键。迁移继续使用顺序 SQL 与 user_version，必须同时支持现有 Record 数据库升级和空库初始化，不使用 ORM create_all。
- processing_jobs 的 status 受控为 PENDING、RUNNING、SUCCEEDED、FAILED、CANCELLED。DOCUMENT_PARSE 每轮 max_attempts=3，首次领取计为第 1 次；next_run_at 控制退避，不以阻塞 sleep 占用 worker。
- processing_jobs 是技术状态唯一事实源。record_files 不保存 processing_status；records.status 只保存八态业务状态，前端不得从 attempts 或 progress 发明第九种业务状态。
- sidecar lifespan 的顺序固定为：解析数据目录并取得进程生命周期 OS 排他锁，再执行迁移、创建数据库连接和启动 worker。拿锁失败的第二个进程必须在迁移、备份或 worker 前退出并给出“数据目录正在使用”的明确错误。
- 排他锁依赖操作系统锁语义，锁文件只是锁对象，不以其是否存在判断占用。正常退出和进程崩溃后锁都由操作系统释放；不增加可能残留的自定义 sentinel 协议。
- worker 是 sidecar 进程内单个 asyncio 消费循环，并发度固定为 1。它只领取 next_run_at 已到期的 PENDING Job，并通过条件更新原子转为 RUNNING，避免同一任务被重复领取。
- worker 启动时恢复遗留 RUNNING Job：剩余尝试额度存在时，以 WORKER_INTERRUPTED 记录本次中断并重新排为 PENDING；额度已经耗尽时置为 FAILED 且 retryable，等待用户手动开启新一轮。
- 文档解析使用简单的按格式分派 Service：TXT/MD 使用 Python 标准库，PDF 使用 PyMuPDF，DOCX 使用 python-docx。只有一个 DOCUMENT_PARSE 消费者，不创建单实现接口、工厂注册表或通用文档加载器。
- TXT 与 MD 仅接受 UTF-8 或 UTF-8 BOM。解析去除 BOM、统一 CRLF/CR 为 LF，其余文本原样保留；MD 不渲染、不移除 Markdown 标记、不改写代码围栏。
- PDF 必须具有有效 PDF 结构且无需密码。按页顺序读取文本层，丢弃纯空白页，以一个空行连接非空页；不插入页码，不做页眉页脚去重，不 OCR，不读取图片文字。
- DOCX 必须是有效且可读取的 Office Open XML 文档。按文档顺序提取正文段落和表格中的文本；排除页眉页脚、脚注/尾注、批注、文本框、嵌入对象、修订删除文字和图片文字，不兼容旧 DOC。
- 成功解析必须得到至少一个非空白字符。结果写入一 Record 一份的 Transcript，language=und、source_version 初始值、edited_by_user=false；content 保留提取后的源文本，不翻译、不总结、不建立 Segment 或 Source Anchor。
- Transcript 写入、Job→SUCCEEDED 和 Record→SUMMARY_PENDING 在同一数据库事务内提交。任一步失败都不能留下“Job 成功但无 Transcript”或“Record 等待总结但内容未就绪”的状态。
- 课程只在提交时要求 ACTIVE。任务受理后 Course 变为 ARCHIVED 不取消解析，成功时仍保存 Transcript 并推进 SUMMARY_PENDING；后续总结功能必须在调用 AI 前重新校验 ACTIVE，本功能不代替该检查。
- 可恢复错误限定为临时文件 I/O、SQLite busy 和 worker 意外中断。未耗尽额度时 Job 从 RUNNING 回到 PENDING、attempts 保留并设置退避时间；耗尽后 Job 和 Record 进入 FAILED，retryable=true。
- 确定性错误包括损坏文件、密码保护 PDF、格式伪装、非 UTF-8 TXT/MD、纯图片 PDF 和所有非零但无可提取文本的输入。它们立即使 Job 与 Record 进入 FAILED，retryable=false；NO_EXTRACTABLE_TEXT 使用稳定错误码。
- 错误响应和日志只记录稳定错误码、record_id、job_id、格式和请求编号等诊断元数据，不记录正文、完整用户路径、启动令牌或解析器原始敏感输出。面向用户的错误文案由稳定错误码映射。
- Record 详情在 `tab=transcript` 时启用 Transcript 页签。PENDING/RUNNING 状态展示处理提示；SUCCEEDED 展示全文；可恢复 FAILED 展示手动重试；确定性 FAILED 只展示删除并重新选择；CANCELLED 按已删除 Record 语义不可继续操作。
- 桌面端仅在 Job 为 PENDING 或 RUNNING 时每 2 秒查询同一 job_id。进入 SUCCEEDED、FAILED 或 CANCELLED 后立即停止；成功后失效 Record、课程 Record 列表和 Transcript 查询缓存，刷新真实终态。
- 普通 Record 详情仍默认进入 Summary。只有文档导入成功受理后的导航显式携带 Transcript 页签；不全局改变 02 已冻结的默认页签合同。
- 删除继续复用现有 Record 软删除入口。删除事务同时把该 Record 的 PENDING/RUNNING Job 置为 CANCELLED；SUCCEEDED、FAILED、CANCELLED 等终态 Job 不被重写。
- worker 在解析前以及写 Transcript、Job 结果或 Record 状态前检查 Record deleted_at 和 Job 当前状态。发现软删或 CANCELLED 后停止任务、丢弃内存结果和临时产物，不再写入任何业务产物。
- 现有启动清理扩展到所有 Record 墓碑，包括独立删除和随 Course 软删除的 Record。软删满 30 天后，必须先清理其文档资产，再物理删除 Transcript、record_files、processing_jobs 和 Record；父 Course 的物理删除必须排在后代文档资产清理之后，不能让外键级联提前隐藏文件目标。未满 30 天不清理。
- 清理只处理路径解析后仍位于数据目录允许子树的文件。文件已不存在视为幂等成功；文件处理或数据库提交失败时保留或恢复可再次定位的清理目标，不能留下无法追踪的原件，也不能删除仍被活跃行引用的文件。
- 孤儿清理只删除能够证明属于一次未提交导入或已物理清理实体的文件，不按文件名猜测活跃资产。正常 content_hash 重复、相同原始文件名或独立 Record 不能被当作孤儿。
- 本功能不增加外部网络调用。解析、任务调度、重试和清理全部在本地完成；不得调用 LLM、Embedding、ASR、LangGraph 或任何 Provider。
- 用户可见交互遵循现有 Continuous Work Surface、明暗主题、焦点和无整体横向溢出合同。状态必须有文字与可访问语义，不能只依赖颜色、旋转图标或 toast。

## Testing Decisions

- 好测试只观察外部行为：HTTP 状态与响应、数据库可见状态、数据目录产物、进程生命周期以及用户可访问交互。不得断言组件内部 state、私有函数调用顺序、SQLAlchemy 内部对象、具体 CSS 类名或 worker 循环实现细节。
- 已确认采用三个现有接缝，不为本功能增加第四套测试基础设施：后端 ASGI 集成主接缝、桌面 Vitest/Testing Library/MSW 行为接缝，以及窄范围真实 sidecar/socket 进程接缝。
- 最高层主接缝复用现有 FastAPI lifespan + ASGITransport + 正式迁移链 + 临时数据目录。它启动真实单并发 worker，覆盖 multipart 受理、文件落盘、数据库注册、解析、重试、取消、清理和应用内重启恢复。
- 主接缝为 TXT、MD、PDF、DOCX 各提供一个最小真实样本，断言原件字节不变、record_files 元数据正确、Transcript 符合提取规则、Job=SUCCEEDED、Record=SUMMARY_PENDING，并证明没有 Provider 或 AI 产物。
- TXT/MD 样本覆盖 UTF-8、UTF-8 BOM、CRLF/CR 归一化、Markdown 标记和非 ASCII 原文；非法编码进入确定性 FAILED，不提供重试。
- PDF 样本覆盖多页文本、空白页、页间空行、无人工页码；另有密码保护、损坏、格式伪装和纯图片/无文本样本验证确定性失败。
- DOCX 样本覆盖正文段落与表格交错顺序，并包含可识别的页眉页脚或其他排除内容，证明这些内容不进入 Transcript；损坏包进入确定性失败。
- API 边界测试覆盖缺失 token、错误 token、缺失课程、Course 不存在/已删除/ARCHIVED、缺失文件、0 字节、不支持扩展名和磁盘空间不足；这些情形均不得产生 Record、Job、record_files 或存档原件。
- 文件一致性测试通过可控故障验证临时写失败、原子改名失败和数据库提交失败的补偿结果；测试结束后不得遗留可见 Record 或不可解释孤儿。
- 重复导入测试两次提交完全相同的文件，断言 content_hash 相同但 Record、record_files、Job 和物理原件均独立。
- 任务状态测试覆盖 PENDING→RUNNING→SUCCEEDED、可恢复失败 RUNNING→PENDING 的退避、首次计入的每轮 3 次上限、额度耗尽后的 FAILED，以及手动重试的新一轮原子重置。
- 确定性失败测试断言 attempts 不进入自动重试循环、retryable=false、Record=FAILED，并拒绝手动重试命令。
- 删除竞态测试分别在 PENDING、RUNNING 和解析完成但提交前删除 Record，断言非终态 Job=CANCELLED、无 Transcript 或后续状态回写、临时产物被丢弃；终态 Job 不被删除动作改写。
- 课程归档竞态测试在任务受理后归档 Course，断言解析仍完成并保留 Transcript；本功能只证明没有 AI 调用，不替代 06 对 ACTIVE 再校验的测试。
- 可控时钟测试覆盖独立删除和随 Course 删除的 Record：未满 30 天保留，满 30 天后先清理文档资产再删除本阶段业务行与父 Course；文件处理或数据库提交失败时仍可重试，并验证重复执行清理的幂等性。
- 桌面行为接缝复用现有 Vitest、Testing Library 和 MSW。它覆盖打开导入 Dialog、单文件限制、课程必选、FormData 请求、202 后 Transcript 导航、各任务状态、2 秒条件轮询、终态停止、错误动作和键盘/读屏语义。
- 前端测试必须检查 multipart 请求没有被统一客户端强制写成 application/json，但不固定浏览器生成的 boundary 字符串。
- 组件测试中的 MSW 只证明桌面端行为和请求合同，不作为真实 localhost、SQLite、文件系统、worker、操作系统锁或桌面 Network 证据。
- 真实进程接缝复用现有 sidecar 随机端口测试，只补充必须跨进程证明的行为：multipart 请求穿过真实 socket、原件和 Transcript 跨重启持久化、遗留 RUNNING 恢复、同一数据目录第二进程在迁移/worker 前失败、首进程退出后锁可重新取得。
- 真实进程测试使用唯一临时数据目录、随机启动令牌和随机 loopback 端口，只终止测试自己创建的进程；日志断言不泄漏令牌、正文或完整用户路径。
- OpenAPI 门禁重新导出 schema、生成 TypeScript 类型并执行无漂移检查；生成物必须保持仓库既定换行规则。
- 静态门禁覆盖后端 Ruff、Pyright、pytest，桌面 TypeScript、ESLint、Vitest、Prettier 和构建。PyMuPDF 与 python-docx 使用锁定依赖，不额外引入文档框架。
- 实现完成后的人工渲染检查覆盖现有三个桌面尺寸、明暗主题、键盘焦点、长文件名、长 Transcript、加载/成功/两类失败和无整体横向溢出；该检查不新增 Playwright 或完整浏览器 E2E 接缝。
- 完成报告分别列出源码/静态、迁移与 SQLite、ASGI/文件/worker、桌面组件、真实 HTTP/socket/锁、人工 Network/渲染证据。未执行的层级必须明确标为未验证。

## Out of Scope

- DOC、PPT、PPTX、RTF、网页、图片、扫描件 OCR、PDF 密码输入和任何其他格式。
- 一次选择多个文件、一条 Record 关联多个文档、音频与文档混合、文件排序或处理开始后的重排；这些由 04 承接。
- SSE、事件推送或“推送为主、轮询兜底”；05 只做每 2 秒条件轮询，04 再接入 SSE。
- 未选择课程的文档捕获、Inbox 可达性、事后归类或升级；这些由 11 承接。
- Summary Job、Provider、LLM、LangGraph、HITL、知识点、习题、Todo、Embedding、Segment、Document Segment 和 Source Anchor；总结/HITL 由 06 承接。
- Transcript 编辑、版本回滚、搜索、高亮、分页、虚拟滚动、导出或基于页码的来源跳转。
- 全局任务中心、并发度配置、优先级队列、多 worker、多进程队列、分布式锁或外部消息中间件。
- 基于 content_hash 阻止重复、复用物理文件、秒传或用户可见的重复文件警告。
- 文档页眉页脚智能去重、版面还原、样式保留、表格结构化展示、图片提取、语言检测或翻译。
- 完整浏览器 E2E、MSI/PyInstaller 分发验证、新机安装、CI 发布和自动更新。

## Further Notes

- 当前 Record 表、课程内列表、全局详情、软删除、随机 localhost 端口、启动令牌、SQLite 迁移链、OpenAPI 类型链和桌面测试接缝已经存在；文档导入应扩展这些路径，不重建基础设施。
- 当前生产 Record 没有创建入口。本功能完成后，只有文档导入能够生产创建 DOCUMENT_IMPORT Record；这不等于录音、音频、粘贴、速记或 Inbox 捕获已经完成。
- 当前 sidecar lifespan 在迁移前尚未持有数据目录 OS 排他锁，现有清理只覆盖 Course 墓碑。两者都是本功能首次成为文件/worker 写者后必须补齐的完整性边界，不是可选优化。
- 当前 Record 详情默认 Summary 且 Transcript 禁用。本功能只在真实 Transcript 合同存在后启用该页签，并保持普通详情默认 Summary 的既有行为。
- 本规格遵循已接受的本地优先 ADR：数据目录是唯一业务事实源、sidecar 是唯一写者、云端不是依赖。文档解析没有新的不可逆架构选择，因此不新增 ADR。
- `ready-for-agent` 表示需求与测试策略已可供后续拆票/实现；它不表示代码、迁移、真实文件解析或桌面渲染已经完成。
