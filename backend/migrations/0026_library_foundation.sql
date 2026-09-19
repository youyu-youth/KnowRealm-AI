-- 资料库 / RAG Agent + Learner Memory V1 数据地基（library-rag-v1 工单 02）：
-- 四张新表 + 存量结构改造集中在一次迁移（DDL 终稿由工单 01 冻结于
-- .scratch/library-rag-v1/contract.md §1；逐列核对数据模型 v3.0，含实施级
-- 调整 #3 = library_items.favorite 列与 2 个补充索引）。
-- 存量哈希/条目/关联补建不走迁移，由 LIBRARY_BACKFILL 幂等后台 Job 完成。
PRAGMA legacy_alter_table=ON;

CREATE TABLE library_items (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE SET NULL,
    source_type TEXT NOT NULL CHECK (
        source_type IN ('AUDIO', 'DOCUMENT', 'WEB', 'BOOK', 'TEXT')
    ),
    title TEXT NOT NULL CHECK (length(trim(title)) >= 1),
    origin_uri TEXT,
    local_path TEXT,
    mime_type TEXT,
    file_size INTEGER CHECK (file_size IS NULL OR file_size >= 0),
    content_hash TEXT NOT NULL,
    fetched_at TEXT,
    metadata_json TEXT NOT NULL CHECK (json_valid(metadata_json)),
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version >= 1),
    favorite INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE INDEX idx_library_items_course_updated ON library_items(course_id, updated_at DESC);
CREATE INDEX idx_library_items_source_type ON library_items(source_type, updated_at DESC);
CREATE INDEX idx_library_items_status ON library_items(status, updated_at DESC);
CREATE INDEX idx_library_items_content_hash ON library_items(content_hash);
CREATE INDEX idx_library_items_deleted_at ON library_items(deleted_at);

CREATE TABLE library_item_records (
    library_item_id TEXT NOT NULL REFERENCES library_items(id) ON DELETE CASCADE,
    record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('PRIMARY', 'SUPPLEMENTAL')),
    sequence_no INTEGER NOT NULL DEFAULT 0 CHECK (sequence_no >= 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (library_item_id, record_id)
);

CREATE INDEX idx_library_item_records_record ON library_item_records(record_id);

CREATE TABLE agent_proposals (
    id TEXT PRIMARY KEY,
    proposal_type TEXT NOT NULL CHECK (
        proposal_type IN ('ORGANIZE', 'MEMORY', 'RESEARCH_INGEST')
    ),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'APPLIED', 'REJECTED', 'FAILED')),
    session_id TEXT,
    message_id TEXT,
    target_type TEXT,
    target_id TEXT,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    evidence_refs_json TEXT CHECK (
        evidence_refs_json IS NULL OR json_valid(evidence_refs_json)
    ),
    error_code TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE INDEX idx_agent_proposals_status_created ON agent_proposals(status, created_at DESC);
CREATE INDEX idx_agent_proposals_target ON agent_proposals(target_type, target_id);

CREATE TABLE learner_preferences (
    id TEXT PRIMARY KEY CHECK (id = 'me'),
    user_selected_preference TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(user_selected_preference)),
    observed_learning_preference TEXT CHECK (
        observed_learning_preference IS NULL
        OR json_valid(observed_learning_preference)
    ),
    observed_confidence REAL CHECK (
        observed_confidence IS NULL OR observed_confidence BETWEEN 0 AND 1
    ),
    evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
    last_observed_at TEXT,
    updated_at TEXT NOT NULL
);

-- chat_sessions：scope CHECK 扩五档 + library_item_id（无表级 LIBRARY_ITEM→NOT NULL
-- CHECK：条目物理删除走 SET NULL，会话保留为运行时推导的挂载失效态）。
ALTER TABLE chat_sessions RENAME TO chat_sessions_v25;

CREATE TABLE chat_sessions (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE SET NULL,
    record_id TEXT REFERENCES records(id) ON DELETE SET NULL,
    concept_id TEXT,
    library_item_id TEXT REFERENCES library_items(id) ON DELETE SET NULL,
    mode TEXT NOT NULL CHECK (
        mode IN ('ASK', 'COURSE_QA', 'SOCRATIC_TUTOR', 'TEACH_BACK')
    ),
    scope TEXT NOT NULL DEFAULT 'FREE' CHECK (
        scope IN ('FREE', 'RECORD', 'LIBRARY_ITEM', 'COURSE', 'ALL')
    ),
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

INSERT INTO chat_sessions (
    id, course_id, record_id, concept_id, library_item_id, mode, scope,
    title, created_at, updated_at, deleted_at
)
SELECT
    id, course_id, record_id, concept_id, NULL, mode, scope,
    title, created_at, updated_at, deleted_at
FROM chat_sessions_v25;

DROP TABLE chat_sessions_v25;

CREATE INDEX idx_chat_sessions_list ON chat_sessions(deleted_at, updated_at DESC);

-- processing_jobs：library_item_id 关联 + job_type 扩展（0017 全列照抄 + 三新类型）。
ALTER TABLE processing_jobs RENAME TO processing_jobs_v25;

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
            'INDEX_REBUILD', 'CLEANUP', 'BACKUP_EXPORT'
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
    id, record_id, NULL, job_type, status, progress, attempts,
    max_attempts, next_run_at, input_json, result_json, error_code, error_message,
    started_at, finished_at, created_at, updated_at, waiting_reason
FROM processing_jobs_v25;

DROP TABLE processing_jobs_v25;

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

-- document_segments：course_material_id 改名 library_item_id 并补 FK（其余原样）。
ALTER TABLE document_segments RENAME TO document_segments_v25;

CREATE TABLE document_segments (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE CASCADE,
    record_id TEXT REFERENCES records(id) ON DELETE CASCADE,
    record_file_id TEXT REFERENCES record_files(id) ON DELETE CASCADE,
    library_item_id TEXT REFERENCES library_items(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL CHECK (sequence_no >= 0),
    page_no INTEGER,
    section_title TEXT,
    content TEXT NOT NULL,
    start_offset INTEGER,
    end_offset INTEGER,
    content_hash TEXT NOT NULL,
    CHECK ((record_file_id IS NULL) != (library_item_id IS NULL))
);

INSERT INTO document_segments (
    id, course_id, record_id, record_file_id, library_item_id, sequence_no,
    page_no, section_title, content, start_offset, end_offset, content_hash
)
SELECT
    id, course_id, record_id, record_file_id, course_material_id, sequence_no,
    page_no, section_title, content, start_offset, end_offset, content_hash
FROM document_segments_v25;

DROP TABLE document_segments_v25;

-- source_anchors：course_id 改可空（全局来源真实锚点）+ 改名列补 FK（其余原样）。
ALTER TABLE source_anchors RENAME TO source_anchors_v25;

CREATE TABLE source_anchors (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (
        source_type IN ('AUDIO_SEGMENT', 'DOCUMENT_SEGMENT', 'USER_NOTE', 'CHAT_MESSAGE')
    ),
    source_id TEXT NOT NULL,
    record_id TEXT REFERENCES records(id) ON DELETE CASCADE,
    record_file_id TEXT REFERENCES record_files(id) ON DELETE CASCADE,
    library_item_id TEXT REFERENCES library_items(id) ON DELETE CASCADE,
    transcript_segment_id TEXT REFERENCES transcript_segments(id) ON DELETE CASCADE,
    document_segment_id TEXT REFERENCES document_segments(id) ON DELETE CASCADE,
    start_offset INTEGER,
    end_offset INTEGER,
    page_no INTEGER,
    CHECK (
        (source_type != 'AUDIO_SEGMENT' OR transcript_segment_id IS NOT NULL)
        AND (source_type != 'DOCUMENT_SEGMENT' OR document_segment_id IS NOT NULL)
    )
);

INSERT INTO source_anchors (
    id, course_id, source_type, source_id, record_id, record_file_id,
    library_item_id, transcript_segment_id, document_segment_id,
    start_offset, end_offset, page_no
)
SELECT
    id, course_id, source_type, source_id, record_id, record_file_id,
    course_material_id, transcript_segment_id, document_segment_id,
    start_offset, end_offset, page_no
FROM source_anchors_v25;

DROP TABLE source_anchors_v25;

PRAGMA legacy_alter_table=OFF;
