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
