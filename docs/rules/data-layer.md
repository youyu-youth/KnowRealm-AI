# 规范：数据层（Pydantic + SQLAlchemy + Supabase + SQLite）

> 适用范围：`services/api/` 的模型、Schema、数据库访问；`supabase/` 迁移文件。

## 0. 版本基线与职责分工（2026-08 核实）

| 组件 | 版本基线 | 职责 |
|---|---|---|
| Pydantic / pydantic-settings | **2.x**（≥2.11，当前 2.12/2.13 线） | 请求/响应校验、LLM 结构化输出 Schema、配置 |
| SQLAlchemy | **2.0.x**（当前 2.0.52，勿用 2.1 beta） | ORM，async + psycopg 3 访问 Supabase Postgres |
| supabase-py | **2.x**（当前 2.31.x） | Storage 上传/签名、Admin API（service role） |
| SQLite（aiosqlite） | — | 后端单测 + LangGraph 本地开发；桌面端缓存（tauri-plugin-sql） |

一句话分工：**Pydantic 管边界校验，SQLAlchemy 管读写，Supabase 管云端事实，SQLite 只做缓存和测试**。

## 1. Pydantic v2

### 1.1 模型写法（v2 语法，不是 v1）

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator

class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="课程名")
    semester: str | None = None

class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)   # v2：替代 v1 的 orm_mode
    id: UUID
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

# 配置一律继承 BaseSettings（详见 fastapi.md §8）
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
```

- 跨字段校验用 `@model_validator(mode="after")`，单字段用 `@field_validator`。
- LLM 结构化输出 Schema（习题/知识点/Concept）也是 Pydantic 模型，同样放 `schemas/`，字段必须带 `description`。

## 2. SQLAlchemy 2.0（async + psycopg 3）

> 选型依据：不采用官方模板的 **SQLModel**（ORM 与 Pydantic 合一）——其类型完备性与复杂查询能力弱于 SQLAlchemy 2.0 原生注解风格；生产社区主流（zhanymkanov/fastapi-best-practices 等）同为 SQLAlchemy + 独立 Pydantic schemas 的分离路线。

### 2.1 模型：2.0 类型注解风格 + 通用列规范

**通用列规范（数据模型 §2，全表适用）**：
- 表名 `snake_case` **复数、无前缀**（`records`、`record_files`）；主键 `uuid`；时间 `timestamptz`；JSON 一律 `jsonb`。
- **可编辑实体**统一携带：`version`（乐观锁：更新校验 version，不匹配返回 409，不默认 Last-Write-Wins）、`updated_at`、`deleted_at`（软删，可空）。
- **纯追加型事实表例外**（`learning_events` / `learning_evidence` / `chat_messages` / `llm_call_logs`）：不做软删与 version，只追加。
- 幂等事实表（`learning_events`）必带 `idempotency_key` **UNIQUE**。
- 用户私有表必有 `user_id`（带索引）。

```python
# models/base.py
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

# models/record.py
from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

class Record(Base):
    __tablename__ = "records"          # ✅ snake_case 复数、无前缀

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(default="CREATED")
    version: Mapped[int] = mapped_column(default=1)             # 乐观锁
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)   # 软删
```

```python
# ❌ 1.x 旧风格（Column(...)），项目内禁止新增
class OldRecord(Base):
    __tablename__ = "t_record"        # ❌ t_ 前缀（数据模型明确无前缀）
    id = Column(UUID, primary_key=True)
```

规则：
- **迁移不走 Alembic**：schema 由 `supabase/migrations/*.sql` 管理（Supabase CLI 单一事实源），SQLAlchemy 模型手写维护、与迁移保持同步。改表 = 新增一个 SQL 迁移文件 + 手改模型。

### 2.2 引擎与会话

```python
# core/db.py
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

engine = create_async_engine(
    settings.database_url,          # postgresql+psycopg://...（psycopg 3，全项目唯一 PG 驱动）
    pool_size=10,
    max_overflow=5,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

- 连接串 scheme 用 `postgresql+psycopg://`（不是 `postgresql://`（默认驱动）也不是 `+psycopg2://`）。
- API 进程用 Supabase **transaction 池化端口**（6543）；procrastinate worker 用 **session 池化或 direct 端口（5432）**——`LISTEN/NOTIFY` 不被事务池化支持。
- `expire_on_commit=False`：避免 commit 后再访问属性触发多余的同步刷新。

### 2.3 查询：2.0 select 风格

```python
from sqlalchemy import select

async def get_record(session: AsyncSession, record_id: UUID, user_id: UUID) -> Record | None:
    stmt = (
        select(Record)
        .where(Record.id == record_id)
        .where(Record.user_id == user_id)       # ✅ 每个 WHERE 都带 user_id
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

```python
# services/record_service.py —— 事务边界示例
async def create_with_todo(self, session: AsyncSession, ...):
    async with session.begin():            # 一个业务动作 = 一个事务块
        session.add(record)
        session.add_all(todos)
```

## 3. Supabase

### 3.1 三个角色分清

| 能力 | 客户端 | 谁能用 |
|---|---|---|
| 业务数据读写 | SQLAlchemy（直连 Postgres，**最小权限数据库角色**） | 后端 |
| Storage 上传/签名、Admin API | `supabase-py`（**service role key**） | 仅后端必要管理操作（`core/` 封装） |
| Auth 会话、直传、Realtime | `@supabase/supabase-js` | 仅桌面端前端 |

```python
# 业务连接用最小权限角色（RLS 对其生效，双保险第一道在角色、第二道在代码）
engine = create_async_engine(settings.database_url)   # 连接串内嵌最小权限角色凭证

# service role 是最高权限，仅限 Storage/Admin 等必要管理操作，不下发前端、不进日志
from supabase import create_client
supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
signed = supabase.storage.from_("recordings").create_signed_url(path, expires_in=3600)
```

### 3.2 数据隔离双保险

1. **最小权限角色 + 代码过滤（第一道）**：后端业务连接用最小权限数据库角色，且**每条查询/写入必须显式带 `user_id`**——service 层数据访问方法签名强制把 `user_id` 作为参数传入，缺失即 bug。
2. **RLS（库层兜底）**：所有业务表开 RLS，策略 `auth.uid() = user_id`；迁移文件里逐表写明。service_role 绕过 RLS，故不能依赖 RLS 替代代码过滤。
3. pgvector 检索同理且更严：**`user_id` + `deleted_at IS NULL` 必带，`course_id` 视挂载范围**（@课程带、@全部资料不带，v1.5 裁决 #24——`semantic_embeddings.course_id` 可空，Inbox 内容照常入索引）。详见 langchain-langgraph.md §10。

### 3.3 迁移纪律

- 任何 schema 变更（表/列/索引/RLS/pgvector/Storage 策略）**只能**新增 `supabase/migrations/<timestamp>_xxx.sql` 文件，禁止在控制台手改后不落文件。
- 本地 `supabase db reset` 可重放全部迁移——迁移文件必须幂等可重放（用 `create table if not exists` / `alter ... if exists` 等）。

## 4. SQLite（边界最容易被突破，从严）

SQLite 在本项目只有三个合法用途，**永远不做云端主库**：

| 用途 | 方式 |
|---|---|
| 后端单测 | `sqlite+aiosqlite://` 内存库（纯逻辑测试；pgvector/RLS 相关测试必须用真 Postgres） |
| LangGraph 本地开发 | `SqliteSaver`（生产换 AsyncPostgresSaver） |
| 桌面端缓存 | tauri-plugin-sql（读缓存 + 录音暂存队列；**业务写一律在线走 API**） |

```python
# 测试夹具：SQLite 内存库
engine = create_async_engine("sqlite+aiosqlite://")

async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)   # 每个测试全新 schema
```

注意差异：SQLite 不支持 `UUID/JSONB/vector` 等 PG 专有类型——**测试模型与生产模型共用时，PG 专有类型须用 `sa.TypeDecorator` 或 `with_variant`**，不要为通过测试弱化生产模型定义。

## 5. 反模式速查

| 禁止 | 用什么代替 |
|---|---|
| Pydantic v1 写法（`class Config` / `parse_obj` / `@validator`） | `ConfigDict` / `model_validate` / `@field_validator` |
| ORM 模型直接当 API 响应 | `schemas/` 独立模型 + `from_attributes` |
| `Column(...)` 旧式模型、`session.query()` | `Mapped[]/mapped_column`、`select()` |
| `postgresql://`（psycopg2）连接串 | `postgresql+psycopg://`（psycopg 3） |
| Alembic 迁移 | `supabase/migrations/*.sql`（Supabase CLI） |
| 可软删表查询不过滤 `deleted_at` | 查询必带 `deleted_at IS NULL`（Base 层统一注入） |
| 控制台手改 schema 不落迁移文件 | 一律新增 SQL 迁移文件 |
| 业务连接用 service role / 查询不带 `user_id` | 最小权限角色 + service 方法签名强制传入 |
| 覆盖式更新（Last-Write-Wins） | 校验 `version`，冲突返回 409 |
| 追加型事实表（events/evidence/messages/logs）加软删或 version | 只追加，不可变 |
| 全局共享 / 长持有 AsyncSession | 请求级会话，`async with` 管理 |
| service role key 出现在前端/日志 | 仅后端环境变量，仅管理操作 |
| SQLite 存业务事实（做主库） | 云端事实一律进 Supabase Postgres |
| 为 SQLite 测试弱化 PG 类型定义 | `TypeDecorator` / `with_variant` |
