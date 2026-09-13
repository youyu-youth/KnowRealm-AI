# 01 — 分片 FTS 索引地基（迁移 0020 + 索引服务 + 写路径挂点 + 回填）

**What to build:** 应用升级后数据库具备分片级检索索引：新增迁移 0020 建 `segment_search_index`（FTS5：entity_type 两值 + entity_id + body 分词串，照 `search_index` 先删后插同事务幂等模式）；索引维护服务归 search 模块（复用 tokenizer 与 upsert 模式），写路径挂点接入分片的全部写入处（finalizer 转写/文档分片、编辑重切、F1 存量回填），启动幂等回填与既有搜索索引回填并列。本票是 02 检索工具的数据地基，不改任何对外行为（/api/search 与分片端点零变化）。

**Spec 参考:** 同目录 `../spec.md`（grill 定稿裁决、测试 seam、Out of Scope；实施前先读，票与 spec 不一致时以 spec 为准）。

**Blocked by:** None — can start immediately.

**Status:** done

- [x] 迁移 0020 建 `segment_search_index` FTS5 虚拟表（entity_type ∈ {transcript_segment, document_segment} / entity_id / body），与 `search_index` 分表不复用；全量 user_version 断言同步（19→20），导入归档版本上限经动态函数自动生效
- [x] search 模块新增分片索引维护服务：按分片 id 的 upsert（jieba tokenize 走线程池）与删除，查询接口 = MATCH 命中 → 回表分片业务表（逐字 content + 时间戳/页码 + sequence_no），限定挂载 record_id、transcript 未软删、文档分片按 record 挂靠路径过滤
- [x] 写路径挂点（全部同事务）：finalizer 建转写分片与文档分片后、编辑重切（realign，物理删除行同事务清索引行）后、F1 存量回填建分片后
- [x] 启动幂等回填：main.py 与搜索索引回填、分片回填并列，同容错级（失败记日志不阻断启动）
- [x] 测试（test_search.py 模式）：同事务 upsert 幂等、编辑重切索引同步（保留句命中 / 删除行清理）、查询期回表过滤软删与失效 transcript、回填幂等（重复启动零副作用）；全套门禁绿（pytest --basetemp / ruff / pyright strict）

**交付注记（2026-09-13）：**
- 落点：`backend/migrations/0020_segment_search_index.sql`；`backend/app/modules/search/segment_service.py`（`SegmentSearchService`，查询命中结构 `SegmentSearchHit` 在 `search/schemas.py`）；写路径挂点在 `transcript/finalizer.py` 两处 + `transcript/segments.py` `realign_for_edit` 与 `SegmentService.backfill_missing`；`app/main.py` 启动回填第三挂位。
- user_version 断言同步 11 处（0019 后从 6 处增长，test_chat_sessions/courses/records/todos/quiz_tests/quizzes/document_import/knowledge_points/source_anchors/review_materials/summary）。
- code-review 两轴通过（无硬违规、无 spec 缺失）；已采纳修复：entity_type 参数收紧为 `SegmentEntityType` Literal、removed_ids 的 set 提出循环。
- 门禁：pytest 全量 430 绿（--basetemp）、ruff 全绿、pyright strict 0 错误；新增 `tests/test_segment_search.py` 7 项（迁移断言 / upsert 幂等+逐字命中 / 文档 page_no / record 作用域+软删查询期过滤+恢复即恢复 / 编辑重切索引同步 / 文档导入 finalizer 端到端 / 回填幂等）。
- 查询接口 `SegmentSearchService.search_segments(session, record_id, query, limit)` 供票 02 的 `search_transcript` 工具调用（chat→search 单向依赖）。
