-- 新轮绑定准备身份；重试请求身份在任务中持久去重。
ALTER TABLE quiz_tests ADD COLUMN preparation_id TEXT
    REFERENCES practice_preparations(id);
CREATE UNIQUE INDEX idx_quiz_tests_preparation ON quiz_tests(preparation_id)
    WHERE preparation_id IS NOT NULL;
CREATE TABLE practice_grading_requests (
    request_id TEXT PRIMARY KEY,
    test_id TEXT NOT NULL REFERENCES quiz_tests(id) ON DELETE CASCADE,
    job_id TEXT REFERENCES processing_jobs(id) ON DELETE CASCADE
);
CREATE TABLE practice_round_requests (
    request_id TEXT PRIMARY KEY,
    test_id TEXT NOT NULL REFERENCES quiz_tests(id) ON DELETE CASCADE,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
);
