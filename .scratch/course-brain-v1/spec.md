# F4 Course Brain V1（课程知识大脑：Concept 图谱 + 构建审核闭环 + B2 检索增强）

Status: in-progress

依据：`.scratch/course-brain-v1/plan.md`（用户提供的开发计划）+ 2026-09-15 grill 九问裁决（全部按推荐）。
权威对齐：数据模型 v2.7 §4.6 Course Brain 域（升 v2.8 时标注已实施）、基线 v2.7 F4（:280/:307）、ADR-0022（本 Epic 新增）。

## Problem Statement

课程详情页的知识图谱/脑图至今是 mock（`courseDetailInsights.ts`，文件头注释自认"后端无课程级聚合接口"）；跨记录问答（B2）靠 BM25 词面检索，同义词/简称问法（"可见性怎么实现"→MVCC）召回不稳，"老师讲过几次 X"无法按真实来源回答。需要 Course 级 Concept 底座：多来源抽取 → 人工审核 → 可追溯图谱 → Agent 只读消费。

## Solution

新增 `course_brain` 模块：三张 Concept 表（迁移 0023）+ 构建 job（启用预留 `CONCEPT_EXTRACTION`）+ 查询服务 + 审核端点；B2 `search_library` 增强（Concept 命中→检索词扩展→Segment 引用）；前端 map Tab 升级为 Course Brain 主页面，mock 彻底删除。

## grill 裁决记录（2026-09-15，用户全部"按推荐"）

| # | 决策 |
|---|---|
| Q1 | job_type 用 SQL CHECK **预留值 `CONCEPT_EXTRACTION`**（Python 枚举补成员），零表重建；worker 内部命名 course_brain_build |
| Q2 | 来源关联双轨：Transcript/Document/Chat = `source_anchor_links(resource_type='CONCEPT')`；KP = `record_concepts.knowledge_point_id` 桥列（不为 KP 造新锚点类型） |
| Q3 | `UNIQUE INDEX ... WHERE status='CONFIRMED'` 部分唯一索引落地；数据模型 v2.8 更正"SQLite 无部分唯一索引"错误论断 |
| Q4 | STALE 检测 = **查询时指纹派生**：快照接口现算各来源表 (count, max_updated_at) 聚合指纹，与上次成功构建 result_json 指纹比对；不进 A3 事件消费 |
| Q5 | V1 检索朴素版：Concept 进现有 `segment_search_index`（entity_type='CONCEPT'），命中后 canonical_name + 原查询**并跑** Segment FTS 合并去重，LIKE 兜底照旧；同义词扩展（concepts 加 terms 列）留作 CB-01 失败后的升级路径 |
| Q6 | map Tab = Course Brain 主页面；概览玫瑰图同步吃真实 Concept（Top 概念分布）；未构建两处均显示构建引导空态；`courseDetailInsights.ts` mock 模块彻底删除 |
| Q7 | 来源跳转 V1 含定位增强：TranscriptPanel 定位到 segment（时间），文档带页码；视图层不支持页码定位则降级文本标注 |
| Q8 | CB-01 用合成覆盖样例（同义词/简称/跨记录统计/原文定位四类）冒烟评测；真实语料评测并入用户真机验收清单，结论如实记录口径 |
| Q9 | 按"存量薄"设计：Transcript/Document 分块抽取为主力，KP 为增强种子；不依赖存量假设 |

## 数据合同（迁移 0023_course_brain.sql）

三张新表（列名对齐数据模型 v2.7 §4.6，实现按仓库惯例补齐 id/时间戳）：

**concepts**
- `id TEXT PK`（uuid4）、`course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE`
- `canonical_name TEXT NOT NULL`（1-100）、`normalized_name TEXT NOT NULL`、`description TEXT NOT NULL DEFAULT ''`
- `concept_type TEXT NOT NULL DEFAULT 'TERM'`、`importance INTEGER NOT NULL DEFAULT 3`（1-5）
- `status TEXT NOT NULL DEFAULT 'CANDIDATE' CHECK IN ('CANDIDATE','CONFIRMED','ARCHIVED')`
- `source TEXT NOT NULL DEFAULT 'AI_EXTRACTED' CHECK IN ('AI_EXTRACTED','USER_CONFIRMED','SYSTEM')`
- `created_at/updated_at`（ISO8601 UTC）；**无 deleted_at**（ARCHIVED 状态即退役语义，候选忽略也走 ARCHIVED）
- `CREATE UNIQUE INDEX idx_concepts_course_confirmed ON concepts(course_id, normalized_name) WHERE status='CONFIRMED'`
- `normalized_name` = 确定性函数：strip → 空白折叠单空格 → 全角转半角 → casefold

**concept_relations**
- `id PK`、`course_id NOT NULL FK CASCADE`
- `source_concept_id/target_concept_id TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE`
- `relation_type CHECK IN ('PREREQUISITE','PART_OF','RELATED_TO','COMPARE_WITH','CAUSES','APPLIES_TO')`
- `confidence REAL NOT NULL DEFAULT 0`（0-1）、`evidence_count INTEGER NOT NULL DEFAULT 0`
- `status CHECK IN ('CANDIDATE','CONFIRMED','DISMISSED')`、`created_at/updated_at`
- `UNIQUE (source_concept_id, target_concept_id, relation_type)`；CHECK source≠target

**record_concepts**
- `id PK`、`record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE`、`concept_id TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE`
- `knowledge_point_id TEXT REFERENCES knowledge_points(id) ON DELETE SET NULL`（KP→Concept 桥，Q2）
- `relevance REAL NOT NULL DEFAULT 0`（0-1）、`evidence_count INTEGER NOT NULL DEFAULT 0`、`first_start_ms INTEGER`（可空，最早出现时间）
- `created_at/updated_at`；`UNIQUE (record_id, concept_id)`

**扩展 source_anchor_links.resource_type**：CHECK 增加 `'CONCEPT'`（rename→重建→拷贝→drop 仓库惯例，参照 0017 的 `PRAGMA legacy_alter_table` 包裹）。

**不新增**：concept_sources、concept_aliases、course_brain_runs、semantic_embeddings/vec0（sqlite-vec 由 CB-01 结论决定，默认延后）。

**user_version 断言**：13 处硬编码 22 → 23（test_records/test_summary/test_document_import/test_quizzes/test_knowledge_points/test_review_materials/test_chat_sessions/test_quiz_tests/test_todos/test_source_anchors/test_segment_search/test_learning/test_courses）。

## 模块与 API（backend/app/modules/course_brain/）

models.py / schemas.py / service.py / worker.py / routes.py。

| 端点 | 说明 |
|---|---|
| `GET /api/courses/{course_id}/brain` | 快照：状态（EMPTY/BUILDING/REVIEW/READY/STALE/FAILED）、概念统计、候选计数、STALE 指纹比对结果 |
| `POST /api/courses/{course_id}/brain/builds` | 触发构建（校验课程存活+非 ARCHIVED；无 key→409 LLM_PROVIDER_UNCONFIGURED、无同意→409 AI_CONSENT_REQUIRED；重复构建→409） |
| `GET /api/courses/{course_id}/brain/concepts` | 概念列表（status 筛选、分页/上限）；含出现次数派生 |
| `GET /api/courses/{course_id}/brain/concepts/{concept_id}` | 概念详情 + 来源概要 |
| `GET /api/courses/{course_id}/brain/concepts/{concept_id}/sources` | 来源列表：anchors（source_type/quote/时间/页码/record）+ KP 桥 + chat 回溯 |
| `POST /api/courses/{course_id}/brain/apply-review` | 审核操作批量端点（见下） |
| `POST /api/courses/{course_id}/brain/concepts` | 手动创建（直接 CONFIRMED，source=USER_CONFIRMED） |

审核操作（apply-review 的 decision 列表）：`confirm`（可带重命名）/ `merge`（候选并入已有 Concept，迁移 record_concepts+anchors）/ `dismiss`（候选→ARCHIVED）/ `confirm_relation` / `dismiss_relation`。

守卫：ARCHIVED 课程全端点 409（对齐 summary/KP 闸门惯例）；跨课程 concept_id 404；重新构建不得修改 CONFIRMED 概念的名称/描述（只增量挂接）；失去全部有效来源的 CONFIRMED 概念由快照派生"待归档"徽章，不自动改状态。

## 构建 Pipeline（worker，job_type=CONCEPT_EXTRACTION）

复用 JobRunner WorkerSpec 协议（参照 quiz_grading_worker）。record_id=None（课程级）。流程：

1. preflight：consent+key（缺→PENDING 等待，与 KP/summary worker 一致）。
2. 校验课程非 ARCHIVED、收集未软删记录（含 ARCHIVED 拦截二次校验）。
3. 按 Record 分块：转写 ≤30k 字符全文（复用 KP worker TRANSCRIPT_LIMIT 惯例），超长降级为已确认摘要+KP 清单；Document Segment 拼入同块（受总预算 40k 上限约束）。
4. LLM 结构化抽取（with_structured_output，schema 带字段 description）：`concepts[]{name, description, concept_type, importance, evidence[]{quote, source_hint}}` + `relations[]{source, target, relation_type, confidence}`；evidence quote 必须逐字（≤120 字符）。
5. 确定性归一化 → 与 CONFIRMED 概念 normalized_name 完全一致→自动挂接（不重复建节点）；相似（编辑距离/token 重叠阈值）→生成 merge 建议候选；全新→CANDIDATE。
6. 原子发布：候选+record_concepts+anchors（原文逐字定位：transcript segment 子串匹配建 AUDIO_SEGMENT/DOCUMENT_SEGMENT 锚点；chat 来源 KP 经桥列）+relation 候选，单事务。失败不破坏上一版图谱。
7. result_json：`{"fingerprint": {...}, "concept_count": n, "candidate_count": n}`；input_json：`{"provider_fingerprint": ..., "source_fingerprint": ...}`（对齐 SUMMARY input 惯例）。

LLM 埋点：graph_name="course-brain"、prompt_version="course_brain_v1"，走 llm_call_logs 统一工厂（零第二套系统）。

## B2 检索增强（CB-07）

`search_library` 内部（挂载条件不变，RECORD/FREE 不受影响）：

1. Concept FTS：concepts（CONFIRMED）建/维护 `segment_search_index(entity_type='CONCEPT', body=canonical_name+description)`——概念增删改同事务 upsert（复用 SegmentSearchService.upsert 约定，加 entity 类型）。
2. 查询时：原查询跑 Concept FTS（top 4）→ 命中概念集 → **原查询 + 各 canonical_name 并跑** Segment FTS（每词 top 8）→ 合并去重（record_id+quote）→ occurrences 按 record 去重。
3. 返回结构扩展（向后兼容）：`{"hits": [...现行...], "concepts": [{concept_id, canonical_name, record_count, occurrence_count}], "occurrences": [{record_id, record_title, anchor 定位, quote}]}`——前端工具卡只吃 hits，不受影响。
4. ALL 会话：Concept 过滤 `course_id IS NOT NULL` 且各课程独立——ALL 检索概念匹配不做课程混入错误（每概念只在归属课程内扩展）。
5. prompt v6（`chat-concept-v6`）：新增纪律——优先用已确认 Concept 理解问题；Concept 描述不得冒充原文引用（引用必须逐字来自检索 hits）；"讲过几次"按 occurrences 去重 Record 计数、禁止模型估算。

## 前端（CB-09/10/11）

- 路由不动：`/spaces/$courseId` map Tab = Course Brain 主页面（状态栏 + 图谱/列表双视图 + 审核抽屉 + Relation 审核区 + 概念详情面板 + 来源列表 + 来源类型筛选 + 重建入口）；overview 玫瑰图吃真实 Concept Top 分布。
- mockCourseKnowledgePoints/aggregateCourseKnowledgePoints/buildCourseKnowledgeRelations 及其测试**整体删除**；ECharts 封装（BaseChart/echarts.ts/token.ts）原样复用，关系图节点=Concept（大小=evidence_count，色=status/importance）、边=CONFIRMED relation（CANDIDATE 虚线或不渲染，取其一）。
- 来源跳转：Transcript→`/records/$recordId?tab=transcript` 定位 segment（时间）；Document→记录文档视图+页码（视图不支持则来源行文本标注页码）；KP→知识点面板；Chat→`/chat/$sessionId`（现状）。
- 状态机六态 EMPTY/BUILDING/REVIEW/READY/STALE/FAILED 由快照接口驱动；BUILDING 轮询。
- i18n：zh/en 同步（一致性防线）；亮/暗/窄窗/减少动效过验收。

## 验收门禁（对齐 plan §十）

- 后端：`uv run pytest --basetemp=.pytest-tmp` + ruff check + ruff format --check + pyright + openapi --check（契约变更后 regenerate）。
- 前端：`pnpm test -- --maxWorkers=4` + lint + build。
- Agent 边界：Agent 只读 CONFIRMED；无写工具；不写 learning_events/Evidence；knowrealm.db 与 langgraph.db 职责不混。
- 文档同步：数据模型 v2.8（§4.6 标已实施+部分唯一索引更正）、PRD/扩展文档 §40.4 序列更新、CONTEXT.md 词条、ADR-0022、PROJECT_PROGRESS（≤200 行）、OpenAPI 类型。
- 真机验收（用户执行，单列不代勾）：多来源首次构建、审核闭环、来源跳转定位、"讲过几次"真实回答、无 Key 降级、窄窗/暗色。

## Out of Scope（V1.1+）

- sqlite-vec / semantic_embeddings（CB-01 结论默认延后；失败主因是词汇不重合时升级）。
- Agent 写工具（propose_* 走 CANDIDATE+HITL，未来票）。
- 图上拖拽创建关系、Knowledge GPS、Mastery 消费、课件 Diff。
- User Note / Course Material 来源（真实写入者完成后接入）。
- 同义词扩展列（concepts.terms）与 query-time LLM 扩展（CB-01 失败路径）。
