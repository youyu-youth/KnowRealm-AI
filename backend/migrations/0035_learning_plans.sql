-- 学习计划与计划项（通用 Agent 第三阶段工单 02，spec 里程碑一）：计划挂学习目标，
-- (goal_id, plan_version) 唯一；同一目标同时至多一个 ACTIVE 计划（部分唯一索引，
-- 0010/0026/0033/0034 先例）。计划项四类动作，按日排期（无时段）；完成 / 跳过
-- 语义与重生成（新版本 + SUPERSEDED + user_locked 保留）随后续工单 03 启用，
-- 本迁移值域一步到位。phase_title 承载草案的阶段划分（LLM 分组标签，计划 Tab
-- 按阶段分组呈现）；STUDY_RECORD 目标对象经 record_id 关联（软删不级联、物理
-- 删除置空降级为自由任务），REVIEW_CONCEPT 经 concept_id 关联（物理删除置空）。
CREATE TABLE learning_plans (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES learning_goals(id) ON DELETE CASCADE,
    plan_version INTEGER NOT NULL CHECK (plan_version > 0),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (
        status IN ('ACTIVE', 'SUPERSEDED', 'COMPLETED')
    ),
    -- 生效区间（按日）：确认落库日 = effective_from；换代 / 完结时写 effective_to。
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (goal_id, plan_version)
);

CREATE INDEX idx_learning_plans_goal ON learning_plans(goal_id);
CREATE UNIQUE INDEX idx_learning_plans_one_active
    ON learning_plans(goal_id)
    WHERE status = 'ACTIVE';

CREATE TABLE learning_plan_items (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES learning_plans(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL CHECK (
        action_type IN ('STUDY_RECORD', 'PRACTICE_QUIZ', 'REVIEW_CONCEPT', 'CUSTOM')
    ),
    content TEXT NOT NULL,
    record_id TEXT REFERENCES records(id) ON DELETE SET NULL,
    concept_id TEXT REFERENCES concepts(id) ON DELETE SET NULL,
    phase_title TEXT NOT NULL,
    priority INTEGER NOT NULL,
    estimated_minutes INTEGER CHECK (estimated_minutes IS NULL OR estimated_minutes > 0),
    scheduled_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'DONE', 'SKIPPED')),
    user_locked INTEGER NOT NULL DEFAULT 0 CHECK (user_locked IN (0, 1)),
    reason_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_learning_plan_items_plan ON learning_plan_items(plan_id);
CREATE INDEX idx_learning_plan_items_scheduled_date ON learning_plan_items(scheduled_date);
