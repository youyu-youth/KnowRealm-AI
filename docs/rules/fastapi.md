---
paths:
  - "backend/**"
---

# 规范：FastAPI 后端服务层

> 适用范围：`backend/app/`。FastAPI 以 Tauri sidecar 运行，经 PyInstaller 随 `.msi` 分发；版本由 uv 锁定。

## 1. 架构（feature-first 模块化单体，ADR-0015）

| 位置 | 唯一职责 |
|---|---|
| `modules/<域>/` | 业务域闭环：薄路由 + service（业务与事务边界）+ worker + models + schemas；`__init__.py` 仅 docstring |
| `core/` | 进程机制：日志、事件循环、数据目录锁；无业务无状态 |
| `db/` | engine、`user_version` 迁移执行器、Declarative Base |
| `shared/` | 跨域契约：deps（会话/令牌依赖）、全局错误 Schema、失效通知总线 |

- 模块清单：平台 `llm`/`jobs`/`settings`/`data`（被单向依赖）+ 业务域 `course`/`record`/`capture`/`transcript`/`summary`/`knowledge_point`/`quiz`/`todo`/`agent`/`learning`/`search`/`source_anchor`/`review_material`/`profile`/`today`；供应商集成落域内 `integrations/` 子包。
- 跨模块引用（行为与数据契约同规则）直达具体文件（如 `from app.modules.quiz.service import QuizService`）；模块间方向无环，法定方向 = `capture → transcript → summary → {knowledge_point, quiz, todo}`，agent/today 下游，course/record 上游聚合。
- 路由必须薄层（不写 SQL、不调 LLM、不编排业务流程）；事务与领域约束集中在 service；后台任务无独立 worker 进程：`processing_jobs` 表 + 进程内 asyncio 任务池消费。

## 2. 路由与 OpenAPI 契约

- 每资源一个 APIRouter（统一 prefix/tags）；路径复数名词 kebab-case，行为由 HTTP 方法表达；路径/查询参数用具体类型（`UUID`、`int`、query model）在边界校验。
- 请求/响应 `XxxCreate`/`XxxUpdate`/`XxxOut`；更新模型用可选字段 + `model_dump(exclude_unset=True)` 区分未传/显式空值；每路由必须 `response_model`，只暴露对外字段，不返回 ORM/内部技术字段。
- OpenAPI（`/api/openapi.json`）是 `packages/api-types` 生成 TS 类型的唯一契约：破坏性字段变更必须同步生成物再更新前端。

## 3. 安全与异步

- 所有端点（含 health、SSE）校验 Tauri 壳生成的 `X-KnowRealm-Token` 单次启动能力令牌，缺失/错误统一 403；不引入 JWT/`get_current_user`（localhost 不是信任边界）。
- 数据库会话由依赖按请求创建关闭，路由不自建不长期持有。
- uvicorn 经 `app/core/loop.py` 的 loop 工厂启动，入口不散落 `asyncio.run()`；全异步（httpx、SQLAlchemy async），禁协程内 `requests`/同步 SDK/直跑 ffmpeg；重活只进 `processing_jobs` worker；无法替换的同步调用用 `to_thread()` 包裹并注明；subprocess 统一 `create_subprocess_exec()`；对外 HTTP 统一 httpx 且 `trust_env=False`（防系统代理劫持 localhost）。

## 4. SSE

- `sse-starlette` 的 `EventSourceResponse`，不手拼 StreamingResponse；POST + 与普通 API 同样的令牌校验。
- 事件类型固定 `status`/`token`/`tool_call`/`tool_result`/`citation`/`interrupt`/`done`/`error`（ADR-0019；`tool_call`/`tool_result` 仅工具调用流，`interrupt` 保留给需前端确认界面的流）；流内异常必须转 `error` 事件，不得无声断开。

## 5. 错误与日志

- 业务错误用 `CodedHTTPException`（`shared/errors.py`）：稳定错误码 + 语义状态码（400 参数/404 不存在/409 冲突），禁裸 `HTTPException`（防线测试强制）；响应统一 `{"detail": "中文说明", "code": "STABLE_CODE"}`，码名规范见 `docs/后端错误码清单.md`（ADR-0017）。
- 422 统一 `REQUEST_VALIDATION_FAILED`；未预期异常 500 `INTERNAL_ERROR` + `params.request_id`，不暴露堆栈。
- 日志 loguru（InterceptHandler 接管标准 logging）；只记最小元数据（`record_id`/`session_id`/token 数/latency/model/prompt_version/error code），禁记完整转写、敏感对话、prompt/输出正文、密钥或能力令牌。

## 6. 配置与生命周期

- **当前后端不读 `.env`、无 pydantic-settings**：部署级常量为模块内语义常量（先例 `agent/context.py`，配置体系统一后迁移）；不得散落 `os.getenv` 或硬编码配置。
- 用户级供应商密钥存数据目录 `config/providers.json`、偏好存 `config/settings.json`，由 sidecar 运行时读写；数据目录、端口、启动令牌由 Tauri 壳启动参数注入。
- engine/session factory、checkpointer、迁移、worker 的创建销毁统一 lifespan（禁 `@app.on_event`）；启动顺序：解析数据目录 → OS 排他锁 → 迁移 → 共享资源 → worker；退出反向释放。唯一例外：`--import-archive` 在 ensure_data_dir 之后、目录锁与开库之前执行（ADR-0013）。

## 7. 测试与门禁

- 路由测试 `httpx.AsyncClient` + `ASGITransport(app=app)`；数据库测试 aiosqlite 临时库完整重放迁移链（不用 `create_all()`）。
- Ruff 同时负责 lint 与 format、Pyright strict，配置集中 `pyproject.toml`，不新增重复配置文件。
