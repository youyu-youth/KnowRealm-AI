# 01 — B2 跨记录 / 课程级问答全栈闭环：scope 契约 + search_library + 跨记录引用 + 范围接真

**What to build:** chat 会话获得四档范围（FREE/RECORD/COURSE/ALL）的**前后端完整闭环**：后端加显式 `scope` 列（迁移 0022）并启用 `course_id` 写入，课程/全部范围会话挂载新工具 `search_library`（跨记录分片 FTS + LIKE 兜底），上下文喂记录标题清单 + 检索指引，回答引用升级为跨记录契约（`[n] 摘录（来源：记录标题）`，校验器裁定归属并落 `record_title` 快照），web_search 对 COURSE/ALL 按挂载语义联动；前端把「课程 / 全部资料」从禁用占位接成真实能力（范围胶囊、选课入口、课程详情对话 Tab、引用与工具卡适配）；文档收尾（数据模型 v2.7、扩展文档 §40 回写）。记录范围会话行为零变更。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

**后端（契约与数据层）**

- [ ] 迁移 0022：`chat_sessions` 加 `scope TEXT NOT NULL DEFAULT 'FREE'` + CHECK 四值，存量回填（record_id 非空 → RECORD）；`user_version` 断言全库 grep 同步
- [ ] `ChatScope` StrEnum（FREE/RECORD/COURSE/ALL）；`ChatSessionCreate` 增 `scope`（不传时按 record_id 派生，旧调用方零破坏）与 `course_id`；校验矩阵：RECORD 必带 record_id、COURSE 必带 course_id 且课程存活未归档（404 CHAT_COURSE_NOT_FOUND / 409 CHAT_COURSE_ARCHIVED，登记错误码清单）、FREE/ALL 拒绝携带 id、knowledge_point_id 仍限 RECORD
- [ ] `ChatSessionOut` 增 `scope`、`course_deleted`；`course_id` 语义启用（COURSE=挂载课程，RECORD 维持运行时派生）；课程软删 → 会话只读、accept 拒绝 409（对齐 record_deleted 先例）
- [ ] `SegmentSearchService.search_scope_segments(session, course_id | None, query, limit)`：跨记录两条 SQL（JOIN records 取 title、record/transcript 软删过滤照旧、course 条件可空），top-8 BM25，命中载荷带 record_id/record_title/content/time|page

**后端（agent 域）**

- [ ] `search_library(query)` @tool + `LibrarySearchContext` ContextVar（每轮生成前绑定，模式同 search_transcript）；FTS 零命中才 LIKE 兜底（整 query 子串、窗 ≤400 字、范围过滤同上）；与 `search_transcript` 互斥挂载
- [ ] `context.py` 增 `library` 材料分支（与 record 互斥）：挂载指令 + 跨记录引用格式约定 + 记录标题清单（标题+日期+无转写标注，updated_at 降序，约 4000 字符预算超出取最近并注明）+ 检索指引
- [ ] 跨记录引用解析：行内 URL → web 条目照旧；「（来源：标题）」→ 标题等值定位（重名逐一逐字验证取首过）→ 无候选全范围逐字扫描兜底（禁止全范围模糊对齐）→ 逐字不过仅在标题定位记录内 `_align_quote`；全失败丢弃；单记录入口（RECORD 会话）零改动
- [ ] `ChatCitationOut` 增可选 `record_title`；落库条目带 title 快照（历史行无键 → None）；SSE done 载荷 citations 同构
- [ ] 装配矩阵扩为 scope（FREE/RECORD/COURSE|ALL）× web_search；COURSE/ALL web_search 生效时追加「材料优先」指引；`CHAT_PROMPT_VERSION` bump v5
- [ ] RECORD 会话回归：上下文组装、>30k 降级、search_transcript、引用解析与现状逐字一致

**前端（接线）**

- [ ] api-types 重新生成并消费（scope/course_id/course_deleted/record_title）
- [ ] `ChatScopeChips` 接真：当前会话范围高亮；点「课程」→ 选课 Dialog（复用课程列表数据）→ 创建 COURSE 会话并跳转；点「全部资料」/「自由聊天」→ 直接建会话跳转；范围会话内不可变（spec 根决策 2）
- [ ] `NewChatButton` 菜单增「课程问答」（选课 Dialog）与「全部资料」入口
- [ ] 课程详情 `CourseChatTab`：CTA / 发送改为创建该课程 COURSE 会话并跳 `/chat/$sessionId`；移除示意消息流与 sample 标记（不留过期信息）
- [ ] 右栏「当前挂载上下文」卡按 scope 展示（课程名 + 记录数 / 全部资料 + 记录数 / 单记录现状不变）；webSearch 开关默认值按 scope（COURSE/ALL 同挂载 = 关，记忆逻辑维持）
- [ ] 工具卡 `search_library` 文案分支（「正在检索学习资料」/ 命中 n 条 / 失败）；SSE 分发零改动
- [ ] 引用列表：record 条目显示 `《record_title》` + 摘录，历史行无 title 降级为现状展示；点击跳转零改动（`useOpenCitation` 已按 citation.record_id）
- [ ] 会话行 / 标题栏范围标识（课程名 / 全部资料），自由 / 记录现状不变；zh.json / en.json 同步新增

**门禁与文档**

- [ ] 后端测试全过（streaming seam 装配矩阵与清单注入、citations 纯函数跨记录矩阵、SegmentSearchService 跨记录查询、会话端点校验矩阵与 course_deleted 只读）；pytest（--basetemp=.pytest-tmp）/ ruff / pyright 全绿；openapi 重新 generate 并随票提交
- [ ] 前端门禁：`pnpm test -- --maxWorkers=4` / `pnpm lint` / 触及文件 Prettier / `pnpm build` 全绿（jsdom：胶囊交互建会话、工具卡文案、引用标题与降级、webSearch 默认值按 scope、zh/en key 一致）
- [ ] 文档收尾：数据模型文档升 v2.7 重命名 + `chat_sessions` scope 列说明 + 全库交叉引用同步；扩展文档 §40.3 B2 行回写「已实施」+ §40.4 第 4 步标记完成；CONTEXT.md 补「会话范围」「跨记录引用」词条；PROJECT_PROGRESS 同步
- [ ] 提交按域分次（type(scope) 规范不变），如 `feat(backend): 实现跨记录问答范围与检索工具（B2）` + `feat(desktop): 接线课程与全部资料问答范围（B2）` + `docs: 回写 B2 交付结论`

**用户真机验收（不代勾）：** 真实课程（多条含转写记录）建课程会话问跨记录对比题，命中检索卡、回答带多记录引用且逐条可跳转；空课程 / 空库如实告知；胶囊点「课程」选课后问答正常且侧栏出现该会话；课程详情对话 Tab 发问即进课程会话；全部资料会话引用点击逐条跳转对应记录；亮 / 暗两态与 zh/en 切换正常。
