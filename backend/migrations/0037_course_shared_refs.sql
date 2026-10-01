-- 共享来源引用（通用 Agent 第三阶段工单 05，spec 用户故事 20~25）：course ↔
-- library_item 多对多，资料保归属被多空间复用、不重复入库。失效为查询期派生
-- （条目软删即失效、恢复即复活，不设失效状态字段）；条目物理删除经 FK
-- CASCADE 级联清理引用行；归属迁移只改 library_items.course_id，不触引用表
-- （引用是两个空间的直接关系，spec 决策：归属与引用解耦）。
CREATE TABLE course_shared_refs (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    library_item_id TEXT NOT NULL REFERENCES library_items(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    UNIQUE (course_id, library_item_id)
);

CREATE INDEX idx_course_shared_refs_item ON course_shared_refs(library_item_id);
