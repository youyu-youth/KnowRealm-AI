# 01 — 课程中可查看真实 Records

**What to build:** 用户进入一个未删除课程的 Records 页签时，能够从真实本地数据库看到该课程的 Record 列表；没有 Record 时看到诚实空态，加载失败时可以重试。这个切片同时建立 Record 的最小持久化合同，并保证删除课程时不会留下仍可见的 Record。

**Blocked by:** None

**Status:** ready-for-agent

- [ ] 新数据库和现有数据库升级后都具有 `records` 表；字段、八种状态约束、非负时长约束、可空 `course_id` 外键、软删除字段、课程与创建时间索引均符合功能 spec，且 `status` 不提供数据库默认值。
- [ ] Record 所属课程被最终物理删除时，数据库外键级联删除其 Record 行；Record 不属于课程时允许 `course_id` 为 `NULL`。
- [ ] 软删除课程与其未删除 Record 在同一事务中写入删除时间；任一步失败时整个操作回滚，现有 Course 删除行为不回归。
- [ ] `GET /api/courses/{course_id}/records` 受启动令牌保护；课程不存在或已软删除返回 404，存在且无 Record 返回 `[]`。
- [ ] 列表只返回未软删除且父课程未软删除的 Record，按 `created_at` 降序排列，并使用统一 Record 输出合同且不暴露 `deleted_at`。
- [ ] OpenAPI JSON 与 TypeScript 声明由现有生成链路更新；生成文件固定为 LF，在 Windows `core.autocrlf=true` 下重复执行检查不会产生假漂移。
- [ ] 课程详情的 Records 页签使用真实查询而非生产 mock，完整呈现加载、失败、重试、空列表和有数据列表状态。
- [ ] 每个列表项显示标题、采集类型、状态、创建时间和时长；空白标题使用统一回退文案，缺失时长不伪造数值。
- [ ] 八种状态按产品文案显示：`NOTE`“仅保存”、`DRAFT`“草稿”、`CONTENT_PROCESSING`“内容处理中”、`SUMMARY_PENDING`“等待生成总结”、`SUMMARY_PROCESSING`“总结生成中”、`SUMMARY_READY`“总结待确认”、`COMPLETED`“已完成”、`FAILED`“处理失败”。
- [ ] 产品代码不增加 Record 创建、编辑、测试种子、后台任务、轮询、SSE 或资产可用性接口。
- [ ] 数据库/API 测试覆盖迁移、约束、排序、软删除过滤、课程 404、课程级联软删除和事务回滚；前端测试覆盖加载、错误重试、空态、列表字段与状态文案。
- [ ] 集成验证只在 sidecar 启动前向临时 SQLite 写入测试 Record，再通过真实随机 localhost 端口和启动令牌读取；该方法不得被描述为录音或导入链路端到端证明。
- [ ] 验收记录分别标明静态检查、自动化测试、真实 HTTP、桌面 Network 与渲染证据，以及尚未验证的生产采集链路。
