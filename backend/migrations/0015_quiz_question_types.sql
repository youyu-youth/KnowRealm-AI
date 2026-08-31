ALTER TABLE quizzes RENAME TO quizzes_v14;

CREATE TABLE quizzes (
    id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    batch_id TEXT REFERENCES processing_jobs(id) ON DELETE SET NULL,
    generated_from_summary_id TEXT REFERENCES ai_summaries(id) ON DELETE SET NULL,
    generation_status TEXT NOT NULL CHECK (
        generation_status IN ('DRAFT', 'ACTIVE', 'SUPERSEDED')
    ),
    question_type TEXT NOT NULL CHECK (
        question_type IN (
            'MULTIPLE_CHOICE', 'MULTIPLE_SELECT', 'TRUE_FALSE',
            'FILL_BLANK', 'SHORT_ANSWER'
        )
    ),
    stem TEXT NOT NULL CHECK (length(stem) BETWEEN 1 AND 500),
    options_json TEXT NOT NULL CHECK (
        json_valid(options_json) AND json_type(options_json) = 'array'
    ),
    correct_answer_json TEXT NOT NULL CHECK (json_valid(correct_answer_json)),
    explanation TEXT NOT NULL CHECK (length(explanation) BETWEEN 1 AND 2000),
    difficulty TEXT NOT NULL CHECK (difficulty IN ('EASY', 'MEDIUM', 'HARD')),
    user_answer_json TEXT,
    answer_result TEXT CHECK (
        answer_result IS NULL OR answer_result IN ('CORRECT', 'WRONG')
    ),
    answered_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

INSERT INTO quizzes (
    id, record_id, batch_id, generated_from_summary_id, generation_status,
    question_type, stem, options_json, correct_answer_json, explanation,
    difficulty, user_answer_json, answer_result, answered_at, created_at,
    updated_at, deleted_at
)
SELECT
    id, record_id, batch_id, generated_from_summary_id, generation_status,
    question_type, stem, options_json, correct_answer_json, explanation,
    difficulty, user_answer_json, answer_result, answered_at, created_at,
    updated_at, deleted_at
FROM quizzes_v14;

DROP TABLE quizzes_v14;

CREATE INDEX idx_quizzes_record_status_created
    ON quizzes(record_id, generation_status, created_at);
CREATE INDEX idx_quizzes_batch ON quizzes(batch_id);

CREATE TRIGGER quizzes_one_active_batch_insert
BEFORE INSERT ON quizzes
WHEN NEW.generation_status = 'ACTIVE'
  AND NEW.deleted_at IS NULL
  AND EXISTS (
      SELECT 1
      FROM quizzes
      WHERE record_id = NEW.record_id
        AND generation_status = 'ACTIVE'
        AND deleted_at IS NULL
        AND batch_id IS NOT NEW.batch_id
  )
BEGIN
    SELECT RAISE(ABORT, 'record already has another active quiz batch');
END;

CREATE TRIGGER quizzes_one_active_batch_update
BEFORE UPDATE OF record_id, generation_status, batch_id, deleted_at ON quizzes
WHEN NEW.generation_status = 'ACTIVE'
  AND NEW.deleted_at IS NULL
  AND EXISTS (
      SELECT 1
      FROM quizzes
      WHERE record_id = NEW.record_id
        AND id != NEW.id
        AND generation_status = 'ACTIVE'
        AND deleted_at IS NULL
        AND batch_id IS NOT NEW.batch_id
  )
BEGIN
    SELECT RAISE(ABORT, 'record already has another active quiz batch');
END;
