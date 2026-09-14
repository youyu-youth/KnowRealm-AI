# 02 — B2 前端接线 + 文档收尾：范围胶囊接真 + 课程对话入口 + 引用标题展示

**What to build:** 前端把「课程 / 全部资料」从禁用占位接成真实能力：范围胶囊可交互（点课程 → 选课 Dialog 建会话、点全部资料直接建会话），NewChatButton 增两入口，课程详情「对话」Tab CTA 改为创建该课程范围会话、示意消息流退场；右栏挂载上下文卡、webSearch 默认值、工具卡文案、引用列表标题展示按 scope 适配；api-types 重新生成；文档收尾（数据模型 v2.7、扩展文档 §40 回写、PROJECT_PROGRESS）。

**Blocked by:** 01（后端契约与 openapi 先行）。

**Status:** ready-for-agent

- [ ] api-types 重新生成并消费（scope/course_id/course_deleted/record_title）
- [ ] `ChatScopeChips` 接真：当前会话范围高亮；点「课程」→ 选课 Dialog（复用课程列表数据）→ 创建 COURSE 会话并跳转；点「全部资料」/「自由聊天」→ 直接建会话跳转；范围会话内不可变（spec 根决策 2）
- [ ] `NewChatButton` 菜单增「课程问答」（选课 Dialog）与「全部资料」入口
- [ ] 课程详情 `CourseChatTab`：CTA / 发送改为创建该课程 COURSE 会话并跳 `/chat/$sessionId`；移除示意消息流与 sample 标记（不留过期信息）
- [ ] 右栏「当前挂载上下文」卡按 scope 展示（课程名 + 记录数 / 全部资料 + 记录数 / 单记录现状不变）；webSearch 开关默认值按 scope（COURSE/ALL 同挂载 = 关，记忆逻辑维持）
- [ ] 工具卡 `search_library` 文案分支（「正在检索学习资料」/ 命中 n 条 / 失败）；SSE 分发零改动
- [ ] 引用列表：record 条目显示 `《record_title》` + 摘录，历史行无 title 降级为现状展示；点击跳转零改动（`useOpenCitation` 已按 citation.record_id）
- [ ] 会话行 / 标题栏范围标识（课程名 / 全部资料），自由 / 记录现状不变；zh.json / en.json 同步新增
- [ ] 前端门禁：`pnpm test -- --maxWorkers=4` / `pnpm lint` / 触及文件 Prettier / `pnpm build` 全绿（jsdom：胶囊交互建会话、工具卡文案、引用标题与降级、webSearch 默认值按 scope、zh/en key 一致）
- [ ] 文档收尾：数据模型文档升 v2.7 重命名 + `chat_sessions` scope 列说明 + 全库交叉引用同步；扩展文档 §40.3 B2 行回写「已实施」+ §40.4 第 4 步标记完成；CONTEXT.md 补「会话范围」「跨记录引用」词条；PROJECT_PROGRESS 同步
- [ ] 提交 `feat(desktop): 接线课程与全部资料问答范围（B2 票 02）` 与 `docs: 回写 B2 交付结论`（或按实际拆合）

**用户真机验收（不代勾）：** 胶囊点「课程」选课后问答正常且侧栏出现该会话；课程详情对话 Tab 发问即进课程会话；全部资料会话引用点击逐条跳转对应记录；亮 / 暗两态与 zh/en 切换正常。
