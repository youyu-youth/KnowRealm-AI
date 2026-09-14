-- B2 跨记录问答：chat_sessions 显式 scope 列（FREE/RECORD/COURSE/ALL）。
-- 与 mode 轴正交（mode 恒 ASK，交互形态留给 B3）；存量回填：record_id 非空 → RECORD。
ALTER TABLE chat_sessions ADD COLUMN scope TEXT NOT NULL DEFAULT 'FREE'
    CHECK (scope IN ('FREE', 'RECORD', 'COURSE', 'ALL'));

UPDATE chat_sessions SET scope = 'RECORD' WHERE record_id IS NOT NULL;
