# KnowRealm-AI 产品简介

**一句话**：开源的个人学习工作台——把课堂录音、音频、文档、粘贴文本和闪念速记统一"捕获"，自动转化为可编辑、可追溯的学习资产（总结 / 知识点 / 习题 / 复习资料），并提供基于内容的 AI 对话问答。

- **给谁用**：一切学习知识的人（学生、程序员、上班族、终身学习者）.
- **核心闭环**：捕获（录音 / 导入 / 粘贴 / 速记）→ ASR 转写 → AI 总结（人工确认）→ 知识点 / 习题 / Todo → AI 问答
- **长期方向**：从"学习助手"演进为"个人学习大脑"（掌握度 / 遗忘复习 / 自适应学习）

**权威文档（一切问题先查这里，改动以此为准）**：

| 文档                                     | 管什么                                        |
| ---------------------------------------- | --------------------------------------------- |
| `docs/KnowRealm-AI-功能需求基线-v2.4.md` | 需求与决策表（#1~#58）                        |
| `docs/KnowRealm-AI-数据模型-v2.2.md`     | 数据模型（42 张表）                           |
| `docs/技术栈设计与审查-v4.4.md`          | 技术选型与项目结构（§7.1 桌面端 / §7.2 后端） |
| `CONTEXT.md`                             | 领域术语表（角色≠学习场景、KP≠Concept 等）    |

> 文档惯例：评审定稿即升版并**重命名文件**；改版本号须同步全部交叉引用（PRD / 技术栈 / CONTEXT.md / 扩展设计文档头部），历史"变更记录"行是史实、不改动。


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

## 编码规范（重要）

1. 写任何代码前必须遵循 `.claude/rules/` 下的编码规范（**正本**；`docs/rules/` 为发布镜像，改动须同步保持一致）。任何时候不要更改rules下的文件。

2. 设计或创建对应的桌面端ui时，需要遵循 impeccable skill 的规范要求，以及调用它来设计。
   - 不要重复造轮子，需要搞清楚当前的ui组件是否 可以用 shadcn ui 来实现。并保持设计规范。

3. **git commit  的提交信息使用中文描述**

4. 在测试中产生的任何临时文件，在测试完毕之后都要进行删除

5. **执行编写任务之前，如果该功能是现有代码可以实现的则复用它，复用优先，禁止重复造轮子，保持代码简洁，且职责分明(适用于前端和后端)**

6. 前端样式设计体系遵循如下分层结构和对应职责：

   | 内容                       | 位置                            |
   | -------------------------- | ------------------------------- |
   | 设计令牌（颜色/圆角/间距） | `styles/tokens.css`（`@theme`） |
   | 主题切换（亮/暗语义变量）  | `styles/theme.css`              |
   | 全局 reset / 基础样式      | `styles/globals.css`            |
   | 动画 keyframes             | `styles/animations.css`         |

7. 在涉及到 `langchain `, `langGraph `, `Deep Agents` 编写，设计，搭建时，请参考 `.agents/skills/`  或 `.zcode/skills/` 或  `.claude/skills/ `下有关的skills来进行编写！如有歧义则提出





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


## 文档的更新

任何文档的更新不要保存以前过期的任何信息，这会增大误解。

## Agent skills

### Issue tracker

议题以本地 markdown 文件跟踪于 `.scratch/<feature-slug>/`。见 `docs/agents/issue-tracker.md`。

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
