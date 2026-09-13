-- 分片级检索索引（chat 检索工具数据地基）：与全局 search_index 分表不复用，
-- 全局搜索三类资产语义不混入分片命中。索引是可再生衍生数据：无 UNIQUE，
-- 先删后插同事务幂等；软删不触碰索引行，查询期回表过滤；分片物理删除
-- （编辑重切）时同事务清理索引行。
CREATE VIRTUAL TABLE segment_search_index USING fts5(
    body,
    entity_type UNINDEXED,
    entity_id UNINDEXED
);
