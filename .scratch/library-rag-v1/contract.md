# 资料库 / RAG Agent + Learner Memory V1 — 实施契约（工单 01 冻结）

> Status: frozen（2026-09-19，工单 01 交付）
> 消费方：工单 02~07。本文件冻结 spec 留白的全部实施级数值与契约形状；后续工单不再重新讨论已定边界。与 ADR-0024/0025、spec、数据模型 v3.0 冲突时以权威文档为准，发现冲突先回 ADR 评审（§42.13 纪律）。
> 正本分工：黄金集与检索阈值正本 = `docs/evaluation/library-rag-retrieval-baseline.md`（本文件 §5 只做引用）；OpenAPI 正本 = 实施后由 FastAPI 生成（`pnpm --filter @knowrealm/api-types generate`），本文件 §2 是实施前契约草案。
>
> **02 实施记录（2026-09-19）**：§2.2 联邦端点按预留口补充两枚只读——`GET /api/library/records`（跨课程记录行 + `library_item_ids` 回链）与 `GET /api/library/assets`（02=已确认知识点行，含 `detail`）；§2.1 ingest 端点归工单 03 与 WebClipAdapter 同票落地（02 的新写路径 = capture 流程同事务入队 LIBRARY_BACKFILL，新捕获秒级出现在工作台）；§2.3 `PATCH` 02 仅实现 favorite，重命名/归类/归档/删除等随 05。数据模型已升 v3.1（调整 #3 落档）。另两处实施备案：①迁移文件名实际为 `0026_library_foundation.sql`（§1 原文 `_library_rag_foundation` 系草案笔误，DDL 内容零漂移）；②`q` 列表搜索实现为三列 LIKE（标题/origin_uri/metadata_json）——全局 `search_index` FTS 不含 library_items 行，FTS 接入随 04/05 检索域统一时评估，导航级语义（故事 15）已满足。


---

## 1. 迁移 0026 — DDL 终稿（工单 02 实施）

**编号冻结**：本波次唯一 Schema 迁移 = `0026_library_rag_foundation.sql`（四张新表 + 存量结构改造集中在一张迁移，含 06 的 `learner_preferences`；与扩展文档 §42.12 的两处实施级调整同源）。如波次内出现不可预见的追加迁移，自 0027 续编，四位编号连续递增不可跳号。

**实施纪律**（spec 迁移纪律照抄，02 执行）：首次应用前创建独立升级前数据库快照；Schema 失败停止启动保留旧数据；存量哈希/条目/关联/索引补建全部走 `LIBRARY_BACKFILL` 幂等后台 Job，不进迁移；表重建沿用 0010/0017 先例（`PRAGMA legacy_alter_table=ON` + rename + recreate + copy + drop + 重建索引）。

### 1.1 四张新表（逐列核对数据模型 v3.0 §4.2/§4.6/§4.10 通过）

```sql
-- 来源条目：用户拥有的原始资料；Record/学习资产不进此表（ADR-0024）。
CREATE TABLE library_items (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE SET NULL,  -- 可空=未归类全局
    source_type TEXT NOT NULL CHECK (
        source_type IN ('AUDIO', 'DOCUMENT', 'WEB', 'BOOK', 'TEXT')
    ),
    title TEXT NOT NULL CHECK (length(trim(title)) >= 1),
    origin_uri TEXT,          -- 只作出处，不作离线依赖
    local_path TEXT,          -- 数据目录内快照相对路径；纯文本可无文件
    mime_type TEXT,
    file_size INTEGER CHECK (file_size IS NULL OR file_size >= 0),
    content_hash TEXT NOT NULL,  -- 重复提示用，不设 UNIQUE（用户可选择保留双份）
    fetched_at TEXT,
    metadata_json TEXT NOT NULL CHECK (json_valid(metadata_json)),
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version >= 1),
    favorite INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),  -- 见 1.3 实施级调整
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT           -- 软删 30 天回收站
);

CREATE INDEX idx_library_items_course_updated ON library_items(course_id, updated_at DESC);
CREATE INDEX idx_library_items_source_type ON library_items(source_type, updated_at DESC);
CREATE INDEX idx_library_items_status ON library_items(status, updated_at DESC);
CREATE INDEX idx_library_items_content_hash ON library_items(content_hash);
CREATE INDEX idx_library_items_deleted_at ON library_items(deleted_at);

-- 来源 ↔ Record 多对多：一书拆多章 / MULTI_SOURCE Record 双向覆盖。
CREATE TABLE library_item_records (
    library_item_id TEXT NOT NULL REFERENCES library_items(id) ON DELETE CASCADE,
    record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('PRIMARY', 'SUPPLEMENTAL')),
    sequence_no INTEGER NOT NULL DEFAULT 0 CHECK (sequence_no >= 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (library_item_id, record_id)
);

CREATE INDEX idx_library_item_records_record ON library_item_records(record_id);

-- 可跨重启审核的业务提案：创建不改事实，确认后领域 Service 原子应用。
CREATE TABLE agent_proposals (
    id TEXT PRIMARY KEY,
    proposal_type TEXT NOT NULL CHECK (
        proposal_type IN ('ORGANIZE', 'MEMORY', 'RESEARCH_INGEST')
    ),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'APPLIED', 'REJECTED', 'FAILED')),
    session_id TEXT,          -- 溯源非授权
    message_id TEXT,
    target_type TEXT,
    target_id TEXT,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),  -- Pydantic 判别校验
    evidence_refs_json TEXT CHECK (
        evidence_refs_json IS NULL OR json_valid(evidence_refs_json)
    ),
    error_code TEXT,          -- 应用失败保留稳定错误码
    created_at TEXT NOT NULL,
    decided_at TEXT           -- 应用或拒绝时填写
);

CREATE INDEX idx_agent_proposals_status_created ON agent_proposals(status, created_at DESC);
CREATE INDEX idx_agent_proposals_target ON agent_proposals(target_type, target_id);

-- 学习者偏好单例事实表（Learner Memory V1，ADR-0025）。
CREATE TABLE learner_preferences (
    id TEXT PRIMARY KEY CHECK (id = 'me'),
    user_selected_preference TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(user_selected_preference)),
    observed_learning_preference TEXT CHECK (
        observed_learning_preference IS NULL
        OR json_valid(observed_learning_preference)
    ),
    observed_confidence REAL CHECK (
        observed_confidence IS NULL OR observed_confidence BETWEEN 0 AND 1
    ),
    evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
    last_observed_at TEXT,
    updated_at TEXT NOT NULL
);
```

### 1.2 存量结构改造（同迁移内）

```sql
PRAGMA legacy_alter_table=ON;

-- chat_sessions：scope CHECK 扩五档 + library_item_id（表重建）。
ALTER TABLE chat_sessions RENAME TO chat_sessions_v25;
CREATE TABLE chat_sessions (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE SET NULL,
    record_id TEXT REFERENCES records(id) ON DELETE SET NULL,
    concept_id TEXT,
    library_item_id TEXT REFERENCES library_items(id) ON DELETE SET NULL,
    mode TEXT NOT NULL CHECK (
        mode IN ('ASK', 'COURSE_QA', 'SOCRATIC_TUTOR', 'TEACH_BACK')
    ),
    scope TEXT NOT NULL DEFAULT 'FREE' CHECK (
        scope IN ('FREE', 'RECORD', 'LIBRARY_ITEM', 'COURSE', 'ALL')
    ),
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
INSERT INTO chat_sessions (
    id, course_id, record_id, concept_id, library_item_id, mode, scope,
    title, created_at, updated_at, deleted_at
)
SELECT
    id, course_id, record_id, concept_id, NULL, mode, scope,
    title, created_at, updated_at, deleted_at
FROM chat_sessions_v25;
DROP TABLE chat_sessions_v25;
CREATE INDEX idx_chat_sessions_list ON chat_sessions(deleted_at, updated_at DESC);

-- processing_jobs：library_item_id 关联 + job_type 扩展（表重建，全列照抄 0017）。
ALTER TABLE processing_jobs RENAME TO processing_jobs_v25;
CREATE TABLE processing_jobs (
    id TEXT PRIMARY KEY,
    record_id TEXT REFERENCES records(id) ON DELETE CASCADE,
    library_item_id TEXT REFERENCES library_items(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL CHECK (
        job_type IN (
            'ASR', 'AUDIO_TRANSCODE', 'DOCUMENT_PARSE', 'EMBEDDING',
            'CONCEPT_EXTRACTION', 'SUMMARY', 'KNOWLEDGE_EXTRACTION',
            'QUIZ_GENERATION', 'TODO_GENERATION', 'QUIZ_GRADING',
            'REVIEW_MATERIAL_GENERATION', 'WEB_FETCH', 'LIBRARY_BACKFILL',
            'INDEX_REBUILD', 'CLEANUP', 'BACKUP_EXPORT'
        )
    ),
    status TEXT NOT NULL CHECK (
        status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')
    ),
    progress REAL NOT NULL CHECK (progress BETWEEN 0 AND 1),
    attempts INTEGER NOT NULL CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL CHECK (max_attempts > 0),
    next_run_at TEXT,
    input_json TEXT NOT NULL,
    result_json TEXT,
    error_code TEXT,
    error_message TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    waiting_reason TEXT CHECK (
        waiting_reason IS NULL OR waiting_reason IN (
            'CONSENT_REQUIRED', 'ASR_KEY_REQUIRED', 'OFFLINE'
        )
    )
);
INSERT INTO processing_jobs (
    id, record_id, library_item_id, job_type, status, progress, attempts,
    max_attempts, next_run_at, input_json, result_json, error_code, error_message,
    started_at, finished_at, created_at, updated_at, waiting_reason
)
SELECT
    id, record_id, NULL, job_type, status, progress, attempts,
    max_attempts, next_run_at, input_json, result_json, error_code, error_message,
    started_at, finished_at, created_at, updated_at, waiting_reason
FROM processing_jobs_v25;
DROP TABLE processing_jobs_v25;
CREATE INDEX idx_processing_jobs_record ON processing_jobs(record_id);
CREATE INDEX idx_processing_jobs_library_item ON processing_jobs(library_item_id);
CREATE INDEX idx_processing_jobs_claim ON processing_jobs(status, next_run_at, created_at);
-- 0017 的五个 one-active 部分唯一索引原样重建（略，02 照抄）。
CREATE UNIQUE INDEX idx_processing_jobs_one_active_web_fetch
    ON processing_jobs(library_item_id)
    WHERE job_type = 'WEB_FETCH' AND status IN ('PENDING', 'RUNNING');
CREATE UNIQUE INDEX idx_processing_jobs_one_active_index_rebuild
    ON processing_jobs(library_item_id)
    WHERE job_type = 'INDEX_REBUILD' AND status IN ('PENDING', 'RUNNING');
-- LIBRARY_BACKFILL 为全局单例 Job：NULL 不受唯一索引约束，单例由 Service 层保证。

-- document_segments：course_material_id 改名 library_item_id + 补 FK（表重建，
-- 其余列与 CHECK XOR 原样；0019 未建过本表索引，无索引需重建）。
ALTER TABLE document_segments RENAME TO document_segments_v25;
CREATE TABLE document_segments (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE CASCADE,
    record_id TEXT REFERENCES records(id) ON DELETE CASCADE,
    record_file_id TEXT REFERENCES record_files(id) ON DELETE CASCADE,
    library_item_id TEXT REFERENCES library_items(id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL CHECK (sequence_no >= 0),
    page_no INTEGER,
    section_title TEXT,
    content TEXT NOT NULL,
    start_offset INTEGER,
    end_offset INTEGER,
    content_hash TEXT NOT NULL,
    CHECK ((record_file_id IS NULL) != (library_item_id IS NULL))
);
INSERT INTO document_segments (
    id, course_id, record_id, record_file_id, library_item_id, sequence_no,
    page_no, section_title, content, start_offset, end_offset, content_hash
)
SELECT
    id, course_id, record_id, record_file_id, course_material_id, sequence_no,
    page_no, section_title, content, start_offset, end_offset, content_hash
FROM document_segments_v25;
DROP TABLE document_segments_v25;

-- source_anchors：course_id 改可空（全局来源真实锚点）+ 改名列补 FK（表重建，
-- 其余列与类型精确 CHECK 原样；无既有索引）。
ALTER TABLE source_anchors RENAME TO source_anchors_v25;
CREATE TABLE source_anchors (
    id TEXT PRIMARY KEY,
    course_id TEXT REFERENCES courses(id) ON DELETE CASCADE,  -- 由 NOT NULL 改可空
    source_type TEXT NOT NULL CHECK (
        source_type IN ('AUDIO_SEGMENT', 'DOCUMENT_SEGMENT', 'USER_NOTE', 'CHAT_MESSAGE')
    ),
    source_id TEXT NOT NULL,
    record_id TEXT REFERENCES records(id) ON DELETE CASCADE,
    record_file_id TEXT REFERENCES record_files(id) ON DELETE CASCADE,
    library_item_id TEXT REFERENCES library_items(id) ON DELETE CASCADE,
    transcript_segment_id TEXT REFERENCES transcript_segments(id) ON DELETE CASCADE,
    document_segment_id TEXT REFERENCES document_segments(id) ON DELETE CASCADE,
    start_offset INTEGER,
    end_offset INTEGER,
    page_no INTEGER,
    CHECK (
        (source_type != 'AUDIO_SEGMENT' OR transcript_segment_id IS NOT NULL)
        AND (source_type != 'DOCUMENT_SEGMENT' OR document_segment_id IS NOT NULL)
    )
);
INSERT INTO source_anchors (
    id, course_id, source_type, source_id, record_id, record_file_id,
    library_item_id, transcript_segment_id, document_segment_id,
    start_offset, end_offset, page_no
)
SELECT
    id, course_id, source_type, source_id, record_id, record_file_id,
    course_material_id, transcript_segment_id, document_segment_id,
    start_offset, end_offset, page_no
FROM source_anchors_v25;
DROP TABLE source_anchors_v25;

PRAGMA legacy_alter_table=OFF;
```

**DDL 层的三个显式决定**：

1. `chat_sessions` **不加** `scope='LIBRARY_ITEM' → library_item_id NOT NULL` 的表级 CHECK：资料条目物理删除走 `ON DELETE SET NULL`，会话保留为运行时推导的「挂载失效」态（对齐 record_deleted 先例），加 CHECK 会让物理删除失败。「仅由资料详情创建并必填」在 Service/API 层校验。
2. `processing_jobs.library_item_id` 用 `ON DELETE CASCADE`：条目物理删除时其技术任务随行消亡（PENDING/RUNNING 由 Service 先置 CANCELLED，对齐 Record 删除纪律）。
3. `semantic_embeddings` 表当前不存在（未实施）：不参与 0026；若 sqlite-vec 经 §5 判据触发，建表时直接使用 `library_item_id` 列名（数据模型 v3.0 §4.7 已如此定义），无需改名。

### 1.3 逐列核对结论与实施级调整 #3

四张新表逐列核对数据模型 v3.0：除下述一项外全部一致。

| 差异 | 说明 | 处置 |
| --- | --- | --- |
| `library_items.favorite` | 数据模型 v3.0 与扩展文档 §42.4 的字段表**均无**收藏列，但 spec 用户故事 14（收藏资料条目）、左侧智能视图「收藏」、跨类型安全动作「收藏」都依赖它；不补列则工单 02 无法交付收藏视图 | **实施级调整 #3**：DDL 增加 `favorite INTEGER NOT NULL DEFAULT 0`（仅条目域，Record/资产收藏不在用户故事内不加）；工单 02 落地时同步数据模型 v3.0 §4.2 字段表，工单 07 校验交叉引用 |
| 补充索引 ×2（`idx_library_items_deleted_at`、`idx_library_item_records_record`） | v3.0 §4.2 只列 4 个索引；回收站视图按 `deleted_at` 取数、详情 `derived_records` 按-record 反查是 02 的两个必经查询路径，缺索引则全表扫 | **实施级调整 #3 附带**：DDL 增加上述 2 个索引；工单 02 同步数据模型 v3.0 索引行 |

其余核对项（列名、可空性、CHECK 值域、FK 动作、v3.0 已列索引）与 v3.0 一致，不逐格重列。

### 1.4 `user_version` 断言盘点（2026-09-19，迁移 0025 后）

| 位置 | 处数 | 形态 |
| --- | --- | --- |
| `backend/tests/`（16 个文件） | 23 | `assert version == (supported_user_version(),)`（test_archive.py 8 处 + 15 文件各 1 处） |
| `app/db/migrations.py` | 1 | `supported_user_version()` 定义（迁移文件数自动发现） |
| `app/modules/data/archive.py` | 1 | `read_user_version` 只读（导出清单），非断言 |
| `backend/AGENTS.md` | 1 | 迁移清单文档行（0026 落地时同步为「0001~0026」） |

**结论**：C2 收敛（3b836b0）后全部断言动态引用 `supported_user_version()`——**0026 落地零测试同步成本**（文件数即版本号，断言自动随动）；0026 的新迁移测试沿用同形断言模式即可。历史「动迁移先全库 grep 断言」纪律保留为兜底防线。

---

## 2. OpenAPI 契约草案（实施前冻结；正本以实施后生成物为准）

### 2.1 统一入库 ingest（02/03 实施）

`POST /api/library/ingest`（JSON，web/text）与 `POST /api/library/ingest/file`（multipart，本地文件）：

```jsonc
// source=web（03）
{ "source": "web", "url": "https://example.com/article", "course_id": null }
// source=text（02）
{ "source": "text", "title": "可选标题", "content": "正文…", "course_id": null }
```

- 响应 `202`：`LibraryItemOut`（立即建条目，`status=ACTIVE`；处理状态由列表/详情派生字段轮询）+ 关联 `ProcessingJobOut` 摘要（web=WEB_FETCH，file=DOCUMENT_PARSE，text 无 Job）。
- 重复哈希：`409 LIBRARY_ITEM_DUPLICATE_CONTENT`，body 含 `existing_item_id`；请求带 `allow_duplicate=true` 时放行保留双份。
- 错误码：`LIBRARY_INGEST_INVALID_REQUEST`（判别失败/正文为空）、`LIBRARY_ITEM_LIMIT_EXCEEDED`（单条正文超限，对齐 30k 索引限长）、`WEB_FETCH_INVALID_URL`、`WEB_FETCH_BLOCKED_URL`（SSRF/私网/重定向重校验）、`WEB_FETCH_CONTENT_TOO_LARGE`、`WEB_FETCH_UNSUPPORTED_CONTENT_TYPE`、`WEB_FETCH_UNREACHABLE`、`WEB_FETCH_EXTRACT_FAILED`（正文垃圾判定 → 前端降级手动粘贴）。

### 2.2 列表与详情（02）

- `GET /api/library/items`：分页 `offset/limit`；筛选 `source_type` / `course_id`（`null`=未归类）/ `status`(ACTIVE|ARCHIVED) / `favorite` / `availability`(PROCESSING|RETRIEVABLE|FAILED，派生) / `view`(recent|needs_review|trash) / `q`（标题/来源/元数据，走现有全局 FTS）；响应 `{ items: LibraryItemSummary[], total }`。
- `GET /api/library/items/{id}`：详情 = 元数据 + 处理与可用性摘要 + `derived_records`（含 record 摘要，供跳转）+ 可执行动作列表。
- `GET /api/library/items/{id}/content`：净化正文快照分页读取（检查器安全预览）。
- 联邦视图冻结：**不新增统一联邦目录端点**——「全部/学习记录/学习资产」分类复用既有 records/summary/knowledge_points 等端点由前端并行拉取（复用优先）；若 02 实施中证明不可行，在 02 内提请补充而不阻塞他票。

### 2.3 生命周期（02/05）

| 端点 | 语义 |
| --- | --- |
| `PATCH /api/library/items/{id}` | 重命名（title）/ 归类（course_id，`null`=取消归类）/ 收藏（favorite） |
| `POST /api/library/items/{id}/archive`、`/unarchive` | 归档退出默认浏览与来源召回，快照关联保留 |
| `DELETE /api/library/items/{id}` | 软删入回收站（30 天）；派生 Record 不级联、不提示 |
| `DELETE /api/library/items/{id}?permanent=true` | 物理删除；存在未软删派生 Record 时 `409 LIBRARY_ITEM_HAS_DERIVED_RECORDS` |
| `POST /api/library/items/{id}/restore` | 回收站恢复（校验快照、按需重建索引） |
| `POST /api/library/items/{id}/retry` | 失败重试（复用原 Job，attempts 归零） |
| `POST /api/library/items/{id}/refetch` | 同 URL 重新抓取 → **新条目**（不覆盖旧快照） |
| `POST /api/library/items/{id}/rebuild-index` | 索引重建 Job |

通用错误：`LIBRARY_ITEM_NOT_FOUND`、`LIBRARY_ITEM_ALREADY_ARCHIVED/ACTIVE`、`LIBRARY_ITEM_NOT_IN_TRASH`。

### 2.4 提案（05/06）

- `GET /api/proposals?status=PENDING&proposal_type=ORGANIZE|MEMORY|RESEARCH_INGEST`
- `POST /api/proposals/{id}/confirm` → 领域 Service 原子应用 → `200 { status: "APPLIED", result? }`；已决 `409 PROPOSAL_ALREADY_DECIDED`；应用失败落 `FAILED` + `error_code` → `422 PROPOSAL_APPLY_FAILED`
- `POST /api/proposals/{id}/reject` → `200 { status: "REJECTED" }`（拒绝不改任何事实）
- 错误码：`PROPOSAL_NOT_FOUND`。

### 2.5 Learner Memory（06）

- `GET /api/learner/preferences`：单例视图（显式偏好 + 观察偏好含置信度/证据数/确认时间 + 外发开关）。
- `PUT /api/learner/preferences`：编辑显式偏好（立即生效）。
- `DELETE /api/learner/preferences/observed/{key}`：删除单条观察偏好。
- `PUT /api/learner/memory-outbound`：`{ enabled: bool }` 长期记忆外发开关（关闭=本地保留不外发）。

### 2.6 会话与检索（04）

- `POST /api/chat/sessions` 扩展：`{ "scope": "LIBRARY_ITEM", "library_item_id": "…" }`（仅资料详情入口创建）；`404 LIBRARY_ITEM_NOT_FOUND`、`409 LIBRARY_ITEM_ARCHIVED` / `LIBRARY_ITEM_DELETED`。既有端点形状不变，scope 会话内不可变。
- **RAG 检索不开公开查询端点**：`LibraryRetrievalService` 仅供业务模块内部调用（`search_library` 工具经 ContextVar 绑定范围），spec 已否决任意查询入口。
- `chat_messages.citations_json` 新增 library 条目（数据级，无 DDL）：`{ "index": 1, "source": "library", "library_item_id": "…", "title": "…", "quote": "≤80字逐字", "anchor_id": "…" }`；与 record 条目同样必须回业务 Segment 逐字校验，web 条目维持仅非空检查。

**RetrievalResult 三类结构**（服务内部契约，工具载荷）：

```jsonc
{
  "evidence_hits": [{          // 唯一可引用类
    "library_item_id": "…", "record_id": "…?", "source_title": "…",
    "quote": "逐字原文", "context_window": "受限相邻窗口",
    "segment_id": "…", "anchor_id": "…?", "locator": { "time": "0:10-0:25" } | { "page": 12 },
    "source_type": "AUDIO|DOCUMENT|WEB|BOOK|TEXT", "channel": "fts|concept_expansion|vector?"
  }],
  "asset_matches": [{ "type": "LIBRARY_ITEM|RECORD|KNOWLEDGE_POINT|…", "id": "…", "title": "…" }],
  "concept_hints": [{ "concept_id": "…", "canonical_name": "…", "description": "…", "course_id": "…" }]
}
```

分数只用于排序，不出现在用户可见载荷（不伪装可信度）；禁止引用 FTS token / Embedding / Concept 描述 / AI 摘要为来源。

### 2.7 错误码登记纪律

上列新错误码在 02~06 各自实施时登记 `shared/errors` 并同步 zh/en 文案（plan20 纪律）；命名前缀按域（`LIBRARY_*` / `PROPOSAL_*` / `WEB_FETCH_*`）。

---

## 3. Agent 工具预算与检索常量（04 实施 enforcement）

| 数值 | 冻结值 | 依据 |
| --- | --- | --- |
| 每轮（每条用户消息）工具调用上限 | **6 次** | 检索改写重试（2~3）+ web_search + 余量；超限提示直接回答并声明检索范围 |
| `search_library` 单次 evidence_hits 上限 | **8** | 对齐现役 `SEARCH_LIBRARY_LIMIT=8`（BM25 top-8） |
| `search_library` 单次 concept_hints 上限 | **4** | 对齐现役 `CONCEPT_MATCH_LIMIT=4` |
| `search_library` 单次 asset_matches 上限 | **8** | 导航命中与证据同量级，防刷屏 |
| 概念扩展词单词命中上限 | **8** | 对齐现役 `_EXPANSION_PER_TERM_LIMIT=8` |
| 单次工具结果载荷上限 | **4,000 字符** | 8 命中 × ~400 字窗口 + hints，截断保护 |
| 每轮工具输出累计回喂上限 | **12,000 字符** | 6 次 × 4k 理论满载 24k 收缩至一半；超限截断 + 提示收窄查询 |
| 引用条目 quote 上限 | **80 字** | 对齐现役 `_OCCURRENCE_QUOTE_LIMIT` 与引用规范 |
| 单命中上下文窗口上限 | **400 字符** | 对齐现役 `FALLBACK_HIT_MAX_CHARS` |
| Recall@K 的 K | **8** | 与 evidence_hits 上限同源 |

预算超限行为：截断并附带 `"truncated": true` 说明，不静默丢弃整个结果；Agent 提示词声明预算与「换词重试 ≤2 次后如实回答」纪律。

---

## 4. 检索链冻结摘要（04 实施依据）

- 管线顺序固定：作用域与软删过滤 → 查询规范化（jieba `cut_for_search` 索引/查询同源）→ Segment FTS 与 CONFIRMED Concept 扩展并行召回 →（触发判据满足时）sqlite-vec 追加 → 去重（record_id+content）与确定性排序 → 回业务表逐字原文 → Source Anchor 组装。
- 五档 Scope 隔离语义与「挂载范围无证据必须回答未找到」按 spec；LIKE 兜底不进入服务管线（B2 迁移期产物，`search_transcript` 降为内部复用代码后由记录级路径继承）。
- sqlite-vec 触发判据与当前判定：见 §5。

## 5. 黄金集与阈值（正本引用）

正本：`docs/evaluation/library-rag-retrieval-baseline.md`（黄金集 20 查询 + 四指标冻结阈值：Recall@8 ≥ 0.90、MRR ≥ 0.90、无答案准确率 = 1.0、引用正确率 = 1.0、作用域泄漏 = 0；sqlite-vec 当前判定 = 不进入本波次，1/17 词汇错配未达触发阈值；英文结论 = 无需补英文分词处理；ARCHIVED 来源 / 真实 WEB 来源 / 真实用户语料三项维度的激活时点见其 §3.1 维度激活表——ARCHIVED 条目零召回为 07 硬门禁）。可执行资产：`backend/tests/test_library_retrieval_eval.py`，工单 07 发布门禁复跑同一黄金集断言。
