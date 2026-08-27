# 01 — 文本捕获、可选课程导入与真实 Inbox

**What to build:** 让用户无需先选课程就能把速记、粘贴文本、文档、音频或混合来源可靠保存到本地，并在左栏 Inbox 看到真实未归类时间流。本票完成后，速记与粘贴已形成 Record + Transcript 闭环，统一 Capture Batch 的所有来源组合均可选择或不选择课程，未归类内容保持真实处理状态且不启动 Summary；用户可以从 Inbox 查看、重试或删除，而不是只得到后端接口或禁用页面。

**Blocked by:** None — can start immediately.

**Status:** done

- [x] 新增受启动令牌保护的文本捕获命令，只接受 QUICK_NOTE / PASTE；QUICK_NOTE 固定无课程，PASTE 课程可选且只接受存在、未软删的 ACTIVE 课程。
- [x] 文本捕获在同一 SQLite 事务创建 Record 与 Transcript；任一步失败均不留下半条数据，且不创建 record_files、来源文件或 processing_jobs。
- [x] QUICK_NOTE 与未选课 PASTE 为 NOTE；已选课 PASTE 为 SUMMARY_PENDING，并在本地提交成功后条件尝试复用现有 Summary 入队能力。
- [x] Transcript 初始为 language=und、source_version=1、edited_by_user=false；正文换行统一为 LF，用户可见段落不被标题清理逻辑改写。
- [x] 空白正文在创建业务数据前返回 422；正文按 UTF-8 字节限制为最大 1 MiB，超过时不截断并提示改用 TXT / MD 文档导入。
- [x] Record 标题取正文第一条非空行去除首尾空白后的前 100 个 Unicode 字符，不增加独立标题输入或时间标题。
- [x] 文本捕获响应包含 record_id 与可空 summary_job_id；Provider 缺失、未同意、离线或入队临时失败不得回滚已经成功的 Record/Transcript。
- [x] 当前统一 Capture Batch 移除“含文档必须选课”的旧限制；纯文档、多文档、纯音频和音频+文档混合批次都允许 course_id 为空。
- [x] Capture Batch 提供课程时继续在受理前校验 ACTIVE；课程为空时所有来源照常创建正式来源、Jobs 与 CONTENT_PROCESSING Record，不把文档或混合来源改成 NOTE。
- [x] 文档在无课程时仍立即本地解析；全部来源完成后原子发布 Transcript，Record 停在 SUMMARY_PENDING，且可观测 fake Provider 证明未创建 Summary Job。
- [x] 旧单文件文档导入公开接口同步接受可空课程并复用 ACTIVE 校验；不重新建设第二套桌面导入 UI。
- [x] 顶部捕获栏提供明确分开的“速记”和“粘贴文本”入口，复用同一文本捕获组件但由入口决定 Capture Type，不按字数或 paste 事件猜测。
- [x] 速记不显示课程选择器；粘贴和现有文件导入的课程选择器始终默认“暂不归类”，即使从课程页面打开也不自动预选。
- [x] 文本 Dialog 初始焦点进入正文；提交期间防止重复保存，失败保留正文与课程选择，取消无业务副作用；成功后关闭并在当前工作上下文显示可访问反馈。
- [x] 已选课 PASTE 成功后进入 Record Summary；未选课文本成功后使 Inbox 查询失效，用户保持当前页面，若已在 Inbox 则新行立即出现。
- [x] 左栏 Inbox 从禁用占位变成真实 `/inbox` 路由，读取所有未软删且 course_id 为空的 Record，并按 created_at DESC、Record ID 稳定倒序。
- [x] Inbox 使用既有 Record 标题、Capture Type、Status 与创建时间展示 NOTE、CONTENT_PROCESSING、SUMMARY_PENDING、FAILED 等真实状态，不增加 Inbox 状态或示例数据。
- [x] Inbox 采用 Continuous Work Surface 的连续行列表，不绘制装饰性时间轴或卡片外框；交互行具备 hover、pointer、键盘焦点和长标题完整可访问文本。
- [x] Inbox 存在 CONTENT_PROCESSING 时每 2 秒条件轮询，终态、离开页面或稳定错误时停止；不为列表中的每条 Record 建立 SSE 连接。
- [x] Inbox 行可进入 Record Transcript；无课程 Record 的返回链接指向 Inbox，有课程 Record 的既有返回路径不变。
- [x] CONTENT_PROCESSING 与 FAILED 行保留现有详情、Job 重试和删除出口；NOTE/SUMMARY_PENDING 在本票不呈现尚未实现的归类/升级死按钮。
- [x] 复用现有 Record 软删除与 Job 取消语义；删除成功后 Inbox 立即移除该行，刷新与重启后仍不可见。
- [x] OpenAPI schema 与生成类型覆盖文本捕获、可空课程和 Inbox 查询，生成检查无漂移；前端所有业务事实仍经 localhost API，不直读 SQLite。
- [x] sidecar 最高接缝测试使用真实临时 SQLite/数据目录覆盖文本边界、事务原子性、所有无课程来源组合、Inbox 排序/软删/重启持久化及零 Summary 调用。
- [x] 桌面路由级 MSW 测试覆盖两个入口、默认无课程、空白/1 MiB、提交状态、成功/失败/取消、Inbox 空态/错误/轮询/导航/重试/删除与可访问性，只断言外部行为。
- [x] 使用真实 localhost socket 完成至少一次“无课程文本捕获 → Inbox 可见 → 删除 → 重启后仍不可见”冒烟，并将其与 ASGI、MSW 和构建证据分开报告。
- [x] Python 测试与静态检查、OpenAPI 生成一致性、桌面测试/lint/build、格式检查和 `git diff --check` 全部通过；本票不把 fake Provider、模拟 ASR 或构建成功描述成真实外部供应商验收。

