# 规范：数据层（Pydantic + SQLAlchemy + SQLite）

> 适用范围：`backend/app/` 的模型、Schema、数据库访问；`backend/migrations/` 迁移文件。

## 0. 版本基线与职责分工（2026-08 核实）

| 组件 | 版本基线 | 职责 |
|---|---|---|
| Pydantic / pydantic-settings | **2.x**（≥2.11，当前 2.12/2.13 线） | 请求/响应校验、LLM 结构化输出 Schema、配置 |
| SQLAlchemy | **2.0.x**（当前 2.0.52，勿用 2.1 beta） | ORM，async 访问 knowrealm.db |
| aiosqlite | 最新 | SQLite 异步驱动（全项目唯一 DB 驱动） |
| sqlite-vec | 最新 | 向量检索（vec0 虚拟表，检索红线见 langchain-langgraph.md §10） |

一句话分工：**Pydantic 管边界校验，SQLAlchemy 管读写，SQLite（knowrealm.db）是唯一业务事实源**——sidecar 是数据库唯一写者，UI 不直连（红线 #35 v2.0）。

## 1. Pydantic v2

### 1.1 模型写法（v2 语法，不是 v1）

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator

class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="课程名")
    semester: str | None = None

class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)   # v2：替代 v1 的 orm_mode
    id: str
    name: str
    created_at: datetime
```

```python
# ❌ v1 旧写法，2.x 中已移除
class Old(BaseModel):
    class Config:
        orm_mode = True
```

规则：
- `models/`（SQLAlchemy）与 `schemas/`（Pydantic）**严格分目录**，禁止让 ORM 模型兼任 API 模型。
- 从 ORM 对象构造用 `CourseOut.model_validate(orm_obj)`；字典构造用 `CourseCreate(**data)` 或 `model_validate(data)`——不用已废弃的 `parse_obj`。
- 字段约束（`ge/le/min_length` 等）就地声明，校验在边界完成，service 层不做重复校验。

### 1.2 校验器与设置类

```python
class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = v.strip()                     # 清洗：去首尾空白
        if not v:
            raise ValueError("课程名不能为空白")
        return v

# 配置一律继承 BaseSettings（详见 fastapi.md §8）；部署级配置才进 .env
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    short_answer_review_threshold: float = 0.7   # 数据目录/端口由壳经启动参数注入，不入 .env
```

- 跨字段校验用 `@model_validator(mode="after")`，单字段用 `@field_validator`。
- LLM 结构化输出 Schema（习题/知识点/Concept）也是 Pydantic 模型，同样放 `schemas/`，字段必须带 `description`。

## 2. SQLAlchemy 2.0（async + aiosqlite）

> 选型依据：不采用官方模板的 **SQLModel**（ORM 与 Pydantic 合一）——其类型完备性与复杂查询能力弱于 SQLAlchemy 2.0 原生注解风格；生产社区主流（zhanymkanov/fastapi-best-practices 等）同为 SQLAlchemy + 独立 Pydantic schemas 的分离路线。

### 2.1 模型：2.0 类型注解风格 + 通用列规范

**通用列规范（数据模型 v2.0 §2，SQLite 全表适用）**：
- 表名 `snake_case` **复数、无前缀**（`records`、`record_files`）；主键 `id TEXT`（应用层生成 uuid4 字符串）；时间列 TEXT（ISO8601 UTC）；JSON 一律 TEXT（JSON 字符串）；数组 TEXT（JSON 数组字符串）。
- **无 `user_id` 列、无 RLS**（本地单用户库）；sidecar 仅监听 127.0.0.1 且为唯一写者。
- **可编辑实体**统一携带：`updated_at`、`deleted_at`（软删，可空）。
- **纯追加型事实表例外**（`learning_events` / `learning_evidence` / `chat_messages` / `llm_call_logs`）：不做软删，只追加。
- 幂等事实表（`learning_events`）必带 `idempotency_key` **UNIQUE**。
- **无 `version` 乐观锁列**（单写者无并发冲突，原 409/Last-Write-Wins 问题随同步概念整体删除）；`ai_summaries.version_no` / `transcripts.source_version` 是业务版本号，语义不同，保留。

```python
# models/base.py
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

# models/base.py —— 时间列统一类型：钉死 SQLite 落盘格式为 ISO8601 UTC 文本
# （方言默认是空格分隔无时区，与数据模型 v2.0 §2 "TEXT(ISO8601 UTC)" 不符）
from sqlalchemy.dialects.sqlite import DATETIME as SQLITE_DATETIME

ISODateTime = SQLITE_DATETIME(
    storage_format="%(year)04d-%(month)02d-%(day)02dT%(hour)02d:%(minute)02d:%(second)02d.%(microsecond)06dZ",
    regexp=r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?Z",
)

# models/record.py
import uuid
from datetime import UTC, datetime
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

def utcnow() -> datetime:
    return datetime.now(UTC)          # 一律 aware UTC；禁 naive datetime 入库

class Record(Base):
    __tablename__ = "records"          # ✅ snake_case 复数、无前缀

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")  # 受控枚举，禁裸字符串
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)   # 软删
```

```python
# ❌ 1.x 旧风格（Column(...)），项目内禁止新增
class OldRecord(Base):
    __tablename__ = "t_record"        # ❌ t_ 前缀（数据模型明确无前缀）
    id = Column(String, primary_key=True)
```

规则：
- **迁移不走 Alembic**：schema 由 `backend/migrations/*.sql` 管理（`PRAGMA user_version` 编号推进，唯一权威），SQLAlchemy 模型手写维护、与迁移保持同步。改表 = 新增一个编号 SQL 迁移文件 + 手改模型。
- **时间列一律 `ISODateTime`**（ORM 映射用 `Mapped[datetime]` 保持人机工学，落盘格式钉死 ISO8601 UTC——见 base.py 片段）；写入只允许 aware UTC。

### 2.2 引擎与会话

```python
# app/db/engine.py
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

engine = create_async_engine(f"sqlite+aiosqlite:///{data_dir / 'knowrealm.db'}")

@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragma(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")     # 外键约束，每连接生效
    cur.execute("PRAGMA journal_mode=WAL")    # 数据库持久属性
    cur.close()

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

- 连接串 scheme 用 `sqlite+aiosqlite:///`（不是同步的 `sqlite:///`）。
- **不调池参数**（`pool_size`/`max_overflow` 是 PG 时代的调优项）——aiosqlite 方言默认连接管理即可，单用户单写者无并发压力。
- `expire_on_commit=False`：避免 commit 后再访问属性触发多余的同步刷新。
- **唯一写者**：API 与 worker 同进程组共用这一份 engine/SessionLocal；`knowrealm.db` 的写连接只存在于 sidecar 进程内。

### 2.3 查询：2.0 select 风格

```python
from sqlalchemy import select

async def get_record(session: AsyncSession, record_id: str) -> Record | None:
    stmt = (
        select(Record)
        .where(Record.id == record_id)
        .where(Record.deleted_at.is_(None))     # ✅ 可软删表必须过滤 deleted_at
    )
    return (await session.execute(stmt)).scalar_one_or_none()
```

- **软删过滤规则**：凡是带 `deleted_at` 列的表，查询一律加 `deleted_at IS NULL`（追加型事实表无此列、不适用）。为防手写遗漏，在 Base 层用 `with_loader_criteria` 对软删 mixin 统一注入；列表/详情/计数全覆盖，漏一处就会把已删数据漏给用户。

```python
# ❌ 1.x legacy 查询 API，禁止
session.query(Record).filter_by(id=record_id).first()
```

### 2.4 事务边界

- **事务边界在 service 层**：一个业务动作一个事务。
- 会话随请求创建（FastAPI 依赖 `async with SessionLocal() as session: yield session`），用完即关，**禁止全局共享会话、禁止把会话存到对象属性里长期持有**。
- 提交失败要让异常抛出去，不要吞掉再返回半成功状态。
- **写事务短小**：WAL 允许一写多读，但并发写事务会 busy——LLM 调用、ffmpeg/ASR 等待等长活不持有写事务，先算后写。

```python
# services/record_service.py —— 事务边界示例
async def create_with_todo(self, session: AsyncSession, ...):
    async with session.begin():            # 一个业务动作 = 一个事务块
        session.add(record)
        session.add_all(todos)
```

## 3. 数据目录与迁移

### 3.1 数据目录（唯一事实源）

布局（数据模型 v2.0 §5）：

```
%USERPROFILE%\KnowRealm\           ← 首启选择，可换；启动时检测同步盘接管
├── knowrealm.db                   # 全部业务表（WAL）+ vec0 向量表
├── langgraph.db                   # LangGraph Checkpoint（非业务事实，langchain-langgraph.md §7）
├── files/                         # 存档原件（明文）：导入原件 + 转码后 ogg-opus
├── cache/                         # 可清可重建：转码产物、staging/ 录音分片（转码成功即删）
├── exports/   backups/            # 导出 zip / 启动滚动备份（每日 ×7）
└── config/                        # settings.json + providers.json（明文密钥）
```

规则：
- **单写者**（红线 #35 v2.0）：业务数据的读写只经 sidecar API；UI 不直连数据库、不直写数据目录（录音分片落盘是唯一例外，见 desktop-tauri.md §5）。
- **files/ 只进原件**：导入文件原样保留（可逆性优先）；可重建的中间产物进 `cache/`，不占 `files/`。
- **向量与业务数据同库**：sqlite-vec vec0 表随 db 文件一体备份/导出/迁移——不引入独立向量库（Qdrant 等）。
- 备份与全量导出用 `VACUUM INTO` 一致性快照原语；导出 zip 默认不含 `providers.json`。

### 3.2 迁移纪律（PRAGMA user_version）

- 任何 schema 变更（表/列/索引/vec0 虚拟表）**只能**新增 `backend/migrations/NNNN_name.sql` 编号文件（四位递增），禁止手改运行中的库不落文件。
- 迁移文件只写 DDL；`PRAGMA user_version` 由执行器（`app/db/migrations.py`）在脚本执行成功后统一推进——应用启动时比对编号、按序执行未应用脚本。
- 迁移编号即版本：**不允许修改/删除已发布的迁移文件**，纠错 = 新增一个迁移。

## 4. SQLite 纪律（生产主库，限制即生产约束）

SQLite 不再是"测试替身"而是生产本体，其方言限制直接决定模型写法：

| 事项 | 约定 |
|---|---|
| PG 专有类型全禁 | `UUID`→`String(36)`、`JSONB`→`sa.JSON`（TEXT 存储）、`vector`→vec0 虚拟表（不经 ORM 模型表达，检索走封装层） |
| 时间 | 应用层统一 aware UTC（`datetime.now(UTC)`）生成；ISO8601 文本可按字典序比较排序 |
| 布尔 | `Mapped[bool]` + `Boolean`（自动映射 INTEGER 0/1） |
| 测试 | 临时库重放迁移链建表——生产与测试同形态，无 PG/SQLite 双库差异问题 |

```python
# 测试夹具：临时库 + 迁移链（与生产同一路径建表，不用 create_all 防模型与 SQL 漂移）
engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
await run_migrations(engine)        # app/db/migrations.py 的执行器，逐版本验证
```

## 5. 反模式速查

| 禁止 | 用什么代替 |
|---|---|
| Pydantic v1 写法（`class Config` / `parse_obj` / `@validator`） | `ConfigDict` / `model_validate` / `@field_validator` |
| ORM 模型直接当 API 响应 | `schemas/` 独立模型 + `from_attributes` |
| `Column(...)` 旧式模型、`session.query()` | `Mapped[]/mapped_column`、`select()` |
| Alembic 迁移 | `backend/migrations/*.sql` + `PRAGMA user_version` |
| 可软删表查询不过滤 `deleted_at` | 查询必带 `deleted_at IS NULL`（Base 层统一注入） |
| 手改 schema 不落迁移文件 | 一律新增编号 SQL 迁移文件 |
| 引入 `user_id` 列 / RLS / `version` 乐观锁 | 本地单用户单写者，无此概念（数据模型 v2.0 §2） |
| sidecar 之外任何进程直连写 knowrealm.db | 唯一写者 = sidecar，一切经 localhost API |
| 长活（LLM/ffmpeg/ASR 等待）持有写事务 | 先算后写，写事务短小 |
| 追加型事实表（events/evidence/messages/logs）加软删 | 只追加，不可变 |
| 全局共享 / 长持有 AsyncSession | 请求级会话，`async with` 管理 |
| 独立向量库（Qdrant/Neo4j）存向量 | sqlite-vec 随 knowrealm.db 一体 |
| 用 `create_all` 建生产/测试 schema | 迁移链重放（模型与 SQL 不漂移） |
