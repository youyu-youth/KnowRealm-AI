# KnowRealm-AI 数据模型 v3.1

> **文档定位**：KnowRealm-AI 的**唯一数据模型基线**，与《功能需求基线 v2.8》配套。表设计冲突已按功能基线 §10 决策记录定稿；技术栈约束见 `技术栈设计与审查-v4.6.md`。
> **核心原则（v2.0 范式，ADR-0001 / 决策 #55）**：
> - **SQLite（knowrealm.db，WAL）= 唯一业务事实源**——全部业务实体、学习状态、向量、技术任务状态
> - **LangGraph Checkpoint（langgraph.db，独立文件）= Agent 运行态**（框架自管，非业务事实）
> - **云端（P2 可选）= 只读快照副本**——永不回写、永不双向同步
>
> 本文只做设计，不含迁移 SQL，不开始实现。
> **编写日期**：2026-08-17
> **变更记录**：v3.1（2026-09-19）**资料库数据地基已实施（迁移 0026，library-rag-v1 工单 02，ADR-0024/0025）**——§4.2 `library_items` / `library_item_records` 与 §4.10 `agent_proposals`、§4.6 `learner_preferences` 四表**已实施**（0026 一次建齐，升级前独立快照 `knowrealm-premigrate-NNNN.db` + LIBRARY_BACKFILL 幂等回填 Job 配套）；`library_items` 落地工单 01 契约**实施级调整 #3**：增 `favorite INTEGER NOT NULL DEFAULT 0`（收藏智能视图依赖，Record/资产收藏不在 V1 范围）与补充索引 `idx_library_items_deleted_at`（回收站视图）/ `idx_library_item_records_record`（反向派生查询）；`document_segments` / `source_anchors` 预留列 `course_material_id` 落地为 `library_item_id` 并补 FK CASCADE，`source_anchors.course_id` 改可空；`chat_sessions.scope` CHECK 扩五档（新增 LIBRARY_ITEM）并增可空 `library_item_id`（FK SET NULL，无表级 CHECK——条目物理删除后会话保留为运行时挂载失效态）；`processing_jobs` 增 `library_item_id`（FK CASCADE）与 job_type 三值扩展（WEB_FETCH / LIBRARY_BACKFILL / INDEX_REBUILD，WEB_FETCH/INDEX_REBUILD 建每条目 one-active 部分唯一索引，LIBRARY_BACKFILL 全局单例由服务层保证）。正式表合计 44 张不变，**已实施 31 张**（截至迁移 0026）。
> **变更记录**：v3.0（2026-09-18）**资料库 / RAG Agent 与 Learner Memory V1 评审定稿（ADR-0024/0025）**——未实施的 `course_materials` 草案被 `library_items` + `library_item_records` 通用来源资产模型替换，`document_segments` / `source_anchors` / `semantic_embeddings` 的预留 `course_material_id` 统一改为 `library_item_id`；`chat_sessions` 规划 `LIBRARY_ITEM` 精确范围与 `library_item_id`；新增轻量 `agent_proposals` 承载整理、记忆和研究入库提案，业务提案不寄存在 LangGraph Checkpoint；`learner_preferences` 冻结为长期记忆 V1 的单例事实表，Mastery / Misconception / Goal 保持各自事实源，由 LearnerProfileService 聚合。sqlite-vec 改为真实语料评测触发，不再是资料库开工前置。正式表设计口径由 42 张调整为 **44 张**，已实施仍为 27 张；本版只定设计，不声明迁移已实施。
> **变更记录**：v2.9（2026-09-18）**Concept Mastery V1 已实施（迁移 0024/0025，concept-mastery-v1 plan，ADR-0023）**——§4.3 **quizzes** 增可空 `concept_id`（REFERENCES concepts ON DELETE SET NULL + 索引；一题至多一个主概念：生成只从同课程 CONFIRMED 概念建议、服务端校验、作答前可改/清空、首答后应用层锁定、Event 固化；存量行 NULL 不回填，2026-08-25「不建 concept_id」草案口径就此作废）；§4.7 **user_concept_mastery** 首张落地（Learner Brain 域 P4 提前）：course_id（FK CASCADE）/ concept_id **UNIQUE**（FK CASCADE）/ mastery_score 与 mastery_confidence 可空 0~1 CHECK / 证据三计数 ≥0 CHECK / last_practiced_at / last_verified_at / **algorithm_version** / updated_at——**只建 V1 真实使用列**，草案中的 memory_strength / transfer_score / reasoning_score / next_review_at / last_learned_at 不建（Forgetting / Transfer / Reasoning 落地时再迁移）；唯一写入口 = Mastery Engine（确定性纯函数 12 条窗口四条半衰，ADR-0023），快照由有效 Quiz Evidence 全量重建，<3 条 = NOT_ENOUGH_DATA 分数置空。正式表设计口径 42 张不变，**已实施 27 张**（截至迁移 0025）。
> **变更记录**：v2.8（2026-09-16）**F4 Course Brain V1 已实施（迁移 0023，course-brain-v1 plan，ADR-0022）**——§4.6 concepts / concept_relations / record_concepts 三表标注**已实施**（无 deleted_at：ARCHIVED 即退役语义；normalized_name = 应用层确定性函数：strip → 空白折叠 → 全角转半角 → casefold；record_concepts 草案中的 importance 列未建，概念重要度只在 concepts.importance）；`source_anchor_links.resource_type` 值域扩 `'CONCEPT'`（rename→重建→拷贝→drop，0017 同款）；**更正**：「SQLite 无部分唯一索引」论断有误——CONFIRMED 唯一由部分唯一索引 `UNIQUE ... WHERE status='CONFIRMED'` 库级兜底（0017 已有先例）；semantic_embeddings / vec0 **维持未建**（CB-01 合成评测四维全过 → sqlite-vec 延后，见 `docs/evaluation/course-brain-retrieval-baseline.md`）；正式表设计口径 42 张不变，已实施 26 张（另有 search_index / segment_search_index 两张 FTS 衍生索引表，纪律不计正式表数）。
> **变更记录**：v2.7（2026-09-14）**B2 跨记录/课程级问答已实施（迁移 0022，cross-record-qa plan）**——§4.4 chat_sessions 增 `scope` 列（TEXT NOT NULL DEFAULT 'FREE'，CHECK ∈ FREE/RECORD/COURSE/ALL；存量回填 record_id 非空→RECORD）：显式四档会话范围，与 mode 轴正交（mode 恒 ASK，交互形态留给 B3）；course_id 列自此启用语义（COURSE 会话=挂载课程；RECORD 会话维持随 record 派生；课程软删→会话只读，course_deleted 运行时推导，对齐 record_deleted 先例）；citations_json record 条目增 `record_title` （标题快照，跨记录引用归属由校验器裁定；历史行无此键→null，前端降级展示）。
> **变更记录**：2026-09-14 **B1 web_search 已实施（web-search plan 两票，零表变更不升版）**——§4.4 chat_messages.citations_json 条目**判别化**就地补记：record 条目照旧（逐字校验不变、历史行无 source 键按 "record" 读取），web 条目 `{index, source:"web", url, title}`（联网搜索来源，仅非空检查）；citations_json 本就是自由 JSON，零迁移。
> **变更记录**：v2.6（2026-09-14）**A3 事件消费框架 + Evidence Builder 已实施（迁移 0021，learning-evidence plan）**——§4.5 learning_events / learning_evidence 标注**已实施**（learning 域：统一事件写入函数 `learning.events.write_learning_event`、独立 asyncio 水位消费循环 `learning/consumer.py`、映射规则集中声明，ADR-0021；水位 = 隐式 rowid 单调扫描、禁 NOT EXISTS；event_id 预查幂等 + 唯一约束兜底；失败 3 次跳过不建死信表；证据可由事件流清空重放再生）；event_id 由普通索引**收紧为唯一约束**（重放幂等的数据库级保障，一事件至多一证据）；learning 域薄只读查询（按记录/课程取证据流）就位，为 Mastery Engine 与 agent 学习上下文中间件共同底座；concept_id / source_anchor_id 本期恒 NULL。
> **变更记录**：v2.5（2026-09-13）**A1+A2 Chat 检索工具已实施（迁移 0020，chat-retrieval-tool plan）**——§4.5 增配套 FTS5 虚拟表 `segment_search_index`（entity_type ∈ {transcript_segment, document_segment} / entity_id / body 为 jieba 分词串；与全局搜索 `search_index` 分表，`/api/search` 语义零变化）；可再生衍生索引不计正式表数，纪律同 ADR-0016（写路径同事务先删后插、软删不触碰索引行、查询期回表过滤）。挂载对话经 `search_transcript` 工具消费该索引：命中一律回业务表取逐字原文（索引只负责"找到哪个片段"），无分片记录退化为 transcript 全文子串兜底。
> **变更记录**：v2.4（2026-09-10）**F1 转写分片与来源时间轴已实施（迁移 0019，transcript-segments plan）**——§4.5 前四表（transcript_segments / document_segments / source_anchors / source_anchor_links）标注**已实施**，表结构以此节为准。实施定案：transcript_segments 四个时间戳列允许 NULL（= 无时间轴来源，存量回填 / in-flight 降级 / 编辑未命中句三场景共用同一退化语义）；document_segments.course_id 可空（收件箱导入未归类为一等场景）、course_material_id 挂靠路径列预留（course_materials P5 未建，暂无外键，其落地时补约束）；source_anchors「至少关联一个分片」收紧为精确类型 CHECK（AUDIO_SEGMENT 必挂 transcript_segment_id、DOCUMENT_SEGMENT 必挂 document_segment_id，§10 同步）；四表为派生定位/引用结构，不带 created_at / 软删列（随父实体级联删除）；锚点两表空表就位、本期零写入者（首个写入者随 A1 检索工具 / A3 Evidence Builder）。
> **变更记录**：v2.3（2026-09-06）**复习资料定稿（16 plan grill）**——review_materials 由 6 字段草案补齐完整形态：status（GENERATED / CONFIRMED / SUPERSEDED，确认必选）、version_no（(record_id, version_no) 唯一；仅 AI 重生成换代，手动编辑就地生效不换代）、transcript_source_version（过期锚点：转写已改则拒绝新提交）、generated_from_summary_id（可空，仅溯源不阻塞）、user_feedback / token_usage_json / latency_ms / confirmed_at / 软删列。生成上下文定为**转写/文档解析全文为主 + 已确认总结辅助**（KP 不进，弃"总结+KP"草案）；生成走 LangGraph interrupt/resume（复用 langgraph.db，thread_id 前缀隔离，与总结同构）；超长按模型窗口自适应（装得下单次调用、超限语义分块 map-reduce，禁静默截断）；Top 重点清单条数不固定（LLM 按内容密度决定）。
> **变更记录**：2026-08-25 **习题生成与作答定稿（08 plan grill）**——quizzes 增作答三列（user_answer_json / answer_result 可空 CORRECT·WRONG，NULL=简答待自评 / answered_at，与 QUIZ_ANSWERED 同事务写）并补软删标注；不建 model / prompt_version / quality_score / cognitive_level / concept_id / source_anchor_id 列（溯源记 processing_jobs.result_json——07 先例，P3 / P5 / 评测域后补）；选择题单选、判断题 options 固定「对/错」两项与选择题同构；逐题模式一题一答、简答二态自评；learning_events 幂等键构造定为 `{event-slug}:{source-id}`（quiz-answered:{quiz_id}）；习题批次采纳不发学习事件；Wave B 测验模式同题再答键位另立（quiz-answered:test:{item_id} 风格）。
> **变更记录**：2026-08-24 **知识点提取定稿（07 plan grill）**——knowledge_points 取消独立 status 列（generation_status 单列承载，对齐 quizzes）；importance 定标 1~5、tags ≤5；AI 候选生成即落 DRAFT 行、每 Record 至多一个在途 DRAFT 批次；确认时绑定的 Summary 须仍为 CONFIRMED；批次溯源（model / prompt_version / 候选条数）记入 processing_jobs.result_json，表不加列。
> **变更记录**：v2.2（2026-08-22）**多来源音频与版本绑定定稿**——records.capture_type 增加 MULTI_SOURCE；Capture Batch 明确为非持久化命令边界；Transcript source_version 同时作为内容版本与显式保存前置条件；ai_summaries 绑定 transcript_source_version；KP/Quiz/Todo 的 AI 结果绑定 summary_id 且可标记 SUPERSEDED；processing_jobs 定义 ASR 顺序切片检查点、等待态与差异化手动重试。
> **变更记录**：v2.1（2026-08-20）**文档任务与单写者约束定稿**——processing_jobs 增加 CANCELLED、失败分类与重试转移；删除 record_files.processing_status，技术任务状态以 processing_jobs 为唯一事实源；同一数据目录增加进程生命周期排他锁；文档 Transcript 语言 V1 写 und；content_hash 仅用于完整性校验和重复检测，允许重复导入。
> **变更记录**：v2.0（2026-08-17）**SQLite 化范式转向（#55）**——`user_id` 列全删（单用户库）、RLS/auth.uid 全删、Storage 桶→数据目录 `files/`、pgvector→sqlite-vec（vec0 虚拟表）、jsonb→TEXT(JSON)、text[]→TEXT(JSON)、timestamptz→TEXT(ISO8601 UTC)、uuid PK→TEXT(应用生成 uuid4)、`version` 乐观锁列全删（单写者无并发冲突）；~~user_settings~~ 并入 `config/settings.json`、profiles→单行 `profile`；状态机 9 态→**8 态**（UPLOADING 消解）；新增 `recording_sessions`（录音会话恢复）；`processing_jobs` 升格为**任务队列本体**（自研队列替代 procrastinate）；SQLite 本地十表（cached_*/sync_*/local_*）整体删除；§7 改为"备份、导出与换机"。v1.1~v1.10 变更史见 git（文件 v1.10 于本版删除；v1.11 表结构审查裁决〔transcripts 补 deleted_at/source_version、chat 失效态运行时推导、Wave A 基线 15 张〕已并入本版）。

---

## 1. 三层职责边界

| 层 | 存储 | 职责 | 禁止 |
|----|------|------|------|
| 本地业务事实 | 数据目录 `knowrealm.db`（SQLite WAL）+ `files/`（原始文件） | 全部业务实体、学习状态、向量、技术任务状态；同一数据目录由 sidecar 持有进程生命周期排他锁 | UI/第二个 sidecar 直写 |
| Agent 运行态 | `langgraph.db`（SqliteSaver，独立文件） | Graph 暂停/恢复状态（HITL 等待等） | 当业务表查询；长期事实只存这里 |
| 云端（可选，P2） | 用户自配 WebDAV/S3 上的导出 zip | 只读快照副本（防丢/换机） | 任何形式的回写与双向同步 |

## 2. 通用规范（SQLite 全表适用）

- 表名 `snake_case`，无前缀；主键 `id TEXT`（应用层生成 uuid4）；时间 `created_at TEXT`（ISO8601 UTC）；JSON 一律 `TEXT`（存 JSON 字符串）；数组 `TEXT`（JSON 数组字符串）
- **无 `user_id` 列、无 RLS**（单用户本地库，#55）；sidecar 仅监听 127.0.0.1；同一数据目录必须先取得操作系统非阻塞排他锁再迁移或启动 worker，确保最多一个写者（红线 #35）
- 可编辑实体统一携带：`updated_at`、`deleted_at`（软删，可空）；纯追加型事实表（events/evidence/messages/logs）不做软删。通用 `version` 乐观锁列仍不设置；`ai_summaries.version_no` 是业务版本号，`transcripts.source_version` 既是内容版本，也是 Transcript 显式保存的并发前置条件（只保护用户正文，不扩张为全表通用锁）。
- 状态/枚举字段用受控枚举（CHECK 约束或应用层 Enum 注册），禁止裸字符串随意写入
- **PRAGMA**：`foreign_keys=ON`、`journal_mode=WAL`；连接仅 sidecar（UI 不直连库）
- 向量检索**恒定强制前置过滤 `deleted_at IS NULL`**；course_id/record_id 仅范围检索时附加；禁止裸向量查询（#28 v2.0）
- 迁移唯一权威 = `backend/migrations/*.sql`（`PRAGMA user_version` 编号推进，#10 v2.0）

## 3. 表总览

| 域 | 表 | 建表阶段 |
|----|----|---------|
| 档案（1） | profile | P0 |
| 课程、记录与资料（8） | courses, records, record_files, transcripts, recording_sessions, library_items, library_item_records, record_markers | P0×5 / 本波次×2 / P2 |
| AI 产出（8） | ai_summaries, knowledge_points, quizzes, quiz_tests, quiz_test_items, review_materials, todo_items, record_analyses | P1×7 / P3 |
| 对话（2） | chat_sessions, chat_messages | P1 |
| 学习数据基础（6） | transcript_segments, document_segments, source_anchors, source_anchor_links, learning_events, learning_evidence | P2（learning_events 提前 **P1**，#33） |
| Course Brain（4） | concepts, concept_relations, record_concepts, semantic_embeddings（+vec0 虚拟表） | **P3×3 已实施**（0023）/ P2 未建 |
| Learner Brain（5） | user_concept_mastery*, misconceptions, misconception_evidence, review_schedules, learner_preferences | **user_concept_mastery 已实施**（0025，P4 提前）/ 其余 P4 |
| Agent 提案（1） | agent_proposals | 本波次 |
| Adaptive / Planner（6） | teach_back_attempts, learning_goals, learning_plans, learning_plan_items, learning_agent_actions, learning_agent_feedback | P5 / P6×5 |
| Outcome（1） | learning_passport_snapshots | P7 |
| 基础设施（2） | processing_jobs（兼任务队列）, llm_call_logs | P0 |
| 暂缓 | ~~shares~~（不建，分享=Markdown 本地导出）、study_pods 系列（P8） | — |

正式表合计 **44 张**（v3.0：`course_materials` 以 `library_items` + `library_item_records` 替换，净增 1；新增 `agent_proposals`，净增 1；表名 user_concept_mastery 为历史命名，语义=概念掌握度，更名成本大于收益，保留）。**已实施 31 张**（截至迁移 0026；v3.1 四表落地，其余本版新增模型未实施）；另有 `search_index` / `segment_search_index` 两张 FTS 衍生索引表，可再生不计正式表数（ADR-0016 纪律）。**Wave A 基线 15 张**：profile / courses / records / record_files / transcripts / recording_sessions / processing_jobs / llm_call_logs / ai_summaries / knowledge_points / quizzes / todo_items / chat_sessions / chat_messages / learning_events。

## 4. 表设计

> 说明列仅写关键约束；所有表默认含 `created_at TEXT`，下文不再重复。标注〔软删〕= 含 deleted_at。类型列统一按 §2 规范（TEXT 为主）。

### 4.1 档案域

**profile** — 本地档案（单行表，P0）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT | PK（固定单行 'me' 或 uuid） |
| nickname | TEXT | |
| avatar_file | TEXT | 可空；数据目录内相对路径（files/avatars/…） |
| primary_role | TEXT | STUDENT / DEVELOPER / OFFICE_WORKER / OTHER（#52——首启角色卡/建课程默认值/自由聊天系统提示；不进课程 AI 管线与 Evidence） |
| about_me | TEXT | ≤200 字自我介绍（随角色注入自由聊天系统提示；新会话生效不追溯） |
| updated_at | TEXT | |

不保存任何认证事实（v2.0 无认证）。偏好与供应商配置不入库——见 §5 `config/`。

### 4.2 课程与记录域

**courses**（P0，〔软删〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT | PK |
| name | TEXT | NOT NULL |
| learning_context | TEXT | SCHOOL / CAREER / INTEREST（必填，进 AI 上下文） |
| education_stage | TEXT | MIDDLE_SCHOOL / HIGH_SCHOOL / UNDERGRADUATE / GRADUATE / DOCTORAL——**仅 SCHOOL 场景必填** |
| depth | TEXT | BEGINNER / INTERMEDIATE / ADVANCED——**仅 CAREER/INTEREST 场景必填** |
| course_type | TEXT | MAJOR / GENERAL / ELECTIVE——可空 |
| description | TEXT | 可空 |
| hot_words | TEXT | JSON 数组，可空（#54）——ASR 热词手动列表（≤100 词）；自动同步 P2 |
| status | TEXT | ACTIVE / ARCHIVED；只有 ACTIVE 可接受新捕获、归类、升级或 AI 触发 |

CHECK：`learning_context='SCHOOL' → education_stage 非空；learning_context≠'SCHOOL' → depth 非空`
索引：`(updated_at desc)`、`(learning_context)`、`(course_type)`

**records** — 学习记录（P0，〔软删〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT | PK |
| course_id | TEXT | FK，**可空——为空即收件箱 Inbox 未分类捕获** |
| capture_type | TEXT | RECORDING / AUDIO_IMPORT / DOCUMENT_IMPORT / MULTI_SOURCE / PASTE / QUICK_NOTE / CLIP；同一封口批次含多种 file/source 类型时写 MULTI_SOURCE |
| title | TEXT | |
| status | TEXT | 业务状态机 **8 态**：NOTE / DRAFT / CONTENT_PROCESSING / SUMMARY_PENDING / SUMMARY_PROCESSING / SUMMARY_READY / COMPLETED / FAILED（技术任务状态只入 processing_jobs） |
| duration_ms | INTEGER | ≥0 |
| summary_confirmed_at | TEXT | HITL 确认时刻 |

索引：`(created_at desc)`、`(course_id, created_at desc)`、`(status)`

**record_files** — Record 关联文件（P0，〔软删〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / record_id | TEXT | |
| file_type | TEXT | AUDIO / DOCUMENT |
| source_type | TEXT | RECORDED / UPLOADED |
| file_path | TEXT | **数据目录内相对路径**（#49 v2.0）：存档原件 `files/{record_id}/{file_id}.{ext}`；中间产物在 `cache/` |
| original_name / mime_type | TEXT | |
| file_size | INTEGER | ≥0 |
| duration_ms | INTEGER | 仅音频 |
| sequence_no | INTEGER | 封口批次内顺序，≥0；按提交数组写 0..N-1，正式注册后不可追加或重排（#54/#58） |
| content_hash | TEXT | 完整性校验/重复检测；不设 UNIQUE，相同文件允许创建独立 Record |

索引：`(record_id, sequence_no)`、`(content_hash)`

**transcripts** — 转写文本（P0，〔软删 v1.11 裁决〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / record_id | TEXT | record_id UNIQUE（一 Record 一份当前转写） |
| language | TEXT | BCP 47 或 `und`；纯普通话音频写 `zh-CN`，文档/混合来源 V1 不做语言猜测，写 `und` |
| content | TEXT | 当前合并全文；V1 按 sequence_no 以两个换行连接，不含文件名/时间戳等人造正文；P2 可经 transcript_segments 溯源。轻捕获无 record_file，内容直接写入此表 |
| source_version | INTEGER | 初始 1；用户每次显式保存 +1。PATCH 必须携带 expected_source_version 并原子比较，不匹配返回 409 |
| edited_by_user | INTEGER | 0/1 |
| updated_at / deleted_at | TEXT | |

**recording_sessions** — 录音会话（进行中，v2.0 新增，P0）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT | PK（会话即未来 record_id） |
| course_id | TEXT | 可空（默认 Inbox） |
| title | TEXT | 可空 |
| started_at / updated_at | TEXT | |
| state | TEXT | RECORDING / PAUSED / FINALIZING / DONE；进入 FINALIZING 后分片清单封口，不得追加或重排 |
| chunk_paths | TEXT | JSON 有序数组——cache/staging/ 分片清单（崩溃恢复与 03→04 交接用）；04 原子注册最终 Ogg 后才清理对应文件 |

**library_items** — 用户拥有的原始资料条目（本波次规划，〔软删〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT | PK |
| course_id | TEXT | FK ON DELETE SET NULL，可空；为空表示未归类 / 全局资料。移动资料不静默移动关联 Record |
| source_type | TEXT | AUDIO / DOCUMENT / WEB / BOOK / TEXT |
| title | TEXT | 用户可编辑标题，NOT NULL |
| origin_uri | TEXT | 可空；原始 URL 或导入来源标识，只用于出处，不作为离线依赖；日志不得记录敏感查询参数 |
| local_path | TEXT | 可空；数据目录内正式快照相对路径。已有 `record_files` 原件只复用，不复制字节；纯文本可直接复用正式文本来源 |
| mime_type / file_size | TEXT / INTEGER | 可空；file_size ≥0 |
| content_hash | TEXT | NOT NULL；相同哈希触发重复提示但不设 UNIQUE，用户可选择继续保留 |
| fetched_at | TEXT | 网页抓取时间，可空 |
| metadata_json | TEXT | 按 source_type 经 Pydantic 判别校验的来源专属小字段 |
| schema_version | INTEGER | metadata_json 结构版本，≥1 |
| favorite | INTEGER | NOT NULL DEFAULT 0；收藏智能视图（v3.1 调整 #3，仅条目域） |
| status | TEXT | ACTIVE / ARCHIVED；解析、分片、索引等技术状态不复制到本表 |
| created_at / updated_at / deleted_at | TEXT | 软删 30 天内可从资料条目回收站恢复 |

索引：`(course_id, updated_at desc)`、`(source_type, updated_at desc)`、`(status, updated_at desc)`、`(content_hash)`、`(deleted_at)`（v3.1 补充，回收站视图）；`library_item_records` 另有 `(record_id)` 反查索引。

**library_item_records** — 资料条目与 Record 多对多关系（本波次规划）
| 字段 | 类型 | 说明 |
|---|---|---|
| library_item_id / record_id | TEXT | 联合 PK；FK 均 ON DELETE CASCADE |
| role | TEXT | PRIMARY / SUPPLEMENTAL |
| sequence_no | INTEGER | ≥0；同一资料拆多个 Record 时保持章节 / 内容顺序 |
| created_at | TEXT | |

一个 LibraryItem 可按章派生多个 Record；一个 MULTI_SOURCE Record 可关联多个 LibraryItem。资料软删、归档或移动 Course 均不级联改变 Record 生命周期或 Course 归属。

**record_markers** — 课堂实时标记（P2）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / course_id / record_id / file_id | TEXT | |
| marker_type | TEXT | IMPORTANT / CONFUSED / NOTE |
| record_offset_ms / file_offset_ms | INTEGER | 双时间轴 |
| note | TEXT | 可空 |
| status | TEXT | ACTIVE / RESOLVED |

### 4.3 AI 产出域

**ai_summaries** — 版本化总结（P1）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / record_id | TEXT | |
| version_no | INTEGER | 与 record_id 联合唯一 |
| transcript_source_version | INTEGER | 生成输入对应的 transcripts.source_version；Summary 写回前必须校验仍为当前版本 |
| topic | TEXT | 一句话主题 |
| abstract | TEXT | 500~1000 字摘要 |
| summary_json | TEXT | 结构化分点总结 |
| status | TEXT | GENERATED / CONFIRMED / SUPERSEDED |
| model / prompt_version | TEXT | 可追溯 |
| token_usage_json | TEXT | JSON |
| latency_ms | INTEGER | |
| user_feedback | TEXT | 触发重新生成的反馈 |
| confirmed_at | TEXT | |

**knowledge_points** — 知识点（Record 级资产，P1，〔软删〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / record_id | TEXT | |
| batch_id | TEXT | 可空；同次 AI 候选批次共用，手工补充可空 |
| name / detail | TEXT | |
| tags | TEXT | JSON 数组（≤5 个） |
| importance | REAL | 1~5 |
| generated_from_summary_id | TEXT | 可空；AI 生成时绑定已确认 Summary，手工补充可空；确认批次时该 Summary 仍须 CONFIRMED |
| generation_status | TEXT | DRAFT / ACTIVE / SUPERSEDED（单列状态，2026-08-24 取消原 status 列，对齐 quizzes）；确认新批次后才将旧 AI 批次置 SUPERSEDED，用户确认/编辑的历史行不自动删除 |
| source_anchor_id | TEXT | 可空，主锚点（完整来源走 source_anchor_links；P1 恒空） |
| updated_at | TEXT | |

**quizzes** — 习题（P1，〔软删〕；2026-08-25 08 plan grill 定稿；0024 增主概念列）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / record_id | TEXT | |
| batch_id | TEXT | 同次生成批次 |
| generated_from_summary_id | TEXT | 生成批次绑定的已确认 Summary |
| generation_status | TEXT | DRAFT / ACTIVE / SUPERSEDED；已作答历史不随批次换代删除 |
| question_type | TEXT | MULTIPLE_CHOICE / TRUE_FALSE / SHORT_ANSWER；选择题单选，判断题 options 固定「对/错」两项（与选择题同构） |
| stem | TEXT | 题干 |
| options_json / correct_answer_json | TEXT | JSON；correct_answer：选择题 / 判断题 = 正确项下标，简答题 = 参考答案文本 |
| explanation | TEXT | 解析 |
| difficulty | TEXT | EASY / MEDIUM / HARD |
| user_answer_json | TEXT | 用户作答；与 answer_result / answered_at 同事务写 |
| answer_result | TEXT | 可空：CORRECT / WRONG；NULL = 简答已提交待自评（客观题提交即判分） |
| answered_at | TEXT | 可空；非空 = 已作答锁定（一题一答，不可重做） |
| concept_id | TEXT | 可空主概念（**0024 已实施**，REFERENCES concepts ON DELETE SET NULL + 索引）：生成只从同课程 CONFIRMED 概念建议、服务端校验；作答前可改/清空，首答后应用层锁定（Quiz/模拟测试题同语义），Event 固化归属；概念物理删除置空，历史行不回填 |

不建 model / prompt_version（溯源记 processing_jobs.result_json，07 先例）、quality_score（评测域 Wave B）、cognitive_level（P5）、source_anchor_id——均由后续迁移加列。（concept_id 已于 0024 落地，见上。）

**quiz_tests** — 模拟/自适应测试（P1；ADAPTIVE 模式 P5）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / course_id | TEXT | record_id 可空 |
| mode | TEXT | MOCK / ADAPTIVE |
| status | TEXT | |
| score | REAL | |
| started_at / completed_at | TEXT | |

**quiz_test_items** — 作答明细（P1）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / test_id / quiz_id | TEXT | (test_id, sequence_no) 唯一 |
| sequence_no | INTEGER | |
| user_answer_json | TEXT | |
| result | TEXT | CORRECT / WRONG / PARTIAL |
| score | REAL | |
| ai_grade_json | TEXT | 简答题 AI 评分依据（必存，不裸给分） |
| answered_at | TEXT | |

**review_materials** — 复习资料（P1，v2.3 定稿，〔软删〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / record_id | TEXT | record_id FK→records ON DELETE CASCADE |
| version_no | INTEGER ≥1 | (record_id, version_no) 唯一；仅 AI 重生成递增，手动编辑不换代 |
| transcript_source_version | INTEGER ≥1 | 过期锚点：转写已改则拒绝新提交（照 ai_summaries 绑定语义）；旧内容不删不覆盖 |
| generated_from_summary_id | TEXT | 可空；生成上下文含已确认总结时绑定，仅溯源、总结换代不阻塞 |
| quick_review | TEXT | 考前速记（Markdown，可含代码块；程序员场景默认含代码速查块） |
| key_list_json | TEXT | Top 重点清单（条数由 LLM 按内容密度决定，不固定） |
| mind_map_markdown | TEXT | Markdown 大纲（纯标题层级树 + 叶子短语，禁代码块/表格；前端树形渲染） |
| status | TEXT | GENERATED / CONFIRMED / SUPERSEDED（确认必选，确认不锁编辑） |
| model / prompt_version | TEXT | 随版本留痕 |
| user_feedback | TEXT | 可空；调整反馈 |
| token_usage_json / latency_ms | TEXT / INTEGER ≥0 | 同 ai_summaries 行上留痕 |
| confirmed_at | TEXT | 可空 |

**todo_items** — Record 级任务（P1，〔软删〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / record_id | TEXT | |
| batch_id | TEXT | 可空；同次 AI 候选批次共用，手工项可空 |
| content | TEXT | |
| status | TEXT | TODO / DONE |
| source | TEXT | AI / MANUAL |
| generated_from_summary_id | TEXT | 可空；仅 AI 来源绑定 Summary |
| generation_status | TEXT | 可空；AI 来源为 DRAFT / ACTIVE / SUPERSEDED，手工/用户修改项不自动换代 |
| sort_order | INTEGER | |
| updated_at | TEXT | |

不得与 learning_plan_items / learning_agent_actions 合表。

**record_analyses** — Record 级结构化分析（P3，课件 Diff 等）
analysis_type（COURSEWARE_DIFF / EXAM_FOCUS / OTHER）、version_no（(record_id, analysis_type, version_no) 唯一）、input_refs_json、result_json、model、prompt_version。

### 4.4 对话域

**chat_sessions**（P1，〔软删〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT | PK |
| course_id | TEXT | **可空**——COURSE 会话 = 挂载课程；RECORD 会话随 record 填其课程；LIBRARY_ITEM 可快照条目当前课程但检索授权始终以 library_item_id 为准；FREE/ALL 为空。**课程软删→会话只读（course_deleted 运行时推导，不落列，对齐 record_deleted 先例）** |
| record_id / concept_id / library_item_id | TEXT | 可空；LIBRARY_ITEM 仅由资料详情创建并必须填写 library_item_id。**挂载失效态运行时推导，不落列**：分别回查 Record / LibraryItem 当前生命周期 |
| mode | TEXT | ASK / COURSE_QA / SOCRATIC_TUTOR / TEACH_BACK |
| scope | TEXT | NOT NULL DEFAULT 'FREE'，CHECK ∈ FREE / RECORD / LIBRARY_ITEM / COURSE / ALL（LIBRARY_ITEM 本波次规划）。**范围会话内不可变**；与 mode 轴正交（mode 恒 ASK，B3 启用）。LIBRARY_ITEM=单资料及其关联 Record，COURSE=该课程全部未软删资料与记录，ALL=全部未软删资料与记录（含未归类内容） |
| title | TEXT | 可空——默认取首条用户消息截断，重命名覆盖 |
| updated_at | TEXT | |

Record Chat、Course Chat、自由聊天、Tutor、Teach-back 共用此模型，不建第二套消息体系。

**chat_messages**（P1，追加型）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / session_id | TEXT | |
| role | TEXT | USER / ASSISTANT / SYSTEM / TOOL |
| content | TEXT | |
| citations_json | TEXT | 引用条目数组（答案溯源）。record 条目 `{index, source:"record", record_id, record_title?, quote≤80, anchor_id?}`；library 条目 `{index, source:"library", library_item_id, title, quote≤80, anchor_id}`，两者都必须回业务 Segment 逐字校验并定位；web 条目 `{index, source:"web", url, title}` 仅非空检查。历史行无 source 键仍按 record 读取 |
| model | TEXT | 可空 |
| token_usage_json | TEXT | JSON，可空 |
| created_at | TEXT | 索引 (session_id, created_at) |

### 4.5 学习数据基础域（P2；learning_events P1）

> **v2.4 已实施标注**：本节前四表已随 F1 落地（迁移 0019，2026-09-10）。四表均为派生定位/引用结构（非可编辑实体）：不带 created_at / updated_at / deleted_at，生命周期随父实体 ON DELETE CASCADE。锚点两表空表就位，本期零写入者。
> **v2.6 已实施标注**：learning_events 四事件 MVP 与 learning_evidence 已随 A3 落地（迁移 0021，2026-09-14）。四事件与业务动作同事务写入（统一经 `learning.events.write_learning_event`，幂等键冲突静默跳过）；消费为独立 asyncio 水位循环（ADR-0021，不入 processing_jobs，水位 = 隐式 rowid 单调扫描、禁 NOT EXISTS 子查询）；证据可由事件流清空重放再生（event_id 唯一 = 数据库级重放幂等）；learning 域薄只读查询（按记录/课程取证据流）为 Mastery Engine 与 agent 学习上下文中间件的共同底座；concept_id 自 Concept Mastery V1（0024/0025，2026-09-18）起由 Quiz 事件固化写入（Event 原样复制进 Evidence），source_anchor_id 本期恒 NULL（锚点回填属后续溯源域）。

**transcript_segments** — 句子级转写分片（已实施）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / transcript_id / record_id / file_id | TEXT | FK 级联删除 |
| sequence_no | INTEGER | 记录内全局连续；索引 (record_id, sequence_no) |
| record_start_ms / record_end_ms | INTEGER | **可空**——课堂拼接时间轴（多文件按顺序累加，非真实墙钟） |
| file_start_ms / file_end_ms | INTEGER | **可空**——文件内时间轴；索引 (file_id, file_start_ms)、(record_id, record_start_ms) |
| speaker | TEXT | 可空，恒 NULL（说话人分离预留） |
| content / content_hash | TEXT | content_hash 供编辑增量对齐重切 |

四个时间戳列 NULL = **无时间轴来源**（全库唯一退化态）：存量回填 / in-flight 降级合并 / 编辑未命中句三场景共用同一语义（v2.4 修正——v2.3 按 NOT NULL 设计）。

**document_segments** — 文档分片（已实施）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / course_id | TEXT | course_id **可空**（收件箱导入未归类） |
| record_id | TEXT | 可空 |
| record_file_id / library_item_id | TEXT | 至少一个非空；library_item_id 为本波次新增 FK，允许直接来源分片与复用 record_file 的关联分片共存，写路径须避免为同一正文重复建 Segment |
| sequence_no / page_no / section_title | INTEGER / INTEGER / TEXT | sequence_no 记录内全局连续；page_no 可空（PDF 逐页提取、页码 1 起；DOCX/txt/md 为 NULL）；section_title 可空 |
| content / start_offset / end_offset / content_hash | TEXT / INTEGER / INTEGER / TEXT | start_offset / end_offset 可空，为相对文档全文 content 的字符偏移 |

配套 **FTS5 虚拟表** `segment_search_index(entity_type, entity_id, body)`（v2.5，迁移 0020）——entity_type ∈ {transcript_segment, document_segment}；body 为 jieba `cut_for_search` 分词串，BM25 排序；与全局搜索 `search_index` 分表（`/api/search` 不混入分片命中）。可再生衍生索引：**不计正式表数**，写入同事务先删后插、软删不触碰索引行、查询期回表过滤（ADR-0016 纪律）。

**source_anchors** — 来源锚点（已实施，空表零写入者）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / course_id | TEXT | course_id 可空；全局 / 未归类 LibraryItem 的锚点不伪造课程归属 |
| source_type | TEXT | AUDIO_SEGMENT / DOCUMENT_SEGMENT / USER_NOTE / CHAT_MESSAGE（CHECK） |
| source_id | TEXT | |
| record_id / record_file_id / library_item_id / transcript_segment_id / document_segment_id | TEXT | 可空；CHECK 精确类型匹配：AUDIO_SEGMENT 必挂 transcript_segment_id、DOCUMENT_SEGMENT 必挂 document_segment_id；资料来源锚点同时保存 library_item_id 以支持无 Record 来源回跳 |
| start_offset / end_offset / page_no | INTEGER | 可空 |

**source_anchor_links** — 多来源关联（多态，已实施）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT | PK |
| resource_type | TEXT | SUMMARY / KNOWLEDGE_POINT / QUIZ / MISCONCEPTION / CHAT_MESSAGE / RECORD_ANALYSIS / CONCEPT（CHECK） |
| resource_id | TEXT | |
| source_anchor_id | TEXT | FK 级联删除 |
| relation_type | TEXT | SUPPORTS / PRIMARY / CONTRADICTS / REFERENCES（CHECK） |

唯一约束 `(resource_type, resource_id, source_anchor_id, relation_type)`。实体表上的 `source_anchor_id` 仅为可选主锚点。

**learning_events** — 学习行为事实（追加型，不软删，已实施；**提前至 P1**，MVP 四事件：SUMMARY_CONFIRMED / KNOWLEDGE_CONFIRMED / QUIZ_ANSWERED / QUIZ_TEST_COMPLETED，#33/#43）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / course_id | TEXT | record_id / concept_id 可空 |
| event_type | TEXT | SUMMARY_CONFIRMED / KNOWLEDGE_CONFIRMED / QUIZ_ANSWERED / QUIZ_TEST_COMPLETED / TEACH_BACK_COMPLETED / TUTOR_CHECK_COMPLETED / REVIEW_VERIFIED / MARKER_CREATED / MISCONCEPTION_CONFIRMED / MISCONCEPTION_RESOLVED / PLAN_ITEM_COMPLETED / CONCEPT_MASTERED |
| source_type / source_id | TEXT | 行为来源（如 quiz_test_item） |
| result / score / difficulty / duration_ms | TEXT / REAL / TEXT / INTEGER | 一个行为只记一个事件 |
| metadata_json | TEXT | |
| idempotency_key | TEXT | **UNIQUE**（幂等）；构造格式 `{event-slug}:{source-id}`——summary-confirmed:{summary_id} / knowledge-confirmed:{batch_id} / quiz-answered:{quiz_id}（Wave B 测验同题再答另立键位） |
| schema_version | INTEGER | |
| occurred_at / created_at | TEXT | 索引 (occurred_at desc)、(concept_id, occurred_at desc)、(course_id, event_type, occurred_at desc) |

**learning_evidence** — 学习证据（追加型，已实施）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / course_id / concept_id / event_id | TEXT | event_id **唯一**（重放幂等键）；concept_id 由 Quiz 事件固化写入（Concept Mastery V1，2026-09-18），无归属为 NULL |
| evidence_type | TEXT | QUIZ / RECALL / TEACH_BACK / TUTOR_CHECK / TRANSFER / CLASSROOM_SIGNAL / USER_CONFIRMATION |
| result / score / difficulty | | |
| weight / confidence | REAL | 0~1；AI_SYNTHESIS 不作为证据类型 |
| source_anchor_id | TEXT | 可空，本期恒 NULL（锚点回填属后续溯源域） |
| metadata_json | TEXT | |
| occurred_at / created_at | TEXT | 索引 (concept_id, occurred_at desc)；**唯一约束 (event_id)**（v2.6 由普通索引收紧） |

### 4.6 Course Brain 域（concepts / concept_relations / record_concepts 已实施；semantic_embeddings 未建）

> **✅ 已实施回写（2026-09-16，F4 Course Brain V1 完结，迁移 0023，ADR-0022）**：三表结构与 `source_anchor_links.resource_type='CONCEPT'` 值域扩展以本节为准；构建 / 审核 / 检索全链见 `backend/app/modules/course_brain/`。

**concepts** — 课程级规范概念（已实施；无 deleted_at——ARCHIVED 即退役语义，候选忽略亦置 ARCHIVED）
id、course_id（FK CASCADE）、canonical_name（1~100）、normalized_name（应用层确定性函数：strip → 空白折叠 → 全角转半角 → casefold）、description、concept_type（默认 TERM）、importance（1~5，默认 3）、status（CANDIDATE / CONFIRMED / ARCHIVED）、source（AI_EXTRACTED / USER_CONFIRMED / SYSTEM）、created_at / updated_at。
唯一性：**部分唯一索引** `CREATE UNIQUE INDEX idx_concepts_course_confirmed ON concepts(course_id, normalized_name) WHERE status='CONFIRMED'`——CONFIRMED 落定唯一由库级兜底（v2.7「SQLite 无部分唯一索引」论断有误，已更正；0017 重建表时已有部分索引先例）；Candidate 阶段允许同义/重复进入 Resolution。重建不覆盖：normalized_name 与既有 CONFIRMED 概念一致者只增量挂接，名称/描述任何路径不可改（CB-04/CB-05）。

**concept_relations** — 概念关系（已实施）
id、course_id（FK CASCADE）、source_concept_id / target_concept_id（FK CASCADE，CHECK source≠target）、relation_type（PREREQUISITE / PART_OF / RELATED_TO / COMPARE_WITH / CAUSES / APPLIES_TO）、confidence（0~1）、evidence_count、status（CANDIDATE / CONFIRMED / DISMISSED）、created_at / updated_at；(source_concept_id, target_concept_id, relation_type) 唯一。DISMISSED 不被重建复活；CONFIRMED 关系 stale（最近一次成功构建零证据支撑）查询期派生徽章，不落库、不自动降级（CB-06）。

**record_concepts** — 记录-概念出现索引（已实施）
(record_id, concept_id) 唯一；knowledge_point_id 可空（KP→Concept Resolution 桥，ON DELETE SET NULL）；relevance（0~1）、evidence_count、first_start_ms（可空，最早出现时间）、created_at / updated_at。（草案中的 importance 列未建——概念重要度只在 concepts.importance。）

**semantic_embeddings** — 统一向量索引（**未实施**；CB-01 合成评测四维全过 → sqlite-vec 延后，见 `docs/evaluation/course-brain-retrieval-baseline.md`；升级路径 = concepts.terms 同义词列 / query-time LLM 扩展 / CB-VEC 票）
| 字段 | 类型 | 说明 |
|---|---|---|
| rowid | INTEGER | PRIMARY KEY；与 vec0 虚拟表 rowid 显式一致，作为可重建索引内部键 |
| id | TEXT | UNIQUE NOT NULL；应用层逻辑 id，不承担 vec0 整数键职责 |
| course_id | TEXT | **可空**——未分类/Inbox 内容照常入索引；@全部资料全局 RAG 即全库检索 |
| library_item_id / record_id / record_file_id | TEXT | 可空；向量若经评测启用，必须能回到 LibraryItem 与当前业务 Segment |
| source_type | TEXT | TRANSCRIPT_SEGMENT / DOCUMENT_SEGMENT / KNOWLEDGE_POINT / CONCEPT |
| source_id | TEXT | |
| content_hash | TEXT | 内容变更检测（hash 变则重嵌入） |
| embedding_model | TEXT | 当前 text-embedding-v3（换模型全量重嵌入） |
| metadata_json | TEXT | |
| deleted_at | TEXT | 软删标记，检索必过滤 |

配套 **vec0 虚拟表** `semantic_embeddings_vec(rowid, embedding float[1024])`——rowid 与上表显式 INTEGER PRIMARY KEY 一致；KNN 查询后必须回元数据表做作用域、生命周期与来源类型过滤，再回业务 Segment 取逐字引用。Knowledge Point / Concept 向量命中只能进入 `asset_matches` / `concept_hints`，不得成为 `evidence_hits`。统一表的意义是让向量失效与删除只有一个管理入口；它仍是可重建派生索引。

### 4.7 Learner Brain 域（P4）

**user_concept_mastery** — concept_id 唯一（表名历史命名，保留）——**P4 提前已实施**（0025，2026-09-18，Concept Mastery V1）
> **已实施结构**：course_id（FK CASCADE）/ concept_id（**UNIQUE**，FK CASCADE）/ mastery_score / mastery_confidence（均可空，0~1 CHECK）/ evidence_count / positive_evidence_count / negative_evidence_count（≥0 CHECK）/ last_practiced_at / last_verified_at / **algorithm_version** / updated_at。V1 不显示伪精确：<3 条有效证据 = NOT_ENOUGH_DATA，分数与置信度置空。**仅建 V1 真实使用列**——草案中的 memory_strength / transfer_score / reasoning_score / next_review_at / last_learned_at 未建，Forgetting / Transfer / Reasoning 落地时再迁移；Concept 物理删除级联清快照，归档保留快照但退出活跃聚合。
**唯一写入口 = Mastery Engine**（红线 #3；ADR-0023：确定性派生、证据可全量重建）。

**misconceptions**
type（KNOWLEDGE_GAP / MISCONCEPTION / MEMORY_DECAY / REASONING_GAP / PREREQUISITE_GAP / UNKNOWN）、title、description、confidence、evidence_count、status（SUSPECTED / CONFIRMED / RESOLVED / DISMISSED）、first_detected_at / last_detected_at / confirmed_at / resolved_at。

**misconception_evidence** — (misconception_id, learning_evidence_id) 唯一；support_score。

**review_schedules** — concept_id 唯一
scheduler_type（RULE_V1 / FSRS）、stability / difficulty / retrievability 可空、last_review_at / next_review_at / last_result / review_count、priority_score。

**learner_preferences** — 单行表
id（固定 `me`）、user_selected_preference（JSON）、observed_learning_preference（JSON）、observed_confidence（0~1）、evidence_count、last_observed_at、updated_at。用户显式选择可直接编辑；观察偏好只可由结构化学习证据或用户明确“记住”产生提案，确认后写入。推测偏好不得覆盖用户选择；普通聊天不得静默提取。

Learner Memory V1 不复制 `user_concept_mastery`、`misconceptions` 或 `learning_goals`。`LearnerProfileService` 按任务与会话范围聚合偏好、掌握度、误区、近期 Evidence 与目标，生成限长的可重建 Learner Context；Course 状态不得越界注入。设置页单独控制是否允许把长期记忆发送给外部 LLM。

### 4.8 Adaptive / Planner 域

**teach_back_attempts**（P5）：concept_id、session_id（复用 chat_sessions）、transcript、coverage/reasoning/accuracy_score、confidence、result_json、started_at / completed_at。

**learning_goals**（P6）：goal_type、title、target_date、target_score、daily_minutes、exam_scope_json、scope_source（USER_CONFIRMED / TEACHER_DOCUMENT / COURSE_SELECTION / AI_INFERRED）、scope_confirmed（AI_INFERRED 必须用户确认）、status（ACTIVE / COMPLETED / ARCHIVED）。

**learning_plans**（P6）：(goal_id, plan_version) 唯一；status（ACTIVE / SUPERSEDED / COMPLETED）、effective_from / effective_to。

**learning_plan_items**（P6）：plan_id、concept_id 可空、action_type（含 PREVIEW）、priority、estimated_minutes、scheduled_date、status、user_locked、reason_json。

**learning_agent_actions**（P6）：action_type（REVIEW_CONCEPT / START_ADAPTIVE_ASSESSMENT / VERIFY_MISCONCEPTION / TEACH_BACK / START_TUTOR / READ_EVIDENCE / CONTINUE_PLAN_ITEM / COMPLETE_TODO / REST）、reason_code、priority（0~100）、estimated_minutes、confidence、input_snapshot_json、decision_json、status（RECOMMENDED / ACCEPTED / SKIPPED / DEFERRED / RUNNING / COMPLETED / FAILED）、recommended_at / accepted_at / started_at / completed_at。

**learning_agent_feedback**（P6）：action_id、feedback_type、rating、comment、actual_minutes、perceived_helpfulness。

### 4.9 Outcome 域

**learning_passport_snapshots**（P7）：snapshot_type（MONTHLY / SEMESTER / PRE_EXAM / COURSE_COMPLETED / MANUAL）、snapshot_date、mastered_count / learning_count / at_risk_count、summary_json、evidence_summary_json。

### 4.10 Agent 提案域

**agent_proposals** — 可跨重启审核的业务提案（本波次规划）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT | PK |
| proposal_type | TEXT | ORGANIZE / MEMORY / RESEARCH_INGEST，V1 固定枚举 |
| status | TEXT | PENDING / APPLIED / REJECTED / FAILED |
| session_id / message_id | TEXT | 可空；提案来自对话时记录来源，不作为执行授权 |
| target_type / target_id | TEXT | 可空；目标 LibraryItem、Course 或 LearnerPreference |
| payload_json | TEXT | 按 proposal_type 经 Pydantic 判别校验的建议内容；禁止放任意 SQL / 文件路径 / Shell 命令 |
| evidence_refs_json | TEXT | 可空；观察偏好等提案的结构化证据引用与计数 |
| error_code | TEXT | 可空；应用失败时保留稳定错误码供重试或拒绝 |
| created_at / decided_at | TEXT | decided_at 在应用或拒绝时填写 |

提案创建不改变业务事实；用户确认后由对应领域 Service 执行并原子更新状态。它不是 LangGraph Interrupt 或 Checkpoint，不能被 Agent 当作直接写库通道。

### 4.11 基础设施域

**processing_jobs** — 技术任务状态 + **任务队列本体（v2.0 自研队列，#1/#55）**（P0）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT | PK |
| record_id / library_item_id | TEXT | 可空；资料入库、网页抓取、回填或索引任务可直接关联 library_item_id |
| job_type | TEXT | ASR / AUDIO_TRANSCODE / DOCUMENT_PARSE / WEB_FETCH / LIBRARY_BACKFILL / INDEX_REBUILD / EMBEDDING / CONCEPT_EXTRACTION / SUMMARY / CLEANUP / BACKUP_EXPORT / … |
| status | TEXT | PENDING / RUNNING / SUCCEEDED / FAILED / CANCELLED |
| progress | REAL | 0~1 |
| attempts / max_attempts | INTEGER | 当前重试轮次的尝试次数/上限；DOCUMENT_PARSE 与 ASR 安全瞬态故障每轮最多 3 次，首次执行计入；等待条件不计数 |
| next_run_at | TEXT | 可空——退避重试调度 |
| waiting_reason | TEXT | 可空；PENDING 等待条件：CONSENT_REQUIRED / ASR_KEY_REQUIRED / OFFLINE，不作为失败错误码 |
| input_json / result_json | TEXT | 按 job_type 使用类型化结构；DOCUMENT_PARSE input 含 record_file_id。ASR input 固化 record_file_id、切片 manifest（index/起止/cache_path/hash）及非秘密配置快照；result 持久化 task id、切片状态/尝试次数/临时正文与恢复游标，禁止保存 SecretId/SecretKey |
| error_code / error_message | TEXT | 稳定 error_code 决定可重试性；正文不得进入错误或日志 |
| started_at / finished_at | TEXT | |

worker = sidecar 进程内单任务执行器：轮询可运行 PENDING（`next_run_at` 到期且无 waiting_reason）→ 原子置 RUNNING → 执行 → 落检查点/结果/退避。未同意、缺 key 或离线仍为 PENDING，`waiting_reason` 分别为 CONSENT_REQUIRED / ASR_KEY_REQUIRED / OFFLINE，不增加 attempts；条件满足后自动解除等待。可恢复失败且额度未耗尽时 `RUNNING→PENDING`，额度耗尽或确定性失败时 `RUNNING→FAILED`；同一 Record 任一 Job 终态失败后暂停领取其余 PENDING Job，其他 Record 继续。删除 Record 时 PENDING/RUNNING→CANCELLED。

DOCUMENT_PARSE 手动重试沿用 v2.1：复用原 Job、attempts 归零并清空旧 result/progress/error。ASR 手动重试同样复用原 Job并开启新 3 次窗口，但保留成功切片、仍有效 task id 与切片累计 attempts，只重置失败/过期/未提交片；提交超时且无 task id 不自动重提。每次取得腾讯 task id 后须先持久化 result_json 再继续；重启时成功片跳过、已有 task id 只恢复轮询。全部来源成功后才单事务发布 Transcript；成功后 result_json 移除临时正文，仅留任务元数据/耗时/字符数/hash，并清理 cache。与 `records.status` 的分工不变：后者是业务态，processing_jobs 是技术状态唯一事实源。

**llm_call_logs** — LLM 调用观测（P0，追加型）
request_id、graph_name、graph_node、model、prompt_version、embedding_model、token_usage_json、latency_ms、retrieval_count、evidence_count、interrupt_count、error_code、created_at。
（决策 #2：以自建表替代 Sentry/OTel/Langfuse 自托管。）

---

## 5. 数据目录与配置文件（v2.0：取代原"SQLite 本地表"）

```
%USERPROFILE%\KnowRealm\           ← 数据目录（首启选择，可换；检测同步盘接管）
├── .knowrealm.lock                 # sidecar 运行期锁对象；必须由 OS 排他锁持有，不能只靠易残留 sentinel 判断
├── knowrealm.db                   # §4 全部业务表（WAL）——唯一事实源
├── langgraph.db                   # LangGraph Checkpoint（SqliteSaver 自管，非业务事实）
├── files/                         # 存档原件（明文，#49）
│   ├── {record_id}/{file_id}.{ext}
│   ├── library/{library_item_id}/source.{ext} # 新资料正式快照；已有 record_file 原件只引用不复制
│   └── avatars/…
├── cache/                         # 可清可重建：转码产物、ASR 片、staging/ 录音分片（最终 Ogg 原子注册后删）
├── exports/                       # 全量导出 zip 输出（db 快照 + files + config，默认不含密钥）
├── backups/                       # 启动滚动备份（db 每日一份 × 7，自动清理）
└── config/
    ├── settings.json              # 偏好+本机行为（theme/font_scale/locale/timezone/
    │                              #   close_behavior/autostart/capture_hotkey/
    │                              #   last_learning_context/quiz_last_count/window_bounds）
    │                              # + external_processing_consents.tencent_asr.accepted_at
    └── providers.json             # 供应商卡（LLM 端点+key+model / 腾讯 ASR key）——明文
```

原 v1.x 本地十表（local_record_drafts / local_files / cached_* / sync_outbox / sync_cursor / local_settings）**整体删除**——本地即事实源后无"缓存/上传队列/游标"概念：录音会话恢复由 `recording_sessions` 承载，浏览缓存由 TanStack Query 内存承担。

## 6. LangGraph 框架表（langgraph.db）

由 SqliteSaver 自管（checkpoints/checkpoint_writes 等）。规则：不手工查询、不在业务层依赖其内部字段、Graph State 只存运行状态；确认结果、版本链等长期事实必须落业务表（如 ai_summaries）。与业务库同目录、不同文件；全量导出可选包含（含亦无害）。

## 7. 备份、导出与换机（v2.0：取代原"云端与本地同步"）

| 场景 | 机制 |
|------|------|
| 日常防损 | app 启动时 `VACUUM INTO` 快照 db → `backups/`（每日一份 × 7 自动清理）；WAL 模式 |
| 全量导出（V1，Wave B） | zip = db 快照（VACUUM INTO）+ files/ + config/（**默认不含 providers.json，可选勾选含**）；必须包含资料条目、关联、本地快照和 Learner Memory 业务事实；输出至 exports/ 与用户选定位置 |
| 换机恢复 | 新机首启 → 选空数据目录 → 从导出包导入 → 校验落位（向量索引在 db 内，一体迁移） |
| 快照备份（P2） | 可选配置 WebDAV/S3 → 定期单向推送导出 zip；**无回写路径**（红线 #1） |
| 冲突处理 | 同一数据目录的操作系统排他锁保证单写者；第二个 sidecar 在迁移/worker 前失败并提示目录正被使用。进程退出或崩溃由 OS 自动释放锁；原 409/乐观锁机制随同步概念删除 |

### 7.1 本波次升级与存量回填

1. 升级前先对 `knowrealm.db` 做独立 `VACUUM INTO` 快照，成功后才执行 schema migration；schema migration 失败即停止启动并保留快照，不启动 worker。
2. migration 只创建 / 调整表、约束与索引，不在启动事务内扫描并重写全部存量 Record。
3. 启动成功后由 `LIBRARY_BACKFILL` 后台任务按稳定游标幂等建立 LibraryItem 与 `library_item_records` 关系；存量 Record 在未回填期间继续按原路径可用。
4. 回填失败只记录稳定错误码并允许重试；不得删除、移动或改写旧 `record_files`、Transcript、Segment 与 Record 关系。索引失败可由 `INDEX_REBUILD` 重建，不影响业务事实。

## 8. 功能 → 业务实体 → 数据表映射

| 功能 | 业务实体 | 表 | 阶段 |
|------|---------|-----|------|
| 首启四步（语言/目录/key/角色卡） | — | config/ + profile | MVP |
| 偏好设置 | — | config/settings.json | MVP |
| 学习统计 | —（聚合） | records/quizzes/chat_messages 等聚合查询 | MVP |
| 课程管理 | Course | courses | MVP |
| 收件箱 Inbox | Record（course_id 为空） | records（course_id NULL） | MVP |
| ⚡速记 | Record(NOTE)+Transcript | records(QUICK_NOTE, NOTE)、transcripts | MVP |
| 📋粘贴长文本 | Record+Transcript | records(PASTE)、transcripts | MVP |
| 统一资料库 | LibraryItem + Record 关系 | library_items、library_item_records | 本波次规划 |
| 🔗网页剪藏 | LibraryItem + 可选 Record/Transcript | library_items(WEB)、records(CLIP)、transcripts、processing_jobs(WEB_FETCH) | 本波次规划 |
| 课堂录音（会话） | Record+RecordingSession | records、recording_sessions | MVP |
| 录音/导入文件 | RecordFile | record_files + files/ 目录 | MVP |
| 音频转码任务 | Job | processing_jobs(AUDIO_TRANSCODE) | MVP |
| ASR 转写 | Transcript | transcripts、processing_jobs | MVP |
| 文档解析 | Transcript 前身 | transcripts（整段）、processing_jobs | MVP |
| 转写编辑 | Transcript | transcripts | MVP |
| AI 总结 + HITL | Summary | ai_summaries + langgraph.db | MVP |
| 知识点提取 | KnowledgePoint | knowledge_points | MVP |
| 习题生成 | Quiz | quizzes | MVP |
| 模拟测试 | QuizTest | quiz_tests、quiz_test_items | MVP |
| 复习资料 | ReviewMaterial | review_materials | MVP |
| Todo | TodoItem | todo_items | MVP |
| 💬 AI 对话（自由/挂载） | ChatSession/Message | chat_sessions、chat_messages（本波次增加 LIBRARY_ITEM 范围） | MVP / 本波次扩展 |
| 对话转学习资产 | KP/Quiz | knowledge_points / quizzes + source_anchor_links(CHAT_MESSAGE) | P2 |
| Concept 掌握度（Knowledge GPS / 脑图标记） | Mastery | user_concept_mastery + learning_evidence（只读聚合） | P2 已实施（V1） |
| 状态通知 | — | records.status + processing_jobs（sidecar SSE） | MVP |
| 后台任务观测 | Job | processing_jobs | MVP |
| LLM 观测 | — | llm_call_logs | MVP |
| 全量导出/导入 | — | 数据目录打包/落位 | MVP(Wave B) |
| 快照备份 | — | processing_jobs(BACKUP_EXPORT) → WebDAV/S3 | P2 |
| 句子级溯源 | Segment/Anchor | transcript_segments、source_anchors、source_anchor_links | P2 |
| 文档分片 | DocumentSegment | document_segments | P2 |
| 课堂标记 | Marker | record_markers | P2 |
| 学习事件/证据 | Event/Evidence | learning_events、learning_evidence | MVP(四事件) / P2(evidence) |
| 资料库 RAG | —（检索服务） | LibraryItem + Segment FTS + Concept；semantic_embeddings + vec0 仅在真实评测触发后加入 | 本波次规划 |
| @全部资料全局 RAG | —（RAG） | LibraryRetrievalService（ALL 作用域） | 本波次规划 |
| 概念图谱 | Concept | concepts、concept_relations、record_concepts | P3 |
| 课件差异分析 | RecordAnalysis | record_analyses | P3 |
| Course Chat | ChatSession | chat_sessions(COURSE_QA) | P3 |
| Knowledge GPS | —（聚合） | concepts + user_concept_mastery 聚合 | P3/P4 |
| 掌握度 | Mastery | user_concept_mastery（Mastery Engine 唯一写入） | P4 |
| 误区诊断 | Misconception | misconceptions、misconception_evidence | P4 |
| 遗忘/复习调度 | ReviewSchedule | review_schedules | P4 |
| Learner Memory V1 / 数字孪生 | —（运行时视图） | learner_preferences + Mastery / Misconception / Goal 聚合 | 本波次规划 / P4 扩展 |
| Agent 业务提案 | AgentProposal | agent_proposals | 本波次规划 |
| Socratic Tutor | ChatSession | chat_sessions(SOCRATIC_TUTOR) | P5 |
| Teach-back | TeachBackAttempt | teach_back_attempts | P5 |
| 自适应测验 | QuizTest | quiz_tests(ADAPTIVE) | P5 |
| 课前预习 | LibraryItem | library_items、learning_plan_items(PREVIEW) | P5 |
| 学习目标/计划 | Goal/Plan | learning_goals、learning_plans、learning_plan_items | P6 |
| Autopilot | AgentAction | learning_agent_actions、learning_agent_feedback | P6 |
| Learning Passport | Snapshot | learning_passport_snapshots | P7 |
| 学习资产 Markdown 导出 | — | 无需表（前端基于 sidecar API 响应组装 .md，并通过 Tauri 写文件） | MVP |

## 9. 删除与数据一致性策略

删除 Record 时的清理链（功能基线 §6.5）：

1. 软删：record 及其全部子资产（files/transcript/segments/anchors/summaries/kp/quizzes/todo），同事务将该 Record 的 PENDING/RUNNING processing_jobs 置为 CANCELLED，已终态 Job 保留原状态，并立即清理该 Record 的 cache 暂存；worker 每次写前校验 deleted_at，迟到结果不得写回——**chat_sessions/chat_messages 不级联**：挂载会话保留可读、标记"原记录已删除"失效态（运行时推导，v1.11），仅显式删会话才删消息（#40）
2. 文件：`files/{record_id}/` 目录异步物理删除（30 天批次）
3. 向量：若已启用，`semantic_embeddings.deleted_at` 标记 → 同批次物理清理（含 vec0 行）；一般业务行仍按 30 天异步清理。LibraryItem 是本波次唯一新增恢复 UI 的对象，30 天内可从资料条目回收站恢复
4. 学习状态：该 Record 产生的 learning_evidence 按 record_id **排除出掌握度计算**（行保留作审计），受影响 Concept 由 Mastery Engine 异步重算（#18）
5. 删除 Course：级联其下全部 Record 走上述链路；Concept 及 Mastery 状态同规则重算

LibraryItem 生命周期独立于 Record / 学习资产：

1. 归档或软删 LibraryItem 不级联删除、归档或移动关联 Record；`LibraryRetrievalService` 不再召回该 LibraryItem 自身，但仍可通过未删除 Record 的 Segment 回答并引用 Record。
2. 资料条目回收站只展示 LibraryItem，保留 30 天；Record 与学习资产沿用各自既有删除行为，不混入该回收站。
3. 仍有未删除 Record 引用时禁止物理删除 LibraryItem；30 天到期只清理无活跃引用的条目与其独占快照。复用 `record_files` 的原件不得因 LibraryItem 清理被删除。
4. LibraryItem 所属 Course 被删除时仅将 `library_items.course_id` 置空；关联 Record 的 Course 与生命周期不受影响。

## 10. 数据库完整性约束清单（CHECK 摘要）

```
0 ≤ mastery_score / mastery_confidence / memory_strength / confidence / weight / quality_score / progress ≤ 1
0 ≤ priority ≤ 100        duration_ms ≥ 0        file_size ≥ 0
sequence_no ≥ 0           evidence_count ≥ 0     attempts ≥ 0
document_segments: record_file_id / library_item_id 至少一个非空；同一正文不得重复建 Segment
source_anchors: AUDIO_SEGMENT 必挂 transcript_segment_id、DOCUMENT_SEGMENT 必挂 document_segment_id（精确类型匹配，v2.4 收紧）
learning_events.idempotency_key 全表唯一
record_id+version_no、concept_id（mastery/review）、goal_id+plan_version 等复合唯一（见各表）
状态字段受控枚举（CHECK 或应用层 Enum 注册）
```

## 11. 建表阶段规划

| 阶段 | 建表 |
|------|------|
| P0（**Wave A 基线含 P1 前排表共 15 张**） | profile、courses、records、record_files、transcripts、recording_sessions、processing_jobs、llm_call_logs、ai_summaries、knowledge_points、quizzes、todo_items、chat_sessions、chat_messages、learning_events |
| P1 补（Wave B） | quiz_tests、quiz_test_items、review_materials |
| P2 / 本波次 | transcript_segments、document_segments、source_anchors、source_anchor_links、record_markers、learning_evidence；library_items、library_item_records、agent_proposals；semantic_embeddings（+vec0）仅评测触发 |
| P3 | concepts、concept_relations、record_concepts（**三表已实施 0023，提前于 P2 系列表部分落地后**）、record_analyses（未建） |
| P4 | user_concept_mastery、misconceptions、misconception_evidence、review_schedules；learner_preferences 随 Learner Memory V1 提前到本波次 |
| P5 | teach_back_attempts |
| P6 | learning_goals、learning_plans、learning_plan_items、learning_agent_actions、learning_agent_feedback |
| P7 | learning_passport_snapshots |
| 暂缓 | ~~shares~~（不建）、study_pods 系列（P8） |

langgraph.db 随 P0 初始化（SqliteSaver 建表）。

## 12. 数据模型待确认问题

| # | 问题 | 关联 |
|---|------|------|
| Q6 | 录音 POC（含本地 ffmpeg 转码实测）结果回填 | 功能基线 §11-Q6 |
| Q11 | embedding 维度 1024 已定稿；若未来更换模型需全量重嵌入的迁移窗口策略 | 已知成本 |
