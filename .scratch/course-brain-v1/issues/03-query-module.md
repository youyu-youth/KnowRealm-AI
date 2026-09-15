# CB-03 — Course Brain 查询模块：snapshot / search / concept_sources（零 LLM）

**What to build:** `course_brain/service.py` 查询三件套 + 手动创建 + REST 路由。此阶段不依赖 LLM：手动创建的 Concept 即可被统一查询模块读取（阶段目标）。状态机 EMPTY/BUILDING/REVIEW/READY/STALE/FAILED 派生逻辑在此实现。

**Blocked by:** CB-02。

**Status:** done

**后端**

- [x] `CourseBrainService`：`get_snapshot(course_id)`（六态派生：无 job 无概念=EMPTY；RUNNING job=BUILDING；有候选=REVIEW；指纹不一致=STALE；上次 job FAILED 且无正式概念=FAILED；否则 READY——指纹=各来源表 (count, max_updated_at) 聚合，与最近一次成功 CONCEPT_EXTRACTION job 的 result_json.fingerprint 比对，查询时派生零后台任务）/ `search(course_id, query, limit=8)`（只查 CONFIRMED，Concept FTS + Segment 并跑合并去重，返回 matched_concepts/occurrences/related_concepts，数量与长度上限）/ `get_concept_sources(concept_id)`（anchors + KP 桥 + chat 回溯派生）
- [x] 手动创建：`create_concept(course_id, name, description?, ...)` 直接 CONFIRMED（source=USER_CONFIRMED），归一化撞名 409
- [x] 路由 `routes.py`：GET /courses/{id}/brain、GET /brain/concepts、GET /brain/concepts/{cid}、GET /brain/concepts/{cid}/sources、POST /brain/concepts；ARCHIVED 课程 409、跨课程 404、课程软删 404（对齐既有闸门惯例）
- [x] Concept FTS 写路径：concepts 增删改同事务 upsert `segment_search_index(entity_type='CONCEPT', body=canonical_name+description)`（复用 search 模块 30k 限长约定）
- [x] schemas.py：XxxOut 全套 + 快照 Schema；错误码新增按需（COURSE_BRAIN_* 前缀，进错误码清单）
- [x] 测试：快照六态派生、CONFIRMED-only 泄漏检查（候选/归档/跨课程/软删记录不出现）、来源三类（anchor/KP/chat）、手动创建撞名 409、长度与数量上限

**门禁**

- [x] 后端四门禁全绿；openapi 重导出（`pnpm --filter @knowrealm/api-types generate` 或后端导出 --check 前先 regenerate）
- [x] 提交：`feat(backend): 实现 Course Brain 查询模块与手动创建（F4 CB-03）`
