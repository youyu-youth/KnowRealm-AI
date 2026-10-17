-- 计划练习轮次：quiz_tests 挂计划项/要求修订/轮次号（mode 新增 PLAN），
-- quiz_test_items 冻结启动时题面与判分依据（frozen_json），原题身份改为
-- 可空 + ON DELETE SET NULL——追溯用，不再是读取题面或阻塞来源清理的强依赖。
PRAGMA legacy_alter_table=ON;

ALTER TABLE quiz_tests RENAME TO quiz_tests_v53;

CREATE TABLE quiz_tests (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id),
    record_id TEXT REFERENCES records(id) CHECK (record_id IS NULL),
    mode TEXT NOT NULL CHECK (mode IN ('MOCK', 'ADAPTIVE', 'PLAN')),
    status TEXT NOT NULL CHECK (
        status IN ('IN_PROGRESS', 'GRADING', 'GRADING_FAILED', 'COMPLETED', 'ABANDONED')
    ),
    score REAL CHECK (score IS NULL OR score BETWEEN 0 AND 1),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    plan_item_id TEXT REFERENCES learning_plan_items(id) ON DELETE CASCADE,
    practice_round_no INTEGER CHECK (practice_round_no IS NULL OR practice_round_no > 0),
    requirements_id TEXT REFERENCES practice_requirements(id) ON DELETE CASCADE,
    request_id TEXT UNIQUE,
    CHECK (
        (mode = 'PLAN') = (
            plan_item_id IS NOT NULL
            AND practice_round_no IS NOT NULL
            AND requirements_id IS NOT NULL
            AND request_id IS NOT NULL
        )
    ),
    UNIQUE (plan_item_id, practice_round_no)
);

INSERT INTO quiz_tests (
    id, course_id, record_id, mode, status, score, started_at, completed_at,
    created_at, updated_at, deleted_at
)
SELECT
    id, course_id, record_id, mode, status, score, started_at, completed_at,
    created_at, updated_at, deleted_at
FROM quiz_tests_v53;

DROP TABLE quiz_tests_v53;

CREATE INDEX idx_quiz_tests_course_created
    ON quiz_tests(course_id, created_at DESC);
CREATE INDEX idx_quiz_tests_plan_item
    ON quiz_tests(plan_item_id, practice_round_no DESC);
-- 每个计划项最多一轮可作答（IN_PROGRESS）；终态后允许下一轮（04 重练）。
CREATE UNIQUE INDEX idx_quiz_tests_one_answerable_round
    ON quiz_tests(plan_item_id)
    WHERE mode = 'PLAN' AND status = 'IN_PROGRESS';

ALTER TABLE quiz_test_items RENAME TO quiz_test_items_v53;

CREATE TABLE quiz_test_items (
    id TEXT PRIMARY KEY,
    test_id TEXT NOT NULL REFERENCES quiz_tests(id) ON DELETE CASCADE,
    quiz_id TEXT REFERENCES quizzes(id) ON DELETE SET NULL,
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0),
    user_answer_json TEXT CHECK (
        user_answer_json IS NULL OR json_valid(user_answer_json)
    ),
    result TEXT CHECK (
        result IS NULL OR result IN ('CORRECT', 'WRONG', 'PARTIAL')
    ),
    score REAL CHECK (score IS NULL OR score BETWEEN 0 AND 1),
    ai_grade_json TEXT CHECK (
        ai_grade_json IS NULL OR json_valid(ai_grade_json)
    ),
    frozen_json TEXT CHECK (frozen_json IS NULL OR json_valid(frozen_json)),
    answered_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    UNIQUE (test_id, sequence_no)
);

INSERT INTO quiz_test_items (
    id, test_id, quiz_id, sequence_no, user_answer_json, result, score,
    ai_grade_json, answered_at, created_at, updated_at, deleted_at
)
SELECT
    id, test_id, quiz_id, sequence_no, user_answer_json, result, score,
    ai_grade_json, answered_at, created_at, updated_at, deleted_at
FROM quiz_test_items_v53;

DROP TABLE quiz_test_items_v53;

PRAGMA legacy_alter_table=OFF;
