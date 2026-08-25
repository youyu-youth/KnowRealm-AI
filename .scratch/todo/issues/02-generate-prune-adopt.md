# 02 — AI 生成候选、修剪与批次生命周期

**What to build:** 总结确认后零参数一键生成待办建议（3~8 条、贴合总结内容）：异步生成成功落库为 DRAFT 候选，用户可逐条修剪（编辑文字、剔除条目）后整批**采纳**或**丢弃**；采纳后候选生效进清单、旧 AI 批次自动置 SUPERSEDED（数据保留可回溯）；总结换代后既有 Todo 照常、在途候选采纳被阻止并引导基于新总结重新生成。（裁决与契约细节见 `.scratch/todo/spec.md`）

**Blocked by:** 01 — 手动 Todo 闭环与页签挂载

**Status:** ready-for-agent

- [ ] `processing_jobs.job_type` 新增 TODO_GENERATION；每 Record 至多一个 PENDING/RUNNING Todo 任务的部分唯一索引；应用工厂提供 Todo 生成模型注入缝（镜像 FakeQuizModel 缝，支持序列输出与阻塞控制）
- [ ] worker 单次结构化生成（无 LangGraph）：prompt 仅课程上下文 + 已确认 Summary、prompt 版本化自 todo_v1 起、90 秒超时、llm_call_logs 埋点且 prompt 与输出不进日志；严格 Pydantic 校验（每条 content 非空带字数上限、总数 3~8）——违规 Job FAILED（LLM_OUTPUT_INVALID）不自动修正；成功单事务落整批 DRAFT 行（batch_id = Job id、绑定 generated_from_summary_id、批内按输出顺序分配 sort_order 追加尾部）
- [ ] worker 领取 / 发布两阶段复核 Summary 仍 CONFIRMED，失效则 CANCELLED；手动重试复用同 Summary 的失败 Job 不新建
- [ ] 生成前置校验（409 不建 Job）：CONFIRMED Summary 存在、课程 ACTIVE、Provider 已配置、外发同意有效；已有活跃 Job 或在途 DRAFT 再生成 409（并发由部分唯一索引兜底）
- [ ] 候选修剪：DRAFT 行可编辑 content、可删除（复用 01 端点，放开 DRAFT 行权限）；DRAFT 项不可勾选 DONE；丢弃整批 DRAFT（软删）回可再生成态
- [ ] 批次采纳（单事务）：前置 = 绑定 Summary 仍 CONFIRMED 且课程 ACTIVE 否则 409 引导丢弃重生成；效果 = 该批 DRAFT→ACTIVE、既有其他 AI **ACTIVE** 批次置 SUPERSEDED（谓词只匹配 ACTIVE 行）；重复采纳幂等返回现状；采纳不发学习事件
- [ ] 换代联动：读端点在 DRAFT 绑定的总结已换代时给 SUMMARY_SUPERSEDED 并引导丢弃重生成；既有 ACTIVE 批次与手工项照常可用；基于当前已确认总结重新生成入口（有 ACTIVE、无 DRAFT、无活跃 Job 时）
- [ ] SUPERSEDED 批次默认隐藏，`?include=superseded` API 可回溯（无 UI 入口）
- [ ] 前端：生成按钮与 blocked 指引、active_job_id 条件轮询进行中态、失败重试态、候选区块（逐条修剪 + 整批采纳 / 丢弃）与主清单共存布局；OpenAPI → api-types 重新生成
- [ ] 后端全栈测试（FakeTodoModel 序列输出测 Schema 违规重试与 FAILED、阻塞控制测防重、409 矩阵：前置缺失 × 活跃 Job × 在途 DRAFT × 换代阻止 × 归档、修剪后整批采纳、旧 ACTIVE 批 SUPERSEDED 而手工项保留、回溯）；前端 MSW 测试（生成流、修剪、采纳丢弃、失败态）
