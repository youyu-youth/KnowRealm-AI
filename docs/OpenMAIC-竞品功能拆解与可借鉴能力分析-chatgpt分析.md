可以。这个项目非常值得 KnowRealm-AI 研究，而且我认为它的参考价值已经不只是“AI 教育应用”，而是已经进化成一个相当完整的 **Agent 驱动内容生产 + 多 Agent 教学运行时 + 交互式学习内容引擎**。

我结合了 OpenMAIC 当前 `main`、README、CHANGELOG、核心 `director-graph.ts`、技术依赖，以及你现在的 **KnowRealm-AI 功能需求基线 v2.3** 做了对照分析。OpenMAIC 最新的 **v1.0.0 发布于 2026-08-27**，仅几天前，因此下面以这个版本为主。([GitHub](https://github.com/THU-MAIC/OpenMAIC))

# OpenMAIC 深度分析与 KnowRealm-AI 借鉴报告

## 一、先给结论

如果用一句话概括 OpenMAIC：

> **它正在从“一键生成 AI 课堂”，进化成“AI Agent 自动规划、生成、编辑并运行整个学习体验的课程操作系统”。**

而 KnowRealm-AI 当前的方向是：

> **捕获真实学习资料 → 形成可追溯学习资产 → 长期维护用户掌握度 → 决定下一步学什么。**

你现在 PRD 明确把 KnowRealm-AI 分成 **个人学习工作台 → AI Personal Learning Brain → AI Learning OS** 三阶段，并强调五级捕获、Record、Knowledge Point、Concept、Learning Evidence、Mastery、Autopilot 等长期学习状态。

所以两者实际上非常互补：

| OpenMAIC 强项                     | KnowRealm-AI 强项                |
| --------------------------------- | -------------------------------- |
| Teach / 教学呈现                  | Learn / 学习闭环                 |
| 自动生成课程                      | 从真实课堂和资料沉淀知识         |
| Slides / Quiz / Interactive / PBL | Record / KP / Concept / Evidence |
| 多 Agent 教学                     | 长期学习状态建模                 |
| AI Teacher 主动演示               | AI Learning Brain 主动诊断       |
| Agent Workbench                   | Learning Workbench               |
| Course DSL / Scene DSL            | 学习事实与知识模型               |
| 课程一次性体验                    | 长期跨课程记忆与掌握度           |

### 我最建议 KnowRealm-AI 学习的，不是“AI 老师头像”或者“课堂 UI”。

真正值得借鉴的是这 **8 个设计思想**：

1. **Agent Workbench**
2. **Durable Agent Runtime**
3. **Skill System**
4. **Stage / Scene DSL**
5. **Action Engine**
6. **结构化 AI 编辑 / Patch**
7. **Interactive Learning Scene**
8. **Provider-neutral Capability System**

其中 **1、2、4、5、6** 对 KnowRealm-AI 的长期产品形态尤其重要。

------

# 二、OpenMAIC 到底是什么

OpenMAIC 的完整名字是：

**Open Multi-Agent Interactive Classroom**

它不是简单的：

> PDF → 总结

也不是：

> ChatGPT + PPT

而是：

```text
主题 / PDF / Word / PPT / 音频 / 视频
                ↓
           AI 课程规划
                ↓
          Course / Stage
                ↓
    ┌───────────┼───────────┐
    ↓           ↓           ↓
   Slide       Quiz     Interactive
                            ↓
                 Simulation / Game
                 MindMap / Code / 3D
    └───────────┬───────────┘
                ↓
        Multi-Agent Classroom
                ↓
      Teacher / Peer / Student
                ↓
          Action Engine
                ↓
   Speech / Whiteboard / Pointer
   Highlight / Interaction / Q&A
```

官方描述明确表示，它可以从任意主题或材料生成 slides、quiz、interactive simulations 和 PBL 内容，再由 AI 教师和 AI 同学进行讲授、讨论、绘制白板和实时互动。([GitHub](https://github.com/THU-MAIC/OpenMAIC))

目前 GitHub 页面显示大约 **26k Stars、4.7k Forks**，MIT License，项目成熟度已经明显高于普通 Demo。([GitHub](https://github.com/THU-MAIC/OpenMAIC))

------

# 三、OpenMAIC 当前主要功能全景

我把它归为 **10 大系统**。

## 1. 一键课程生成

最基础也是最早期的能力：

```text
用户输入主题 / 上传资料
        ↓
Outline Generation
        ↓
用户可编辑 Outline
        ↓
Scene Generation
        ↓
完整课程
```

目前材料输入已经支持：

- PDF
- Word
- PowerPoint
- Spreadsheet
- TXT
- Image
- Audio
- Video

其经典生成链路明确采用：

> Outline → Scenes

两阶段生成。([GitHub](https://github.com/THU-MAIC/OpenMAIC))

### 这个设计值得 KnowRealm 借鉴

KnowRealm 目前是：

```text
Transcript
 ↓
Summary
 ↓
Knowledge Point
 ↓
Quiz
 ↓
Todo / Review
```

可以逐渐演进成：

```text
真实学习资料
      ↓
Knowledge Outline
      ↓
用户确认
      ↓
Learning Assets Generation
      ↓
KP / Quiz / MindMap / Explain / Review
```

也就是说：

### 不要让 LLM 一次生成所有东西。

可以借 OpenMAIC 的方式形成：

> **Plan → Confirm → Generate**

它和你现在 Summary HITL 的产品原则非常一致。

------

# 四、最重要的新功能：Agent Workbench

这是 OpenMAIC v1.0.0 最大的改变。

以前：

```text
Prompt
  ↓
自动生成课程
  ↓
完成
```

现在：

```text
用户
 ↓
Agent
 ↓
规划课程
 ↓
调用工具
 ↓
创建页面
 ↓
修改页面
 ↓
导入资料
 ↓
生成媒体
 ↓
检查结果
 ↓
用户继续告诉 Agent 修改
```

已经非常接近：

> Cursor / Claude Code / ChatGPT Work

只是它操作的是 **Course**，而不是代码。

官方称之为：

**Agent Workbench / Pro Mode**

工作区大致由：

```text
┌──────────────┬──────────────────┬────────────────────┐
│ Folder       │ Agent Chat       │ Course / Classroom │
│ Conversations│                  │                    │
│              │  用户 ↔ Agent    │ Slides             │
│ Course       │                  │ Quiz               │
│              │ Tool calls       │ Interactive        │
│              │                  │ Editor             │
└──────────────┴──────────────────┴────────────────────┘
```

组成。

Agent 可以：

| 类别     | 能力                   |
| -------- | ---------------------- |
| Plan     | 规划多节课程           |
| Organize | 创建 Course / Folder   |
| Build    | 创建页面               |
| Edit     | 删除、插入、复制、排序 |
| Material | 上传、读取、搜索材料   |
| Web      | 搜索 Web / Fetch URL   |
| Media    | 生成图片、视频、语音   |
| PPT      | Import PPTX            |
| Voice    | 管理 AI Agent 声音     |
| Agent    | 配置课堂 Agent roster  |

这些都不是直接操作一个大 JSON，而是通过 **validated tools** 操作。([GitHub](https://github.com/THU-MAIC/OpenMAIC))

------

# 五、这对 KnowRealm-AI 特别重要

你当前的产品定义已经叫：

> **Learning Workbench**

并且规划：

```text
顶部快速捕获
左侧：
今日
收件箱
课程
资产库
学习画像
```



我认为可以吸收 OpenMAIC 的 Workbench 思路，把 KnowRealm 最终形态进一步明确成：

```text
┌─────────────┬─────────────────────┬──────────────────────┐
│ Knowledge   │ AI Learning Agent   │ Learning Workspace   │
│ Spaces      │                     │                      │
│             │ 对话                │ Transcript           │
│ Today       │ Thinking            │ Summary              │
│ Inbox       │ Actions             │ Knowledge Points     │
│ Courses     │ Tools               │ Quiz                 │
│ Assets      │ Sources             │ Concept Graph        │
│             │                     │ Review               │
└─────────────┴─────────────────────┴──────────────────────┘
```

这甚至可以成为 KnowRealm-AI 长期 UI 的核心布局。

不是：

> 打开一个 Chat 页面。

而是：

> **AI 与真实学习资产共存于一个 Workbench 中。**

这一点我认为非常值得吸收。

------

# 六、Durable Agent Runtime：非常值得研究

OpenMAIC v1.0.0 第二个很重要的东西不是 UI，而是：

> **Durable Agent Runtime**

Agent Session 支持：

- server-backed session
- resume
- cancel
- follow-up steering
- crash recovery
- heartbeat
- lease
- replayable event transcript
- tool timeout
- cancel fencing

即使 Worker 重启，Agent 任务仍可以继续恢复。([GitHub](https://github.com/THU-MAIC/OpenMAIC))

简单理解：

```text
用户：
帮我根据这几个文档做一门完整课程

Agent:
分析文件
  ↓
规划
  ↓
生成第1页
  ↓
生成第2页
  ↓
[程序崩了]
  ↓
重新启动
  ↓
继续第3页
```

而不是：

```text
程序挂了
↓
整个 Agent Session 消失
```

------

# 七、这和 KnowRealm 的架构高度相关

你的 PRD 已经明确：

```text
业务事实
SQLite knowrealm.db

Agent Runtime
LangGraph checkpoint / langgraph.db
```

而且明确规定：

> LangGraph 只用于需要状态、暂停恢复、HITL 或 Agent 决策的流程，禁止构建超级 Graph。

所以：

### 不建议照搬 OpenMAIC 的 PostgreSQL Agent Runtime。

但非常建议学习它的 **运行语义**：

```text
AgentRun

CREATED
 ↓
RUNNING
 ↓
WAITING_USER
 ↓
RUNNING
 ↓
COMPLETED

同时支持：

PAUSED
CANCELLED
FAILED
INTERRUPTED
```

将来可以形成：

```text
KnowRealm Agent Runtime
        │
        ├─ SummaryGraph
        ├─ TutorGraph
        ├─ TeachBackGraph
        ├─ MisconceptionGraph
        └─ AutopilotGraph
```

每个 Graph 独立。

这正好不违反你的“禁止 Super Graph”原则。

------

# 八、Multi-Agent Classroom

这是 OpenMAIC 最有辨识度的功能。

不是一个 Agent 一直说话，而是：

```text
                Director
                   │
       ┌───────────┼───────────┐
       ↓           ↓           ↓
    Teacher      Expert      Student
       ↓           ↓           ↓
            Discussion
```

OpenMAIC 当前有：

- Classroom Discussion
- Roundtable Debate
- Q&A
- AI Whiteboard

Agent 可以主动发起讨论，用户可以随时加入，甚至会被 AI Agent 点名。([GitHub](https://github.com/THU-MAIC/OpenMAIC))

其 DSL 中 Agent 已经是一等对象，例如：

```text
GeneratedAgentConfig

id
name
role
persona
avatar
color
priority
```

以及 MultiAgentConfig。([GitHub](https://github.com/THU-MAIC/OpenMAIC/issues/815?utm_source=chatgpt.com))

------

# 九、它的 Multi-Agent 并不是简单 Group Chat

这一点非常值得学习。

核心存在一个：

> **Director**

实际实现用了 LangGraph。

其当前拓扑非常克制：

```text
START
  ↓
Director
  │
  ├── END
  │
  └── Agent Generate
          ↓
         END
```

也就是说：

### Server 每次只决定一个 Agent 行为。

多轮讨论实际上由客户端连续请求形成。

并不是：

```text
while true:
   Agent1
   Agent2
   Agent3
   Agent1
   ...
```

这种失控式 AutoGen。

Director 根据：

- 当前 conversation
- agent list
- previous responses
- user profile
- whiteboard ledger
- discussion context

决定：

```text
NEXT_AGENT
USER
END
```

并且单 Agent 情况甚至不调用 Director LLM，直接通过程序逻辑处理，以减少成本。([GitHub](https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/orchestration/director-graph.ts?utm_source=chatgpt.com))

这个实现非常值得参考。

------

# 十、KnowRealm 要不要做 Multi-Agent？

我的建议是：

## 可以，但不要照搬“AI 教室”。

KnowRealm 更适合的是：

```text
Learning Agent
    │
    ├─ Tutor
    ├─ Socratic Coach
    ├─ Examiner
    ├─ Explainer
    └─ Reviewer
```

例如一个知识点：

> 什么是 TCP 三次握手？

可以出现：

### Tutor

解释概念。

### Socratic Coach

不直接告诉答案，逐步追问。

### Examiner

出题验证。

### Reviewer

检查回答中是否存在 misconception。

### Learning Brain

最终根据真实 Evidence 更新 Mastery。

这和 OpenMAIC：

> Teacher + classmates

相比，更符合 KnowRealm：

> **个人认知系统**

的定位。

------

# 十一、但不要默认启动 5 个 Agent

这是一个很重要的产品判断。

OpenMAIC 的多 Agent 非常有表现力。

但对 KnowRealm：

```text
多 Agent
→ 更多 Token
→ 更多等待时间
→ 更多噪音
→ 更难解释 Learning Evidence
```

因此建议：

```text
默认：
Single Agent

需要时：
Multi-Agent
```

比如：

### 普通总结

1 Agent。

### 普通问答

1 Agent。

### Misconception Verification

可以 2 Agent。

```text
Tutor
vs
Reviewer
```

### Debate / 复杂概念

允许用户启动：

> 多视角讨论

而不是每一个问题都 Multi-Agent。

------

# 十二、OpenMAIC 的 Action Engine 是一个被低估的设计

它内部并不是让 Agent 只输出 Markdown。

Agent 可以执行：

> Action

官方架构描述其 Action Engine 可以执行 **28+ Action Types**。([GitHub](https://github.com/THU-MAIC/OpenMAIC))

例如：

```text
Speak
DrawText
DrawShape
DrawChart
Highlight
Spotlight
LaserPointer
Whiteboard
...
```

所以 Agent 输出：

```text
“这里注意”
```

同时可以真正：

```text
spotlight(element_17)
```

而不只是写：

> 请注意右边的图。

------

# 十三、这个机制我非常建议 KnowRealm 借鉴

可以设计：

# Learning Action Protocol

让 KnowRealm Agent 不只是：

```text
AI:
你之前这里没听懂。
```

而是可以调用：

```text
open_transcript(record_id)

jump_to_source(anchor_id)

highlight_transcript(segment_id)

open_knowledge_point(kp_id)

show_concept(concept_id)

start_quiz(quiz_id)

compare_sources(a, b)

open_audio(timestamp)

create_draft_note(...)

suggest_review(concept_id)
```

于是用户问：

> 为什么这里说 TCP 是可靠的？

Agent 可以：

```text
1. 跳到课堂录音 01:12:34
2. Highlight 对应 Transcript
3. 打开 TCP Knowledge Point
4. 画三次握手示意图
5. 最后给一道 Recall Quiz
```

这会比普通 RAG Chat 高一个产品层级。

------

# 十四、尤其符合 KnowRealm 的 Source Anchor

KnowRealm 已经有一个非常好的概念：

> Source Anchor

也就是：

```text
AI结论
   ↓
原始音频
文档页
用户笔记
```



因此：

```text
Agent Action
      +
Source Anchor
```

可以成为 KnowRealm 一个非常强的差异化能力。

例如：

> “你上周其实讲过这个问题。”

然后自动：

**跳回原声 → 定位 Transcript → Highlight → 播放音频。**

我认为这个体验值得列入长期产品重点。

------

# 十五、Deep Interactive Mode

OpenMAIC 的另一个核心功能是：

**Deep Interactive Mode**

它不满足于：

```text
PPT + Chat
```

而是生成真正可以操作的学习 UI。

目前支持 5 类：

| 类型               | 功能       |
| ------------------ | ---------- |
| 3D Visualization   | 三维模型   |
| Simulation         | 模拟实验   |
| Game               | 学习小游戏 |
| Mind Map           | 知识图     |
| Online Programming | 在线编程   |

([GitHub](https://github.com/THU-MAIC/OpenMAIC))

更重要的是：

> AI Teacher 可以操作这些 UI。

例如：

```text
Teacher:
把速度改成 20m/s，看看发生什么。

↓
AI 自动操作 slider

↓
模拟器变化
```

而不仅仅是生成网页让用户自己玩。([GitHub](https://github.com/THU-MAIC/OpenMAIC))

------

# 十六、KnowRealm 可以选择性吸收

我不建议一开始做：

- 3D
- 游戏
- 通用 Simulation

工程量太大。

但非常适合逐步加入：

### 第一优先级

```text
Mind Map
Concept Map
Timeline
Diagram
Code Runner
```

### 第二优先级

```text
Interactive Formula
Algorithm Visualizer
Flashcard
Sorting / Matching
```

### 第三优先级

```text
Simulation
3D
Game
```

这样 KnowRealm 从：

> AI 总结工具

逐渐变成：

> **AI 主动生成最适合当前 Concept 的学习界面。**

------

# 十七、PBL：Project Based Learning

OpenMAIC 还有一个值得注意的功能：

> Project-Based Learning

用户不是单纯“上课”，而是：

```text
选择 Role
   ↓
完成 Project
   ↓
Milestone
   ↓
Deliverable
   ↓
与 AI Agent 合作
```

README 明确描述 PBL 允许学习者选择角色，与 AI Agent 一起完成具有 milestones 和 deliverables 的结构化项目。([GitHub](https://github.com/THU-MAIC/OpenMAIC))

项目另外还有一个独立的 **OpenMAIC-Project**：

```text
Chat
Code Editor
File Tree
Terminal
Browser
Docker Sandbox
Multi Agent
Project Planner
```

形成完整项目式学习环境。([GitHub](https://github.com/THU-MAIC/OpenMAIC-Project/blob/main/README.md?utm_source=chatgpt.com))

------

# 十八、KnowRealm 怎么借 PBL

不建议直接加入：

> Project 页面。

而是可以形成未来的：

# Learning Mission

例如：

```text
目标：
学会 FastAPI

Mission 1
构建 REST API

Mission 2
添加数据库

Mission 3
实现认证

Mission 4
编写测试
```

每个 Mission 自动对应：

```text
Concept
Evidence
Mastery
```

于是：

```text
Project Learning
       ↓
Learning Events
       ↓
Learning Evidence
       ↓
Mastery
```

这比 OpenMAIC 本身甚至更完整。

------

# 十九、Skill System：我认为非常值得 KnowRealm 研究

OpenMAIC v1.0.0 已经加入：

> **20 个 Built-in Skills**

涉及：

- curriculum planning
- deep research
- lecture
- workshop
- interactive
- vocational
- PPT import
- slide editing
- style reuse

并允许：

> User-authored Skills

用户 Skills 按 owner 存储，可以创建、读取和修改。([GitHub](https://github.com/THU-MAIC/OpenMAIC))

CHANGELOG 还特别提到了：

- Feynman
- Spiral Curriculum

等教学方法被做成 Skill。([GitHub](https://github.com/THU-MAIC/OpenMAIC/blob/main/CHANGELOG.md))

------

# 二十、这个设计几乎可以直接转化成 KnowRealm 的 Learning Skills

例如：

```text
/skills

feynman
socratic
exam-prep
deep-reading
paper-reading
coding-interview
memorization
teach-back
concept-map
active-recall
spaced-review
```

用户可以说：

> 用费曼法教我这个知识点。

Agent 加载：

```text
skills/feynman/SKILL.md
```

然后执行对应教学策略。

这样：

### Prompt 不会全部堆进一个 System Prompt。

而是：

```text
Learning Agent
      ↓
选择 Skill
      ↓
动态加载
      ↓
执行
```

我认为这很适合 KnowRealm。

------

# 二十一、甚至可以形成 Skill Marketplace，但不必 V1 做

长期可以：

```text
Learning Skills
├── 官方
├── 用户自建
├── 社区
└── Course-specific
```

例如：

```text
考研数学强化
LeetCode Interview
JLPT N1
IELTS Writing
医学考试 Recall
论文精读
```

不过这更适合 P4+。

------

# 二十二、Course / Scene DSL：非常重要

OpenMAIC 后来把自己的内容模型抽象成独立 npm packages：

```text
@openmaic/dsl
@openmaic/renderer
@openmaic/editor
@openmaic/importer
@openmaic/generation
@openmaic/storage
```

([GitHub](https://github.com/THU-MAIC/OpenMAIC))

它实际上形成了：

```text
Course
 ↓
Stage
 ↓
Scene
 ↓
Elements
 ↓
Actions
```

然后：

```text
DSL
 ↓
Renderer
 ↓
Editor
 ↓
Exporter
```

这是非常成熟的产品架构。

------

# 二十三、KnowRealm 以后也建议拥有自己的 Learning Artifact DSL

不一定现在马上实现。

长期可以形成：

```text
LearningArtifact
     │
     ├─ Explanation
     ├─ KnowledgePoint
     ├─ Quiz
     ├─ Flashcard
     ├─ Diagram
     ├─ CodeExample
     ├─ ConceptMap
     ├─ Timeline
     └─ Interactive
```

例如：

```json
{
  "type": "concept_map",
  "concept": "TCP",
  "nodes": [],
  "edges": [],
  "sources": []
}
```

那么：

```text
LLM
 ↓
Learning Artifact DSL
 ↓
Validator
 ↓
Renderer
```

而不是：

```text
LLM
 ↓
任意 HTML
```

这会显著提升：

- 稳定性
- 可编辑性
- 可测试性
- 可版本迁移
- 可导出
- Agent 修改能力

------

# 二十四、Edit with AI 的实现也值得重点抄思路

OpenMAIC 支持：

> Edit with AI

用户可以：

```text
“把标题放大”
“这一页更简洁”
“把图片换成流程图”
```

AI 不直接重新生成整个 Course。

后来升级成：

```text
Natural Language
      ↓
Typed EditIntent
      ↓
Validated JSON Patch
      ↓
Document
```

([GitHub](https://github.com/THU-MAIC/OpenMAIC/blob/main/CHANGELOG.md))

这是非常正确的工程方式。

------

# 二十五、KnowRealm 也应该采用类似思想

例如用户修改 Summary：

不要：

```text
AI重新输出整个Summary
↓
覆盖旧数据
```

更好的长期方式：

```text
User:
把第二点拆成两部分

AI
 ↓
Structured Edit
 ↓
Patch
 ↓
Validator
 ↓
新 version
```

或者 Concept：

```text
rename_concept
merge_suggestion
split_concept
add_source
remove_source
```

尤其要注意：

### Agent 应该提交“操作”，而不是随意改数据库。

这和你现在 KnowRealm：

> 本地业务事实是唯一权威数据源

的架构思想高度兼容。

------

# 二十六、Materials System 也值得参考

OpenMAIC v1.0 对 Material 做得越来越正式。

已经有：

```text
Original Material
       ↓
Asset
       ↓
Extraction
       ↓
Derived Asset
       ↓
Text / Images / Media
       ↓
Agent Search
```

并且包含：

- lineage
- extraction cache
- asset manifest
- media extraction
- ffmpeg/ffprobe
- material search

([GitHub](https://github.com/THU-MAIC/OpenMAIC/blob/main/CHANGELOG.md))

这和 KnowRealm：

```text
Record
 ↓
record_files
 ↓
Transcript
 ↓
Source Anchor
```

相似。

------

# 二十七、但这里 KnowRealm 实际上设计得比 OpenMAIC 更严谨

你已经把：

```text
原文件
Transcript
Segment
Source Anchor
AI Summary
Knowledge Point
Concept
Evidence
```

严格区分。



所以：

### 数据模型不要照抄 OpenMAIC。

只借它：

- asset lineage
- derived asset cache
- material manifest
- extraction lifecycle

就可以。

------

# 二十八、Whiteboard

OpenMAIC 的 Whiteboard 并不是普通用户白板。

AI Agent 也能写。

包括：

```text
Text
Formula
Shape
Chart
Code
Diagram
```

并且 Action Engine 可以控制绘制过程。

官方甚至专门做了：

> Whiteboard Layout Eval

用来检测：

- overlap
- line through bbox
- canvas clipping

并把布局错误反馈给模型。

仅 Prompt + 几何检测器，其自己的评测里整体质量从约 5.4 提高到 6.1，overlap 指标从约 6.3 提高到 8.1。([GitHub](https://github.com/THU-MAIC/OpenMAIC/blob/main/CHANGELOG.md))

------

# 二十九、这说明 OpenMAIC 一个特别值得学的地方

它不只是：

> 做功能。

它开始：

> **给 Agent 能力建立 Eval。**

目前项目里可以看到：

```text
eval/pbl-v2-planner
eval/whiteboard-layout
eval/outline-language
eval/orchestration
```

([GitHub](https://github.com/THU-MAIC/OpenMAIC/blob/main/package.json?utm_source=chatgpt.com))

这对 KnowRealm 很重要。

你以后可以建立：

```text
eval/
├─ summary-groundedness
├─ source-anchor
├─ knowledge-point
├─ quiz-quality
├─ misconception
├─ tutor-answer
├─ concept-mapping
└─ autopilot-decision
```

特别应该测：

```text
是否引用真实资料
是否 hallucination
Source Anchor 是否正确
Quiz 是否真的考 Concept
Evidence 是否错误影响 Mastery
```

------

# 三十、Provider-neutral 架构：KnowRealm 强烈建议吸收

OpenMAIC 支持非常多模型：

- OpenAI
- Anthropic
- Gemini
- Azure
- Amazon Bedrock
- Ollama
- OpenRouter
- GLM
- MiniMax
- Kimi
- Grok
- 等等

并且：

```text
LLM
Image
Video
TTS
ASR
Search
Storage
```

全部逐渐抽象为 capability。

系统会：

```text
discover capability
resolve provider
validate config
disable unavailable function
```

而不是业务代码直接写：

```text
if openai...
if anthropic...
if glm...
```

v1.0 甚至强调：

> 无法 resolve 的模型必须明确报错，而不是偷偷猜 Provider。([GitHub](https://github.com/THU-MAIC/OpenMAIC))

------

# 三十一、这与 KnowRealm 当前 Provider Card 非常契合

你的 PRD 已经是：

```text
DashScope preset
+
Custom OpenAI compatible endpoint
+
Tencent ASR
```

且无 key 时采用：

> 功能级降级 + 健康检查。

建议进一步抽象：

```text
CapabilityRegistry

LLM
Embedding
ASR
WebSearch
Image
TTS
```

每个 capability：

```text
AVAILABLE
MISCONFIGURED
MISSING_KEY
OFFLINE
DISABLED
```

然后 UI 自己决定：

```text
总结按钮 Disabled
原因：LLM 未配置
```

这可以直接借 OpenMAIC 的 Provider-neutral 思想。

------

# 三十二、技术栈

OpenMAIC 当前核心技术大致为：

```text
Next.js 16
React 19
TypeScript

LangGraph
Vercel AI SDK
assistant-ui
CopilotKit / Pi Agent

Zustand

shadcn
Radix UI

PostgreSQL
Dexie / browser storage

KaTeX
ECharts
XYFlow

ProseMirror

Playwright
Vitest
```

另外还集成 MCP SDK。([GitHub](https://github.com/THU-MAIC/OpenMAIC/blob/main/package.json?utm_source=chatgpt.com))

架构核心：

```text
Generation Pipeline
Agent Runtime
Multi-Agent Orchestration
Playback Engine
Action Engine
Persistence
```

([GitHub](https://github.com/THU-MAIC/OpenMAIC))

------

# 三十三、与 KnowRealm 技术架构的关系

KnowRealm 当前是：

```text
Tauri
React / TypeScript
       ↓
localhost
       ↓
FastAPI Python Sidecar
       ↓
SQLite
       ↓
LangGraph
```



### 我不建议为了 OpenMAIC 改成 Next.js。

你的 Desktop Local-first 架构更符合 KnowRealm。

真正值得吸收的是：

```text
OpenMAIC
LangGraph Orchestration

        ↓思想迁移

KnowRealm
Python LangGraph
```

以及：

```text
OpenMAIC Action Engine
      ↓

KnowRealm Learning Action Engine
```

------

# 三十四、存储层不要照搬

OpenMAIC 已经逐步走向：

```text
Browser
or
HTTP
or
PostgreSQL
or
S3
```

它需要兼顾 Hosted。

([GitHub](https://github.com/THU-MAIC/OpenMAIC))

KnowRealm 的核心原则却是：

> **Local First**

```text
SQLite
+
files/
```

是唯一业务事实源。

因此 OpenMAIC 的：

- PostgreSQL multi-user
- owner scoped stage
- S3 asset
- server persistence

### 不应该复制。

否则会重新把 KnowRealm 拉回你已经主动放弃的复杂云端架构。

------

# 三十五、账号体系同样不要照搬

OpenMAIC 现在已经出现：

```text
owner
ownership
owner-scoped folder
stage ownership
```

主要为了 Hosted / Server Workbench。([GitHub](https://github.com/THU-MAIC/OpenMAIC))

KnowRealm 当前 V1：

> 无登录、无认证、无邮件、本地单用户。



所以 OpenMAIC 的 owner/account 层暂时没有必要。

------

# 三十六、安全方面却值得学习

OpenMAIC 在 Web Fetch / Material Fetch 上非常重视 SSRF。

包括：

- URL trust gate
- 禁止 private network
- redirect 防护
- DNS rebinding 防护
- credentials 不发送给 browser

CHANGELOG 多次记录 SSRF hardening。([GitHub](https://github.com/THU-MAIC/OpenMAIC/blob/main/CHANGELOG.md))

这对 KnowRealm P2 的：

```text
网页剪藏
Web Search
URL Fetch
```

非常重要。

建议到时候直接建立：

```text
URLTrustPolicy
```

统一处理，而不是每个 Fetch 功能自己实现一次。

------

# 三十七、OpenMAIC UI 设计也值得参考

它已经逐渐从：

```text
Home
→ Generate
→ Classroom
```

演化成：

```text
Workbench

Folders
Conversations

Agent Chat

Course Tabs

Editor
```

这其实已经越来越像 Cursor / ChatGPT Work。

一张当前项目展示中的界面可以看出课堂主体、Quiz 和 Agent 对话是同时存在的：

KnowRealm 可以借的是：

> **内容永远是主角，Chat 是辅助操作层。**

不要变成：

```text
80% Chat
20% Knowledge
```

而应该：

```text
Knowledge / Learning Surface
+
Agent
```

------

# 三十八、OpenMAIC 与 KnowRealm 功能对应关系

这是我认为最重要的一张表。

| OpenMAIC          | KnowRealm 对应                      | 借鉴价值 |
| ----------------- | ----------------------------------- | -------- |
| Agent Workbench   | Learning Workbench                  | ★★★★★    |
| Durable Session   | LangGraph Checkpoint / Agent Run    | ★★★★★    |
| Course Tools      | Learning Tools                      | ★★★★★    |
| Action Engine     | Learning Action Engine              | ★★★★★    |
| Stage/Scene DSL   | Learning Artifact DSL               | ★★★★★    |
| Edit with AI      | Summary/KP/Concept structured patch | ★★★★★    |
| Skill System      | Learning Skills                     | ★★★★★    |
| Material Pipeline | Record/File/Transcript              | ★★★★☆    |
| Agent Roster      | Tutor/Examiner/Coach                | ★★★★☆    |
| Director Agent    | Multi-Agent Router                  | ★★★★☆    |
| Deep Interactive  | Interactive Learning Artifact       | ★★★★☆    |
| Mind Map          | Concept Map                         | ★★★★★    |
| Online Coding     | Programming Learning Mode           | ★★★★☆    |
| PBL               | Learning Mission                    | ★★★★☆    |
| Quiz              | Quiz + Evidence                     | ★★★★☆    |
| Whiteboard        | AI Explain Canvas                   | ★★★★☆    |
| TTS/ASR           | 已有 ASR，可扩 TTS                  | ★★★☆☆    |
| Web Search        | Chat Tool                           | ★★★★☆    |
| PPTX Import       | 学习材料导入                        | ★★☆☆☆    |
| PPTX Export       | Study Pack                          | ★★☆☆☆    |
| MP4 Export        | 视频课程                            | ★☆☆☆☆    |
| PostgreSQL        | SQLite                              | 不建议   |
| S3                | files/                              | 不建议   |
| Hosted account    | 本地 Profile                        | 不建议   |

------

# 三十九、我建议加入 KnowRealm PRD 的功能

如果要真正把调研成果转化成需求，我建议新增 **6 个中长期模块**。

## F1 — Learning Agent Workbench

建议定义：

> 在 Record / Course 页面提供 AI Workbench，使 AI 能在对话过程中读取、定位、展示和操作当前学习资产，而不是把 AI Chat 作为独立信息孤岛。

页面：

```text
Knowledge Navigation
       │
Agent Chat
       │
Learning Surface
```

优先级：

**P2~P3**

------

## F2 — Learning Action Protocol

统一 Agent 可执行动作：

```text
source.open
source.jump
source.highlight

record.open
transcript.jump

knowledge.open
knowledge.create_draft

concept.open

quiz.start
quiz.explain

review.suggest

ui.spotlight
ui.diagram
```

所有动作：

```text
LLM
 ↓
Schema
 ↓
Validator
 ↓
Permission
 ↓
Execute
```

而不是 LLM 直接操纵数据库。

优先级：

**P2~P3**

------

## F3 — Learning Skill System

定义：

```text
Skill
id
name
description
instructions
tools
version
```

初始官方 Skill：

```text
Feynman
Socratic
Teach Back
Active Recall
Exam Prep
Paper Reading
Code Learning
Concept Mapping
```

优先级：

**P3**

------

## F4 — Learning Artifact DSL

统一：

```text
Explanation
Quiz
Flashcard
Diagram
ConceptMap
Timeline
CodeExample
Interactive
```

形成：

```text
Generator
 ↓
DSL
 ↓
Validator
 ↓
Renderer
 ↓
Editor
```

优先级：

**P3**

------

## F5 — Interactive Learning

第一阶段仅：

```text
Concept Map
Mind Map
Diagram
Timeline
Code Runner
```

然后再考虑：

```text
Simulation
Game
3D
```

优先级：

**P3~P5**

------

## F6 — Multi-Agent Learning Mode

不要做“AI 同学”。

建议做：

```text
Tutor
Examiner
Socratic Coach
Reviewer
```

Director 根据任务决定角色。

仅在：

```text
TeachBack
Misconception Verification
Deep Discussion
```

等场景开启。

优先级：

**P4+**

------

# 四十、按投入产出比，我给出的实施排序

如果只能从 OpenMAIC 学 5 个东西，我建议这个顺序：

| 排名  | 功能                       | 推荐   |
| ----- | -------------------------- | ------ |
| **1** | Learning Action Protocol   | 🔥 强烈 |
| **2** | Agent Workbench            | 🔥 强烈 |
| **3** | Structured AI Edit / Patch | 🔥 强烈 |
| **4** | Skill System               | 🔥 强烈 |
| **5** | Learning Artifact DSL      | 🔥 强烈 |
| 6     | Durable Agent Runtime      | 高     |
| 7     | Mind Map / Concept Map     | 高     |
| 8     | Multi-Agent Director       | 中高   |
| 9     | PBL / Learning Mission     | 中     |
| 10    | 3D / Simulation / Game     | 后期   |

------

# 四十一、为什么我把 Action Engine 排第一

因为它会改变 KnowRealm 的产品级别。

现在大量 AI 学习产品是：

```text
资料
 ↓
RAG
 ↓
Chat
```

KnowRealm 未来可以是：

```text
资料
 ↓
Learning Brain
 ↓
Reasoning
 ↓
Action
 ↓
真实学习资产
 ↓
Evidence
 ↓
Mastery
```

例如：

```text
用户：
这个地方我还是没懂。

Learning Brain：
发现 Concept X Mastery = 0.42
发现两次 Quiz 失败
发现 Record #34 用户标记 ❓
            ↓
调用 Source Anchor
            ↓
打开 34:21 原始课堂录音
            ↓
高亮 Transcript
            ↓
启动 Socratic Skill
            ↓
展示 Diagram
            ↓
问一道 Recall
            ↓
产生 Learning Event
            ↓
Evidence
            ↓
重新计算 Mastery
```

这才真正接近你 PRD 里面定义的：

> **Observe → Understand → Diagnose → Decide → Teach → Verify → Update**



而 OpenMAIC 的 Action Engine 已经证明：

> Agent 不必局限于 Chat。

------

# 四十二、哪些部分千万不要照搬

OpenMAIC 虽然优秀，但有几个地方并不适合 KnowRealm。

### 不建议 1：默认 Multi-Agent

会增加 token、延迟和噪音。

### 不建议 2：把“课程生成”作为核心

KnowRealm 的核心应该始终是：

> **用户真实学习经历。**

而不是 AI 生成出来的一门课。

### 不建议 3：Postgres / S3 / Server-first

破坏 Local-first。

### 不建议 4：过早做 3D / Game / Simulation

ROI 很低。

### 不建议 5：AI 自动修改 Learning Facts

特别是：

```text
Mastery
Evidence
Misconception
Concept
```

必须继续遵守 KnowRealm 当前的数据红线。

### 不建议 6：超级 Agent Graph

OpenMAIC 的 Workbench Agent 本身可以非常综合，但 KnowRealm 当前规定：

> Summary / Tutor / TeachBack / Autopilot / Misconception Verification 独立 Graph。

我认为这个设计应该保留。

------

# 四十三、最终产品定位上的启发

OpenMAIC 当前正在做：

> **AI Course OS**

KnowRealm 不应该跟它正面做一样的东西。

KnowRealm 更有机会成为：

# AI Personal Learning OS

也就是：

```text
                OpenMAIC
                   │
            AI generates course
                   │
                  Teach


用户真实世界
课堂 / 文档 / 音频 / 网页
            │
            ▼
        KnowRealm
            │
         Observe
            │
         Understand
            │
         Remember
            │
         Diagnose
            │
          Decide
            │
          Teach
            │
          Verify
            │
          Update
            │
        Learning Brain
```

所以我对这次调研最大的结论不是：

> “KnowRealm 应该加入 AI 老师。”

而是：

> **KnowRealm 应该学习 OpenMAIC 如何把 Agent 从“聊天机器人”升级成“能够通过 Tool + Skill + Action + DSL 操作整个应用的智能运行时”。**

这是 OpenMAIC 目前最有价值的地方。

------

# 四十四、给 KnowRealm 的推荐架构形态

结合目前 PRD，我会倾向于未来演进成：

```text
┌──────────────────────────────────────────┐
│             KnowRealm Desktop            │
│                                          │
│  Capture / Inbox / Course / Today        │
│                  │                       │
│                  ▼                       │
│            Learning Workbench            │
│                                          │
│ ┌──────────┐ ┌───────────┐ ┌──────────┐ │
│ │Navigation│ │Learning   │ │AI Agent  │ │
│ │          │ │Surface    │ │          │ │
│ │Course    │ │Transcript │ │Chat      │ │
│ │Record    │ │Summary    │ │Actions   │ │
│ │Concept   │ │KP / Quiz  │ │Skills    │ │
│ └──────────┘ └───────────┘ └──────────┘ │
│                       │                  │
│                       ▼                  │
│             Learning Action API          │
│                       │                  │
└───────────────────────┼──────────────────┘
                        │
                 FastAPI Sidecar
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
      Services       LangGraph      Tools
          │           Runtime         │
          │             │             │
          └─────────────┼─────────────┘
                        ▼
              SQLite + files/
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
        Records       Concept     Evidence
        Sources       Mastery      Events
```

这个方向既能学习 OpenMAIC，又不会破坏 KnowRealm 当前最重要的 **Local-first、Evidence-driven、长期学习状态** 三个根基。

------

## 综合评分

如果单纯评价 OpenMAIC：

| 维度                  | 评分       |
| --------------------- | ---------- |
| 产品创新              | **9/10**   |
| Agent 架构            | **9/10**   |
| 教育交互              | **9.5/10** |
| 多 Agent              | **8.5/10** |
| 内容生成              | **9/10**   |
| 编辑能力              | **8.5/10** |
| 可扩展性              | **9/10**   |
| 本地优先              | **6/10**   |
| 长期学习建模          | **4/10**   |
| 学习 Evidence         | **3/10**   |
| 对 KnowRealm 参考价值 | **9.5/10** |

**最终判断：强烈建议将 OpenMAIC 列为 KnowRealm-AI 的重点长期竞品/参考项目，但重点研究“Agent Runtime / Tool / Skill / Action / DSL”，而不是照搬它的 AI Classroom 产品形态。**

[OpenMAIC GitHub 仓库](https://github.com/THU-MAIC/OpenMAIC?utm_source=chatgpt.com)
[查看 OpenMAIC v1.0.0 CHANGELOG](https://github.com/THU-MAIC/OpenMAIC/blob/main/CHANGELOG.md?utm_source=chatgpt.com)
[查看 Multi-Agent Director 实现](https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/orchestration/director-graph.ts?utm_source=chatgpt.com)

如果你后续持续关注这个项目，我也可以定期检查 OpenMAIC 的 Release / 新功能，并只筛选出**值得 KnowRealm-AI 借鉴的变化**。