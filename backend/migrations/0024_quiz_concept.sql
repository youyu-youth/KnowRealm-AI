-- Quiz 主概念（Concept Mastery V1 票 01）：一道题至多一个可空主概念，
-- 存量行保持 NULL，不做历史回填；首次作答后由应用层锁定（库级不设不可变约束）。
-- 概念物理删除时归属随之外键置空；CONFIRMED/课程匹配校验在服务端执行。
ALTER TABLE quizzes ADD COLUMN concept_id TEXT REFERENCES concepts(id) ON DELETE SET NULL;

CREATE INDEX idx_quizzes_concept ON quizzes(concept_id);
