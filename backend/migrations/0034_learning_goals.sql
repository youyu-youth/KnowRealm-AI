-- 学习目标（通用 Agent 第三阶段工单 01，spec 里程碑一）：目标挂单个知识空间。
-- 对数据模型 v3.1 P6 原设计的显式修正：新增 course_id 必填外键（原设计为全局
-- learner 视角无归属）；本期不含 exam_scope_json（票面字段集）。
-- 单空间单 ACTIVE 由部分唯一索引在存储层保证（0010/0026/0033 先例，SQLite
-- 3.9+ 支持部分索引）；跨空间目标不受限。
-- 课程软删后目标随空间不可见（查询期 JOIN 过滤，不写级联）；恢复课程即恢复
-- （与 Record 同模式）。课程物理删除经 FK CASCADE 清目标。
CREATE TABLE learning_goals (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    goal_type TEXT NOT NULL CHECK (
        goal_type IN ('SKILL', 'EXAM', 'PROJECT', 'READING', 'CUSTOM')
    ),
    title TEXT NOT NULL,
    target_date TEXT,
    daily_minutes INTEGER CHECK (daily_minutes IS NULL OR daily_minutes > 0),
    target_score REAL,
    scope_source TEXT NOT NULL CHECK (
        scope_source IN ('USER_CONFIRMED', 'COURSE_SELECTION', 'AI_INFERRED')
    ),
    scope_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (scope_confirmed IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (
        status IN ('ACTIVE', 'COMPLETED', 'ARCHIVED')
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_learning_goals_course ON learning_goals(course_id);
CREATE UNIQUE INDEX idx_learning_goals_one_active
    ON learning_goals(course_id)
    WHERE status = 'ACTIVE';
