# 02 — 文档任务重试与恢复

**What to build:** 用户的文档解析遇到临时 I/O、SQLite busy 或 Worker 中断时可以自动恢复；一轮三次尝试耗尽后，用户能够在同一 Record 上手动开启新一轮，而应用重启不会让任务永久停在处理中。已经受理的文档即使所属课程随后归档，也会保留本地 Transcript，但不会在本功能中触发 AI。

**Blocked by:** 01 — 单文件文档导入完整主链

**Status:** completed

- [x] 可恢复错误严格限定为临时文件 I/O、SQLite busy 和 Worker 意外中断；确定性解析错误继续保持不可重试，不能因本票据获得重试入口。
- [x] DOCUMENT_PARSE 每轮最多尝试 3 次且首次执行计入；未耗尽时 Job 从 RUNNING 回到 PENDING，保留 attempts 并设置 next_run_at 退避，不使用阻塞 sleep 占用 Worker。
- [x] 第三次可恢复失败后 Job 与 Record 进入 FAILED，技术响应明确 retryable=true；UI 停止自动轮询并展示同一文件的手动重试动作。
- [x] 手动重试只接受 FAILED 且 retryable 的 DOCUMENT_PARSE Job；命令复用原 Job、Record 和原件，不创建重复 Record 或文件关联。
- [x] 手动重试在单个事务中执行 Record→CONTENT_PROCESSING、Job→PENDING、attempts 归零并清除上一轮进度、错误及执行时间，成功返回受理状态并恢复条件轮询。
- [x] 不可重试 Job、非 FAILED Job、已删除 Record、已取消 Job 或不匹配的 Record/Job 请求被明确拒绝，且不发生部分状态更新。
- [x] sidecar 在持有数据目录排他锁并完成迁移后恢复遗留 RUNNING Job：有剩余额度时以 WORKER_INTERRUPTED 重新排为 PENDING，额度耗尽时置为可手动重试的 FAILED。
- [x] 同一数据目录重启后，原件、attempts、next_run_at、Job/Record 状态和已完成 Transcript 都从 SQLite 与文件系统恢复，不依赖前端内存或测试种子。
- [x] 文档提交时仍要求 Course 为 ACTIVE；受理后 Course 变为 ARCHIVED 不取消解析，成功时保留 Transcript 并推进 SUMMARY_PENDING，但本票据不创建 Summary Job、不调用 Provider。
- [x] Job 查询、错误文案和日志只暴露稳定错误码及必要诊断元数据，不泄漏正文、令牌、内部异常堆栈或完整用户路径。
- [x] ASGI 集成测试使用可控故障和时钟覆盖三次上限、退避、耗尽、手动新一轮、非法重试和归档竞态；测试断言外部状态与产物，不绑定 Worker 私有调用顺序。
- [x] 真实 sidecar 进程测试覆盖运行中退出、同一数据目录重启、遗留 RUNNING 恢复和最终 Transcript 持久化；只终止测试创建的进程，并与组件模拟证据分开报告。
- [x] 桌面测试覆盖可恢复失败、重试按钮、重复提交保护、重试失败保留上下文、成功重新轮询和终态停止；既有确定性失败“删除并重选”行为不回归。
- [x] 完成报告分开列出静态检查、迁移/SQLite、ASGI/Worker、真实进程/socket、桌面组件和人工渲染证据，并明确 30 天清理与删除竞态仍由 03 承接。
