# 01 — 搜索服务纵切：FTS5 统一索引 + /api/search + 启动回填

**What to build:** 应用启动后，存量学习资产可被检索：新增后端 search 模块作为唯一搜索入口，`GET /api/search` 返回按类型分组（课程/学习记录/知识点）的检索结果；SQLite FTS5 统一索引表（jieba 应用层分词、BM25 排序）随新增迁移建立，启动时幂等回填存量数据并预热词典。引擎选型与作废方案依据 ADR-0016；本票不含写路径同步（02 承接），回填使本票独立可验收。

**Blocked by:** None — can start immediately.

**Status:** done

- [x] jieba 进入后端依赖；新增迁移创建统一 FTS5 索引表（可检索列 title/body/keywords 存切词文本，entity_type/entity_id 为 UNINDEXED）
- [x] `GET /api/search`：参数 q 必填（trim、长度上限）与 limit（每类上限，默认 5）；响应按类型分组，每项含实体 id、标题、snippet、所属课程名、updated_at；空/超长 q 返回 422
- [x] 中文 2 字词命中学习记录（标题/转写正文）、知识点（名称/详情/tags）、课程（名称/hot_words）
- [x] 结果按 BM25 相关度排序（含「标题命中优先于正文命中」的构造用例）
- [x] 软删（deleted_at）实体与 ARCHIVED 课程（含其记录与知识点）不进结果（测试经 SQL 直改模拟）
- [x] 启动回填幂等：迁移执行后为存量三类实体补索引行，重复执行不重复不遗漏；启动预热 jieba 词典
- [x] openapi 导出零漂移，api-types 重新生成
- [x] 上述全部有 pytest（真实 SQLite）覆盖，只断言 HTTP 响应行为，不测内部切词函数

**实现备注（2026-09-07，agent 交付）：**

- search 模块四文件：`tokenizer.py`（jieba 适配层，索引/查询共用 `cut_for_search`，文件级 pyright 关闭 jieba 无存根的 unknown 检查）、`schemas.py`、`service.py`（SearchService：search / upsert_\*_index / backfill_missing）、`search.py`（路由）。`upsert_record_index` 等三方法已按「查源→upsert（实体物理删除则清行）」实现，02 票写路径直接调用即可。
- BM25 列权重 10:1:1（title/body/keywords）实现「标题命中优先」；snippet 取 body 列摘录、无正文回退 title 列（FTS5 snippet 对无命中列返回该列开头文本，非 NULL——已实测确认）。
- 口径扩展（评审明示）：知识点过滤 `generation_status IN ('DRAFT','ACTIVE')`（与知识点默认视图口径一致，SUPERSEDED 不进结果）；knowledge_points 条目附带 `record_id`（spec User Story 11 跳转宿主所需，契约一次到位）；回填失败仅记日志不阻断启动（与滚动备份同容错级，下次启动重试）。
- 已知取舍：snippet 为切词文本的摘录（中文 token 间含空格），03/04 票渲染时若体验不佳凭真实反馈再议；hot_words 命中的课程 snippet 展示课程名片段（body 列无正文可摘）。
- 全量 375 pytest / ruff / pyright(strict) 全绿；既有 10 处 user_version==17 断言随 0018 同步为 18。

**用户真机验收（用户执行，agent 不代勾）：**

- [ ] 真实数据目录启动完成回填后，历史记录/知识点/课程可被中文关键词搜到（可与 03 交付的面板合并验收）
