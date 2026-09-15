# CB-02 — 数据模型与迁移 0023：三张 Concept 表 + CONCEPT 锚点链接值域

**What to build:** `backend/migrations/0023_course_brain.sql` 新建 concepts / concept_relations / record_concepts（列口径见 spec 数据合同，对齐数据模型 v2.7 §4.6）；`source_anchor_links.resource_type` CHECK 扩 `'CONCEPT'`（rename→重建→拷贝→drop，参照 0017 `PRAGMA legacy_alter_table` 包裹惯例）；同步 ORM 与枚举。

**Blocked by:** CB-00（done）。

**Status:** done

**后端**

- [x] 迁移 0023：三表 DDL（外键 CASCADE、CHECK 状态枚举、`UNIQUE INDEX idx_concepts_course_confirmed ON concepts(course_id, normalized_name) WHERE status='CONFIRMED'`、record_concepts UNIQUE(record_id, concept_id)、relations CHECK source≠target）
- [x] source_anchor_links 值域重建：+CONCEPT，数据逐行拷贝，FK 与 UNIQUE 约束等价保留
- [x] `app/modules/course_brain/` 模块骨架（models.py：Concept/ConceptRelation/RecordConcept ORM，2.0 Mapped 风格，ISODateTime 惯例）+ `__init__.py` docstring；source_anchor 的 ResourceType Literal +CONCEPT
- [x] **13 处硬编码 user_version=22 断言 → 23**（test_records/test_summary/test_document_import/test_quizzes/test_knowledge_points/test_review_materials/test_chat_sessions/test_quiz_tests/test_todos/test_source_anchors/test_segment_search/test_learning/test_courses）
- [x] 迁移测试 `tests/test_course_brain.py`：`assert_course_brain_schema`（PRAGMA table_info/foreign_key_list/index_list 全断言）+ 回滚式升级测试（手工执行 migrations[:-1] 再 run_migrations，双库对照，对齐 test_source_anchors 动态惯例）+ source_anchor_links 重建后既有行完好断言

**门禁**

- [x] uv run pytest --basetemp=.pytest-tmp 全绿（.pytest-tmp 测后删除）/ ruff check + format --check / pyright strict / openapi --check 零 diff
- [x] 提交：`feat(backend): 新增 Course Brain 三表迁移与 CONCEPT 锚点链接值域（F4 CB-02）`
