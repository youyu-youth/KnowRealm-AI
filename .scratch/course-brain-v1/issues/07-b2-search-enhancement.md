# CB-07 — B2 search_library 检索增强 + Chat Prompt v6

**What to build:** `search_library` 内部接入 `CourseBrainService.search`：Concept 命中→检索词扩展（原查询+canonical_name 并跑）→Segment 逐字引用→occurrences 按 Record 去重。挂载条件不变（RECORD/FREE 不受影响）。CHAT_PROMPT_VERSION v5→v6。

**Blocked by:** CB-06。

**Status:** done（2026-09-15，后端 546 测试绿 + ruff/format/pyright/openapi check 全绿）

**后端（agent 域）**

- [x] `search_library` 增强：原查询先跑 Concept FTS（top 4，CONFIRMED-only，ALL 会话每概念只在归属课程内扩展、不跨课程混入）→ 命中概念集与原查询并跑 SegmentSearchService（每词 top 8）→ 合并去重（record_id+quote）→ occurrences 按 record 去重计数
  - 实施备注：工单字面「接入 CourseBrainService.search」落地为新增 `CourseBrainService.match_concepts(course_id 可空, 返回含归属 course_id)`——search 的课程内签名装不下 ALL 范围语义（每概念按归属课程扩展），search 改为复用 match_concepts 消除重复；去重 key=(record_id, content)（content 即逐字原文，比 (record_id, quote) 口径更严不并错）；原查询 top 8（SEARCH_LIBRARY_LIMIT）+ 扩展词各 top 8（_EXPANSION_PER_TERM_LIMIT），hits 合并后截 8 回喂、occurrences 来自截断前 merged（每 record 取首个命中代表，quote 截 80 字）
- [x] 返回结构向后兼容扩展：`{"hits": [...], "concepts": [...], "occurrences": [...]}`（前端工具卡只吃 hits 不受影响；CourseBrainSearchResult 合同见 spec）
  - 实施备注：concepts 元素={concept_id, canonical_name, description, record_count, occurrence_count}（多带 description 供 prompt「用概念理解问题」；BrainSearchConceptOut 加必填 course_id 供工具编排，无路由引用零 openapi diff）；SSE tool_result 摘要 {tool, hits, ok} 未动；LIKE 兜底路径也带 concepts（概念命中但分片零命中时不丢术语上下文）
- [x] 无构建/零命中的课程自然退化为现行行为（LIKE 兜底照旧）
- [x] `CHAT_PROMPT_VERSION = "chat-concept-v6"`（graph.py）+ prompt 新纪律（context.py _library_instructions）：优先用已确认 Concept 理解问题；Concept 描述不得冒充原文引用（引用必须逐字来自检索结果）；"讲过几次 X"按 occurrences 去重 Record 计数、禁止模型主观估算
- [x] 测试：COURSE 会话概念增强生效、RECORD 会话零影响、ALL 不跨课程混入、候选概念不进 Agent 上下文（CONFIRMED-only）、引用仍过现有校验器（逐字+≤80 字）、无 brain 课程退化路径
  - 实施备注：新增 4 直调测试（ainvoke 绑 ContextVar：COURSE 扩展生效/ALL 归属课程扩展+原查询全库/CANDIDATE 直插索引行仍被 SQL 排除/无概念 LIKE 兜底退化）；「RECORD 零影响」由既有挂载矩阵测试、「引用校验」由既有跨记录引用流测试回归覆盖（prompt_version 断言 v5→v6 同步一处）

**门禁**

- [x] 后端四门禁全绿 + openapi 零 diff（工具返回非 OpenAPI 面）；提交：`feat(agent): search_library 接入 Concept 检索增强并升 prompt v6（F4 CB-07）`

**已知口径（供后续观察，非阻塞）**

- hits 截 8 且原查询命中在前：概念扩展命中可能进不了 hits 但必进 occurrences（截断前 merged）；「讲过几次」按 occurrences 计数不受 hits 截断影响。
- occurrences 计数是检索面口径（5 词×top8 合并），与 concepts.occurrence_count 的 DB 全量口径并存；prompt 纪律已绑定「按 occurrences 计数」，模型混用风险留真机观察。
