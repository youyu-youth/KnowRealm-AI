-- 通用 Agent 第二阶段工单 05：Run 推进触发 job 的 job_type 放开与领取守卫。
-- ① processing_jobs.job_type CHECK 增加 'AGENT_RUN'（Run 推进触发 job：无状态
--    触发器，input_json 仅携带 run_id，不承载任务状态——Run 状态是唯一事实源）。
--    SQLite 不能就地修改 CHECK，照 0009/0010/0016/0017/0026 先例整表重建，
--    存量行原样搬运（列集与 0026 终态一致）。
-- ② 「同一 run 至多一个活动触发 job」由部分唯一索引在存储层保证（0010/0026
--    的 one_active_* 先例）：领取守卫判定之外再留一道纵深防御，防止唤醒路径
--    并发重复投递触发 job。
PRAGMA legacy_alter_table=ON;

ALTER TABLE processing_jobs RENAME TO processing_jobs_v32;

CREATE TABLE processing_jobs (
    id TEXT PRIMARY KEY,
    record_id TEXT REFERENCES records(id) ON DELETE CASCADE,
    library_item_id TEXT REFERENCES library_items(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL CHECK (
        job_type IN (
            'ASR', 'AUDIO_TRANSCODE', 'DOCUMENT_PARSE', 'EMBEDDING',
            'CONCEPT_EXTRACTION', 'SUMMARY', 'KNOWLEDGE_EXTRACTION',
            'QUIZ_GENERATION', 'TODO_GENERATION', 'QUIZ_GRADING',
            'REVIEW_MATERIAL_GENERATION', 'WEB_FETCH', 'LIBRARY_BACKFILL',
            'INDEX_REBUILD', 'CLEANUP', 'BACKUP_EXPORT', 'AGENT_RUN'
        )
    ),
    status TEXT NOT NULL CHECK (
        status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')
    ),
    progress REAL NOT NULL CHECK (progress BETWEEN 0 AND 1),
    attempts INTEGER NOT NULL CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL CHECK (max_attempts > 0),
    next_run_at TEXT,
    input_json TEXT NOT NULL,
    result_json TEXT,
    error_code TEXT,
    error_message TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    waiting_reason TEXT CHECK (
        waiting_reason IS NULL OR waiting_reason IN (
            'CONSENT_REQUIRED', 'ASR_KEY_REQUIRED', 'OFFLINE'
        )
    )
);

INSERT INTO processing_jobs (
    id, record_id, library_item_id, job_type, status, progress, attempts,
    max_attempts, next_run_at, input_json, result_json, error_code, error_message,
    started_at, finished_at, created_at, updated_at, waiting_reason
)
SELECT
    id, record_id, library_item_id, job_type, status, progress, attempts,
    max_attempts, next_run_at, input_json, result_json, error_code, error_message,
    started_at, finished_at, created_at, updated_at, waiting_reason
FROM processing_jobs_v32;

DROP TABLE processing_jobs_v32;

CREATE INDEX idx_processing_jobs_record ON processing_jobs(record_id);
CREATE INDEX idx_processing_jobs_library_item ON processing_jobs(library_item_id);
CREATE INDEX idx_processing_jobs_claim ON processing_jobs(status, next_run_at, created_at);
CREATE UNIQUE INDEX idx_processing_jobs_one_active_summary
    ON processing_jobs(record_id)
    WHERE job_type = 'SUMMARY' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_knowledge_extraction
    ON processing_jobs(record_id)
    WHERE job_type = 'KNOWLEDGE_EXTRACTION' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_quiz_generation
    ON processing_jobs(record_id)
    WHERE job_type = 'QUIZ_GENERATION' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_todo_generation
    ON processing_jobs(record_id)
    WHERE job_type = 'TODO_GENERATION' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_review_material_generation
    ON processing_jobs(record_id)
    WHERE job_type = 'REVIEW_MATERIAL_GENERATION' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_web_fetch
    ON processing_jobs(library_item_id)
    WHERE job_type = 'WEB_FETCH' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_index_rebuild
    ON processing_jobs(library_item_id)
    WHERE job_type = 'INDEX_REBUILD' AND status IN ('PENDING', 'RUNNING');
-- 同 run 至多一个活动触发 job：run_id 在无列承载（只存 input_json），
-- 用表达式索引投影（json_extract 带字面路径为确定性函数，SQLite 3.49 支持）。
CREATE UNIQUE INDEX idx_processing_jobs_one_active_agent_run
    ON processing_jobs(json_extract(input_json, '$.run_id'))
    WHERE job_type = 'AGENT_RUN' AND status IN ('PENDING', 'RUNNING');

PRAGMA legacy_alter_table=OFF;
