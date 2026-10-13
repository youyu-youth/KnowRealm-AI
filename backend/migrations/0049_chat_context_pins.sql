ALTER TABLE chat_context_states ADD COLUMN pins_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE chat_context_inputs ADD COLUMN pins_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE chat_model_requests ADD COLUMN pins_json TEXT NOT NULL DEFAULT '[]';
