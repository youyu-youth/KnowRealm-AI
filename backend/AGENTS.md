# backend（FastAPI sidecar）

**开发必读**：开始功能设计、开发和评审前，必须阅读并遵循[根目录 AGENTS.md](../AGENTS.md)的“Agent 自动执行优先（长期架构原则）”。适合 Agent 执行的能力须同时考虑 Tool / API、上下文与参数、自动执行流程及确认权限；复用领域 Service 和受控执行入口。

本地单用户 FastAPI sidecar：SQLAlchemy 2.0 async + aiosqlite + WAL，是 `knowrealm.db` 与数据目录业务文件的唯一写者/协调者。由 Tauri 壳以子进程拉起（127.0.0.1 随机端口 + 一次性启动令牌），不独立部署。

> 编码规范正本是根目录 `.claude/rules/fastapi.md` 与 `data-layer.md`（自动加载，本文不重复）。本文件记录本目录的**命令、结构与已验证现状**；rules 中 LangGraph、sqlite-vec、pydantic-settings 等内容是目标态，差异见文末 Gotchas——按 function plan 推进，勿擅自补实现。

## 常用命令（backend/ 下执行，uv 管理）

| 命令 | 说明 |
| --- | --- |
| `uv sync` | 安装依赖到 `.venv`（dev 依赖经 dependency-groups） |
| `uv run pytest` | 全量测试；建议 `--basetemp .tmp/pytest-<tag>` 且测完删除（`*.tmp` 已被 gitignore） |
| `uv run ruff check .` / `uv run ruff format --check .` | lint 与格式门禁（target py312、line-length 100、select E/F/I/B/UP） |
| `uv run pyright` | strict 模式，include `app` + `tests` |
| `uv run python -m scripts.export_openapi ../packages/api-types/openapi.json [--check]` | 导出 / 校验 OpenAPI 契约 |

**本地运行没有独立 uvicorn 命令**：由 `pnpm --filter @knowrealm/desktop tauri dev` 拉起（debug 用本目录 `.venv/Scripts/python.exe`），等价于：

```
python -m app.server --port 0 --token <32字节hex> --data-dir %USERPROFILE%\KnowRealm --ffmpeg <随包ffmpeg>
```

（argparse 四参数均必填；`--port 0` = 绑随机端口；loop 用 `app/core/loop.py` 的 Proactor 工厂）。

## 目录结构

```
app/
├── main.py          # create_app 工厂 + lifespan（顺序见下）；CORS 限 tauri 来源；全局异常处理器；唯一组合根
├── server.py        # CLI 入口：bind_socket → stdout 打 KNOWREALM_SIDECAR_PORT=<port> → uvicorn 运行
├── modules/         # Feature-first 模块化单体（ADR-0015）：一域一模块（路由+service+worker+models+schemas），包 __init__ 仅 docstring
│   ├── llm/         # 平台：OpenAI 兼容结构化调用 + llm_call_logs 埋点
│   ├── jobs/        # 平台：processing_jobs 队列 + JobRunner（ADR-0012）+ 控制面 API
│   ├── settings/    # 平台：providers/consents/preferences（config.py 读写 settings.json、providers.json）
│   ├── data/        # 平台：数据目录导出/导入/滚动备份
│   ├── course/ course_brain/ record/ capture/ transcript/ summary/ knowledge_point/ quiz/ todo/ profile/ today/
│   ├── learning/ library/ review_material/ search/ source_anchor/
│   ├── agent/        # 对话式 Agent 域（ADR-0020）：chat 产品面 + graph 装配 + tools/ + middleware/（chat/ 更名升级）
│   └── transcript/integrations/tencent.py  # 腾讯 ASR 客户端（供应商集成样板）
├── shared/          # deps（令牌与会话依赖）/ schemas（ErrorResponse）/ errors（ADR-0017 错误码子类）/ prompts（#59 内容语言指令）/ events（Record 失效通知总线）
├── core/            # data_dir（OS 排他锁）/ logging（loguru InterceptHandler）/ loop / version（APP_VERSION）；无 config.py
└── db/              # engine（WAL + PRAGMA foreign_keys=ON）/ migrations（迁移执行器）/ base（Declarative Base + utcnow）
```

- 跨模块引用（行为与契约同规则）直达具体文件（`from app.modules.quiz.service import QuizService`）；模块间方向无环：`capture → transcript → summary → {kp, quiz, todo}`，agent/today 下游，learning/library/review_material/source_anchor 亦下游，search 无跨模块业务依赖；平台四件套被单向依赖。

- api 路由前缀：`/api/courses`、`/api/records…`（含 `GET /records/{id}/events` SSE、`/{id}/summary*` 总结读/生成/调整/确认/版本、`/{id}/transcript`、`/{id}/jobs`）、`/api/audio-imports`、`/api/capture-batches`、`/api/chat-sessions`、`/api/document-imports`、`/api/library`、`/api/processing-jobs`、`/api/profile`、`/api/proposals`、`/api/recording-sessions`、`/api/search`、`/api/settings…`（providers/llm 与 external-processing-consents）、`/api/text-captures`、`/api/today/pending-summaries`、`/api/health`。
- services 分组：课程与记录（course / record_service）；导入与解析（document_import / document_parser / audio_import / capture_batch）；任务域（job_runner 骨架 + 十个 worker 执行体、processing_job_service / lifecycle / policy、transcript_finalizer、record_invalidation、summary_derivation）；ASR（tencent_asr_client）；录音会话（recording_session_service）；清理与配置（cache_lifecycle / document_cleanup / local_config）；AI 总结（summary_service）；今日待办（today_service）；AI 对话（agent/session_service）；档案（profile_service）；学习证据（learning/consumer / mastery / queries）；资料库（library/service / backfill / proposals）；复习资料（review_material/service）；全局搜索（search/service / tokenizer / web_search / integrations/tavily）；源锚点（source_anchor/source_anchors）。

## agent功能代码编写向导

涉及 `langchain` / `langGraph` / `Deep Agents` 等 Agent 相关代码的编写、设计、搭建时，必须先使用 **langchain mcp 工具**（`langchain-docs`，` langchain-reference`）查询官方文档与 API 参考，**复用现成能力、避免重复造轮子**；或使用 `.agents/skills/` / `.zcode/skills/` / `.claude/skills/` 下的相关 skills（langchain-* / langgraph-* / deep-agents-*）。

**多使用Middleware 中间件等**

## 关键机制

### 启动握手（与 Tauri 壳的协议）

`server.py` 先 `bind_socket()`，再向 **stdout** 打印 `KNOWREALM_SIDECAR_PORT=<port>`，壳读该行后以带令牌的 `GET /api/health` 探活。改此协议必须两侧同步（`apps/desktop/src-tauri/src/sidecar.rs`）。

### lifespan 顺序（顺序敏感）

解析数据目录 → `DataDirectoryLock` 获取 `.knowrealm.lock` OS 排他锁（Windows msvcrt / POSIX flock；失败抛 `DataDirectoryInUseError`，**必须在迁移与 worker 前退出**）→ `ensure_data_dir`（files / cache / exports / backups / config）→ `run_migrations` → `create_database`（engine + session_factory）→ 过期清理（课程墓碑、staging 孤儿）→ `recover_interrupted()` + 启动 worker；退出严格逆序（stop worker → await 任务 → `engine.dispose()` → 释放目录锁）。

### 迁移纪律

`migrations/NNNN_snake_case.sql` 四位编号**必须从 0001 连续递增**（执行器校验拒绝跳号）；脚本只写 DDL，`PRAGMA user_version` 由 `db/migrations.py` 执行器在事务内统一推进；已发布迁移不可改，纠错新增迁移。当前最新 **0026**（资料库数据地基：`library_items`/`library_item_records`/`agent_proposals`/`learner_preferences` 四新表 + `course_material_id`→`library_item_id` 改名列补 FK + `chat_sessions` 五档 scope 与 `library_item_id` + `processing_jobs.library_item_id` 与三新 job_type；升级前自动落 `knowrealm-premigrate-NNNN.db` 快照，存量映射走 LIBRARY_BACKFILL 幂等 Job）。全部 `user_version` 断言（16 个测试文件，`test_archive.py` 8 处 + 其余各 1 处）自 C2 收敛（3b836b0）起统一引用 `supported_user_version()` 动态值，**新增迁移零断言同步**（新迁移测试沿用同形断言；全库 grep 断言处数保留为兜底纪律）。

### 令牌校验

`api/deps.py::require_launch_token` 以 `hmac.compare_digest` 校验 Header `X-KnowRealm-Token`（与 `app.state.launch_token` 比较），缺失/不匹配 403「无权访问本地服务」。所有端点（含 `/api/health` 与 SSE）都挂此依赖。

### 进程内 worker（processing_jobs 即队列，无独立 worker 进程）

任务循环骨架单一归属 `services/job_runner.py`（ADR-0012）：九个 worker（document / audio / summary / review_material / knowledge_point / quiz / quiz_grading / todo / course_brain）各是一份声明式 `WorkerSpec`（候选查询 + 领取校验三态 + 执行体 + 写回 + 失败结局）注入 JobRunner，每 worker 一个 asyncio 任务，lifespan 内经显式工厂表启动。**新生成域一律写执行体描述，禁止复制骨架**；测试挂闸走公开接缝（模块级钩子函数 / `JobRunner.claim_one`），禁止 patch 私有方法。音频链：ffmpeg 转码（16k 单声道 libopus、300s 切片，经 `asyncio.create_subprocess_exec` 调随包 ffmpeg）→ 腾讯云 ASR（TC3-HMAC-SHA256 自签、httpx `trust_env=False`；consent / 密钥 / 离线三种 waiting_reason 不消耗 attempts；task_id 断点存 input_json，重启续轮询不重提交）。

### SSE（ADR-0008 按流语义拆分）

- Record 失效通知（**已实现**）：`GET /api/records/{id}/events`，只发 `invalidate` 事件（`RecordInvalidationNotifier`：per-record 版本号 + asyncio.Event；15s ping）；REST/SQLite 恒为事实源。
- AI/Chat 命令流（**已实现**）：POST + `status/token/tool_call/tool_result/citation/done/error` 七种事件（`interrupt` 尚未在 chat 命令流发出）。事件清单扩展决策见 ADR-0019，两份 rules 及镜像已同步为八事件全集。

### 录音分片接收（ADR-0009：sidecar 拥有暂存）

`recording_session_service`：multipart 分片 → 临时 `.part` 文件 + `os.replace` 原子改名 → WebM 魔数与 SHA-256 幂等校验 → 更新 `recording_sessions.chunk_paths` 有序清单；会话状态机（RECORDING / PAUSED / FINALIZING…）与崩溃恢复同在此文件。

### 配置

实际配置 = 数据目录 `config/settings.json` + `config/providers.json`（`local_config.py`：tmp + replace + fsync 原子写）+ Tauri 启动参数注入。**无 pydantic-settings，不读任何 .env**。

## 测试约定

- **无 conftest.py**：各测试文件自带 async contextmanager fixture——`create_app(data_dir=临时目录, launch_token="test-launch-token")` → `async with app.router.lifespan_context(app)`（完整重放生产迁移链，绝不用 create_all）→ `httpx.AsyncClient(transport=ASGITransport(app))` + 固定令牌头。
- 异步标记 `@pytest.mark.anyio`（anyio 插件，**非 pytest-asyncio**；pyproject 无 asyncio_mode 配置）。
- `--basetemp` 前须确保 `.tmp` 父目录存在：此 pytest 在 Windows 不建父目录，删掉 `.tmp` 本体会让全量测试以 FileNotFoundError 批量假失败。
- `tests/test_server_process.py`：真实子进程集成（本机无 ffmpeg 自动 skip；从 stdout 解析端口；覆盖二次 sidecar 拿锁失败 `DATA_DIRECTORY_IN_USE` 等）；ASR 场景用 `tests/sidecar_asr_fixture.py` 的假腾讯 HTTP 传输（control JSON 切换 success/pending/503 等）。
- 数据库断言直接 `aiosqlite.connect` 查 `PRAGMA user_version` / 表结构 / 外键。
- 已知基线：`app/core/logging.py:46` 有一个 loguru 类型 stub 的既有 pyright 错误（非新代码引入）；全量 pyright 门禁以"无新增错误"为准。
