# KnowRealm-AI 产品简介

**一句话**：开源的个人学习工作台——把课堂录音、音频、文档、粘贴文本和闪念速记统一"捕获"，自动转化为可编辑、可追溯的学习资产（总结 / 知识点 / 习题 / 复习资料），并提供基于内容的 AI 对话问答。

- **给谁用**：一切学习知识的人（学生、程序员、上班族、终身学习者）.
- **产品定位（本地优先）**：数据全部落在用户可见、可搬移的本地目录；零部署（.msi 即用）、无账号、桌面端永不强制登录（ADR-0014）。**新能力先过两问**：① 数据是否落在本地可见可搬移的目录？② 是否要求用户多装任何东西？
- **核心闭环**：捕获（录音 / 导入 / 粘贴 / 速记）→ ASR 转写 → AI 总结（人工确认）→ 知识点 / 习题 / Todo → AI 问答
- **长期方向**：从"学习助手"演进为"个人学习大脑"（掌握度 / 遗忘复习 / 自适应学习）

**权威文档（一切问题先查这里，改动以此为准）**：

| 文档                                          | 管什么                                                       |
| --------------------------------------------- | ------------------------------------------------------------ |
| `docs/KnowRealm-AI-功能需求基线-v2.8.md`      | 需求与决策表（#1~#61）                                       |
| `docs/knowRealm-AI-功能升级与创新扩展设计.md` | KnowRealm-AI 扩展功能文档                                    |
| `docs/KnowRealm-AI-数据模型-v3.1.md`          | 数据模型（设计 44 张表，已实施 31 张）                       |
| `PROJECT_PROGRESS.md`                         | 项目进度总览文档/交接文档                                    |
| `docs/技术栈设计与审查-v4.6.md`               | 技术选型与项目结构（§7.1 桌面端 / §7.2 后端）                |
| `CONTEXT.md`                                  | 领域术语表（角色≠学习场景、KP≠Concept 等）                   |
| `docs/adr/`                                   | 架构决策记录（数据目录 / 登录 / 模块化 / 搜索选型 / 错误码等定稿决策） |

> 文档惯例：评审定稿即升版并**重命名文件**；改版本号须同步全部交叉引用（PRD / 技术栈 / CONTEXT.md / 扩展设计文档头部），历史"变更记录"行是史实、不改动。重大技术决策落 ADR（编号递增）；与既有 ADR 冲突须显式提出，不得默默覆盖。

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


## KnowRealm-AI产品AI能力实现的相关准则
**本规范仅适用于 KnowRealm-AI 产品内部的 AI / Agent 能力调用：**

- KnowRealm-AI 中能通过脚本、程序逻辑或工具稳定完成的任务，应优先使用确定性方案，不调用 LLM。
- 只有脚本难以实现，或任务涉及语义理解、推理、生成等能力时，才使用 LLM。
- **总体原则：**KnowRealm-AI 内部脚本优先、LLM 次之，以降低 Token 消耗、延迟和运行成本。

## 编码规范（重要）

1. 写任何代码前必须遵循 `.claude/rules/` 下的编码规范（**正本**；`docs/rules/` 为发布镜像，改动须同步保持一致）。每份规范带 `paths` frontmatter，按所改文件路径自动/按需加载——只读匹配当前任务的规范即可，不要全读。任何时候不要更改rules下的文件。

2. 设计或创建对应的桌面端ui时，需要遵循 impeccable skill 的规范要求，以及调用它来设计。
   - 不要重复造轮子，需要搞清楚当前的ui组件是否 可以用 shadcn ui 来实现。并保持设计规范。

3. 在测试中产生的任何临时文件，在测试完毕之后都要进行删除

4. **执行编写任务之前，如果该功能是现有代码可以实现的则复用它，复用优先，禁止重复造轮子，保持代码简洁，且职责分明(适用于前端和后端)**

5. 前端样式设计体系遵循如下分层结构和对应职责：

   | 内容                       | 位置                            |
   | -------------------------- | ------------------------------- |
   | 设计令牌（颜色/圆角/间距） | `styles/tokens.css`（`@theme`） |
   | 主题切换（亮/暗语义变量）  | `styles/theme.css`              |
   | 全局 reset / 基础样式      | `styles/globals.css`            |
   | 动画 keyframes             | `styles/animations.css`         |

6. 在涉及到 `langchain `, `langGraph `, `Deep Agents` 编写，设计，搭建时，请参考 `.agents/skills/`  或 `.zcode/skills/` 或  `.claude/skills/ `下有关的skills来进行编写！或者使用 对应的 mcp tools 工具来进行文档的查询，或者参考其他Agent的设计，下面是仓库代码地址：(可以参考Agent架构设计)

   - `E:\workspace\project\agent-project\open-swe`
   - `E:\workspace\project\agent-project\EvoScientist`
   - `E:\workspace\project\agent-project\Yuxi`

7. 编码时必要时遵循 SOLID、KISS、DRY、YAGNI，保持高内聚、低耦合，避免过度设计与无意义抽象。

8. 根据实际场景合理使用 Service、Adapter、Strategy、Factory、Registry、Pipeline、State Machine、Event 等设计模式，不要为了套模式而套模式。

9. UI 文案新增或修改时，必须同步更新 `zh.json` 与 `en.json`（两边 key 一致；en 缺失会被一致性防线脚本拦截）。




## 项目交接原则(遵循)

- Agent 开始任务前或完成功能必须先阅读 `PROJECT_PROGRESS.md`，了解当前项目进度、技术决策和已知问题。
- 完成重要功能、架构调整或技术方案变更后，必须同步更新 `PROJECT_PROGRESS.md`。
- 文档内容必须以当前代码实际状态为准，避免重复开发、状态失真或 Agent 之间的信息断层。
- `PROJECT_PROGRESS.md`文档行数始终保持在200行内。



## DESIGN.md

遵循 DESIGN.md 文件 的ui产品风格设计



## 约束
- 有关前端的操作必须放到前端来实现，即tauri原生已经支持的实现，不要重复造轮子


## 工具(tools)使用习惯，重要原则

- 在探索或检索代码库时，优先使用 codegraph 相关工具来探索或检索代码
- 当需要爬取网页数据的时候，你可以使用firecrawl 相关工具来进行爬取
- 技术文档查询时，使用 context7 tools ！
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
单上下文布局：根目录 `CONTEXT.md` + `docs/adr/`。见 `docs/agents/domain.md`。


## 参考
- LangGraph 文档： https://langchain-ai.github.io/langgraph/
- LangChain 文档： https://python.langchain.com/docs/
- DeepAgents 文档：https://docs.langchain.com/oss/python/deepagents
- FastAPI 文档： https://fastapi.tiangolo.com/
- shadcn ui 文档：https://ui.shadcn.com/docs
- tauri 文档参考：https://v2.tauri.app/reference/cli/
- tauri 能力：https://tauri.app/zh-cn/reference/acl/capability/
- tauri配置：https://tauri.app/zh-cn/reference/config/
- tauri快捷键配置：https://tauri.app/zh-cn/reference/javascript/global-shortcut/
- tauri触觉反馈:https://tauri.app/zh-cn/reference/javascript/haptics/
