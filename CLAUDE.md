

# KnowRealm-AI 产品简介

**一句话**：开源的个人学习工作台——把课堂录音、音频、文档、粘贴文本和闪念速记统一"捕获"，自动转化为可编辑、可追溯的学习资产（总结 / 知识点 / 习题 / 复习资料），并提供基于内容的 AI 对话问答。

- **给谁用**：一切学习知识的人（学生、程序员、上班族、终身学习者）；作者自用优先，开源供他人自部署
- **核心闭环**：捕获（录音 / 导入 / 粘贴 / 速记）→ ASR 转写 → AI 总结（人工确认）→ 知识点 / 习题 / Todo → AI 问答
- **长期方向**：从"学习助手"演进为"个人学习大脑"（掌握度 / 遗忘复习 / 自适应学习）

**权威文档（一切问题先查这里，改动以此为准）**：

| 文档 | 管什么 |
|------|--------|
| `docs/KnowRealm-AI-功能需求基线-v2.1.md` | 需求与决策表（#1~#56） |
| `docs/KnowRealm-AI-数据模型-v2.0.md` | 数据模型（42 张表） |
| `docs/技术栈设计与审查-v4.md`（v4.1） | 技术选型与项目结构（§7.1 桌面端 / §7.2 后端） |
| `CONTEXT.md` | 领域术语表（角色≠学习场景、KP≠Concept 等） |

> 文档惯例：评审定稿即升版并**重命名文件**；改版本号须同步全部交叉引用（PRD / 技术栈 / CONTEXT.md / 扩展设计文档头部），历史"变更记录"行是史实、不改动。

## 编码规范（.claude/rules）

写任何代码前必须遵循 `.claude/rules/` 下的编码规范（**正本**；`docs/rules/` 为发布镜像，改动须同步保持一致）。

## DESIGN.md
遵循 DESIGN.md 文件 的ui产品风格设计


## 工具(tools)使用习惯

- 在探索或检索代码库时，优先使用 codegraph 相关工具来探索或检索代码
- 当需要爬取网页数据的时候，你可以使用firecrawl 相关工具来进行爬取
- 当需要操作浏览器的时候，你可以使用playwright 工具来进行操作
- 技术文档查询时，适用context7 tools 即可



## 文档的更新

任何文档的更新不要保存以前过期的任何信息，这会增大误解。

## Agent skills

### Issue tracker

议题以本地 markdown 文件跟踪于 `.scratch/<feature-slug>/`。见 `docs/agents/issue-tracker.md`。

### Triage labels

使用五个默认规范角色标签：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。见 `docs/agents/triage-labels.md`。

### Domain docs

单上下文布局：根目录 `CONTEXT.md` + `docs/adr/`。见 `docs/agents/domain.md`。
