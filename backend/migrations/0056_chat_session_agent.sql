ALTER TABLE chat_sessions ADD COLUMN agent_id TEXT NOT NULL DEFAULT 'general'
    CHECK (agent_id IN ('general', 'knowledge'));
