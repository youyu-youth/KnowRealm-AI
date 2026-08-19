# 规范：FastAPI 后端服务层

> 适用范围：`backend/app/`。FastAPI 以 Tauri sidecar 运行，并由 PyInstaller 随 `.msi` 分发。稳定线为 0.14x；0.x minor 可能破坏兼容，版本必须由 uv 锁定。

## 1. 架构与职责

| 目录 | 唯一职责 |
|---|---|
| `api/` | 解析参数、调用 service、返回响应 |
| `services/` | 业务逻辑与事务边界 |
| `models/` | SQLAlchemy ORM 模型 |
| `schemas/` | Pydantic 请求、响应和结构化输出 |
| `agents/` | LangGraph 编排 |
| `db/` | engine 与 `user_version` 迁移执行器 |
| `core/` | 配置、日志、事件循环和依赖 |

- 路由必须保持薄层，不得直接写 SQL、调用 LLM 或组装业务流程。
- service 层集中承载事务、worker 复用逻辑和唯一写入口等领域约束。
- 后台任务不设独立 worker 进程：`processing_jobs` 表作为队列，由 sidecar 进程内 asyncio 任务池消费。

## 2. 路由与 OpenAPI 契约

- 每个资源一个 `APIRouter`，统一 `prefix` 和 `tags`。路径使用复数名词 kebab-case，行为由 HTTP 方法表达；子动作也使用名词资源。
- 路径和查询参数使用 `UUID`、`int`、Pydantic query model 等具体类型，让 FastAPI 在边界校验。
- 请求与响应分别使用 `XxxCreate`、`XxxUpdate`、`XxxOut`；更新模型通过可选字段与 `model_dump(exclude_unset=True)` 区分未传和显式空值。
- 每个路由必须声明 `response_model`，每个 Schema 字段必须有类型注解；响应只暴露对外字段，不返回 ORM 或内部技术字段。
- OpenAPI 位于 `/api/openapi.json`，是 `packages/api-types` 生成 TypeScript 类型的唯一契约。破坏性字段变更必须同步 OpenAPI 生成物，再更新前端调用。

## 3. 依赖与安全边界

- 数据库会话由依赖按请求创建并关闭；路由不得自行创建或长期持有 Session。
- 本机单用户模式不引入 JWT、`get_current_user` 或 RLS claims，但 localhost 不是信任边界。
- 所有端点，包括 health 和 SSE，都必须校验 Tauri 壳生成的 `X-KnowRealm-Token` 单次启动能力令牌；缺失或错误统一返回 403。该令牌不是用户登录认证。

## 4. Windows 与异步纪律

- uvicorn 必须通过 `app/core/loop.py` 的 loop 工厂和专用入口启动；不得在入口散落 `asyncio.run()`。
- 路由和 service 使用 `async def` 与异步 IO（httpx、SQLAlchemy async）。不得在 API 协程中调用 `requests`、同步 SDK 或直接执行 ffmpeg。
- ASR、ffmpeg 等重活只在 `processing_jobs` worker 任务中执行；无法替换的同步第三方调用用 `asyncio.to_thread()` 包裹并注明原因。
- subprocess 统一使用 `asyncio.create_subprocess_exec()`。
- 对外 HTTP 统一使用 httpx 且设置 `trust_env=False`，避免 Windows 系统代理劫持 localhost 或直连请求。

## 5. SSE

- 服务端使用 `sse-starlette` 的 `EventSourceResponse`，不得手拼 `StreamingResponse` 格式。
- SSE 端点使用 POST，并与普通 API 一样校验 `X-KnowRealm-Token`。
- 事件类型固定为 `token`、`status`、`citation`、`interrupt`、`done`、`error`。
- 流内异常必须转换为 `error` 事件，不能无声断开；`interrupt` 必须携带前端渲染确认界面所需的完整 payload，并由恢复接口继续流程。
- sidecar 状态变更同样通过进程内事件推送 SSE；UI 轮询仅作断线兜底。

## 6. 错误与日志

- 业务错误使用 `HTTPException` 和语义化状态码：400 参数错误、404 资源不存在、409 业务状态冲突；错误响应统一为 `{"detail": "..."}`。
- 未预期异常由全局处理器记录后返回 500 和 request_id；不得向前端暴露堆栈或内部异常。
- 日志统一使用 loguru；`InterceptHandler` 接管 uvicorn、SQLAlchemy 标准 logging，附加字段通过 kwargs 写入。
- 日志只记录最小元数据：`record_id`、`segment_id`、`session_id`、token 数量、latency、model、prompt_version、error code。
- 禁止记录完整转写、Teach-back、敏感对话、prompt/输出正文、密钥或能力令牌。

## 7. 配置与生命周期

- 部署级配置集中到继承 `BaseSettings` 的 Settings 单例；`.env` 不入仓库，新增项同步补充 `.env.example`。不得散落 `os.getenv` 或硬编码配置。
- 用户级供应商密钥存于数据目录 `config/providers.json`，偏好存于 `config/settings.json`，均由 sidecar 运行时读写；数据目录、端口和启动令牌由 Tauri 壳通过启动参数注入，不进入 `.env`。
- 取值有限的配置使用 `Literal` 等类型约束。
- engine/session factory、LangGraph checkpointer、迁移和 worker 的创建与销毁统一放在 FastAPI `lifespan`；不得新增 `@app.on_event`。
- lifespan 启动顺序：解析数据目录 → 执行迁移 → 创建共享资源 → 启动 worker；退出时停止 worker 并释放 engine 等资源。

## 8. 测试与质量门禁

- 路由测试使用 `httpx.AsyncClient` + `ASGITransport(app=app)`，无需启动真实服务。
- 数据库测试使用 aiosqlite 临时库并完整重放生产迁移链；不得用 `create_all()` 替代迁移。
- Ruff 同时负责 lint 与 format，Pyright 使用 strict；配置统一放 `pyproject.toml`，不新增 `.flake8`、`.isort.cfg` 等重复配置。
- CI 门禁为 `ruff check`、`ruff format --check`、`pyright`；`ty` 仍为观察项，暂不引入。
