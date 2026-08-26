# 02 — 习题 / Todo 单项 Markdown 导出

**What to build:** 在已经可真实保存 Markdown 的导出通道上，让用户从习题或 Todo Tab 导出当前正式内容。习题文件必须完整保持现有作答与防剧透语义，Todo 文件必须反映用户当前实际维护的清单；完成后四种 Wave A 学习资产都能独立导出。

**Blocked by:** 01 — Summary / 知识点单项导出与 Tauri 保存闭环.

**Status:** ready-for-agent

- [ ] 当前 Tab 为习题或 Todo 且存在可导出正式内容时，“导出当前 Tab”可用；每次触发显式读取该资产的最新 localhost API 事实并复用 01 的保存、文件名、错误与打开闭环。
- [ ] 习题只导出当前未删除的 ACTIVE 项，排除 DRAFT 与 SUPERSEDED，并沿用当前 API/UI 顺序，不新增导出专用排序字段。
- [ ] 未作答 ACTIVE 习题只包含题型、题干、难度和按页面顺序排列的选项；文件中不得出现正确答案、解析或可推导答案的内部值。
- [ ] 已作答客观题增加用户答案、本地化结果、正确答案和解析；用户答案与正确答案使用面向人的选项文字，不暴露 JSON 或选项下标。
- [ ] 简答题已提交但尚未自评时包含用户答案、参考答案和解析，并明确标记“待自评”；自评后再显示本地化的正确/错误结果。
- [ ] 习题 Markdown 以 Record 展示标题为一级标题、习题为二级标题，各题按序号分节；相同字段不重复输出，纯文本不会破坏 Markdown 层级。
- [ ] Todo 只导出当前未删除的正式清单：ACTIVE AI 项、手工项和被接管 AI 项；排除 DRAFT 与 SUPERSEDED。
- [ ] Todo 同时保留 TODO 与 DONE，并严格沿用 `sort_order`；TODO 输出标准未勾选任务，DONE 输出标准已勾选任务，不按来源或状态重新分组。
- [ ] Todo Markdown 以 Record 展示标题为一级标题、Todo 为二级标题；content 按纯文本语义转义且不输出 source、batch、Summary 绑定等内部元数据。
- [ ] 单项默认名分别为 `{Record展示标题}-习题.md` 与 `{Record展示标题}-Todo.md`，并完整复用 01 的 Windows 文件名与 `.md` 扩展名规则。
- [ ] 无 ACTIVE 习题或无正式 Todo 时不进入保存流程并显示无可导出内容；接口读取失败不得伪装成空内容。
- [ ] 习题序列化测试覆盖未作答、客观题已作答、简答待自评、简答已自评，以及 DRAFT/SUPERSEDED 过滤和面向人答案展示。
- [ ] Todo 序列化测试覆盖 ACTIVE AI、手工、被接管、TODO、DONE 的混排顺序，并证明 DRAFT/SUPERSEDED 被排除。
- [ ] Record 详情组件测试覆盖习题/Todo 菜单可用性、每次导出重新读取、无内容禁用、保存调用与错误反馈；不断言内部 helper 调用顺序。
- [ ] 现有 Summary/知识点单项导出、Tauri 保存反馈和打开文件行为保持通过；本票不新增后端端点、数据库迁移、OpenAPI schema、依赖或 learning_events。

