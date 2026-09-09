-- 四表均为派生定位/引用结构（非可编辑实体）：不带 updated_at/deleted_at 软删列。
CREATE TABLE transcript_segments (
    id TEXT PRIMARY KEY,
    transcript_id TEXT NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    file_id TEXT NOT NULL REFERENCES record_files(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL CHECK (sequence_no >= 0),
    record_start_ms INTEGER,
    record_end_ms INTEGER,
    file_start_ms INTEGER,
    file_end_ms INTEGER,
    speaker TEXT,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL
);

CREATE INDEX idx_transcript_segments_record_sequence
    ON transcript_segments(record_id, sequence_no);
CREATE INDEX idx_transcript_segments_file_start
    ON transcript_segments(file_id, file_start_ms);
CREATE INDEX idx_transcript_segments_record_start
    ON transcript_segments(record_id, record_start_ms);

CREATE TABLE document_segments (
    id TEXT PRIMARY KEY,
    -- course_id 随挂靠记录所属课程；收件箱导入（未归类）为 NULL。
    course_id TEXT REFERENCES courses(id) ON DELETE CASCADE,
    record_id TEXT REFERENCES records(id) ON DELETE CASCADE,
    record_file_id TEXT REFERENCES record_files(id) ON DELETE CASCADE,
    course_material_id TEXT,
    sequence_no INTEGER NOT NULL CHECK (sequence_no >= 0),
    page_no INTEGER,
    section_title TEXT,
    content TEXT NOT NULL,
    start_offset INTEGER,
    end_offset INTEGER,
    content_hash TEXT NOT NULL,
    CHECK ((record_file_id IS NULL) != (course_material_id IS NULL))
);

CREATE TABLE source_anchors (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (
        source_type IN ('AUDIO_SEGMENT', 'DOCUMENT_SEGMENT', 'USER_NOTE', 'CHAT_MESSAGE')
    ),
    source_id TEXT NOT NULL,
    record_id TEXT REFERENCES records(id) ON DELETE CASCADE,
    record_file_id TEXT REFERENCES record_files(id) ON DELETE CASCADE,
    course_material_id TEXT,
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

CREATE TABLE source_anchor_links (
    id TEXT PRIMARY KEY,
    resource_type TEXT NOT NULL CHECK (
        resource_type IN (
            'SUMMARY', 'KNOWLEDGE_POINT', 'QUIZ', 'MISCONCEPTION',
            'CHAT_MESSAGE', 'RECORD_ANALYSIS'
        )
    ),
    resource_id TEXT NOT NULL,
    source_anchor_id TEXT NOT NULL REFERENCES source_anchors(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL CHECK (
        relation_type IN ('SUPPORTS', 'PRIMARY', 'CONTRADICTS', 'REFERENCES')
    ),
    UNIQUE (resource_type, resource_id, source_anchor_id, relation_type)
);
