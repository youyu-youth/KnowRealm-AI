# 规范：数据层（Pydantic + SQLAlchemy + SQLite）

> 适用范围：`backend/app/` 的模型、Schema、数据库访问，以及 `backend/migrations/`。

## 1. 核心架构

- **Pydantic 管边界校验，SQLAlchemy 管持久化，`knowrealm.db` 是唯一业务事实源。**
- FastAPI sidecar 是数据库与数据目录业务文件的唯一协调者；同一数据目录必须由 sidecar 持有进程生命周期操作系统排他锁，拿锁失败时不得执行迁移、备份或启动 worker。UI 与 Tauri 只能通过 localhost API 读写业务数据和录音暂存，不得直连数据库或直接写数据目录。
- 本地单用户库不设 `user_id`、RLS 或通用 `version` 乐观锁列。`ai_summaries.version_no`、`transcripts.source_version` 属于业务版本号，继续保留。
- 固定技术线：Pydantic / pydantic-settings 2.x（≥2.11）、SQLAlchemy 2.0.x、aiosqlite、sqlite-vec；依赖版本以锁文件为准，不采用 SQLModel、SQLAlchemy 2.1 beta 或其他数据库驱动。

## 2. Pydantic v2

- ORM 模型放 `models/`，Pydantic 模型放 `schemas/`；两者严格分离，API 不得直接暴露 ORM 模型。
- 使用 v2 API：`ConfigDict(from_attributes=True)`、`model_validate()`、`field_validator`、`model_validator`；不得新增 `class Config`、`orm_mode`、`parse_obj` 或 `@validator`。
- 请求、响应和 LLM 结构化输出均使用独立 Schema。字段类型与 `min_length`、`ge` 等约束就地声明；LLM 输出字段必须带 `description`。
- 单字段清洗用 `@field_validator`，跨字段约束用 `@model_validator(mode="after")`。边界已完成的校验不得在 service 层重复实现。
- ORM 对象使用 `XxxOut.model_validate(obj)`，字典使用构造器或 `model_validate(data)`。
- 配置模型继承 `BaseSettings`；部署配置的归属规则见 `fastapi.md`。

## 3. 表与 ORM 模型

### 3.1 通用列规范

- 表名使用复数 `snake_case` 且无前缀；主键为应用层生成的 uuid4 字符串，SQLite 类型为 `TEXT` / ORM `String(36)`。
- 时间列落盘为 ISO8601 UTC `TEXT`。ORM 统一复用 `models/base.py` 的 `ISODateTime` 和 `utcnow()`；只写入 aware UTC，禁止 naive datetime。
- JSON 和数组落为 JSON 文本；布尔值用 `Mapped[bool]` + `Boolean`，由 SQLite 存为 `INTEGER 0/1`。
- 状态等受控值使用枚举，不在业务代码散落裸字符串。
- 可编辑实体统一包含 `updated_at`、可空 `deleted_at`，删除采用软删。
- `learning_events`、`learning_evidence`、`chat_messages`、`llm_call_logs` 是纯追加事实表，不设软删；`learning_events.idempotency_key` 必须 `UNIQUE`。
- sqlite-vec 的 vec0 虚拟表不映射为 ORM 模型，统一经向量检索封装访问；检索约束见 `langchain-langgraph.md`。

### 3.2 SQLAlchemy 2.0

- 模型使用 `DeclarativeBase`、`Mapped[T]`、`mapped_column()`；查询使用 `select()`，不得新增 `Column(...)` 旧式声明或 `session.query()`。
- 引擎使用 `sqlite+aiosqlite:///` 和 `async_sessionmaker(..., expire_on_commit=False)`；不配置 `pool_size`、`max_overflow` 等 PostgreSQL 式池参数。
- 每个连接启用 `PRAGMA foreign_keys=ON`；数据库启用 WAL。API 与进程内 worker 共用 sidecar 内同一份 engine / session factory；engine 只能在数据目录排他锁取得后创建。
- 所有带 `deleted_at` 的表，其列表、详情、关联和计数查询都必须过滤 `deleted_at IS NULL`。优先通过 soft-delete mixin + `with_loader_criteria` 在 Base 层统一注入，避免调用方遗漏。

## 4. 会话与事务

- 会话按请求创建并通过 `async with` 关闭；不得全局共享、跨请求复用或长期存放在对象属性中。
- 事务边界位于 service 层；一个业务动作对应一个事务，相关写入必须原子提交。
- 提交失败应抛出异常，不得吞错后返回半成功状态。
- 写事务必须短小。LLM、ASR、ffmpeg 和网络等待均先执行，完成后再开启写事务，避免 WAL 写锁和 `busy`。

## 5. 数据目录

默认数据目录为 `%USERPROFILE%\KnowRealm\`，首启可选择并在之后更换；启动时检测同步盘接管。标准布局：

| 路径 | 内容与约束 |
|---|---|
| `.knowrealm.lock` | sidecar 运行期 OS 排他锁对象；不能只判断文件是否存在，进程退出/崩溃后锁必须由 OS 自动释放 |
| `knowrealm.db` | 全部业务表、WAL、vec0 向量表 |
| `langgraph.db` | LangGraph checkpoint，不是业务事实源 |
| `files/` | 导入原件与转码后的 ogg-opus；原件保持可逆 |
| `cache/` | 可删除、可重建的中间产物及 `staging/` 录音分片；转码成功后删除分片 |
| `exports/`、`backups/` | 导出包与启动时生成的每日滚动备份（保留 7 份） |
| `config/` | `settings.json`、`providers.json`；密钥明文且用户可见 |

- 可重建产物只进 `cache/`，不得进入 `files/`。
- 向量数据与业务数据同库备份、导出和迁移，不引入 Qdrant、Neo4j 等独立向量库。
- 备份和全量导出使用 `VACUUM INTO` 生成一致性快照；导出 zip 默认排除 `providers.json`。

## 6. 迁移与测试

- Schema 唯一权威是 `backend/migrations/NNNN_name.sql`。任何表、列、索引或 vec0 变更都新增四位连续递增迁移，并同步修改 ORM 模型。
- 迁移脚本只写 DDL；执行器在脚本成功后统一推进 `PRAGMA user_version`。不得使用 Alembic，也不得手改运行库而不留迁移。
- 已发布迁移不可修改、删除或重排；纠错必须新增迁移。
- 生产和测试都通过迁移链建表，不使用 `Base.metadata.create_all()`。测试使用 aiosqlite 临时库完整重放迁移，确保与生产同形态。
- 禁止 PostgreSQL 专有类型：UUID 映射 `String(36)`，JSONB 映射 SQLite JSON/TEXT，vector 映射 vec0。
