ALTER TABLE recording_sessions
ADD COLUMN recorded_duration_ms INTEGER NOT NULL DEFAULT 0
CHECK (recorded_duration_ms >= 0 AND recorded_duration_ms <= 10800000);
