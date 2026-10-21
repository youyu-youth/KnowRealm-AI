# backend（FastAPI sidecar）

**开发必读**：开始功能设计、开发和评审前，必须阅读并遵循[根目录 AGENTS.md](../AGENTS.md)的“Agent 自动执行优先（长期架构原则）”。适合 Agent 执行的能力须同时考虑 Tool / API、上下文与参数、自动执行流程及确认权限；复用领域 Service 和受控执行入口。

本地单用户 FastAPI sidecar：SQLAlchemy 2.0 async + aiosqlite + WAL，是 `knowrealm.db` 与数据目录业务文件的唯一写者/协调者。由 Tauri 壳以子进程拉起（127.0.0.1 随机端口 + 一次性启动令牌），不独立部署。

> 编码规范正本是根目录 `.claude/rules/fastapi.md` 与 `data-layer.md`（自动加载，本文不重复）。本文件记录本目录的**命令、结构与已验证现状**；rules 中 LangGraph、sqlite-vec、pydantic-settings 等内容是目标态，按 function plan 推进，勿擅自补实现。

- 改动 Agent 装配、模型 Middleware 顺序、默认摘要或文件卸载时，按 `../docs/agents/validation.md` 的“Agent 装配变更”验证真实装配后的输入及恢复边界，复用现有预算与恢复回归。

## 常用命令（backend/ 下执行，uv 管理）

| 命令 | 说明 |
| --- | --- |
| `uv sync` | 安装依赖到 `.venv`（dev 依赖经 dependency-groups） |
| `uv run --frozen python -m scripts.run_tests backend` | 统一后端测试入口；筛选、基点、互斥与结果记录见 `../docs/agents/validation.md` |
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
backend/
├── app/
│   ├── main.py       # create_app 工厂 + lifespan（顺序见下）；CORS 限 tauri 来源；全局异常处理器；唯一组合根
│   ├── server.py     # CLI 入口：bind_socket → stdout 打 KNOWREALM_SIDECAR_PORT=<port> → uvicorn 运行
│   ├── modules/      # Feature-first 模块化单体（ADR-0015）：一域一模块（路由+service+worker+models+schemas），包 __init__ 仅 docstring
│   │   ├── llm/                # 平台：OpenAI 兼容结构化调用 + llm_call_logs 埋点
│   │   ├── jobs/               # 平台：processing_jobs 队列 + JobRunner（ADR-0012）+ 控制面 API
│   │   ├── settings/           # 平台：providers/consents/preferences（config.py 读写 settings.json、providers.json）
│   │   ├── data/               # 平台：数据目录导出/导入/滚动备份
│   │   ├── course/             # 课程：CRUD 与归档闸门（/api/courses）
│   │   ├── course_brain/       # 课程大脑：概念图谱构建 worker + 审核闭环
│   │   ├── record/             # 记录：资产主体 CRUD、软删/恢复、SSE 失效事件
│   │   ├── capture/            # 捕获入口：文本/录音会话/音频导入/文档导入/批量捕获 + web_fetch worker
│   │   ├── transcript/         # 转写：document/audio 双 worker（ffmpeg→腾讯 ASR）+ segments + tencent.py 供应商集成样板
│   │   ├── summary/            # AI 总结：生成/调整/确认/版本链 worker
│   │   ├── knowledge_point/    # 知识点：生成 worker + CRUD + 对话锚点写入
│   │   ├── quiz/               # 习题：生成 worker + 逐题评分 grading_worker + 模拟测试
│   │   ├── todo/               # 待办：生成 worker + CRUD
│   │   ├── profile/            # 档案：个人资料与头像
│   │   ├── today/              # 今日：跨域待办汇总
│   │   ├── learning/           # 学习证据：learning_events 水位消费（ADR-0021）+ 概念掌握度
│   │   ├── library/            # 资料库/RAG：library_items + FTS 检索 + backfill/index_rebuild 双 worker + proposals
│   │   ├── review_material/    # 复习资料：生成/确认/版本链 worker
│   │   ├── search/             # 全局搜索：统一索引 + jieba 分词 + web_search（Tavily）
│   │   ├── source_anchor/      # 源锚点：跨资产引用定位
│   │   ├── agent/              # 对话式 Agent 域（ADR-0020/0026）：chat 产品面 + graph 装配 + tools/ + middleware/ + runs/（受控执行：审计/undo/resume）+ operations/ + auth_mode 授权档
│   │   ├── learner/            # 学习者偏好：learner_preferences（含记忆外发开关），agent_proposals 快照冻结用
│   │   └── learning_plan/      # 学习目标与计划：goals/plans/items CRUD + LLM 生成 + 锁定容量铺排 + 人工审计（0034~0036）
│   ├── shared/         # deps（令牌与会话依赖）/ schemas（ErrorResponse）/ errors（ADR-0017 错误码子类）/ prompts（#59 内容语言指令）/ events（Record 失效通知总线）
│   ├── core/           # data_dir（OS 排他锁）/ logging（loguru InterceptHandler）/ loop / version（APP_VERSION）；无 config.py
│   └── db/             # engine（WAL + PRAGMA foreign_keys=ON）/ migrations.py（迁移执行器）/ base（Declarative Base + utcnow）
├── migrations/         # 0001~0036 SQL 迁移（四位编号连续递增；user_version 由 app/db/migrations.py 执行器统一推进）
├── scripts/            # export_openapi 契约导出等工具脚本
└── tests/              # 58 个测试文件；无 conftest，各文件自带 fixture
```

- 跨模块引用（行为与契约同规则）直达具体文件（`from app.modules.quiz.service import QuizService`）；模块间方向无环：`capture → transcript → summary → {kp, quiz, todo}`，agent/today 下游，learning/library/review_material/source_anchor/learner/learning_plan 亦下游，search 无跨模块业务依赖；平台四件套被单向依赖。

- api 路由前缀：`/api/courses`、`/api/records…`（含 `GET /records/{id}/events` SSE、`/{id}/summary*` 总结读/生成/调整/确认/版本、`/{id}/transcript`、`/{id}/jobs`）、`/api/agent…`（auth-mode、runs 的 cancel/resume/undo/retry/purge 与 operations/activity）、`/api/audio-imports`、`/api/capture-batches`、`/api/chat-sessions`、`/api/document-imports`、`/api/learner`（preferences / memory-outbound）、`/api/library`、`/api/processing-jobs`、`/api/profile`、`/api/proposals`、`/api/recording-sessions`、`/api/search`、`/api/settings…`（providers/llm 与 external-processing-consents）、`/api/text-captures`、`/api/today/pending-summaries`、`/api/health`。
- services 分组：课程与记录（course / record_service）；导入与解析（document_import / document_parser / audio_import / capture_batch）；任务域（job_runner 骨架 + 十三个 worker 执行体、processing_job_service / lifecycle / policy、transcript_finalizer、record_invalidation、summary_derivation）；ASR（tencent_asr_client）；录音会话（recording_session_service）；清理与配置（cache_lifecycle / document_cleanup / local_config）；AI 总结（summary_service）；今日待办（today_service）；AI 对话与 Agent 受控执行（agent/session_service、runs/operations/undo 与 auth_mode）；档案（profile_service）；学习证据（learning/consumer / mastery / queries）；资料库（library/service / backfill / proposals）；复习资料（review_material/service）；全局搜索（search/service / tokenizer / web_search / integrations/tavily）；源锚点（source_anchor/source_anchors）。

## agent功能代码编写向导

涉及 `langchain` / `langGraph` / `Deep Agents` 等 Agent 相关代码的编写、设计、搭建时，必须先使用 **langchain mcp 工具**（`langchain-docs`，` langchain-reference`）查询官方文档与 API 参考，**复用现成能力、避免重复造轮子**；或使用 `.agents/skills/` / `.zcode/skills/` / `.claude/skills/` 下的相关 skills（langchain-* / langgraph-* / deep-agents-*）。

**agent相关功能，多使用Middleware 中间件等 （优先遵循），如果框架自带的Middleware不能满足需求，则进行自定义的Middleware**

**多使用Middleware 中间件等**


## KnowRealm-AI产品AI能力实现的相关准则
**本规范仅适用于 KnowRealm-AI 产品内部的 AI / Agent 能力调用：**

- KnowRealm-AI 中能通过脚本、程序逻辑或工具稳定完成的任务，应优先使用确定性方案，不调用 LLM。
- 只有脚本难以实现，或任务涉及语义理解、推理、生成等能力时，才使用 LLM。
- **总体原则：**KnowRealm-AI 内部脚本优先、LLM 次之，以降低 Token 消耗、延迟和运行成本。

## 关键机制

### 启动握手（与 Tauri 壳的协议）

`server.py` 先 `bind_socket()`，再向 **stdout** 打印 `KNOWREALM_SIDECAR_PORT=<port>`，壳读该行后以带令牌的 `GET /api/health` 探活。改此协议必须两侧同步（`apps/desktop/src-tauri/src/sidecar.rs`）。

### lifespan 顺序（顺序敏感）

解析数据目录 → `DataDirectoryLock` 获取 `.knowrealm.lock` OS 排他锁（Windows msvcrt / POSIX flock；失败抛 `DataDirectoryInUseError`，**必须在迁移与 worker 前退出**）→ `ensure_data_dir`（files / cache / exports / backups / config）→ `run_migrations` → `create_database`（engine + session_factory）→ 过期清理（课程墓碑、staging 孤儿）→ `recover_interrupted()` + 启动 worker；退出严格逆序（stop worker → await 任务 → `engine.dispose()` → 释放目录锁）。

### 迁移纪律

`migrations/NNNN_snake_case.sql` 四位编号**必须从 0001 连续递增**（执行器校验拒绝跳号）；脚本只写 DDL，`PRAGMA user_version` 由 `db/migrations.py` 执行器在事务内统一推进；已发布迁移不可改，纠错新增迁移。当前最新 **0036**（0027 研究会话 RESEARCH 模式整表重建；0028~0033 Agent 受控执行：proposal 结果落库与文本/record 关联、agent_runs/agent_operations/agent_activity 三表、chat_message 执行锚点、proposal 快照、agent_run job_type；0034~0036 学习目标与计划两表加列；升级前自动落 `knowrealm-premigrate-NNNN.db` 快照）。全部 `user_version` 断言（22 个测试文件）自 C2 收敛（3b836b0）起统一引用 `supported_user_version()` 动态值，**新增迁移零断言同步**（新迁移测试沿用同形断言；全库 grep 断言处数保留为兜底纪律）。

### 令牌校验

`api/deps.py::require_launch_token` 以 `hmac.compare_digest` 校验 Header `X-KnowRealm-Token`（与 `app.state.launch_token` 比较），缺失/不匹配 403「无权访问本地服务」。所有端点（含 `/api/health` 与 SSE）都挂此依赖。

### 进程内 worker（processing_jobs 即队列，无独立 worker 进程）

任务循环骨架单一归属 `modules/jobs/runner.py`（ADR-0012）：十三个 worker（document / audio / summary / review_material / knowledge_point / quiz / quiz_grading / todo / course_brain / library_backfill / web_fetch / library_index_rebuild / agent_run）各是一份声明式 `WorkerSpec`（候选查询 + 领取校验三态 + 执行体 + 写回 + 失败结局）注入 JobRunner，每 worker 一个 asyncio 任务，lifespan 内经显式工厂表启动。**新生成域一律写执行体描述，禁止复制骨架**；测试挂闸走公开接缝（模块级钩子函数 / `JobRunner.claim_one`），禁止 patch 私有方法。音频链：ffmpeg 转码（16k 单声道 libopus、300s 切片，经 `asyncio.create_subprocess_exec` 调随包 ffmpeg）→ 腾讯云 ASR（TC3-HMAC-SHA256 自签、httpx `trust_env=False`；consent / 密钥 / 离线三种 waiting_reason 不消耗 attempts；task_id 断点存 input_json，重启续轮询不重提交）。

### SSE（ADR-0008 按流语义拆分）

- Record 失效通知（**已实现**）：`GET /api/records/{id}/events`，只发 `invalidate` 事件（`RecordInvalidationNotifier`：per-record 版本号 + asyncio.Event；15s ping）；REST/SQLite 恒为事实源。
- AI/Chat 命令流（**已实现**）：POST + `status/token/tool_call/tool_result/citation/done/error` 七种事件（`interrupt` 尚未在 chat 命令流发出）。事件清单扩展决策见 ADR-0019，两份 rules 及镜像已同步为八事件全集。

### Agent 受控执行（ADR-0026）

写侧动作走 `agent_proposals` 确认卡 + `agent_runs`/`agent_operations` 审计账本。授权档 `AuthMode` 三档（REQUEST_APPROVAL / AUTO_APPROVE / FULL_ACCESS）：实际授权＝固化档（PUT `/api/agent/auth-mode`）∩ 会话覆盖（降档即时生效，重启仅剩固化档）。undo 按账本逆序补偿（run 级与单 operation 级端点）。执行体为 `agent_run` worker（`modules/agent/runs/worker.py`）。新增 Agent 写能力必须挂进该链路（复用 proposals + operations 回执），禁止绕过直写。

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
- 全量 pyright 门禁以零错误为准。
