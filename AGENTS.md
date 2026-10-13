# AGENTS.md

## 必读：Agent 自动执行优先（长期架构原则）

KnowRealm 是一个面向个人学习与工作的 **通用 Agent 工作台**。

**开始功能设计、开发和评审前必须阅读本节。** 开发大部分功能时，都必须优先考虑该功能是否可以被 Agent 自动理解、调用和执行：用户应能通过 AI 对话表达意图，由 Agent 调用对应 Tool / API 与 Service 完成任务，尽量减少必须手动进入页面、点击按钮才能完成的流程。

对于适合接入 Agent 的功能，设计和开发阶段必须同时明确：

- **能力入口**：需要提供或复用哪些 Tool / API，以及对应的领域 Service。
- **上下文与参数**：目标对象、作用范围、必填参数，以及信息缺失时的追问和歧义消除方式。
- **自动执行流程**：从理解意图、调用能力到返回结果的完整路径，以及失败时如何反馈。
- **确认与权限**：哪些操作需要确认、授权覆盖哪些对象与参数，以及执行端如何校验权限。

**验收要求**：在功能方案或工单中明确 Agent 接入方式；不适合接入或本期暂不接入时，说明原因和范围，不能默认只设计页面操作。

**架构边界**：Agent 与页面操作复用领域 Service 和受控执行入口；确定性业务仍由程序执行，遵循下文“产品 AI 能力实现的相关准则”。自动执行遵循 ADR-0026 及当前已实现的授权机制，保留必要确认和操作回执，页面上下文与模型判断不构成授权。

> **功能设计不仅要考虑“用户怎么操作”，还必须考虑“Agent 怎么自动完成”。**

**一句话**：开源的个人学习工作台——把课堂录音、音频、文档、粘贴文本和闪念速记统一"捕获"，自动转化为可编辑、可追溯的学习资产（总结 / 知识点 / 习题 / 复习资料），提供基于内容的 AI 对话问答；内置通用 Agent，用户通过自然语言描述意图，指挥 Agent 自动化执行任务。

- **给谁用**：一切学习知识的人（学生、程序员、上班族、终身学习者）.
- **产品定位（本地优先）**：数据全部落在用户可见、可搬移的本地目录；零部署（.msi 即用）、无账号、桌面端永不强制登录（ADR-0014）。**新能力先过两问**：① 数据是否落在本地可见可搬移的目录？② 是否要求用户多装任何东西？
- **通用 Agent（自动化执行）**：用户通过自然语言描述指挥 Agent 自动化完成任务（受控写路径 + 确认卡 + 回执，见扩展文档 §44 / ADR-0026）
- **长期方向**：从"学习助手"演进为"个人学习大脑"（掌握度 / 遗忘复习 / 自适应学习）

**权威文档（一切问题先查这里，改动以此为准）**：

| 文档                                          | 管什么                                                       |
| --------------------------------------------- | ------------------------------------------------------------ |
| `docs/KnowRealm-AI-功能需求基线-v2.8.md`      | 需求与决策表（#1~#61）                                       |
| `docs/knowRealm-AI-功能升级与创新扩展设计.md` | KnowRealm-AI 扩展功能文档                                    |
| `docs/KnowRealm-AI-数据模型-v3.1.md`          | 数据模型设计基线；实施差异核对 `backend/migrations/` 与 `PROJECT_PROGRESS.md` |
| `PROJECT_PROGRESS.md`                         | 项目进度总览文档/交接文档                                    |
| `docs/技术栈设计与审查-v4.6.md`               | 技术选型与项目结构（§7.1 桌面端 / §7.2 后端）                |
| `GLOSSARY.md`                                  | 领域术语表（角色≠学习场景、KP≠Concept 等）                   |
| `docs/adr/`                                   | 架构决策记录（数据目录 / 登录 / 模块化 / 搜索选型 / 错误码等定稿决策） |

> 文档惯例：评审定稿即升版并**重命名文件**；改版本号须同步全部交叉引用（PRD / 技术栈 / GLOSSARY.md / 扩展设计文档头部），历史"变更记录"行是史实、不改动。重大技术决策落 ADR（编号递增）；与既有 ADR 冲突须显式提出，不得默默覆盖。

<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->


## 仓库布局与命令总览

- `apps/desktop` — Tauri 2 桌面端（pnpm workspace）：dev/build/test/lint 命令见 `apps/desktop/CLAUDE.md`
- `backend` — FastAPI sidecar（uv 管理）：pytest/ruff/pyright 命令见 `backend/CLAUDE.md`
- `packages/api-types` — OpenAPI → TS 类型生成（前后端契约链：后端 schema 变更后须重新 generate）
- 无根 package.json；前端 workspace 由 `pnpm-workspace.yaml` 定义，后端独立用 uv
- 同仓多会话并行时：pytest 各自独立 basetemp（互踩会产生伪失败）、提交点名 add、git mv 后用 `--follow` 核对
- 按改动检查或复现基点失败时，先读 `docs/agents/validation.md`；范围检查入口为 `scripts/check-changed.ps1`，CI 接线见 `.github/workflows/check.yml`。

## 按任务定位功能入口

下列路径相对仓库根目录；用于定位现有实现，不代表对应功能已完成全部验收。进入前后端目录后，继续阅读该目录的 `AGENTS.md`。

| 任务 | 优先入口 | 职责边界 |
| --- | --- | --- |
| 聊天提交、订阅、停止与返回会话 | `apps/desktop/src/features/chat/useChatTurns.ts`；`backend/app/modules/agent/turns/` | ChatTurn 管一次回答生成；历史消息查询与过程投影见 `agent/message_service.py`，Agent 装配见 `agent/graph.py` |
| Agent 工具与受控写操作 | `backend/app/modules/agent/tools/`、`middleware/`、`operations/registry.py`；`backend/app/modules/library/proposals.py` | Tool 表达能力，Middleware 拦截调用，注册表与提案框架连接受控执行；业务规则复用领域 Service |
| 多步业务执行、等待、取消与恢复 | `backend/app/modules/agent/runs/worker.py`；`backend/app/modules/jobs/runner.py`；`backend/app/main.py` | Run 管业务执行，ProcessingJob 管调度；启动装配与恢复接线在 lifespan，不能只检查执行体 |
| 资料检索、共享范围与引用定位 | `backend/app/modules/library/retrieval.py`、`shared_refs.py`；`backend/app/modules/source_anchor/source_anchors.py` | 分别负责检索、共享可见性与只读边界、来源定位；新增消费方先核对既有作用域口径 |
| 课程概念图谱 | `backend/app/modules/course_brain/service.py`；`apps/desktop/src/features/courses/` | Course 级 Concept 与 Record 级知识点是不同实体，术语与生命周期查 `GLOSSARY.md` |
| 学习证据与掌握度 | `backend/app/modules/learning/consumer.py`、`mastery.py` | Consumer 消费学习事实，Mastery 使用确定性算法；不要另建 LLM 掌握度计算链 |
| 学习目标与计划 | `backend/app/modules/learning_plan/service.py`、`generation.py`、`scheduling.py`；`apps/desktop/src/features/learningPlan/` | 分别定位业务入口、生成与材料收集、确定性排期；Agent 接入继续追踪 `agent/operations/` 与 Run |
| 项目脚本 | `scripts` | 仓库级脚本文件位置 |



## 技术文档查询 使用 context7 mcp 或相关context7 skills




## KnowRealm-AI产品AI能力实现的相关准则
**本规范仅适用于 KnowRealm-AI 产品内部的 AI / Agent 能力调用：**

- KnowRealm-AI 中能通过脚本、程序逻辑或工具稳定完成的任务，应优先使用确定性方案，不调用 LLM。
- 只有脚本难以实现，或任务涉及语义理解、推理、生成等能力时，才使用 LLM。
- **总体原则：**KnowRealm-AI 内部脚本优先、LLM 次之，以降低 Token 消耗、延迟和运行成本。

## 编码规范（重要）

1. 写任何代码前必须遵循 `.claude/rules/` 下的编码规范（**正本**；`docs/rules/` 为发布镜像，改动须同步保持一致）。每份规范带 `paths` frontmatter，按所改文件路径自动/按需加载——只读匹配当前任务的规范即可，不要全读。任何时候不要更改rules下的文件。

2. 设计或创建对应的桌面端ui时，需要遵循 impeccable skill 的规范要求，以及调用它来设计。
   - 不要重复造轮子，需要搞清楚当前的ui组件是否 可以用 shadcn ui 来实现。并保持设计规范。

3. **执行编写任务之前，如果该功能是现有代码可以实现的则复用它，复用优先，禁止重复造轮子，保持代码简洁，且职责分明(适用于前端和后端)**

4. 前端样式设计体系遵循如下分层结构和对应职责：

   | 内容                       | 位置                            |
   | -------------------------- | ------------------------------- |
   | 设计令牌（颜色/圆角/间距） | `styles/tokens.css`（`@theme`） |
   | 主题切换（亮/暗语义变量）  | `styles/theme.css`              |
   | 全局 reset / 基础样式      | `styles/globals.css`            |
   | 动画 keyframes             | `styles/animations.css`         |

5. **（必须遵循）**涉及 `langchain` / `langGraph` / `Deep Agents` 等 Agent 相关代码的编写、设计、搭建时，必须先使用 **langchain mcp 工具**（`langchain-docs`，` langchain-reference`）查询官方文档与 API 参考，**复用现成能力、避免重复造轮子**；或使用 `.agents/skills/` / `.zcode/skills/` / `.claude/skills/` 下的相关 skills（langchain-* / langgraph-* / deep-agents-*）。

6. UI 文案新增或修改时，必须同步更新 `zh.json` 与 `en.json`（两边 key 一致；en 缺失会被一致性防线脚本拦截）。

7. agent相关功能，多使用Middleware 中间件等 （优先遵循），如果框架自带的Middleware不能满足需求，则进行自定义的Middleware
8. desktop端界面的修改都需要考虑到多主题的适配和兼容
9. 新增 HTTP 错误码时，同步登记 `docs/后端错误码清单.md` 与 `zh.json`、`en.json` 的 `errors`；三方登记防线见 `backend/tests/test_error_code_guard.py`




## 项目交接原则(遵循)

- Agent 开始任务前或完成功能必须先阅读 `PROJECT_PROGRESS.md`，了解当前项目进度、技术决策和已知问题。
- 完成重要功能、架构调整或技术方案变更后，必须同步更新 `PROJECT_PROGRESS.md`。
- 文档内容必须以当前代码实际状态为准，避免重复开发、状态失真或 Agent 之间的信息断层。
- `PROJECT_PROGRESS.md`文档行数始终保持在200行内。

## 异步功能与恢复验收

- 长任务分别验收“已受理、执行中、已完成”：受理后已落库的用户消息等事实应及时可见，不能只检查最终结果。
- 涉及取消、确认或重试时，追踪实际提交事务及所有独立记账事务，包括失败回执；工具调用前的检查不能替代提交处的取消、执行身份与授权校验。
- 验收记录分别标明自动化测试、模型或网络替身、真实 API/SQLite/Worker、真实模型、真实 Tauri/WebView2 的验证范围及未验证项；浏览器视口或 DPR 模拟不等同于 Windows 系统缩放验收，不代勾用户真机验收。

## 已核实的规范差异

- 聊天当前契约是 POST 提交轮次、GET 订阅持久事件、显式 cancel；切换会话或卸载只关闭订阅。`apps/desktop/AGENTS.md` 的 `useChatStream` 及 `.claude/rules/desktop-state.md`、`fastapi.md` 的 POST 执行流描述尚未对齐；定位实现应从 `useChatTurns.ts` 与 `agent/turns/routes.py` 开始。
- `.claude/rules/data-layer.md` 要求迁移只写 DDL，但 `backend/migrations/0040_web_fetch_plan_draft_recovery_budget.sql` 已使用 UPDATE 回填存量任务。此处仅登记冲突；涉及同类迁移时明确提出处理方案，不自行扩大例外范围。



## DESIGN.md

遵循 DESIGN.md 文件 的ui产品风格设计



## 约束
- 有关前端的操作必须放到前端来实现，即tauri原生已经支持的实现，不要重复造轮子


## 工具(tools)使用习惯，重要原则

- 在探索或检索代码库时，优先使用 codegraph 相关工具来探索或检索代码
- 当需要爬取网页数据的时候，你可以使用firecrawl 相关工具来进行爬取
- 技术文档查询时，使用 context7 mcp 来查询 文档
- 如果使用 lsp 工具更为高效，如 pyright-lsp，则使用它
- 涉及到浏览器交互的操作，优先使用 browser-use mcp 工具.或者 playwright 插件



## git 规范
### git commit 规范
1. 格式为 type(scope): subject，scope 可省略，但 type 和冒号后的一个空格不可省略。
   - feat：新功能;  fix: 缺陷修复;  refactor: 重构;  perf: 性能优化; docs: 文档变更; chore: 杂项 等。
2. subject 用中文书写，以动词开头（实现、修复、完善、重构、移除……），描述“这个提交做了什么”，结尾不加句号。
3. 中文描述


## 文档的更新

任何文档的更新不要保存以前过期的任何信息，这会增大误解。

规范/权威文档的增补先列提案，经用户批准后再动文件。

## Agent skills

### Issue tracker

议题以本地 markdown 文件跟踪于 `.scratch/<feature-slug>/`。见 `docs/agents/issue-tracker.md`。

- 闭环功能不拆前后端票：涉及前后端的功能用一张 issue 完成（票内 checklist 含各域条目，commit 仍按 type(scope) 分次），拆票按功能闭环拆、不按技术层拆。
- 跨会话规模功能须 grill→spec→tickets 同窗口完成、不跳步；单会话小改动才可直连 implement。

### Triage labels

使用五个默认规范角色标签：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。见 `docs/agents/triage-labels.md`。

### Domain docs
单上下文布局：根目录 `GLOSSARY.md` + `docs/adr/`。见 `docs/agents/domain.md`。
