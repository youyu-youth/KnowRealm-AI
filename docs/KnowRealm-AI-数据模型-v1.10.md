# KnowRealm-AI 数据模型 v1.10

> **文档定位**：KnowRealm-AI 的**唯一数据模型基线**，与《功能需求基线 v1.10》配套。表设计冲突已按功能基线 §10 决策记录定稿；技术栈约束见 `技术栈设计与审查-v3.md`（v3.5）。
> **核心原则**：
> - **Supabase = 云端权威数据源**（业务事实）
> - **SQLite = 本地缓存 + 离线数据 + 客户端必要状态**（不复制云端全量，不双主写入）
> - **LangGraph Checkpoint = Agent 运行态**（独立 schema，非业务事实）
>
> 本文只做设计，不含迁移 SQL，不开始实现。
> **编写日期**：2026-08-14
> **变更记录**：v1.1（2026-08-14）同步功能基线裁决——shares 表**不建**（分享形态=Markdown 本地导出，无需表）；L3 离线编辑 V1 不做（record_markers 无本地表需求）；删除重算策略定稿（Evidence 按 record_id 排除 + Concept 异步重算）。
> **变更记录**：v1.2（2026-08-14）工作台升级（功能基线裁决 #21）——`records.course_id` 改**可空**（空=收件箱 Inbox）、新增 `records.capture_type`（捕获来源）、`status` 枚举新增 **NOTE**（速记已保存未升级）；transcripts 允许无文件直写（轻捕获无 record_file）；**零新表**，五级捕获入口全部复用现有实体。
> **变更记录**：v1.3（2026-08-14）AI 对话一级入口（功能基线裁决 #22）——`chat_sessions.course_id` 改**可空**（空=无挂载自由会话）；对话转学习资产复用 knowledge_points/quizzes + source_anchor_links(resource_type=CHAT_MESSAGE)；**零新表**。
> **变更记录**：v1.4（2026-08-14）目标用户泛化（功能基线裁决 #23）——courses 新增 `learning_context`（SCHOOL/CAREER/INTEREST）与 `depth`（BEGINNER/INTERMEDIATE/ADVANCED），`education_stage` 改为仅 SCHOOL 场景必填、`course_type` 改可空；英文内容与全量数据导出 P2（无新表）；视频导入不做。
> **变更记录**：v1.5（2026-08-14）知识库能力补齐（功能基线裁决 #24）——`semantic_embeddings.course_id` 改**可空**（Inbox/未分类内容入向量索引；全局检索仍强制 user_id 过滤）；不引入独立 knowledge_bases 实体；**零新表**。
> **变更记录**：v1.6（2026-08-15）需求评审对齐（功能基线 v1.7 裁决 #25~#50）——§2 向量检索过滤表述改写（user_id + deleted_at 恒定强制，course_id 条件附加，#28）；**learning_events 建表 P2→P1**（MVP 落地四事件，#33/#43）；§9.1 删 Record **不级联删 chat**（#40）；软删业务行 **30 天后物理清理**（#41）；record_files 路径 course_id 为空时**省略该段**（#49）。
> **变更记录**：v1.7（2026-08-15）设置域评审对齐（功能基线 v1.8 裁决 #51）——user_settings：locale V1 隐藏、timezone 默认取 OS（P4 生效）、**严格命名列演进（不加 jsonb 兜底）**；local_settings **V1 八键清单定稿**；local_files 上传+转写成功后即删本地文件。
> **变更记录**：v1.8（2026-08-15）角色域对齐（功能基线 v1.9 裁决 #52）——profiles 新增 `primary_role`（四枚举）与 `about_me`（≤200 字）两列，**零新表**；角色为档案层个性化字段，不进课程 AI 管线与 Evidence。
> **变更记录**：v1.9（2026-08-15）终审修补对齐（功能基线 v1.10 裁决 #54）——courses 新增 `hot_words`（text[] 可空，V1 手动热词列表 ≤100 词；"知识点→热词自动同步"P2）。
> **变更记录**：v1.10（2026-08-15）PRD v1.10 覆盖核对（终审）——chat_sessions 补 `title`（可空，会话列表渲染与重命名）；ai_summaries 补 `token_usage_json` / `latency_ms`（PRD §4.4.1 版本链自包含可回溯）；chat_sessions 删未定义枚举列 `status`（会话删除走通用软删 deleted_at）；修正 §4.1 表格截断格式、§8 粘贴行对齐 #29、§12-Q7 对齐 #54。

---

## 1. 三层职责边界

| 层 | 存储 | 职责 | 禁止 |
|----|------|------|------|
| 云端业务事实 | Supabase PostgreSQL（含 pgvector） | 全部业务实体、学习状态、向量、技术任务状态 | — |
| 本地工作区 | Desktop SQLite（tauri-plugin-sql） | 草稿、本地文件索引与上传队列、只读缓存、本机设置 | 成为 Mastery/业务事实源；独立演化云端状态；与 PG 双主写入 |
| Agent 运行态 | Supabase `langgraph` schema（框架自管） | Graph 暂停/恢复状态（HITL 等待等） | 当业务表查询；长期事实只存这里 |

---

## 2. 通用规范（Supabase 全表适用）

- 表名 `snake_case`，无 `t_` 前缀；主键 `uuid`；时间 `timestamptz`；JSON 一律 `jsonb`
- 所有用户私有表含 `user_id uuid` 并启用 RLS：`user_id = auth.uid()`
- 可同步/可编辑实体统一携带：`version bigint`（乐观锁）、`updated_at`、`deleted_at`（软删，可空）；纯追加型事实表（events/evidence/messages/logs）不做软删与 version
- 后端写路径：最小权限数据库角色 + service 层数据访问代码强制 `user_id` 过滤（不单设 Repository 层，2026-08 定稿）；RLS 为第二道边界（service_role 绕过 RLS，不得作为后端授权依据）
- 向量检索**恒定强制前置过滤 `user_id + deleted_at IS NULL`**；course_id 仅课程/记录范围检索时附加（@全部资料全局检索省略 course_id，功能基线裁决 #28）；禁止任何不含 user_id 的裸向量查询
- 状态/枚举字段用受控枚举（PostgreSQL CHECK 或应用层 Enum 注册），禁止裸字符串随意写入

---

## 3. Supabase 表总览

| 域 | 表 | 建表阶段 |
|----|----|---------|
| 用户（2） | profiles, user_settings | P0 |
| 课程与记录（6） | courses, records, record_files, transcripts, course_materials*, record_markers | P0 / P0 / P0 / P0 / P5 / P2 |
| AI 产出（8） | ai_summaries, knowledge_points, quizzes, quiz_tests, quiz_test_items, review_materials, todo_items, record_analyses | P1×7 / P3 |
| 对话（2） | chat_sessions, chat_messages | P1 |
| 学习数据基础（6） | transcript_segments, document_segments, source_anchors, source_anchor_links, learning_events, learning_evidence | P2（learning_events 提前 **P1**，#33） |
| Course Brain（4） | concepts, concept_relations, record_concepts, semantic_embeddings | P3 / P3 / P3 / P2 |
| Learner Brain（5） | user_concept_mastery, misconceptions, misconception_evidence, review_schedules, learner_preferences | P4 |
| Adaptive / Planner（6） | teach_back_attempts, learning_goals, learning_plans, learning_plan_items, learning_agent_actions, learning_agent_feedback | P5 / P6×5 |
| Outcome（1） | learning_passport_snapshots | P7 |
| 基础设施（2） | processing_jobs, llm_call_logs | P0 / P0 |
| 暂缓 | ~~shares~~（v1.1 定稿：**不建**，分享=Markdown 本地导出无需表）、study_pods 系列（P8） | — |

正式表合计 **42 张**（v1.2 工作台升级**零新表**——五级捕获入口全部复用 records/transcripts）；另有 `langgraph` schema 框架表与 procrastinate 自管 `procrastinate_jobs` 表（**不建 outbox_events**——procrastinate 的任务入队在业务事务内提交，天然具备 Transactional Outbox 语义，功能基线 §10 裁决 #1）。

---

## 4. Supabase 表设计

> 说明列仅写关键约束；所有表默认含 `created_at timestamptz`，下文不再重复。标注〔软删〕= 含 deleted_at，〔锁〕= 含 version。

### 4.1 用户域

**profiles** — Supabase `auth.users` 的业务档案（P0）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | PK，FK → auth.users.id |
| nickname | text | |
| avatar_path | text | Storage 路径（avatars 桶） |
| primary_role | text | STUDENT / DEVELOPER / OFFICE_WORKER / OTHER（v1.8，#52——档案层个性化：首启角色卡/建课程默认值/自由聊天系统提示/文案基调；不进课程 AI 管线与 Evidence） |
| about_me | text | ≤200 字自我介绍（随角色注入自由聊天系统提示；新会话生效不追溯，#52） |
| status | text | ACTIVE / DISABLED |
| updated_at | timestamptz | |

不保存密码与任何认证事实。

**user_settings** — 云端漫游偏好（P0）
| 字段 | 类型 | 说明 |
|---|---|---|
| user_id | uuid | PK/FK |
| theme | text | LIGHT / DARK / SYSTEM |
| font_scale | numeric | |
| locale | text | i18n（默认 zh；V1 仅中文，设置页隐藏语言项，英文 UI 实做时再显示，#51） |
| timezone | text | 默认取 OS、可手动覆盖；消费者为复习提醒调度（P4 生效，#51） |
| updated_at | timestamptz | |

> 演进策略（#51）：user_settings **严格命名列，不加 preferences jsonb 兜底**——新增设置项一律加列迁移，防"设置垃圾抽屉"。

### 4.2 课程与记录域

**courses**（P0，〔软删〕〔锁〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | PK |
| user_id | uuid | FK |
| name | text | NOT NULL |
| learning_context | text | v1.4：SCHOOL / CAREER / INTEREST（必填，进 AI 上下文） |
| education_stage | text | MIDDLE_SCHOOL / HIGH_SCHOOL / UNDERGRADUATE / GRADUATE / DOCTORAL——**仅 SCHOOL 场景必填**，其余可空 |
| depth | text | v1.4：BEGINNER / INTERMEDIATE / ADVANCED——**仅 CAREER/INTEREST 场景必填**，SCHOOL 可空 |
| course_type | text | MAJOR / GENERAL / ELECTIVE——**可空（v1.4）**，职业/兴趣场景可不填 |
| description | text | 可空 |
| hot_words | text[] | 可空（v1.9，#54）——ASR 热词手动列表（≤100 词）；"知识点 → 热词自动同步"P2 |
| status | text | ACTIVE / ARCHIVED |

CHECK：`learning_context='SCHOOL' → education_stage 非空；learning_context≠'SCHOOL' → depth 非空`

索引：`(user_id, updated_at desc)`、`(user_id, learning_context)`、`(user_id, course_type)`

**records** — 课堂记录（P0，〔软删〕〔锁〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id | uuid | PK / FK |
| course_id | uuid | FK，**可空（v1.2）——为空即收件箱 Inbox 中未分类捕获** |
| capture_type | text | 可空（v1.2）：RECORDING / AUDIO_IMPORT / DOCUMENT_IMPORT / PASTE / QUICK_NOTE / CLIP——记录捕获来源（展示与 Inbox 处理用） |
| title | text | |
| status | text | 业务状态机：**NOTE（v1.2：速记已保存未升级）** / DRAFT / UPLOADING / CONTENT_PROCESSING / SUMMARY_PENDING / SUMMARY_PROCESSING / SUMMARY_READY / COMPLETED / FAILED（技术任务状态不入此字段，见 processing_jobs） |
| duration_ms | bigint | ≥0 |
| summary_confirmed_at | timestamptz | HITL 确认时刻 |

索引：`(user_id, created_at desc)`、`(course_id, created_at desc)`、`(user_id, status)`

**record_files** — Record 关联文件（P0，〔软删〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id / record_id | uuid | |
| file_type | text | AUDIO / DOCUMENT |
| source_type | text | RECORDED / UPLOADED |
| storage_bucket / storage_path | text | 私有桶路径 `{bucket}/{user_id}/{course_id}/{record_id}/{file_id}`；course_id 为空（Inbox）时**省略该段**（`{bucket}/{user_id}/{record_id}/{file_id}`），归类后不迁移（#49） |
| original_name / mime_type | text | |
| file_size | bigint | ≥0 |
| duration_ms | bigint | 仅音频 |
| sequence_no | int | 多文件合并顺序，≥0 |
| processing_status | text | 文件级处理状态 |
| content_hash | text | 上传校验/去重 |

索引：`(record_id, sequence_no)`、`(user_id, content_hash)`

**transcripts** — 转写文本（P0）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id / record_id | uuid | record_id UNIQUE（一 Record 一份当前转写） |
| language | text | 默认 zh-CN |
| content | text | 当前合并全文（快速展示用；可溯源自 transcript_segments）；**轻捕获（速记/粘贴/剪藏）无 record_file，内容直接写入此表** |
| source_version | int | 用户编辑次数/版本 |
| edited_by_user | boolean | |
| updated_at | timestamptz | |

**course_materials** — 课程级资料（P5 建表；支撑课前预习/长期课件，与 record_files 职责分立）（〔软删〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id / course_id | uuid | |
| linked_record_id | uuid | 可空；课后可关联到具体 Record |
| purpose | text | COURSEWARE / PREVIEW / REFERENCE |
| storage_bucket / storage_path / original_name / mime_type / file_size / content_hash | 同 record_files | |
| processing_status | text | |

**record_markers** — 课堂实时标记（P2）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id / course_id / record_id / file_id | uuid | |
| marker_type | text | IMPORTANT / CONFUSED / NOTE |
| record_offset_ms / file_offset_ms | bigint | 双时间轴（全局+文件内） |
| note | text | 可空 |
| status | text | ACTIVE / RESOLVED |

CONFUSED 仅主观信号，经验证才进入学习状态。

### 4.3 AI 产出域

**ai_summaries** — 版本化总结（P1）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id / record_id | uuid | |
| version_no | int | 与 record_id 联合唯一 |
| topic | text | 一句话主题 |
| abstract | text | 500~1000 字摘要 |
| summary_json | jsonb | 结构化分点总结 |
| status | text | GENERATED / CONFIRMED / SUPERSEDED |
| model / prompt_version | text | 可追溯 |
| token_usage_json / latency_ms | jsonb / int | 可空（v1.10）——版本链自包含可回溯（model/prompt_version/token/latency/version_no，PRD §4.4.1） |
| user_feedback | text | 触发重新生成的反馈 |
| confirmed_at | timestamptz | |

**knowledge_points** — 知识点（Record 级资产，P1，〔软删〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id / record_id | uuid | |
| name / detail | text | |
| tags | text[] | |
| importance | numeric | |
| status | text | AI_GENERATED / CONFIRMED |
| source_anchor_id | uuid | 可空，主锚点（完整来源走 source_anchor_links） |
| updated_at | | |

**quizzes** — 习题（P1）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id / record_id | uuid | |
| concept_id | uuid | 可空（P3 起回填） |
| batch_id | uuid | 同次生成批次 |
| question_type | text | MULTIPLE_CHOICE / TRUE_FALSE / SHORT_ANSWER |
| stem | text | 题干 |
| options_json / correct_answer_json | jsonb | 选项 / 答案（简答题为参考答案） |
| explanation | text | 解析 |
| difficulty | text | EASY / MEDIUM / HARD |
| cognitive_level | text | RECALL / UNDERSTAND / APPLY / ANALYZE / TRANSFER（P5 起用） |
| source_anchor_id | uuid | 可空，主锚点 |
| quality_score | numeric | 可空，0~1 |
| model / prompt_version | text | |

**quiz_tests** — 模拟/自适应测试（P1；ADAPTIVE 模式 P5 启用）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id / course_id | uuid | record_id 可空 |
| mode | text | MOCK / ADAPTIVE |
| status / score | text / numeric | |
| started_at / completed_at | timestamptz | |

**quiz_test_items** — 作答明细（P1）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / test_id / quiz_id | uuid | (test_id, sequence_no) 唯一 |
| sequence_no | int | |
| user_answer_json | jsonb | |
| result | text | CORRECT / WRONG / PARTIAL |
| score | numeric | |
| ai_grade_json | jsonb | 简答题 AI 评分依据（必存，不裸给分） |
| answered_at | timestamptz | |

**review_materials** — 复习资料（P1）
quick_review（考前速记）、key_list_json（Top 重点清单）、mind_map_markdown（Markdown 大纲思维导图）、model、prompt_version、user_id、record_id。

**todo_items** — Record 级任务（P1，〔软删〕〔锁〕）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id / record_id | uuid | |
| content | text | |
| status | text | TODO / DONE |
| source | text | AI / MANUAL |
| sort_order | int | |
| updated_at | | |

不得与 learning_plan_items / learning_agent_actions 合表。

**record_analyses** — Record 级结构化分析（P3，课件 Diff 等）
analysis_type（COURSEWARE_DIFF / EXAM_FOCUS / OTHER）、version_no（(record_id, analysis_type, version_no) 唯一）、input_refs_json（参与分析的文件/片段引用）、result_json（结构化输出：covered / document_only / teacher_extra / teacher_emphasis / possible_exam_focus）、model、prompt_version。

### 4.4 对话域

**chat_sessions**（P1）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id | uuid | |
| course_id | uuid | **可空（v1.3）**——空 = 无挂载的自由聊天会话；@课程挂载时填（Course Chat）；@记录挂载时随 record 填其课程 |
| record_id / concept_id | uuid | 可空 |
| mode | text | ASK / COURSE_QA / SOCRATIC_TUTOR / TEACH_BACK |
| title | text | 可空（v1.10）——会话列表渲染与重命名；默认取首条用户消息截断，重命名覆盖 |
| updated_at | | |

Record Chat、Course Chat、自由聊天、Tutor、Teach-back 共用此模型，不建第二套消息体系。

**chat_messages**（P1）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / session_id / user_id | uuid | |
| role | text | USER / ASSISTANT / SYSTEM / TOOL |
| content | text | |
| citations_json | jsonb | Source Anchor 引用（答案溯源） |
| model / token_usage_json | text / jsonb | 可空 |
| created_at | timestamptz | 索引 (session_id, created_at) |

### 4.5 学习数据基础域（P2）

**transcript_segments** — 句子级转写分片
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id / transcript_id / record_id / file_id | uuid | |
| sequence_no | int | 索引 (record_id, sequence_no) |
| record_start_ms / record_end_ms | bigint | 课堂全局时间轴 |
| file_start_ms / file_end_ms | bigint | 文件内时间轴（多段录音两者必须同时存在） |
| speaker | text | 可空（说话人分离预留） |
| content / content_hash | text | 索引 (file_id, file_start_ms)、(record_id, record_start_ms) |

**document_segments** — 文档分片
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id / course_id | uuid | |
| record_id | uuid | 可空（课前资料未绑定 Record 时为空） |
| record_file_id / course_material_id | uuid | 二者**必须且只能一个非空**（CHECK 约束） |
| sequence_no / page_no / section_title | int / int / text | page_no 可空（PyMuPDF 提供页码） |
| content / start_offset / end_offset / content_hash | text / int / int / text | |

**source_anchors** — 来源锚点（AI 结论 ↔ 原始出处）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id / course_id | uuid | |
| source_type | text | AUDIO_SEGMENT / DOCUMENT_SEGMENT / USER_NOTE |
| source_id | uuid | |
| record_id / record_file_id / course_material_id / transcript_segment_id / document_segment_id | uuid | 均可空，但 Audio/Document 来源至少关联一个具体 Segment |
| start_offset / end_offset / page_no | int | 可空 |

**source_anchor_links** — 多来源关联（多态）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id | uuid | |
| resource_type | text | SUMMARY / KNOWLEDGE_POINT / QUIZ / MISCONCEPTION / CHAT_MESSAGE / RECORD_ANALYSIS |
| resource_id | uuid | |
| source_anchor_id | uuid | FK |
| relation_type | text | SUPPORTS / PRIMARY / CONTRADICTS / REFERENCES |

唯一约束 `(resource_type, resource_id, source_anchor_id, relation_type)`。实体表上的 `source_anchor_id` 仅为可选主锚点，完整来源集合以此表为准。V1 不为每类资源拆专用关联表。

**learning_events** — 学习行为事实（追加型，不软删；**建表提前至 P1**，MVP 落地事件：SUMMARY_CONFIRMED / KNOWLEDGE_CONFIRMED / QUIZ_ANSWERED / QUIZ_TEST_COMPLETED，#33/#43）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id / course_id | uuid | record_id / concept_id 可空 |
| event_type | text | SUMMARY_CONFIRMED / KNOWLEDGE_CONFIRMED / QUIZ_ANSWERED / QUIZ_TEST_COMPLETED / TEACH_BACK_COMPLETED / TUTOR_CHECK_COMPLETED / REVIEW_VERIFIED / MARKER_CREATED / MISCONCEPTION_CONFIRMED / MISCONCEPTION_RESOLVED / PLAN_ITEM_COMPLETED / CONCEPT_MASTERED |
| source_type / source_id | text / uuid | 行为来源（如 quiz_test_item） |
| result / score / difficulty / duration_ms | text / numeric / text / bigint | 一个行为只记一个事件（result=CORRECT/WRONG，不拆三个事件） |
| metadata_json | jsonb | |
| idempotency_key | text | **UNIQUE**（幂等） |
| schema_version | int | |
| occurred_at / created_at | timestamptz | 索引 (user_id, occurred_at desc)、(concept_id, occurred_at desc)、(course_id, event_type, occurred_at desc) |

**learning_evidence** — 学习证据（追加型）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id / course_id / concept_id / event_id | uuid | |
| evidence_type | text | QUIZ / RECALL / TEACH_BACK / TUTOR_CHECK / TRANSFER / CLASSROOM_SIGNAL / USER_CONFIRMATION |
| result / score / difficulty | | |
| weight / confidence | numeric | 0~1；AI_SYNTHESIS 不作为证据类型 |
| source_anchor_id | uuid | 可空 |
| metadata_json | jsonb | |
| occurred_at / created_at | timestamptz | 索引 (user_id, concept_id, occurred_at desc)、(event_id) |

### 4.6 Course Brain 域

**concepts** — 课程级规范概念（P3）
canonical_name、normalized_name、description、concept_type、importance、status（CANDIDATE / CONFIRMED / ARCHIVED）、source（AI_EXTRACTED / USER_CONFIRMED / SYSTEM）、updated_at。
唯一性策略：仅对 `status='CONFIRMED'` 建 `(course_id, normalized_name)` 部分唯一索引——Candidate 阶段允许同义/重复进入 Resolution，消歧后 Canonical 概念课程内唯一。

**concept_relations**（P3）
source/target_concept_id、relation_type（PREREQUISITE / PART_OF / RELATED_TO / COMPARE_WITH / CAUSES / APPLIES_TO）、confidence（0~1）、evidence_count、status（CANDIDATE / CONFIRMED / DISMISSED）。

**record_concepts**（P3）
(record_id, concept_id) 唯一；knowledge_point_id 可空（KP→Concept Resolution 桥）；relevance、importance、first_start_ms、evidence_count。

**semantic_embeddings** — 统一向量索引表（P2 起）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id | uuid | |
| course_id | uuid | **可空（v1.5）**——未分类/Inbox 内容照常入索引；@全部资料全局 RAG 即全库检索（仍强制 user_id 过滤） |
| record_id / record_file_id / course_material_id | uuid | 可空 |
| source_type | text | TRANSCRIPT_SEGMENT / DOCUMENT_SEGMENT / KNOWLEDGE_POINT / CONCEPT |
| source_id | uuid | |
| content_hash | text | 内容变更检测（hash 变则重嵌入） |
| embedding_model | text | 当前 text-embedding-v3（换模型全量重嵌入） |
| embedding | vector(1024) | 维度随模型定稿（功能基线 §10 裁决 #4） |
| metadata_json | jsonb | |
| deleted_at | timestamptz | 软删标记，检索必过滤 |

统一表的意义：向量生命周期（嵌入/失效/删除）单一管理，与业务软删策略一致；索引类型（HNSW 等）实现期按 pgvector 版本定，不在此写死。

### 4.7 Learner Brain 域（P4）

**user_concept_mastery** — (user_id, concept_id) 唯一
mastery_score / mastery_confidence / memory_strength（0~1 CHECK）；transfer_score / reasoning_score 可空；evidence_count / positive_evidence_count / negative_evidence_count（≥0）；last_learned_at / last_practiced_at / last_verified_at / next_review_at；version、updated_at。
**唯一写入口 = Mastery Engine**（功能基线红线 #3）。

**misconceptions**
type（KNOWLEDGE_GAP / MISCONCEPTION / MEMORY_DECAY / REASONING_GAP / PREREQUISITE_GAP / UNKNOWN）、title、description、confidence、evidence_count、status（SUSPECTED / CONFIRMED / RESOLVED / DISMISSED）、first_detected_at / last_detected_at / confirmed_at / resolved_at。

**misconception_evidence** — (misconception_id, learning_evidence_id) 唯一；support_score。

**review_schedules** — (user_id, concept_id) 唯一
scheduler_type（RULE_V1 / FSRS）、stability / difficulty / retrievability 可空（FSRS P 后期）、last_review_at / next_review_at / last_result / review_count、priority_score。

**learner_preferences** — user_id PK
user_selected_preference（jsonb，用户主动设置）/ observed_learning_preference（jsonb，系统推测）/ observed_confidence（0~1）/ evidence_count / last_observed_at。
推测偏好不得覆盖用户选择。

### 4.8 Adaptive / Planner 域

**teach_back_attempts**（P5）：concept_id、session_id（复用 chat_sessions）、transcript、coverage/reasoning/accuracy_score、confidence、result_json、started_at / completed_at。

**learning_goals**（P6）：goal_type、title、target_date、target_score、daily_minutes、exam_scope_json、scope_source（USER_CONFIRMED / TEACHER_DOCUMENT / COURSE_SELECTION / AI_INFERRED）、scope_confirmed（AI_INFERRED 必须用户确认）、status（ACTIVE / COMPLETED / ARCHIVED）。

**learning_plans**（P6）：(goal_id, plan_version) 唯一；status（ACTIVE / SUPERSEDED / COMPLETED）、effective_from / effective_to。

**learning_plan_items**（P6）：plan_id、concept_id 可空、action_type（含 PREVIEW——课前预习落地形态，不建独立 Preview 表）、priority、estimated_minutes、scheduled_date、status、user_locked（锁定项不自动重排）、reason_json。

**learning_agent_actions**（P6）：action_type（REVIEW_CONCEPT / START_ADAPTIVE_ASSESSMENT / VERIFY_MISCONCEPTION / TEACH_BACK / START_TUTOR / READ_EVIDENCE / CONTINUE_PLAN_ITEM / COMPLETE_TODO / REST）、reason_code、priority（0~100）、estimated_minutes、confidence、input_snapshot_json、decision_json、status（RECOMMENDED / ACCEPTED / SKIPPED / DEFERRED / RUNNING / COMPLETED / FAILED）、recommended_at / accepted_at / started_at / completed_at。

**learning_agent_feedback**（P6）：action_id、feedback_type、rating、comment、actual_minutes、perceived_helpfulness。

### 4.9 Outcome 域

**learning_passport_snapshots**（P7）：snapshot_type（MONTHLY / SEMESTER / PRE_EXAM / COURSE_COMPLETED / MANUAL）、snapshot_date、mastered_count / learning_count / at_risk_count、summary_json、evidence_summary_json。

### 4.10 基础设施域

**processing_jobs** — 技术任务状态（P0）
| 字段 | 类型 | 说明 |
|---|---|---|
| id / user_id | uuid | record_id 可空 |
| job_type | text | ASR / AUDIO_TRANSCODE / DOCUMENT_PARSE / EMBEDDING / CONCEPT_EXTRACTION / SUMMARY / … |
| status | text | PENDING / RUNNING / SUCCEEDED / FAILED |
| progress | numeric | 0~1 |
| attempts / max_attempts | int | 重试控制 |
| input_json / result_json | jsonb | |
| error_code / error_message | text | |
| started_at / finished_at | timestamptz | |

与 `records.status` 的分工：后者是用户可理解业务态，前者承载并行技术任务（多文件不冲突）。

**llm_call_logs** — LLM 调用观测（P0，追加型）
request_id、user_id、graph_name、graph_node、model、prompt_version、embedding_model、token_usage_json、latency_ms、retrieval_count、evidence_count、interrupt_count、error_code、created_at。
（功能基线 §10 裁决 #2：以自建表替代 Sentry/OTel/Langfuse 自托管。）

**shares** — **不建表**（v1.1 定稿）：Desktop 分享形态为 Markdown 本地导出（后端组装 .md / 前端写本地文件系统），无公开访问面，无需服务端表；study_pods 系列四表 **P8 前不建**。

---

## 5. SQLite 本地表设计（Desktop）

> 定位：缓存 + 草稿 + 离线队列 + 本机状态。**只读缓存可随时清除重建；写队列仅限 L2（文件上传注册类）**。主键可用 text(uuid) 或 integer rowid，字段为最小集。

| 表 | 用途 | 关键字段 | 启用 |
|----|------|---------|------|
| **local_record_drafts** | 录音会话草稿（未提交云端） | id、course_id、title、local_status、started_at、updated_at | V1 |
| **local_files** | 本地文件索引 + 上传队列（上传成功且云端转写完成后即删本地文件，#51） | id、local_draft_id/record_id、local_path、mime_type、file_size、content_hash、upload_status（PENDING/UPLOADING/UPLOADED/FAILED）、remote_file_id、attempts、last_error | V1 |
| **cached_courses** | 课程列表/详情快照 | 云端行镜像 + synced_at | V1 |
| **cached_records** | 记录列表/元信息快照 | 云端行镜像 + synced_at | V1 |
| **cached_transcripts** | 最近记录的整段转写（离线查看） | record_id、content、source_version、synced_at | V1 |
| **cached_transcript_segments** | 句子级分片缓存（最近访问的记录） | record_id、segments_json 或行镜像、synced_at | P2 |
| **cached_ai_summaries** | 已确认总结快照 | record_id、version_no、内容镜像、synced_at | V1 |
| **sync_outbox** | 出站同步队列（V1 仅文件注册类操作） | entity_type、entity_id、operation、base_version、payload_json、status、attempts、last_error | V1 |
| **sync_cursor** | 增量拉取游标 | resource、last_synced_at、server_cursor | V1 |
| **local_settings** | 仅本机设置（不漫游，#51） | key、value；**V1 键清单**：window_bounds / close_behavior（默认 tray，可选 quit）/ autostart（默认关）/ capture_hotkey（默认 Ctrl+Alt+N）/ keep_local_audio_after_upload（默认关）/ cache_dir（可空）/ last_learning_context / quiz_last_count | V1 |

不落 SQLite：token（supabase-js localStorage）、Mastery/学习状态、完整 Learning Brain 数据、任何需独立演化的业务事实。知识点/习题/复习/对话等**在线查询，不建缓存表**（TanStack Query 内存缓存即可，后续按需增补缓存表）。

---

## 6. LangGraph 框架表（Supabase，schema `langgraph`）

由 PostgreSQL Checkpointer 自管（checkpoints/checkpoint_writes 等）。规则：不手工查询、不在业务层依赖其内部字段、Graph State 只存运行状态；确认结果、版本链等长期事实必须落业务表（如 ai_summaries）。与业务表共用同一 Supabase 实例、不同 schema。

---

## 7. 云端与本地职责边界及同步策略

### 7.1 实体分级

| 级别 | 实体 | 方向 | 说明 |
|------|------|------|------|
| 只读缓存（L1） | courses、records、transcripts、已确认 summaries、（P2+）segments | 云→端增量拉取（updated_at 游标 sync_cursor） | 可随时清空重建；TanStack Query 负责请求层缓存与失效 |
| 本地先行写（L2） | 录音会话草稿、本地音频文件、上传注册 | 端→云（local_files 队列 + sync_outbox） | 录音全程本地；联网后按队列上传，成功后以 remote_file_id 关联 record_files |
| 在线读写 | 知识点/习题/Todo/对话/Quiz/AI 生成/全部 Learning Brain | 实时 API | 离线仅展示缓存，不提供离线编辑 |
| 离线业务编辑（L3） | — | **V1 不做**（v1.1 定稿，功能基线裁决 #16） | 架构已预留（version 乐观锁 + sync_outbox 通用结构），未来开放 Todo/Marker 离线写只需扩展，不改表结构 |

### 7.2 冲突处理

- 云端可编辑实体带 `version`；后端更新语句校验 version，不匹配返回 **409**，由用户决策，**不默认 Last-Write-Wins**
- 只读缓存无冲突概念（以云端为准，游标重置重拉）

### 7.3 删除联动

软删父实体（course/record）→ 缓存靠游标拉取自然失效；Storage 对象异步物理清理；`semantic_embeddings.deleted_at` 同步标记后物理清理；被删 Record 的 Evidence 按 record_id 排除出掌握度计算并触发 Concept 异步重算（v1.1 定稿，详见 §9）。业务行软删 **30 天后异步物理清理**（与 Storage/向量清理同批次，#41）；挂载被删 Record 的 chat 会话**不级联删除**，仅标记挂载失效（#40）。

---

## 8. 功能 → 业务实体 → 数据表映射

| 功能 | 业务实体 | Supabase 表 | SQLite 表 | 阶段 |
|------|---------|------------|-----------|------|
| 登录认证 | 用户 | auth.users + profiles | — | MVP |
| 偏好设置 | 设置 | user_settings | local_settings | MVP |
| 学习统计 | —（聚合） | records/quizzes/chat_messages 等聚合查询 | — | MVP |
| 课程管理 | Course | courses | cached_courses | MVP |
| 收件箱 Inbox | Record（course_id 为空） | records（course_id NULL 视图） | cached_records | MVP |
| ⚡速记/闪念 | Record(NOTE)+Transcript | records(capture_type=QUICK_NOTE, status=NOTE)、transcripts | — | MVP |
| 📋粘贴长文本 | Record+Transcript | records(capture_type=PASTE)、transcripts（已选课直接进管线；未选课仅存储，#29） | — | MVP |
| 🔗网页剪藏 | Record+Transcript | records(capture_type=CLIP)、transcripts、processing_jobs（FETCH_PAGE） | — | P2 |
| 课堂录音（会话） | Record(DRAFT) | records | local_record_drafts | MVP |
| 录音/导入文件 | RecordFile | record_files + Storage 桶 | local_files | MVP |
| 音频转码任务 | Job | processing_jobs（AUDIO_TRANSCODE） | — | MVP |
| ASR 转写 | Transcript | transcripts、processing_jobs | cached_transcripts | MVP |
| 文档解析 | Transcript/Segment 前身 | transcripts（整段）、processing_jobs | cached_transcripts | MVP |
| 转写编辑 | Transcript | transcripts | （缓存随游标更新） | MVP |
| AI 总结 + HITL | Summary | ai_summaries + langgraph checkpoint | cached_ai_summaries | MVP |
| 知识点提取 | KnowledgePoint | knowledge_points | — | MVP |
| 习题生成 | Quiz | quizzes | — | MVP |
| 模拟测试 | QuizTest | quiz_tests、quiz_test_items | — | MVP |
| 复习资料 | ReviewMaterial | review_materials | — | MVP |
| Todo | TodoItem | todo_items | — | MVP |
| Record 问答 | ChatSession/Message | chat_sessions(mode=ASK)、chat_messages | — | MVP |
| 💬 AI 对话（自由/挂载） | ChatSession/Message | chat_sessions（course_id 可空=自由会话，v1.3）、chat_messages | — | MVP |
| 对话转学习资产 | KP/Quiz | knowledge_points / quizzes + source_anchor_links(resource_type=CHAT_MESSAGE) | — | P2 |
| 状态通知 | — | records.status + processing_jobs（Realtime 推送） | — | MVP |
| 后台任务观测 | Job | processing_jobs | — | MVP |
| LLM 观测 | — | llm_call_logs | — | MVP |
| 增量同步 | — | /api/sync + updated_at 游标 | sync_outbox、sync_cursor、cached_* | MVP |
| 句子级溯源 | Segment/Anchor | transcript_segments、source_anchors、source_anchor_links | cached_transcript_segments | P2 |
| 文档分片 | DocumentSegment | document_segments | — | P2 |
| 课堂标记 | Marker | record_markers | —（离线打点不做，v1.1 定稿） | P2 |
| 学习事件/证据 | Event/Evidence | learning_events、learning_evidence | — | **MVP（events 四事件，#33/#43）** / P2（evidence） |
| 语义检索 | Embedding | semantic_embeddings | — | P2 |
| @全部资料全局 RAG 问答 | —（RAG） | semantic_embeddings（course_id 可空，v1.5） | — | P2 |
| 概念图谱 | Concept | concepts、concept_relations、record_concepts | — | P3 |
| 课件差异分析 | RecordAnalysis | record_analyses | — | P3 |
| Course Chat | ChatSession | chat_sessions(mode=COURSE_QA) | — | P3 |
| Knowledge GPS | —（聚合） | concepts + user_concept_mastery 聚合 | — | P3/P4 |
| 掌握度 | Mastery | user_concept_mastery（Mastery Engine 唯一写入） | — | P4 |
| 误区诊断 | Misconception | misconceptions、misconception_evidence | — | P4 |
| 遗忘/复习调度 | ReviewSchedule | review_schedules | — | P4 |
| 数字孪生 | —（运行时视图） | 聚合 + learner_preferences | — | P4 |
| Socratic Tutor | ChatSession | chat_sessions(mode=SOCRATIC_TUTOR)、chat_messages | — | P5 |
| Teach-back | TeachBackAttempt | teach_back_attempts、chat_sessions(mode=TEACH_BACK) | — | P5 |
| 自适应测验 | QuizTest | quiz_tests(mode=ADAPTIVE)、quiz_test_items | — | P5 |
| 课前预习 | CourseMaterial | course_materials、document_segments、learning_plan_items(action=PREVIEW) | — | P5 |
| 学习目标/计划 | Goal/Plan | learning_goals、learning_plans、learning_plan_items | — | P6 |
| Autopilot | AgentAction | learning_agent_actions、learning_agent_feedback | — | P6 |
| Learning Passport | Snapshot | learning_passport_snapshots | — | P7 |
| Markdown 导出 | — | 无需表（后端组装 .md，前端写本地文件；v1.1 定稿） | —（本地文件系统） | MVP |
| 全量数据导出 | — | 全表只读组装 JSON（含 mastery/evidence；v1.4，无新表） | —（本地文件系统） | P2 |

---

## 9. 删除与数据一致性策略

删除 Record 时的清理链（功能基线 §6.5）：

1. 软删：record 及其全部子资产（files/transcript/segments/anchors/summaries/kp/quizzes/todo）——**chat_sessions/chat_messages 不级联**：挂载会话保留可读、标记"原记录已删除"失效态，仅显式删会话才删消息（#40）
2. Storage：私有桶对象异步物理删除
3. 向量：`semantic_embeddings.deleted_at` 标记 → 定期物理清理；**业务行软删 30 天后同批次物理清理**（V1 无恢复 UI，#41）
4. 学习状态：该 Record 产生的 learning_evidence 按 record_id **排除出掌握度计算**（行保留作审计），受影响 Concept 由 Mastery Engine 异步重算（v1.1 定稿，功能基线裁决 #18）
5. 删除 Course：级联其下全部 Record 走上述链路；Concept 及 Mastery 状态同规则重算

---

## 10. 数据库完整性约束清单（CHECK 摘要）

```
0 ≤ mastery_score / mastery_confidence / memory_strength / confidence / weight / quality_score / progress ≤ 1
0 ≤ priority ≤ 100        duration_ms ≥ 0        file_size ≥ 0
sequence_no ≥ 0           evidence_count ≥ 0     attempts ≥ 0
document_segments: (record_file_id IS NULL) ≠ (course_material_id IS NULL)
source_anchors: AUDIO/DOCUMENT 来源至少一个 segment 引用非空
learning_events.idempotency_key 全表唯一
record_id+version_no、user_id+concept_id、goal_id+plan_version 等复合唯一（见各表）
状态字段受控枚举（CHECK 或应用层 Enum 注册）
```

---

## 11. 建表阶段规划

| 阶段 | 建表 |
|------|------|
| P0 | profiles、user_settings、courses、records、record_files、transcripts、processing_jobs、llm_call_logs（+ langgraph schema 初始化） |
| P1 | ai_summaries、knowledge_points、quizzes、quiz_tests、quiz_test_items、review_materials、todo_items、chat_sessions、chat_messages、learning_events（提前，#33） |
| P2 | transcript_segments、document_segments、source_anchors、source_anchor_links、record_markers、learning_evidence、semantic_embeddings |
| P3 | concepts、concept_relations、record_concepts、record_analyses |
| P4 | user_concept_mastery、misconceptions、misconception_evidence、review_schedules、learner_preferences |
| P5 | teach_back_attempts、course_materials |
| P6 | learning_goals、learning_plans、learning_plan_items、learning_agent_actions、learning_agent_feedback |
| P7 | learning_passport_snapshots |
| 暂缓 | ~~shares~~（v1.1 定稿不建）、study_pods / study_pod_members / study_pod_tasks / study_pod_messages（P8） |

SQLite 十表全部随 V1 建立（cached_transcript_segments 结构先建、P2 启用）。

---

## 12. 数据模型待确认问题

> v1.1 收敛：原 Q2（shares 表）/Q3（L3 离线编辑）/Q8（删除重算）已定稿（功能基线裁决 #15/#16/#18）。以下留待实测：

| # | 问题 | 关联 |
|---|------|------|
| Q4 | Supabase 区域/档位 → 影响 Storage 单文件上限（Q7）与库容量规划 | 功能基线 §11-Q4 |
| Q7 | 上传**原始文件**单文件上限定值（建议 500MB，#54；转码后 3h≈100MB 供参考） | 功能基线 §11-Q7 |
| Q11 | embedding 维度 1024 已定稿；若未来更换模型需全量重嵌入的迁移窗口与停机策略 | 风险（已知成本） |
