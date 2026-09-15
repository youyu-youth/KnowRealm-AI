# CB-07 — B2 search_library 检索增强 + Chat Prompt v6

**What to build:** `search_library` 内部接入 `CourseBrainService.search`：Concept 命中→检索词扩展（原查询+canonical_name 并跑）→Segment 逐字引用→occurrences 按 Record 去重。挂载条件不变（RECORD/FREE 不受影响）。CHAT_PROMPT_VERSION v5→v6。

**Blocked by:** CB-06。

**Status:** todo

**后端（agent 域）**

- [ ] `search_library` 增强：原查询先跑 Concept FTS（top 4，CONFIRMED-only，ALL 会话每概念只在归属课程内扩展、不跨课程混入）→ 命中概念集与原查询并跑 SegmentSearchService（每词 top 8）→ 合并去重（record_id+quote）→ occurrences 按 record 去重计数
- [ ] 返回结构向后兼容扩展：`{"hits": [...], "concepts": [...], "occurrences": [...]}`（前端工具卡只吃 hits 不受影响；CourseBrainSearchResult 合同见 spec）
- [ ] 无构建/零命中的课程自然退化为现行行为（LIKE 兜底照旧）
- [ ] `CHAT_PROMPT_VERSION = "chat-concept-v6"`（graph.py）+ prompt 新纪律（context.py _library_instructions）：优先用已确认 Concept 理解问题；Concept 描述不得冒充原文引用（引用必须逐字来自检索结果）；"讲过几次 X"按 occurrences 去重 Record 计数、禁止模型主观估算
- [ ] 测试：COURSE 会话概念增强生效、RECORD 会话零影响、ALL 不跨课程混入、候选概念不进 Agent 上下文（CONFIRMED-only）、引用仍过现有校验器（逐字+≤80 字）、无 brain 课程退化路径

**门禁**

- [ ] 后端四门禁全绿 + openapi 零 diff（工具返回非 OpenAPI 面）；提交：`feat(agent): search_library 接入 Concept 检索增强并升 prompt v6（F4 CB-07）`
