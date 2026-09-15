---
paths:
  - "backend/**"
---

# 规范：数据层（Pydantic + SQLAlchemy + SQLite）

> 适用范围：`backend/app/` 的模型、Schema、数据库访问，以及 `backend/migrations/`。依赖版本以 uv 锁文件为准。

## 1. 架构

- Pydantic 管边界校验，SQLAlchemy 管持久化，`knowrealm.db` 是唯一业务事实源。
- FastAPI sidecar 是数据库与数据目录业务文件的唯一协调者：同一数据目录必须持有进程生命周期 OS 排他锁，拿锁失败不得迁移、备份或启动 worker；UI 与 Tauri 只经 localhost API 读写，不得直连数据库或直接写数据目录。
- 本地单用户库不设 `user_id`、RLS 或通用乐观锁列（`ai_summaries.version_no` 等业务版本号除外）。

## 2. Pydantic v2

- ORM 模型放 `models/`，Pydantic 放 `schemas/`，API 不直接暴露 ORM；只用 v2 API（`ConfigDict(from_attributes=True)`、`model_validate`、`field_validator`、`model_validator`），禁 `class Config`/`orm_mode`/`parse_obj`/`@validator`。
- 请求、响应、LLM 结构化输出各用独立 Schema；约束（`min_length`、`ge` 等）就地声明，LLM 输出字段必须带 `description`。边界已完成的校验不得在 service 层重复实现。

## 3. 表与查询

- 表名复数 snake_case；主键为应用层 uuid4 字符串（`String(36)`）；时间列 ISO8601 UTC TEXT（复用 `models/base.py` 的 `ISODateTime`/`utcnow()`，只写 aware UTC，禁 naive datetime）；受控值用枚举，不散落裸字符串。
- 可编辑实体统一 `updated_at` + 可空 `deleted_at` 软删；`learning_events`、`learning_evidence`、`chat_messages`、`llm_call_logs` 是纯追加事实表，不设软删。
- SQLAlchemy 2.0：`Mapped`/`mapped_column`/`select()`，禁 `Column()` 旧式声明与 `session.query()`；`sqlite+aiosqlite` + `expire_on_commit=False`，不配 PostgreSQL 式池参数；每连接 `PRAGMA foreign_keys=ON`，库启用 WAL；API 与进程内 worker 共用同一 engine/session factory。
- 所有带 `deleted_at` 的表查询必须过滤 `deleted_at IS NULL`，优先经 soft-delete mixin + `with_loader_criteria` 在 Base 层统一注入。

## 4. 会话与事务

- 会话按请求创建、`async with` 关闭，不跨请求复用；事务边界在 service 层，一个业务动作一个事务，原子提交，不得吞错返回半成功。
- 写事务短小：LLM、ASR、ffmpeg 和网络等待先完成，再开写事务，避免 WAL 写锁与 `busy`。

## 5. 数据目录

默认 `%USERPROFILE%\KnowRealm\`，首启可选可换，启动检测同步盘接管。布局：`.knowrealm.lock`（OS 排他锁，非 sentinel 文件）、`knowrealm.db`、`langgraph.db`（checkpoint，非事实源）、`files/`（原件 + 转码 ogg-opus，原件保持可逆）、`cache/`（可重建产物 + `staging/` 录音分片，转码成功后删分片）、`exports/`、`backups/`（每日滚动保留 7 份）、`config/`（settings.json、providers.json，密钥明文用户可见）。可重建产物只进 `cache/`；备份与全量导出用 `VACUUM INTO`；导出 zip 默认排除 `providers.json`；不引入独立向量库。

## 6. 迁移与测试

- Schema 唯一权威是 `backend/migrations/NNNN_name.sql`：任何表/列/索引变更新增四位递增迁移并同步 ORM 模型；迁移脚本只写 DDL，执行器统一推进 `PRAGMA user_version`；已发布迁移不可修改删除重排，纠错必须新增迁移；不用 Alembic，不手改运行库不留迁移。
- 生产与测试都走迁移链建表，禁 `Base.metadata.create_all()`；测试用 aiosqlite 临时库完整重放迁移链。
- 禁 PostgreSQL 专有类型：UUID 映射 `String(36)`，JSONB 映射 JSON/TEXT。
