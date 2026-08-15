# 规范：FastAPI（后端服务层）

> 适用范围：`services/api/` 全部代码。FastAPI 当前稳定线为 0.14x（2026-08 为 0.141.1），仍属 0.x 版本号——**minor 之间可能有破坏性变更，版本必须由 uv 锁定**。

## 1. 分层：路由薄、业务下沉

> 选型依据：官方模板（`crud.py` 函数层）与 zhanymkanov 流派（无 service 层、依赖链承载复用）均不采用——本项目 service 层是**事务边界**、procrastinate worker 复用业务逻辑、以及红线约束（如 Mastery 唯一写入口）的集中落点；与 [fastapi-best-architecture](https://github.com/fastapi-practices/fastapi-best-architecture) 三层路线一致。

```
app/
├── api/         # 路由层：只做参数解析、调 service、返回响应。禁止写业务逻辑
├── services/    # 业务逻辑：事务边界在这里
├── models/      # SQLAlchemy ORM 模型
├── schemas/     # Pydantic 请求/响应模型
├── agents/      # LangGraph 编排
├── workers/     # procrastinate 异步任务
└── core/        # 配置、auth 验签、日志、依赖
```

```python
# ✅ 路由层应有的样子：一眼看清输入输出
@router.post("", response_model=RecordOut, status_code=201)
async def create_record(
    payload: RecordCreate,
    user_id: str = Depends(get_current_user_id),
    svc: RecordService = Depends(get_record_service),
):
    return await svc.create(user_id, payload)

# ❌ 路由里直接写 SQL / 调 LLM / 组装业务
@router.post("/records")
async def create_record(payload: RecordCreate, request: Request):
    async with SessionLocal() as session:   # 禁止：会话管理散落在路由
        ...
```

## 2. 路由定义

- 每个资源一个 `APIRouter`，统一 `prefix` + `tags`，路径用**复数名词 kebab-case**，动词由 HTTP 方法表达。

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/records", tags=["records"])

# ✅ GET /api/records?course_id=...
@router.get("")
async def list_records(course_id: UUID, ...): ...

# ✅ POST /api/records/{record_id}/transcription  （子动作用名词）
@router.post("/{record_id}/transcription")
async def submit_transcription(record_id: UUID, ...): ...

# ❌ /api/getRecordList、/api/record_delete
```

- 路径参数用具体类型（`UUID`、`int`），让 FastAPI 自动校验 404/422。

## 3. 请求/响应模型（Pydantic）

- 入参出参**必须**定义 Pydantic 模型并声明 `response_model`——这是 OpenAPI 文档（前端生成 TS 类型的来源）完整性的保证。
- 读写分离：`XxxCreate` / `XxxUpdate` / `XxxOut`，禁止一个模型包打天下。
- `Update` 模型的可变字段用 `X | None = None` 区分"未传"与"传空"。

```python
class RecordCreate(BaseModel):
    course_id: UUID
    title: str = Field(min_length=1, max_length=200)
    recorded_at: datetime

class RecordUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)

class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)   # 从 ORM 对象直接构造
    id: UUID
    title: str
    status: RecordStatus
    created_at: datetime
```

- 内部模型**不要**直接暴露给 API：响应模型只挑该暴露的字段（防止 `user_id`、内部状态泄漏）。

## 4. 依赖注入

### 4.1 数据库会话（每请求一会话）

```python
# core/deps.py
async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
```

### 4.2 认证（Supabase JWT 验签 → user_id）

```python
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)

async def get_current_user_id(
    creds: HTTPAuthorizationCredentials | None = Security(bearer),
) -> str:
    if creds is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        claims = verify_supabase_jwt(creds.credentials)   # httpx 拉 JWKS 验签
        return claims["sub"]
    except TokenError:
        raise HTTPException(status_code=401, detail="token 无效")
```

规则：
- 需要登录的路由一律 `Depends(get_current_user_id)`，拿到的 `user_id` 作为参数显式传入 service——**每个查询都要带上它**（RLS 之外的第二道保险）。
- 依赖抛 `HTTPException` 即可，不要在业务层 import FastAPI 异常。

## 5. 异步纪律：不阻塞事件循环

```python
# ✅ 路由/服务统一 async def，IO 用异步库（httpx、SQLAlchemy async）
@router.get("/courses")
async def list_courses(...): ...

# ❌ 在 async 路由里调同步阻塞库（requests、tencentcloud-sdk、ffmpeg）
async def submit_asr(...):
    client.flash_recognizer(req)   # 阻塞整个 worker 进程！
```

- 腾讯云 ASR SDK（同步）、ffmpeg 等 CPU/IO 重活**只允许出现在 procrastinate worker**（`app/workers/`），API 进程内禁止。
- 实在无法异步的第三方同步调用，用 `asyncio.to_thread()` 包裹并注明原因。

## 6. SSE 流式（AI 问答）

用 `sse-starlette`，不要手写 `StreamingResponse` 拼格式。事件类型遵守功能基线 §9.2 约定的六类：**`token`（增量文本）/ `status`（阶段状态）/ `citation`（来源引用）/ `interrupt`（HITL 暂停请求）/ `done` / `error`**：

```python
from sse_starlette.sse import EventSourceResponse

@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, user_id: str = Depends(get_current_user_id)):
    async def event_gen():
        async for chunk in tutor_graph.astream(..., stream_mode="messages"):
            if chunk_token := chunk[0].content:
                yield {"event": "token", "data": chunk_token}        # 前端逐字渲染
        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_gen())
```

- SSE 端点用 **POST**（前端 `@microsoft/fetch-event-source` 带 Bearer 头）。
- 流内异常要捕获并作为 `event: error` 发出，不能让连接无声断掉。
- `interrupt` 事件须自带渲染所需 payload（如待确认总结全文），前端展示确认 UI 后走恢复接口。

## 7. 错误处理

- 业务错误：抛 `HTTPException(status_code=..., detail=...)`，语义化状态码（400 参数错 / 403 越权 / 404 不存在 / 409 状态冲突）。
- **409 专属场景——乐观锁冲突**：可编辑实体带 `version` 字段（数据模型 §2），更新语句校验 version，不匹配返回 409 由用户决策，**禁止默认 Last-Write-Wins 静默覆盖**。
- 未预期异常：注册全局处理器统一返 500 + request_id，禁止把堆栈发给前端：

```python
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_error", path=request.url.path)
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})
```

- 错误响应格式保持统一（`{"detail": "..."}`），前端只解析一种结构。

### 7.1 日志纪律（隐私红线，功能基线 §7）

```python
# ✅ 可记录：定位与统计所需的最小元数据
logger.info("asr_job_finished", record_id=record_id, duration_ms=elapsed,
            model="asr-std", error_code=None)

# ❌ 禁止记录：完整转写全文、Teach-back 全文、敏感对话内容、密钥、Token
logger.debug("transcript", content=transcript)          # 违规！
logger.error("auth_failed", token=access_token)          # 违规！
```

白名单：`record_id` / `segment_id` / `session_id`、token **数量**（非 token 本身）、latency、model、prompt_version、error code。日志库已定案 **loguru**：附加字段用 kwargs 传（自动进 extra），如 `logger.info("asr_job_finished", record_id=rid, latency_ms=ms)`；启动时用 `InterceptHandler` 接管 uvicorn/SQLAlchemy 的标准 logging 输出，全项目单一出口。

## 8. 配置管理（pydantic-settings）

```python
# core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    supabase_url: str
    supabase_service_role_key: str
    dashscope_api_key: str
    environment: Literal["dev", "prod"] = "dev"

settings = Settings()   # 模块级单例
```

- **所有密钥/环境变量走 Settings**，禁止 `os.getenv` 散落各处，禁止硬编码。
- `.env` 不进仓库；新增配置项必须给 `.env.example` 补注释。

## 9. 生命周期（lifespan）

engine、连接池、LangGraph checkpointer 等全局资源在 lifespan 中创建/销毁，**不要用 `@app.on_event`（已废弃）**：

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await create_db_pool()      # 启动
    yield
    await app.state.pool.close()                 # 关闭

app = FastAPI(lifespan=lifespan)
```

## 10. 应用实例与文档

```python
app = FastAPI(
    title="KnowRealm API",
    version="1.0.0",
    openapi_url="/api/openapi.json",
)
```

- OpenAPI schema 是前端 `packages/api-types`（openapi-typescript）的类型来源：**每个路由必须有 `response_model`、每个模型字段必须有类型注解**，否则生成的 TS 类型会退化成 `any`。
- 破坏性 API 变更（改字段名/删字段）要先改 OpenAPI 生成物再动前端。

## 11. 测试

```python
import pytest
from httpx import ASGITransport, AsyncClient

@pytest.fixture
def anyio_backend():
    return "asyncio"

async def test_create_record(db_session, client):
    resp = await client.post(
        "/api/records",
        json={"course_id": str(uuid4()), "title": "操作系统第一课", "recorded_at": "..."},
        headers=auth_headers,
    )
    assert resp.status_code == 201
```

- 纯业务逻辑测试用 **SQLite（aiosqlite）** 内存库；涉及 pgvector / RLS 的测试才起真实 Postgres。
- 用 `httpx.AsyncClient(transport=ASGITransport(app=app))` 测路由，不起真实服务。
- 认证依赖在测试里用 `app.dependency_overrides` 替换，不真调 Supabase。

## 12. 工具链配置（Ruff + Pyright）

- **Ruff 同时承担 lint 与 format**，配置全部进 `pyproject.toml`（不另建 `.flake8` / `.isort.cfg` 等散装配置文件，2026 社区共识）：

```toml
[tool.ruff]
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]   # pycodestyle / pyflakes / isort / bugbear / pyupgrade

[tool.ruff.lint.isort]
known-first-party = ["app"]
```

- **Pyright（strict）** 做类型检查；CI 三关 = `ruff check` + `ruff format --check` + `pyright`（对齐 v3.2 CI 定义）。
- Astral 的 `ty` 类型检查器为 2026 观察项，暂不引入。

## 13. 反模式速查

| 禁止 | 用什么代替 |
|---|---|
| 路由里写 SQL / 业务逻辑 / 调 LLM | 下沉到 service / agents |
| 不写 `response_model` | 必须声明（OpenAPI 类型来源） |
| `@app.on_event("startup")` | `lifespan` |
| async 路由里同步阻塞调用 | 异步库 / worker / `asyncio.to_thread` |
| API 进程内跑 ASR / ffmpeg | procrastinate worker |
| `os.getenv` / 硬编码密钥 | `pydantic-settings` |
| 手拼 SSE 格式的 `StreamingResponse` | `sse-starlette` |
| 路径动词式命名 `/getRecords` | 资源复数 + HTTP 方法语义 |
| 查询不带 `user_id` | 依赖注入 user_id 并层层下传 |
