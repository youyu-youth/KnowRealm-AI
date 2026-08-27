# 02 — 归类、升级与 Summary/HITL 交接

**What to build:** 让用户把已经具备 Transcript 的 Inbox Record 纯归类到 ACTIVE 课程而不调用 LLM，或在一次操作中选择课程并升级进入现有 Summary/HITL；纯归类后仍可从 Record 详情稍后升级。该纵切同时修正 NOTE 编辑、无课程 Summary 提示、幂等与失败恢复，因此完成后“先捕获后整理”已形成真实本地数据到 AI 管线的完整闭环，而不是一组互不相连的按钮。

**Blocked by:** 01 — 文本捕获、可选课程导入与真实 Inbox.

**Status:** ready-for-agent

- [ ] 新增受启动令牌保护的归类命令：目标课程必须存在、未软删且为 ACTIVE；首次操作仅接受未归类 NOTE / SUMMARY_PENDING，并返回最新 Record。
- [ ] 归类只写 course_id 与 updated_at，不改变 NOTE/SUMMARY_PENDING、不创建 Summary Job、不产生 learning_events，且 fake Provider 调用次数保持零。
- [ ] 同一 Record 已归到同一课程时重复归类返回当前 Record；已归到其他课程返回 409，不在本票提供重新归类或移动课程。
- [ ] CONTENT_PROCESSING 与 FAILED 不接受归类；不存在、已软删或父课程已删除遵循现有 404 语义，归档课程与状态冲突返回可理解的 409。
- [ ] 新增升级命令并返回最新 Record 与可空 summary_job_id：未归类 Record 必须选择 ACTIVE 课程，已归类 Record 默认复用当前课程，请求不同课程返回 409。
- [ ] NOTE 首次升级原子写入课程并推进到 SUMMARY_PENDING；SUMMARY_PENDING 首次升级保持状态；两者在本地事务提交后才尝试创建 Summary Job。
- [ ] 升级前再次校验 Transcript、ACTIVE 课程、Record 状态与活动 Summary Job；不得建立后台批量扫描待总结 Record 的任务。
- [ ] 已有活动 Summary Job 时重复升级复用原 Job；状态已经推进到 SUMMARY_PROCESSING、SUMMARY_READY 或 COMPLETED 时重复升级返回当前事实，不倒退状态、不创建第二个 Job。
- [ ] Provider 缺失、当前供应商未同意、离线或入队异常不回滚 course_id、Transcript 或 SUMMARY_PENDING；summary_job_id 为空明确表示本地成功、AI 尚未启动。
- [ ] 入队异常写不含正文、凭据或 Authorization 的结构化日志；用户可从 Summary 页继续配置、授权或重试。
- [ ] 编辑 NOTE Transcript 时递增 source_version、更新正文并置 edited_by_user=true，但 Record 保持 NOTE、标题不变、零 Summary 调用；非 NOTE 编辑继续遵循既有 Summary SUPERSEDED 合同。
- [ ] Summary 读取新增准确的 COURSE_REQUIRED 阻塞原因；无课程显示“请先归类并升级”，不得继续复用“课程已归档”。
- [ ] Inbox 的 NOTE/SUMMARY_PENDING 行提供归类、升级、删除；CONTENT_PROCESSING/FAILED 不显示不可执行动作，课程选择器只列 ACTIVE 课程。
- [ ] 纯归类成功后精确失效 Inbox 与目标课程 Record 列表，留在 Inbox、移除该行并显示“已归类到 {课程}”的可访问反馈。
- [ ] Inbox 升级在一次交互中选择课程、归类和触发 Summary，成功后精确失效 Inbox、课程列表、Record 详情与 Summary，并进入对应 Record Summary 页。
- [ ] 无课程 Record 的 Summary 页提供带 ACTIVE 课程选择器的升级入口；已归类 NOTE/SUMMARY_PENDING 的 Summary 页提供不重复选择课程的升级入口，课程列表不复制该按钮。
- [ ] 没有 ACTIVE 课程、课程加载失败、提交中、409、Provider/同意阻塞和本地成功但未入队都显示诚实且可恢复的界面状态，失败不丢失用户选择。
- [ ] Query cache 只用于即时反馈；mutation 完成后必须重读 REST/SQLite 事实，不把 course_id 或 Summary 状态长期保存在第二个 store。
- [ ] sidecar API/真实 SQLite/fake Provider 测试覆盖归类与升级全部状态、同课程幂等、跨课程冲突、删除/归档竞态、NOTE 编辑、零调用与单次调用、活动 Job 复用和本地提交不回滚。
- [ ] 桌面路由级 MSW 测试覆盖 Inbox 行动作、课程选择、归类留页、升级导航、详情升级、COURSE_REQUIRED、NOTE 编辑、缓存失效、错误保留和键盘/焦点行为。
- [ ] 使用真实 localhost socket 完成至少一次“Inbox NOTE → 纯归类零 Job”及一次“Inbox SUMMARY_PENDING → 升级产生一个 Summary Job”的状态检查，并核对 SQLite 最终事实与重启持久化。
- [ ] 自动化 fake Provider 只证明未归类零 Summary 调用与升级单次调用；本票不要求真实外部 LLM，也不把已有 04 ASR 证据升级为新的腾讯验收。
- [ ] Python 测试与静态检查、OpenAPI 生成一致性、桌面测试/lint/build、格式检查和 `git diff --check` 全部通过，并分别报告 API/SQLite、真实 HTTP、组件交互与构建证据。

