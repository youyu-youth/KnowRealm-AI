ALTER TABLE chat_context_states ADD COLUMN rules_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE chat_context_inputs ADD COLUMN rules_json TEXT NOT NULL DEFAULT '{}';
