# 01 — B2 后端全链：scope 契约 + search_library 工具 + 跨记录引用 + 迁移 0022

**What to build:** chat 会话获得四档范围（FREE/RECORD/COURSE/ALL）：迁移 0022 给 `chat_sessions` 加显式 `scope` 列并启用 `course_id` 写入；课程/全部范围会话挂载新工具 `search_library`（跨记录分片 FTS + LIKE 兜底），上下文喂记录标题清单 + 检索指引；回答引用升级为跨记录契约（`[n] 摘录（来源：记录标题）`，校验器裁定归属并落 `record_title` 快照）；web_search 对 COURSE/ALL 按挂载语义联动。记录范围会话行为零变更。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] 迁移 0022：`chat_sessions` 加 `scope TEXT NOT NULL DEFAULT 'FREE'` + CHECK 四值，存量回填（record_id 非空 → RECORD）；`user_version` 断言全库 grep 同步
- [ ] `ChatScope` StrEnum（FREE/RECORD/COURSE/ALL）；`ChatSessionCreate` 增 `scope`（不传时按 record_id 派生，旧调用方零破坏）与 `course_id`；校验矩阵：RECORD 必带 record_id、COURSE 必带 course_id 且课程存活未归档（404 CHAT_COURSE_NOT_FOUND / 409 CHAT_COURSE_ARCHIVED，登记错误码清单）、FREE/ALL 拒绝携带 id、knowledge_point_id 仍限 RECORD
- [ ] `ChatSessionOut` 增 `scope`、`course_deleted`；`course_id` 语义启用（COURSE=挂载课程，RECORD 维持运行时派生）；课程软删 → 会话只读、accept 拒绝 409（对齐 record_deleted 先例）
- [ ] `SegmentSearchService.search_scope_segments(session, course_id | None, query, limit)`：跨记录两条 SQL（JOIN records 取 title、record/transcript 软删过滤照旧、course 条件可空），top-8 BM25，命中载荷带 record_id/record_title/content/time|page
- [ ] `search_library(query)` @tool + `LibrarySearchContext` ContextVar（每轮生成前绑定，模式同 search_transcript）；FTS 零命中才 LIKE 兜底（整 query 子串、窗 ≤400 字、范围过滤同上）；与 `search_transcript` 互斥挂载
- [ ] `context.py` 增 `library` 材料分支（与 record 互斥）：挂载指令 + 跨记录引用格式约定 + 记录标题清单（标题+日期+无转写标注，updated_at 降序，约 4000 字符预算超出取最近并注明）+ 检索指引
- [ ] 跨记录引用解析：行内 URL → web 条目照旧；「（来源：标题）」→ 标题等值定位（重名逐一逐字验证取首过）→ 无候选全范围逐字扫描兜底（禁止全范围模糊对齐）→ 逐字不过仅在标题定位记录内 `_align_quote`；全失败丢弃；单记录入口（RECORD 会话）零改动
- [ ] `ChatCitationOut` 增可选 `record_title`；落库条目带 title 快照（历史行无键 → None）；SSE done 载荷 citations 同构
- [ ] 装配矩阵扩为 scope（FREE/RECORD/COURSE|ALL）× web_search；COURSE/ALL web_search 生效时追加「材料优先」指引；`CHAT_PROMPT_VERSION` bump v5
- [ ] RECORD 会话回归：上下文组装、>30k 降级、search_transcript、引用解析与现状逐字一致
- [ ] 测试全过（streaming seam 装配矩阵与清单注入、citations 纯函数跨记录矩阵、SegmentSearchService 跨记录查询、会话端点校验矩阵与 course_deleted 只读）
- [ ] 门禁：pytest（--basetemp=.pytest-tmp）/ ruff / pyright 全绿；openapi 重新 generate 并随票提交
- [ ] 提交 `feat(backend): 实现跨记录问答范围与检索工具（B2 票 01）`

**用户真机验收（不代勾）：** 真实课程（多条含转写记录）建课程会话问跨记录对比题，命中检索卡、回答带多记录引用且逐条可跳转；空课程 / 空库如实告知。
