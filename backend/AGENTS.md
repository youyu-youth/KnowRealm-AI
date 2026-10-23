# backend（FastAPI sidecar）

**开发必读**：开始功能设计、开发和评审前，必须阅读并遵循[根目录 AGENTS.md](../AGENTS.md)的“Agent 自动执行优先（长期架构原则）”。适合 Agent 执行的能力须同时考虑 Tool / API、上下文与参数、自动执行流程及确认权限；复用领域 Service 和受控执行入口。

本地单用户 FastAPI sidecar：SQLAlchemy 2.0 async + aiosqlite + WAL，是 `knowrealm.db` 与数据目录业务文件的唯一写者/协调者。由 Tauri 壳以子进程拉起（127.0.0.1 随机端口 + 一次性启动令牌），不独立部署。

> 编码规范正本是根目录 `.claude/rules/fastapi.md`、`data-layer.md`；Agent 相关任务同时读取 `langchain-langgraph.md`。本文件记录本目录的**命令、结构与已验证现状**；已知规范差异见根目录 AGENTS.md，实施与验收状态查 PROJECT_PROGRESS.md。

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
│   │   ├── agent/              # Agent 域（ADR-0020/0026/0030）：固定身份、共享图装配、turns 根轮次、delegations 知识委派、runs/operations 受控业务执行
│   │   ├── learner/            # 学习者偏好：learner_preferences（含记忆外发开关），agent_proposals 快照冻结用
│   │   └── learning_plan/      # 学习目标与计划：goals/plans/items CRUD + LLM 生成 + 锁定容量铺排 + 人工审计（0034~0036）
│   ├── shared/         # deps（令牌与会话依赖）/ schemas（ErrorResponse）/ errors（ADR-0017 错误码子类）/ prompts（#59 内容语言指令）/ events（Record 失效通知总线）
│   ├── core/           # data_dir（OS 排他锁）/ logging（loguru InterceptHandler）/ loop / version（APP_VERSION）；无 config.py
│   └── db/             # engine（WAL + PRAGMA foreign_keys=ON）/ migrations.py（迁移执行器）/ base（Declarative Base + utcnow）
├── migrations/         # 手写 SQL 迁移（四位编号连续递增；user_version 由 app/db/migrations.py 执行器统一推进）
├── scripts/            # export_openapi 契约导出等工具脚本
└── tests/              # 无 conftest，各文件自带 fixture
```

### Agent 任务入口

以下路径相对 `app/modules/agent/`：

| 修改内容 | 优先入口 |
| --- | --- |
| Agent 目录与能力装配 | `agents.py` 提供固定目录；`graph.py` 的 `resolve_agent_config` / `build_agent` 负责专业配置与共享 Harness |
| 根轮次提交与执行 | `turns/routes.py`、`service.py`、`worker.py`；等待绑定与结果对账见 `turns/background.py` |
| 知识委派与恢复 | `tools/delegate_knowledge.py` → `delegations/service.py`、`worker.py`；不确定请求的用户决定见 `delegations/decisions.py` |
| 工具额度与模型收尾 | `budget/middleware.py`、`service.py`、`policy.py`；修改模型可见工具或共享额度时，联查 `context_budget/middleware.py` 的完整输入计量与恢复防重发 |
| 受控业务执行 | `runs/`、`operations/`；知识委派不作为业务操作账本 |

修改 Agent 身份、工具集合／参数／权限、预算策略、委派契约／调度或图状态语义前读 [ADR-0030](../docs/adr/0030-bounded-professional-agents-and-durable-delegation.md)；任务/报告契约及恢复场景查 [Multi-Agent spec](../.scratch/multi-agent-refactor/spec.md)。变更执行链时联查 `app/main.py`、`turns/worker.py` 与 `turns/background.py` 的启动、分派和对账接线。

- 跨模块引用（行为与契约同规则）直达具体文件（`from app.modules.quiz.service import QuizService`）；模块间方向无环：`capture → transcript → summary → {kp, quiz, todo}`，agent/today 下游，learning/library/review_material/source_anchor/learner/learning_plan 亦下游，search 无跨模块业务依赖；平台四件套被单向依赖。

- api 路由前缀：`/api/courses`、`/api/records…`（含 `GET /records/{id}/events` SSE、`/{id}/summary*` 总结读/生成/调整/确认/版本、`/{id}/transcript`、`/{id}/jobs`）、`/api/agent…`（auth-mode、runs 的 cancel/resume/undo/retry/purge 与 operations/activity）、`/api/audio-imports`、`/api/capture-batches`、`/api/chat-sessions`、`/api/document-imports`、`/api/learner`（preferences / memory-outbound）、`/api/library`、`/api/processing-jobs`、`/api/profile`、`/api/proposals`、`/api/recording-sessions`、`/api/search`、`/api/settings…`（providers/llm 与 external-processing-consents）、`/api/text-captures`、`/api/today/pending-summaries`、`/api/health`。

### Agent 能力接入检查

实施前，在工单中选择本次能力的接入路径；复合能力可组合下列路径：

| 能力 | 优先复用路径 |
| --- | --- |
| 查询、计算、读取资料 | 只读 Tool → 领域 Service |
| 修改业务数据 | Tool → 现有受控 Operation／提案入口 → 领域 Service |
| 耗时生成、等待外部处理 | 领域任务 → WorkerSpec／ProcessingJob；多步业务按需关联 AgentRun |
| 需要隔离材料的知识研究 | 现有知识委派链路；后台任务本身不作为新增 Agent 的依据 |

接入完成时，逐项给出本次适用检查的实现位置或验收依据：

- **装配**：目标 Agent 的最终模型请求包含正确的工具及参数 schema，受影响的身份与挂载条件符合预期。
- **范围**：资料范围、目标对象与权限由执行端校验，业务规则复用领域 Service。
- **消费**：明确工具次数、输出字符与业务操作的计量归属，复用适用的准入和持久记账；豁免计量时说明理由。
- **结果**：成功、错误、状态及适用的引用／回执进入既有返回与展示链路。
- **兼容**：按变更范围检查图、提示与预算策略版本，明确旧轮次／子任务的续跑或停止方式，保留原消费和已完成结果。
- **验证**：通过实际装配和执行入口，证明本次受影响的成功、拒绝及必要恢复分支；仅调用工具函数不算接入完成。

## agent功能代码编写向导

涉及 `langchain` / `langGraph` / `Deep Agents` 等 Agent 相关代码的编写、设计、搭建时，必须先使用 **langchain mcp 工具**（`langchain-docs`，` langchain-reference`）查询官方文档与 API 参考，**复用现成能力、避免重复造轮子**；或使用 `.agents/skills/` / `.zcode/skills/` / `.claude/skills/` 下的相关 skills（langchain-* / langgraph-* / deep-agents-*）。

Middleware 选用遵循[根目录 AGENTS.md 的“编码规范（重要）”](../AGENTS.md#编码规范重要)。

## KnowRealm-AI产品AI能力实现的相关准则
产品内部的 AI／Agent 调用遵循[根目录对应准则](../AGENTS.md#knowrealm-ai产品ai能力实现的相关准则)。

## 关键机制

### 启动握手（与 Tauri 壳的协议）

`server.py` 先 `bind_socket()`，再向 **stdout** 打印 `KNOWREALM_SIDECAR_PORT=<port>`，壳读该行后以带令牌的 `GET /api/health` 探活。改此协议必须两侧同步（`apps/desktop/src-tauri/src/sidecar.rs`）。

### lifespan 顺序（顺序敏感）

完整启动与清理顺序以 `app/main.py::lifespan` 为准。目录初始化及可选归档恢复在获取目录锁、开库之前完成；获取目录锁后才进行升级前快照、迁移、开库和 Worker 恢复／启动，锁获取失败须在迁移与 Worker 启动前退出。关闭时先停止并等待 Worker，再释放数据库连接和目录锁。

### 迁移纪律

`migrations/NNNN_snake_case.sql` 四位编号从 0001 连续递增；脚本只写 DDL，执行器统一推进 `PRAGMA user_version`；已发布迁移保持不变，纠错新增迁移。最新编号查 `migrations/`，支持版本通过 `app/db/migrations.py::supported_user_version()` 获取，测试沿用该函数而非复制当前编号。升级前自动保存 `knowrealm-premigrate-NNNN.db` 快照；存量 DML 例外冲突见根目录“已核实的规范差异”。

### 令牌校验

`app/shared/deps.py::require_launch_token` 以 `hmac.compare_digest` 校验 Header `X-KnowRealm-Token`（与 `app.state.launch_token` 比较），缺失/不匹配 403「无权访问本地服务」。所有端点（含 `/api/health` 与 SSE）都挂此依赖。

### 进程内 worker（processing_jobs 即队列，无独立 worker 进程）

任务循环骨架单一归属 `modules/jobs/runner.py`（ADR-0012）：各域以声明式 `WorkerSpec`（候选查询 + 领取校验三态 + 执行体 + 写回 + 失败结局）注入 JobRunner，lifespan 内经显式工厂表启动。`CHAT_TURN` 的两个槽共用 `agent/turns/worker.py::chat_turn_spec`，按持久目标分派根轮次或委派子执行；父进入 WAITING_JOB 后释放槽。**新生成域一律写执行体描述，禁止复制骨架**；测试挂闸走公开接缝（模块级钩子函数 / `JobRunner.claim_one`），禁止 patch 私有方法。音频链：ffmpeg 转码（16k 单声道 libopus、300s 切片，经 `asyncio.create_subprocess_exec` 调随包 ffmpeg）→ 腾讯云 ASR（TC3-HMAC-SHA256 自签、httpx `trust_env=False`；consent / 密钥 / 离线三种 waiting_reason 不消耗 attempts；task_id 断点存 input_json，重启续轮询不重提交）。

### SSE（ADR-0008 按流语义拆分）

- Record 失效通知（**已实现**）：`GET /api/records/{id}/events`，只发 `invalidate` 事件（`RecordInvalidationNotifier`：per-record 版本号 + asyncio.Event；15s ping）；REST/SQLite 恒为事实源。
- Chat 轮次：POST 提交、GET 订阅持久事件、显式 cancel；入口见 `agent/turns/routes.py`。子任务进度复用根事件流与快照，切换会话或卸载仅断订阅；旧 rules 的 POST 执行流描述以根目录“已核实的规范差异”为准。

### Agent 受控执行（ADR-0026）

写侧动作走 `agent_proposals` 确认卡 + `agent_runs`/`agent_operations` 审计账本。授权档 `AuthMode` 三档（REQUEST_APPROVAL / AUTO_APPROVE / FULL_ACCESS）：实际授权＝固化档（PUT `/api/agent/auth-mode`）∩ 会话覆盖（降档即时生效，重启仅剩固化档）。undo 按账本逆序补偿（run 级与单 operation 级端点）。执行体为 `agent_run` worker（`modules/agent/runs/worker.py`）。新增 Agent 写能力必须挂进该链路（复用 proposals + operations 回执），禁止绕过直写。

### 录音分片接收（ADR-0009：sidecar 拥有暂存）

`app/modules/capture/recording_session.py`：multipart 分片 → 临时 `.part` 文件 + `os.replace` 原子改名 → WebM 魔数与 SHA-256 幂等校验 → 更新 `recording_sessions.chunk_paths` 有序清单；会话状态机（RECORDING / PAUSED / FINALIZING…）与崩溃恢复同在此文件。

### 配置

实际配置 = 数据目录 `config/settings.json` + `config/providers.json`（`app/modules/settings/config.py`：tmp + replace + fsync 原子写）+ Tauri 启动参数注入。**无 pydantic-settings，不读任何 .env**。

## 测试约定

- **无 conftest.py**：各测试文件自带 async contextmanager fixture——`create_app(data_dir=临时目录, launch_token="test-launch-token")` → `async with app.router.lifespan_context(app)`（完整重放生产迁移链，绝不用 create_all）→ `httpx.AsyncClient(transport=ASGITransport(app))` + 固定令牌头。
- 异步标记 `@pytest.mark.anyio`（anyio 插件，**非 pytest-asyncio**；pyproject 无 asyncio_mode 配置）。
- 测试临时目录由统一运行器分配；路径、互斥与日志约定见[验证文档的统一入口](../docs/agents/validation.md#本地与-ci-共用的测试入口)。
- `tests/test_server_process.py`：真实子进程集成（本机无 ffmpeg 自动 skip；从 stdout 解析端口；覆盖二次 sidecar 拿锁失败 `DATA_DIRECTORY_IN_USE` 等）；ASR 场景用 `tests/sidecar_asr_fixture.py` 的假腾讯 HTTP 传输（control JSON 切换 success/pending/503 等）。
- 数据库断言直接 `aiosqlite.connect` 查 `PRAGMA user_version` / 表结构 / 外键。
- 全量 pyright 门禁以零错误为准。
