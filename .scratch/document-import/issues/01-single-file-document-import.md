# 01 — 单文件文档导入完整主链

**What to build:** 用户可以从顶部快速捕获栏选择一个 ACTIVE 课程和一个 TXT、MD、PDF 或 DOCX 文件；文件经受保护的 localhost API 原样进入数据目录，由单并发后台任务解析为真实 Transcript，随后直接在 Record 详情中显示全文并停在 SUMMARY_PENDING。该切片同时建立文件资产、技术任务和数据目录单写者的完整基础，使文档导入成为首个生产 Record 创建入口。

**Blocked by:** None — can start immediately

**Status:** completed

- [x] sidecar 在解析数据目录后、迁移和 Worker 启动前取得进程生命周期 OS 排他锁；第二个进程打开同一目录时明确失败，首个进程正常退出或崩溃后可重新取得锁，且不以残留 sentinel 文件判断占用。
- [x] 新数据库和现有 Record 数据库升级后都具有 record_files、transcripts、processing_jobs 的正式 schema、外键、约束和索引；Job 五态含 CANCELLED，record_files 不保存第二份技术处理状态。
- [x] 顶部快速捕获栏启用“导入文档”，对话框使用原生单文件选择、ACTIVE 课程选择、取消和提交；未选课程或文件时不能提交，关闭或取消不产生业务数据。
- [x] 文档导入请求使用 FormData，统一客户端不强制写入 JSON Content-Type；接口受启动令牌保护，成功受理返回 202 及可供详情导航和任务查询的 Record/Job 标识。
- [x] 后端在创建 Record 前拒绝缺失或不可用课程、0 字节、不支持扩展名和可用空间小于文件体积两倍；扩展名比较不区分大小写，文件没有人为体积上限。
- [x] 原件通过同文件系统临时写入和原子落位保存为数据目录内受控相对路径；客户端文件名不能目录穿越或覆盖其他文件，数据库注册失败有补偿，日志和错误不包含正文、完整用户路径或启动令牌。
- [x] 每次成功受理原子注册 DOCUMENT_IMPORT Record、DOCUMENT 类型的 record_files 和 DOCUMENT_PARSE Job；Record 初始为 CONTENT_PROCESSING，标题取文件名去扩展名，content_hash 只用于完整性与重复检测。
- [x] 完全相同的文件允许重复导入，两次导入产生独立 Record、文件关联、Job 和物理原件，不因 content_hash 相同而拒绝、复用或覆盖。
- [x] sidecar 内 Worker 并发度固定为 1，只领取到期 PENDING Job 并原子置为 RUNNING；processing_jobs 是进度、尝试次数和错误信息的唯一技术事实源。
- [x] TXT/MD 仅接受 UTF-8 或 UTF-8 BOM，去除 BOM、统一换行为 LF并保留 Markdown 标记；PDF 按页顺序提取文本层、忽略纯空白页并以空行连接；DOCX 按正文顺序提取段落和表格，并排除规格列明的页眉页脚、批注、文本框、嵌入对象和图片文字。
- [x] 损坏、密码保护、格式伪装、非 UTF-8、纯图片或无可提取文本属于确定性 FAILED；同一文件不自动或手动重试，详情只提供删除并重新选择，NO_EXTRACTABLE_TEXT 等稳定错误码不暴露解析器堆栈。
- [x] 成功解析至少包含一个非空白字符；Transcript 保留提取后的源文本并写入 language=und，Transcript、Job→SUCCEEDED 和 Record→SUMMARY_PENDING 在同一事务中完成，不调用 Provider、不生成 Summary、Segment 或其他 AI 资产。
- [x] 受保护的 Job 查询和 Transcript 读取合同进入 OpenAPI 生成链；桌面端使用生成类型，不复制 Job 状态、错误码或 Transcript 结构。
- [x] 导入受理后进入全局 Record 详情的 Transcript 页签；PENDING/RUNNING 时每 2 秒条件查询，SUCCEEDED/FAILED/CANCELLED 时立即停止，成功后刷新 Record、课程列表和 Transcript 缓存；普通 Record 详情仍默认 Summary。
- [x] 自动化测试通过真实 TXT、MD、PDF、DOCX 样本覆盖迁移、鉴权、边界拒绝、原件字节、解析顺序、确定性失败、重复导入、事务补偿和终态停止轮询；组件 MSW、ASGI/临时数据目录和真实 sidecar/socket 证据明确分层。
- [x] 在既定桌面尺寸、明暗主题、键盘操作、读屏状态、长文件名、长 Transcript 和无整体横向溢出条件下完成人工渲染检查；完成报告明确说明文档生产创建已接入，但重试恢复、删除取消和 30 天清理由后续票据承接。
