# KnowRealm-AI 数据模型 v2.3

> **文档定位**：KnowRealm-AI 的**唯一数据模型基线**，与《功能需求基线 v2.7》配套。表设计冲突已按功能基线 §10 决策记录定稿；技术栈约束见 `技术栈设计与审查-v4.5.md`。
> **核心原则（v2.0 范式，ADR-0001 / 决策 #55）**：
> - **SQLite（knowrealm.db，WAL）= 唯一业务事实源**——全部业务实体、学习状态、向量、技术任务状态
> - **LangGraph Checkpoint（langgraph.db，独立文件）= Agent 运行态**（框架自管，非业务事实）
> - **云端（P2 可选）= 只读快照副本**——永不回写、永不双向同步
>
> 本文只做设计，不含迁移 SQL，不开始实现。
> **编写日期**：2026-08-17
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
| 课程与记录（7） | courses, records, record_files, transcripts, recording_sessions, course_materials*, record_markers | P0×5 / P5 / P2 |
| AI 产出（8） | ai_summaries, knowledge_points, quizzes, quiz_tests, quiz_test_items, review_materials, todo_items, record_analyses | P1×7 / P3 |
| 对话（2） | chat_sessions, chat_messages | P1 |
| 学习数据基础（6） | transcript_segments, document_segments, source_anchors, source_anchor_links, learning_events, learning_evidence | P2（learning_events 提前 **P1**，#33） |
| Course Brain（4） | concepts, concept_relations, record_concepts, semantic_embeddings（+vec0 虚拟表） | P3 / P3 / P3 / P2 |
| Learner Brain（5） | user_concept_mastery*, misconceptions, misconception_evidence, review_schedules, learner_preferences | P4 |
| Adaptive / Planner（6） | teach_back_attempts, learning_goals, learning_plans, learning_plan_items, learning_agent_actions, learning_agent_feedback | P5 / P6×5 |
| Outcome（1） | learning_passport_snapshots | P7 |
| 基础设施（2） | processing_jobs（兼任务队列）, llm_call_logs | P0 |
| 暂缓 | ~~shares~~（不建，分享=Markdown 本地导出）、study_pods 系列（P8） | — |

正式表合计 **42 张**（v2.0：-user_settings +recording_sessions；表名 user_concept_mastery 为历史命名，语义=概念掌握度，更名成本大于收益，保留）。**Wave A 基线 15 张**：profile / courses / records / record_files / transcripts / recording_sessions / processing_jobs / llm_call_logs / ai_summaries / knowledge_points / quizzes / todo_items / chat_sessions / chat_messages / learning_events。

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

**course_materials** — 课程级资料（P5，〔软删〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / course_id | TEXT | |
| linked_record_id | TEXT | 可空 |
| purpose | TEXT | COURSEWARE / PREVIEW / REFERENCE |
| file_path / original_name / mime_type / file_size / content_hash | 同 record_files | |
| processing_status | TEXT | |

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

**quizzes** — 习题（P1，〔软删〕；2026-08-25 08 plan grill 定稿）
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

不建 model / prompt_version（溯源记 processing_jobs.result_json，07 先例）、quality_score（评测域 Wave B）、cognitive_level（P5）、concept_id（P3 起回填）、source_anchor_id——均由后续迁移加列。

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
| course_id | TEXT | **可空**——空 = 无挂载自由会话；@课程挂载时填；@记录挂载时随 record 填其课程 |
| record_id / concept_id | TEXT | 可空（**挂载失效态运行时推导，不落列**——v1.11 裁决：JOIN records.deleted_at 判断） |
| mode | TEXT | ASK / COURSE_QA / SOCRATIC_TUTOR / TEACH_BACK |
| title | TEXT | 可空——默认取首条用户消息截断，重命名覆盖 |
| updated_at | TEXT | |

Record Chat、Course Chat、自由聊天、Tutor、Teach-back 共用此模型，不建第二套消息体系。

**chat_messages**（P1，追加型）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / session_id | TEXT | |
| role | TEXT | USER / ASSISTANT / SYSTEM / TOOL |
| content | TEXT | |
| citations_json | TEXT | Source Anchor 引用（答案溯源） |
| model | TEXT | 可空 |
| token_usage_json | TEXT | JSON，可空 |
| created_at | TEXT | 索引 (session_id, created_at) |

### 4.5 学习数据基础域（P2；learning_events P1）

**transcript_segments** — 句子级转写分片
| 字段 | 类型 | 说明 |
|---|---|---|
| id / transcript_id / record_id / file_id | TEXT | |
| sequence_no | INTEGER | 索引 (record_id, sequence_no) |
| record_start_ms / record_end_ms | INTEGER | 课堂全局时间轴 |
| file_start_ms / file_end_ms | INTEGER | 文件内时间轴 |
| speaker | TEXT | 可空（说话人分离预留） |
| content / content_hash | TEXT | 索引 (file_id, file_start_ms)、(record_id, record_start_ms) |

**document_segments** — 文档分片
| 字段 | 类型 | 说明 |
|---|---|---|
| id / course_id | TEXT | |
| record_id | TEXT | 可空 |
| record_file_id / course_material_id | TEXT | 二者**必须且只能一个非空**（CHECK） |
| sequence_no / page_no / section_title | INTEGER / INTEGER / TEXT | page_no 可空（PyMuPDF 提供页码） |
| content / start_offset / end_offset / content_hash | TEXT / INTEGER / INTEGER / TEXT | |

**source_anchors** — 来源锚点
| 字段 | 类型 | 说明 |
|---|---|---|
| id / course_id | TEXT | |
| source_type | TEXT | AUDIO_SEGMENT / DOCUMENT_SEGMENT / USER_NOTE / CHAT_MESSAGE |
| source_id | TEXT | |
| record_id / record_file_id / course_material_id / transcript_segment_id / document_segment_id | TEXT | 可空，但 Audio/Document 来源至少关联一个具体 Segment |
| start_offset / end_offset / page_no | INTEGER | 可空 |

**source_anchor_links** — 多来源关联（多态）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT | PK |
| resource_type | TEXT | SUMMARY / KNOWLEDGE_POINT / QUIZ / MISCONCEPTION / CHAT_MESSAGE / RECORD_ANALYSIS |
| resource_id | TEXT | |
| source_anchor_id | TEXT | FK |
| relation_type | TEXT | SUPPORTS / PRIMARY / CONTRADICTS / REFERENCES |

唯一约束 `(resource_type, resource_id, source_anchor_id, relation_type)`。实体表上的 `source_anchor_id` 仅为可选主锚点。

**learning_events** — 学习行为事实（追加型，不软删；**提前至 P1**，MVP 四事件：SUMMARY_CONFIRMED / KNOWLEDGE_CONFIRMED / QUIZ_ANSWERED / QUIZ_TEST_COMPLETED，#33/#43）
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

**learning_evidence** — 学习证据（追加型）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / course_id / concept_id / event_id | TEXT | |
| evidence_type | TEXT | QUIZ / RECALL / TEACH_BACK / TUTOR_CHECK / TRANSFER / CLASSROOM_SIGNAL / USER_CONFIRMATION |
| result / score / difficulty | | |
| weight / confidence | REAL | 0~1；AI_SYNTHESIS 不作为证据类型 |
| source_anchor_id | TEXT | 可空 |
| metadata_json | TEXT | |
| occurred_at / created_at | TEXT | 索引 (concept_id, occurred_at desc)、(event_id) |

### 4.6 Course Brain 域

**concepts** — 课程级规范概念（P3）
canonical_name、normalized_name、description、concept_type、importance、status（CANDIDATE / CONFIRMED / ARCHIVED）、source（AI_EXTRACTED / USER_CONFIRMED / SYSTEM）、updated_at。
唯一性：应用层保证 `status='CONFIRMED'` 下 (course_id, normalized_name) 唯一——Candidate 阶段允许同义/重复进入 Resolution（SQLite 无部分唯一索引，CONFIRMED 落定时代码校验）。

**concept_relations**（P3）
source/target_concept_id、relation_type（PREREQUISITE / PART_OF / RELATED_TO / COMPARE_WITH / CAUSES / APPLIES_TO）、confidence（0~1）、evidence_count、status（CANDIDATE / CONFIRMED / DISMISSED）。

**record_concepts**（P3）
(record_id, concept_id) 唯一；knowledge_point_id 可空（KP→Concept Resolution 桥）；relevance、importance、first_start_ms、evidence_count。

**semantic_embeddings** — 统一向量索引（P2 起；sqlite-vec 承载）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT | PK（同时为向量表 rowid 锚，见下） |
| course_id | TEXT | **可空**——未分类/Inbox 内容照常入索引；@全部资料全局 RAG 即全库检索 |
| record_id / record_file_id / course_material_id | TEXT | 可空 |
| source_type | TEXT | TRANSCRIPT_SEGMENT / DOCUMENT_SEGMENT / KNOWLEDGE_POINT / CONCEPT |
| source_id | TEXT | |
| content_hash | TEXT | 内容变更检测（hash 变则重嵌入） |
| embedding_model | TEXT | 当前 text-embedding-v3（换模型全量重嵌入） |
| metadata_json | TEXT | |
| deleted_at | TEXT | 软删标记，检索必过滤 |

配套 **vec0 虚拟表** `semantic_embeddings_vec(rowid, embedding float[1024])`——rowid 与上表 INTEGER rowid 关联；KNN 查询 + `deleted_at IS NULL` 前置过滤在检索封装层实现（个人万级 segment 暴力 KNN 足够，无需 ANN 索引）。统一表的意义：向量生命周期（嵌入/失效/删除）单一管理，与业务软删策略一致；**向量随 db 文件一体备份/导出/迁移——sqlite-vec 单文件红利（#55）**。

### 4.7 Learner Brain 域（P4）

**user_concept_mastery** — concept_id 唯一（表名历史命名，保留）
mastery_score / mastery_confidence / memory_strength（0~1 CHECK）；transfer_score / reasoning_score 可空；evidence_count / positive_evidence_count / negative_evidence_count（≥0）；last_learned_at / last_practiced_at / last_verified_at / next_review_at；updated_at。
**唯一写入口 = Mastery Engine**（红线 #3）。

**misconceptions**
type（KNOWLEDGE_GAP / MISCONCEPTION / MEMORY_DECAY / REASONING_GAP / PREREQUISITE_GAP / UNKNOWN）、title、description、confidence、evidence_count、status（SUSPECTED / CONFIRMED / RESOLVED / DISMISSED）、first_detected_at / last_detected_at / confirmed_at / resolved_at。

**misconception_evidence** — (misconception_id, learning_evidence_id) 唯一；support_score。

**review_schedules** — concept_id 唯一
scheduler_type（RULE_V1 / FSRS）、stability / difficulty / retrievability 可空、last_review_at / next_review_at / last_result / review_count、priority_score。

**learner_preferences** — 单行表
user_selected_preference（JSON）、observed_learning_preference（JSON）、observed_confidence（0~1）、evidence_count、last_observed_at。
推测偏好不得覆盖用户选择。

### 4.8 Adaptive / Planner 域

**teach_back_attempts**（P5）：concept_id、session_id（复用 chat_sessions）、transcript、coverage/reasoning/accuracy_score、confidence、result_json、started_at / completed_at。

**learning_goals**（P6）：goal_type、title、target_date、target_score、daily_minutes、exam_scope_json、scope_source（USER_CONFIRMED / TEACHER_DOCUMENT / COURSE_SELECTION / AI_INFERRED）、scope_confirmed（AI_INFERRED 必须用户确认）、status（ACTIVE / COMPLETED / ARCHIVED）。

**learning_plans**（P6）：(goal_id, plan_version) 唯一；status（ACTIVE / SUPERSEDED / COMPLETED）、effective_from / effective_to。

**learning_plan_items**（P6）：plan_id、concept_id 可空、action_type（含 PREVIEW）、priority、estimated_minutes、scheduled_date、status、user_locked、reason_json。

**learning_agent_actions**（P6）：action_type（REVIEW_CONCEPT / START_ADAPTIVE_ASSESSMENT / VERIFY_MISCONCEPTION / TEACH_BACK / START_TUTOR / READ_EVIDENCE / CONTINUE_PLAN_ITEM / COMPLETE_TODO / REST）、reason_code、priority（0~100）、estimated_minutes、confidence、input_snapshot_json、decision_json、status（RECOMMENDED / ACCEPTED / SKIPPED / DEFERRED / RUNNING / COMPLETED / FAILED）、recommended_at / accepted_at / started_at / completed_at。

**learning_agent_feedback**（P6）：action_id、feedback_type、rating、comment、actual_minutes、perceived_helpfulness。

### 4.9 Outcome 域

**learning_passport_snapshots**（P7）：snapshot_type（MONTHLY / SEMESTER / PRE_EXAM / COURSE_COMPLETED / MANUAL）、snapshot_date、mastered_count / learning_count / at_risk_count、summary_json、evidence_summary_json。

### 4.10 基础设施域

**processing_jobs** — 技术任务状态 + **任务队列本体（v2.0 自研队列，#1/#55）**（P0）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | TEXT | PK |
| record_id | TEXT | 可空 |
| job_type | TEXT | ASR / AUDIO_TRANSCODE / DOCUMENT_PARSE / EMBEDDING / CONCEPT_EXTRACTION / SUMMARY / CLEANUP / BACKUP_EXPORT / … |
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
| 全量导出（V1，Wave B） | zip = db 快照（VACUUM INTO）+ files/ + config/（**默认不含 providers.json，可选勾选含**）；输出至 exports/ 与用户选定位置 |
| 换机恢复 | 新机首启 → 选空数据目录 → 从导出包导入 → 校验落位（向量索引在 db 内，一体迁移） |
| 快照备份（P2） | 可选配置 WebDAV/S3 → 定期单向推送导出 zip；**无回写路径**（红线 #1） |
| 冲突处理 | 同一数据目录的操作系统排他锁保证单写者；第二个 sidecar 在迁移/worker 前失败并提示目录正被使用。进程退出或崩溃由 OS 自动释放锁；原 409/乐观锁机制随同步概念删除 |

## 8. 功能 → 业务实体 → 数据表映射

| 功能 | 业务实体 | 表 | 阶段 |
|------|---------|-----|------|
| 首启三步（目录/key/角色卡） | — | config/ + profile | MVP |
| 偏好设置 | — | config/settings.json | MVP |
| 学习统计 | —（聚合） | records/quizzes/chat_messages 等聚合查询 | MVP |
| 课程管理 | Course | courses | MVP |
| 收件箱 Inbox | Record（course_id 为空） | records（course_id NULL） | MVP |
| ⚡速记 | Record(NOTE)+Transcript | records(QUICK_NOTE, NOTE)、transcripts | MVP |
| 📋粘贴长文本 | Record+Transcript | records(PASTE)、transcripts | MVP |
| 🔗网页剪藏 | Record+Transcript | records(CLIP)、transcripts、processing_jobs(FETCH_PAGE) | P2 |
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
| 💬 AI 对话（自由/挂载） | ChatSession/Message | chat_sessions、chat_messages | MVP |
| 对话转学习资产 | KP/Quiz | knowledge_points / quizzes + source_anchor_links(CHAT_MESSAGE) | P2 |
| 状态通知 | — | records.status + processing_jobs（sidecar SSE） | MVP |
| 后台任务观测 | Job | processing_jobs | MVP |
| LLM 观测 | — | llm_call_logs | MVP |
| 全量导出/导入 | — | 数据目录打包/落位 | MVP(Wave B) |
| 快照备份 | — | processing_jobs(BACKUP_EXPORT) → WebDAV/S3 | P2 |
| 句子级溯源 | Segment/Anchor | transcript_segments、source_anchors、source_anchor_links | P2 |
| 文档分片 | DocumentSegment | document_segments | P2 |
| 课堂标记 | Marker | record_markers | P2 |
| 学习事件/证据 | Event/Evidence | learning_events、learning_evidence | MVP(四事件) / P2(evidence) |
| 语义检索 | Embedding | semantic_embeddings + vec0 | P2 |
| @全部资料全局 RAG | —（RAG） | semantic_embeddings | P2 |
| 概念图谱 | Concept | concepts、concept_relations、record_concepts | P3 |
| 课件差异分析 | RecordAnalysis | record_analyses | P3 |
| Course Chat | ChatSession | chat_sessions(COURSE_QA) | P3 |
| Knowledge GPS | —（聚合） | concepts + user_concept_mastery 聚合 | P3/P4 |
| 掌握度 | Mastery | user_concept_mastery（Mastery Engine 唯一写入） | P4 |
| 误区诊断 | Misconception | misconceptions、misconception_evidence | P4 |
| 遗忘/复习调度 | ReviewSchedule | review_schedules | P4 |
| 数字孪生 | —（运行时视图） | 聚合 + learner_preferences | P4 |
| Socratic Tutor | ChatSession | chat_sessions(SOCRATIC_TUTOR) | P5 |
| Teach-back | TeachBackAttempt | teach_back_attempts | P5 |
| 自适应测验 | QuizTest | quiz_tests(ADAPTIVE) | P5 |
| 课前预习 | CourseMaterial | course_materials、learning_plan_items(PREVIEW) | P5 |
| 学习目标/计划 | Goal/Plan | learning_goals、learning_plans、learning_plan_items | P6 |
| Autopilot | AgentAction | learning_agent_actions、learning_agent_feedback | P6 |
| Learning Passport | Snapshot | learning_passport_snapshots | P7 |
| 学习资产 Markdown 导出 | — | 无需表（前端基于 sidecar API 响应组装 .md，并通过 Tauri 写文件） | MVP |

## 9. 删除与数据一致性策略

删除 Record 时的清理链（功能基线 §6.5）：

1. 软删：record 及其全部子资产（files/transcript/segments/anchors/summaries/kp/quizzes/todo），同事务将该 Record 的 PENDING/RUNNING processing_jobs 置为 CANCELLED，已终态 Job 保留原状态，并立即清理该 Record 的 cache 暂存；worker 每次写前校验 deleted_at，迟到结果不得写回——**chat_sessions/chat_messages 不级联**：挂载会话保留可读、标记"原记录已删除"失效态（运行时推导，v1.11），仅显式删会话才删消息（#40）
2. 文件：`files/{record_id}/` 目录异步物理删除（30 天批次）
3. 向量：`semantic_embeddings.deleted_at` 标记 → 同批次物理清理（含 vec0 行）；**业务行软删 30 天后异步物理清理**（V1 无恢复 UI，#41）
4. 学习状态：该 Record 产生的 learning_evidence 按 record_id **排除出掌握度计算**（行保留作审计），受影响 Concept 由 Mastery Engine 异步重算（#18）
5. 删除 Course：级联其下全部 Record 走上述链路；Concept 及 Mastery 状态同规则重算

## 10. 数据库完整性约束清单（CHECK 摘要）

```
0 ≤ mastery_score / mastery_confidence / memory_strength / confidence / weight / quality_score / progress ≤ 1
0 ≤ priority ≤ 100        duration_ms ≥ 0        file_size ≥ 0
sequence_no ≥ 0           evidence_count ≥ 0     attempts ≥ 0
document_segments: (record_file_id IS NULL) ≠ (course_material_id IS NULL)
source_anchors: AUDIO/DOCUMENT 来源至少一个 segment 引用非空
learning_events.idempotency_key 全表唯一
record_id+version_no、concept_id（mastery/review）、goal_id+plan_version 等复合唯一（见各表）
状态字段受控枚举（CHECK 或应用层 Enum 注册）
```

## 11. 建表阶段规划

| 阶段 | 建表 |
|------|------|
| P0（**Wave A 基线含 P1 前排表共 15 张**） | profile、courses、records、record_files、transcripts、recording_sessions、processing_jobs、llm_call_logs、ai_summaries、knowledge_points、quizzes、todo_items、chat_sessions、chat_messages、learning_events |
| P1 补（Wave B） | quiz_tests、quiz_test_items、review_materials |
| P2 | transcript_segments、document_segments、source_anchors、source_anchor_links、record_markers、learning_evidence、semantic_embeddings（+vec0） |
| P3 | concepts、concept_relations、record_concepts、record_analyses |
| P4 | user_concept_mastery、misconceptions、misconception_evidence、review_schedules、learner_preferences |
| P5 | teach_back_attempts、course_materials |
| P6 | learning_goals、learning_plans、learning_plan_items、learning_agent_actions、learning_agent_feedback |
| P7 | learning_passport_snapshots |
| 暂缓 | ~~shares~~（不建）、study_pods 系列（P8） |

langgraph.db 随 P0 初始化（SqliteSaver 建表）。

## 12. 数据模型待确认问题

| # | 问题 | 关联 |
|---|------|------|
| Q6 | 录音 POC（含本地 ffmpeg 转码实测）结果回填 | 功能基线 §11-Q6 |
| Q11 | embedding 维度 1024 已定稿；若未来更换模型需全量重嵌入的迁移窗口策略 | 已知成本 |
