# Course Brain 数据底座与 Agent 只读边界

---
Status: accepted（2026-09-15，F4 Course Brain V1 计划评审 grill 九问定稿）
---

基线 v2.7 F4（:280/:307）与扩展文档 §39.5 把 Course Brain 定为 P3；对话转资产 V1 完结后，课程图谱 mock 与 B2 词面检索的召回短板成为主要缺口，用户裁决提前实施。核心权衡：Course Brain 做可信的课程知识底座，Agent 通过稳定接口消费它，但 F4 本身不做成复杂 Agent 系统。

**决定**：

- **数据底座 = 三张业务表 + 锚点复用**（迁移 0023）：`concepts` / `concept_relations` / `record_concepts`（列名对齐数据模型 v2.7 §4.6）；来源关系不建新表——Transcript/Document/Chat 走 `source_anchor_links(resource_type='CONCEPT')`（值域扩一项），KP 来源走 `record_concepts.knowledge_point_id` 桥列。不建 concept_sources / concept_aliases / course_brain_runs：构建状态与来源指纹复用 `processing_jobs.input_json/result_json`。
- **构建任务 = 启用预留 job_type `CONCEPT_EXTRACTION`**：processing_jobs 的 SQL CHECK 早已预留该值（无 Python 成员），启用即免重建这张最繁忙的表；不新增 `COURSE_BRAIN_BUILD` 值。构建 = 确定性后台 Pipeline（JobRunner WorkerSpec），**不走 LangGraph**（无状态/无暂停恢复/无 Agent 决策，红线：普通确定性业务写普通 Service）。
- **Agent 只读边界**：Agent（B2 search_library）只能消费 CONFIRMED Concept——命中概念做检索词扩展后，引用仍必须逐字来自 Segment 原文；Concept 描述不得冒充引用；候选数据只进人工审核界面。F4 V1 零 Agent 写工具；未来 propose_* 类工具也必须走「建议 → CANDIDATE → 用户审核 → 业务 Service」链，Agent/Tool/Skill/MCP/SubAgent 永不直写业务表。
- **HITL 保护**：AI 抽取默认 CANDIDATE；与 CONFIRMED 概念 normalized_name 完全一致才自动挂接（语义相似只产生合并建议）；重新构建不得修改用户确认过的名称与描述；失去全部来源的概念标记待归档而非删除。
- **STALE = 查询时指纹派生**：快照接口现算各来源表 (count, max_updated_at) 聚合指纹与上次成功构建指纹比对，不进 A3 事件消费循环（其职责边界是 Evidence），零新消费者零迁移。
- **课程事实只住 knowrealm.db**：与 langgraph.db（checkpoint/运行态）职责不混；不使用 DeepAgents Filesystem Memory / StoreBackend 保存课程事实。
- **零 Evidence 污染**：构建与审核不写 learning_events / learning_evidence（AI 推断 ≠ 用户掌握）。

## Considered Options

| 方案 | 结论 |
|------|------|
| **A. 三表 + 锚点/桥双轨 + 预留 job 值 + 查询时 STALE** | **采纳**——零多余表、零表重建、零后台消费者 |
| B. 新增 COURSE_BRAIN_BUILD job 值 + concept_sources/course_brain_runs 表 | 否决——重建 processing_jobs 高风险；三张新表职责可被锚点复用与 result_json 覆盖 |
| C. A3 消费循环监听事件置脏 STALE | 否决——循环职责越界（Evidence），且指纹派生天然无延迟零成本 |
| D. LangGraph 图编排构建 Pipeline | 否决——纯确定性流程，违反「只有需要状态/暂停/Agent 决策才进 Graph」红线 |
| E. Agent 写工具直接维护概念 | 否决——违背 HITL 与 Evidence 红线，推断不得直写业务表 |

## Consequences

- `source_anchor_links` 值域扩展须重建表（SQLite CHECK 不可 ALTER），按仓库 rename→重建→拷贝→drop 惯例执行。
- v2.7「SQLite 无部分唯一索引」论断是错的（0017 已用部分唯一索引先例）：concepts 落地 `UNIQUE INDEX ... WHERE status='CONFIRMED'`，数据模型升 v2.8 时更正。
- Concept 自身检索进现有 `segment_search_index`（entity_type='CONCEPT'，0020 表本就是多态设计），零新 FTS 表；同义词扩展列为 CB-01 评测失败时的预留升级路径。
- B2 `search_library` 返回结构向后兼容扩展（新增 concepts/occurrences 键），前端工具卡只吃 hits 不受影响；CHAT_PROMPT_VERSION 升 v6（概念优先/描述不冒充引用/次数按去重 Record 计数）。
- 13 处硬编码 user_version 断言随 0023 同步 bump（项目铁律）。
- sqlite-vec / semantic_embeddings 不入本 Epic（检索基线评测结论默认「FTS+Concept 扩展够用」，如实记录口径）；Knowledge GPS / Mastery 消费 / 课件 Diff 不在范围。
