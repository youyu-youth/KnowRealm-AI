CREATE VIRTUAL TABLE search_index USING fts5(
    title,
    body,
    keywords,
    entity_type UNINDEXED,
    entity_id UNINDEXED
);
