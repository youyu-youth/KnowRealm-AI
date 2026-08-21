# 05 - 文档导入

> Wave: A ｜ PRD: §4.3.2（文档）/ §4.3.4 ｜ 决策引用: #35 #41 #44 #45 #54 #57

## 功能描述 / 目标

课件 / 文档捕获（五级入口 L5）的首个真实纵切：单文件经 localhost API 原样落盘，后台解析形成 Transcript，并将 Record 推进到 SUMMARY_PENDING。作为首个后台任务消费者，同步引入并发度 1 的最小 worker、processing_jobs、数据目录排他锁与 UI 条件轮询。

## 功能范围

**做**：
- 单文件格式：TXT / MD / PDF / DOCX（原生文本 / PyMuPDF / python-docx）；提交时必须选择存在、未软删且状态为 ACTIVE 的课程
- `<input type="file">` + FormData 经 localhost API 上传；原件原样写入 `files/{record_id}/{file_id}.{ext}`，注册 Record / record_files / DOCUMENT_PARSE Job
- 最小 sidecar asyncio worker（并发度 1）、processing_jobs 技术任务态、崩溃恢复与处理中条件轮询；`processing_jobs` 是技术状态唯一事实源
- 解析结果写 Transcript（源文本原样保存，`language=und`），Record 从 CONTENT_PROCESSING 推进到 SUMMARY_PENDING；不调用 Provider、不生成 Summary
- 文档导入入口挂载 01 已提供的顶部快速捕获栏；成功后进入 `/records/{id}?tab=transcript`，复用 02 的列表、详情、软删除与错误状态
- 可恢复故障自动退避与手动重试；确定性解析失败只允许删除并重选文件；删除处理中 Record 将非终态 Job 置为 CANCELLED，worker 丢弃后续产物
- 同一数据目录进程生命周期排他锁、文件落盘补偿、孤儿清理，以及 Record/文件/业务行 30 天物理清理

**不做**：
- DOC、PPT/PPTX、OCR、网页剪藏（P2）
- 多文件、音频+文档混合与 SSE（移交 04）
- 未选课文档与 Inbox 可达性（移交 11）
- Summary Job、Provider、LangGraph 与 HITL（移交 06）

## 核心业务流程

选择单文件 + ACTIVE 课程 → API 校验扩展名/0 字节/磁盘空间并原子落盘 → 同事务注册 Record、record_files 与 DOCUMENT_PARSE Job → 202 返回并进入 Transcript 页签 → CONTENT_PROCESSING（worker 解析，UI 每 2 秒条件轮询）→ Transcript 落库 → SUMMARY_PENDING。06 后续消费该状态并在触发 AI 前再次校验课程仍为 ACTIVE。

## 关键业务规则

- TXT/MD 仅接受 UTF-8/UTF-8 BOM，统一换行为 LF，保留 Markdown 标记；Record 标题取去扩展名后的文件名
- PDF 按页顺序提取文本层，非空页用空行合并，不插入人造页码、不做页眉页脚去重；DOCX 按原顺序提取正文段落与表格，排除页眉页脚、脚注/尾注、批注、文本框、嵌入对象、修订删除文字与图片文字
- 0 字节或不支持扩展名在创建 Record 前返回 4xx；非零但无可提取文本、损坏、密码保护、格式伪装立即 FAILED，不自动/手动重跑同一文件
- 临时 I/O、SQLite busy、worker 意外中断每轮最多尝试 3 次（首次计入）；耗尽后可手动重试。手动重试复用原 Job，原子执行 Record→CONTENT_PROCESSING、Job→PENDING，并开启新一轮额度
- worker 每步写入前检查 `record.deleted_at`；软删即终止、丢弃产物并将非终态 Job 置为 CANCELLED（#54）
- 无体积硬限；落盘前要求磁盘剩余空间 ≥2× 文件体积（#44）。同一 content_hash 允许重复导入并创建独立 Record
- 提交时校验 ACTIVE；已受理后课程若变为 ARCHIVED，解析仍完成并保留 Transcript，06 不得在课程非 ACTIVE 时触发 AI
- sidecar 取得数据目录 OS 排他锁后才执行迁移和启动 worker；启动时恢复遗留 RUNNING，进程退出/崩溃后锁由 OS 自动释放

## 前置依赖

- 02（复用 Record 表、列表、详情与软删除语义；本 plan 首次引入后台任务、文件资产与 Transcript 基础）

## 验收标准（出口线）

- [ ] TXT / MD / PDF / DOCX 各有真实单文件样本经 API 原样落盘；详情 Transcript 页签显示符合提取规则的全文，Record 最终停 SUMMARY_PENDING，且没有 AI 调用
- [ ] 未选课程、ARCHIVED 课程、0 字节和不支持扩展名在创建 Record 前被拒；磁盘空间不足有明确提示
- [ ] processing_jobs 可查询 PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED；详情与含 CONTENT_PROCESSING 的课程列表每 2 秒条件轮询，终态停止，刷新应用后可从 SQLite 恢复
- [ ] 临时故障每轮最多尝试 3 次并可手动开启新一轮；损坏、密码保护、纯图片/无文本、格式伪装进入确定性 FAILED，只显示删除并重选
- [ ] 导入成功直达 Transcript；普通 Record 详情仍默认 Summary；英文原文保持不变且 language=und
- [ ] 删除处理中 Record 后 Job=CANCELLED、worker 无后续产物入库；30 天清理可通过可控时钟验证文件与本阶段业务行被物理清理
- [ ] 相同文件重复导入生成两个独立 Record；第二个 sidecar 打开同一数据目录时在迁移/worker 前被拒，首个进程退出后锁可再次取得
