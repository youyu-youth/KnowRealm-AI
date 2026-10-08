-- ChatTurn（切换会话不中断任务，票 01）：一条用户输入对应的一次回答生成。
-- 提交 / 观察 / 控制三分离：受理原子落库（user 消息 + 轮次 + job 同事务），
-- 执行由 CHAT_TURN worker 独立推进，观察走持久事件游标。
-- 前置：processing_jobs.job_type 放开 CHAT_TURN（SQLite 不能就地改 CHECK，
-- 照 0039 先例整表重建，存量行原样搬运，列集与 0039 终态一致）。
PRAGMA legacy_alter_table=ON;

ALTER TABLE processing_jobs RENAME TO processing_jobs_v41;

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
            'INDEX_REBUILD', 'CLEANUP', 'BACKUP_EXPORT', 'AGENT_RUN',
            'PLAN_DRAFT', 'CHAT_TURN'
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
FROM processing_jobs_v41;

DROP TABLE processing_jobs_v41;

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
CREATE UNIQUE INDEX idx_processing_jobs_one_active_agent_run
    ON processing_jobs(json_extract(input_json, '$.run_id'))
    WHERE job_type = 'AGENT_RUN' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_plan_draft
    ON processing_jobs(json_extract(input_json, '$.goal_id'))
    WHERE job_type = 'PLAN_DRAFT' AND status IN ('PENDING', 'RUNNING');

PRAGMA legacy_alter_table=OFF;

CREATE TABLE chat_turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_message_id TEXT NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    -- 客户端一次提交生成的稳定受理身份；网络重试保留。全局唯一。
    request_id TEXT NOT NULL,
    -- 客户端原请求（内容/联网/页面/授权档）的规范化指纹；与执行快照分离，
    -- 全局配置变化不影响指纹判定。
    request_fingerprint TEXT NOT NULL,
    -- 状态机见规格 §6；WAITING_USER/WAITING_JOB 由后续票写入，CHECK 先行铺满。
    status TEXT NOT NULL CHECK (status IN (
        'QUEUED', 'RUNNING', 'WAITING_USER', 'WAITING_JOB',
        'INTERRUPTED', 'COMPLETED', 'FAILED', 'CANCELLED'
    )),
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
    -- 受理时解析的执行快照（联网标志 / 记忆注入许可 / 授权档 / 时区 / 页面快照）；
    -- 不含凭据。
    execution_json TEXT NOT NULL DEFAULT '{}',
    -- 领取身份（执行槽条件更新持有）；终局写入按它防迟到旧执行。
    claim_token TEXT,
    attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    output_revision INTEGER NOT NULL DEFAULT 1 CHECK (output_revision >= 1),
    last_seq INTEGER NOT NULL DEFAULT 0 CHECK (last_seq >= 0),
    final_message_id TEXT REFERENCES chat_messages(id) ON DELETE SET NULL,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE UNIQUE INDEX idx_chat_turns_request_id ON chat_turns(request_id);
-- 同会话最多一个非终态轮次（SQLite 部分唯一索引）；终态后的新问创建新轮次。
CREATE UNIQUE INDEX idx_chat_turns_session_active
ON chat_turns(session_id)
WHERE status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED');
CREATE INDEX idx_chat_turns_session ON chat_turns(session_id, created_at, id);

-- 轮次持久事件日志：正文增量 / 过程 / 引用 / 完成事件；
-- 只读已提交事件，重复 seq 忽略、缺口按游标补拉。
CREATE TABLE chat_turn_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id TEXT NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL CHECK (seq >= 1),
    attempt INTEGER NOT NULL,
    output_revision INTEGER NOT NULL,
    type TEXT NOT NULL CHECK (type IN (
        'token', 'commentary', 'tool_call', 'tool_result', 'citation', 'done'
    )),
    segment_id TEXT,
    tool_call_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_chat_turn_events_seq ON chat_turn_events(turn_id, seq);
