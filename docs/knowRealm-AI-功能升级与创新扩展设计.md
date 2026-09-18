# AI课堂助手：功能升级与创新扩展设计（最终版）

> **文档定位**：Learning Brain（F1~F18）的**功能机制与交互设计参考**。⚠️ **历史文档**：编写于 2026-06 旧技术栈时期，正文中的技术实现与"现有系统"描述已过时，阅读前必读下方 §0 对齐声明；需求边界以《KnowRealm-AI-功能需求基线 v2.7》为准。
> **目标**：不推翻现有“课堂记录 → AI 总结 → HITL → 知识点/习题/Todo/复习 → AI 问答”主流程，而是在其上增加长期学习状态建模能力，将产品从 **AI课堂助手** 逐步升级为 **AI Personal Learning Brain / AI Learning OS**。  
> **适用端**：Tauri Desktop（Windows 为 V1 唯一首发平台）；微信小程序形态已废弃。  
> **设计原则**：现有能力优先复用；扩展能力按阶段引入；所有 AI 判断尽可能可追溯、可验证、可被用户纠正。

---

# 0. 与基线 v2.7 的对齐声明（必读）

> 本文档编写于 2026-06 旧技术栈时期（微信小程序 + Spring Boot + MySQL + MinIO + Qdrant 设想）。产品与架构此后经基线 v1.1~v1.6 多轮演进，本文正文**未随之改写**。阅读规则如下。

**本文档仍然有效的部分（现行价值）**：

- §3 十条架构原则（已被基线 §3.1 十二条红线吸收并扩展）；
- F1~F18 的功能机制、交互流程、Event/Evidence 类型清单、状态机、算法思路（§7~§26）；
- §28 服务拆分与 §30 API 分组的概念结构（已由基线 §9.2 收编）；
- §36 数据与隐私原则（已由基线 §7 收编）。

**已过时的部分——冲突时一律按下表"现行权威"执行**：

| # | 维度 | 本文过时表述（出现位置） | 现行权威 |
|---|------|------------------------|---------|
| D1 | 产品端形态 | 微信小程序 + Desktop 复用 | Tauri Desktop，Windows V1 唯一首发；小程序已废弃（基线 §1.3） |
| D2 | "现有能力"叙述 | 微信登录 / Sa-Token / MinIO / 分享卡片 / 状态轮询（§2 整章） | 无登录/无账号（本地单用户，首启三步）；原始文件明文存数据目录 files/；不做分享=Markdown 本地导出；Record 级 SSE 仅通知失效、REST 为事实源、断线条件轮询（基线 §4.1/§4.6、决策 #3/#8/#15/#58） |
| D3 | 捕获入口 | 仅"录音+文档"双入口 | 五级捕获（速记/粘贴/剪藏/音频/文档）+ 收件箱 Inbox，records.course_id 可空（决策 #21） |
| D4 | 目标用户与课程上下文 | 全学段学生；education_stage 唯一个性化输入 | 一切学习知识的人；learning_context + education_stage/depth 双字段（决策 #23） |
| D5 | AI 对话形态 | 聊天仅作为 Record/Course 上下文二级功能 | 💬 AI 对话一级入口：自由聊天 + @记录/@课程/@全部资料挂载可切换；自由聊天不建向量索引、不进 Learning Evidence 链（决策 #22/#24） |
| D6 | 后端技术栈 | Java / Spring Boot / Spring AI / MyBatis-Plus / Sa-Token（§27.1） | Tauri sidecar（Python 进程内）FastAPI + LangChain/LangGraph + SQLite（WAL）本地数据目录为唯一事实源（技术栈 v4.5） |
| D7 | 异步与缓存 | Redis/Redisson + RabbitMQ（§27.4/§27.5） | 自研 processing_jobs 队列（SQLite 表即队列 + sidecar 进程内 asyncio worker），无 Redis / RabbitMQ / procrastinate（决策 #1） |
| D8 | 向量检索 | Qdrant（§10.4/§25.3/§27.2） | sqlite-vec（vec0 虚拟表）+ semantic_embeddings 统一表；明确不做 Qdrant / pgvector（技术栈 v4.5） |
| D9 | 数据表设计 | 全文 `t_` 前缀表草案（§7.3、§12、§13、§25、§26 等） | 数据模型 v2.9（无前缀 snake_case 定稿）；本文表结构仅作字段语义参考，不得据此建表 |
| D10 | shares 表 | §25.1 保留 t_share | 不建 shares 表（决策 #15） |
| D11 | F15 落地 | 不新增表（仅 action_type=PREVIEW） | 依赖资料库来源资产模型（原 course_materials 草案由 §42 统一重审，决策 #12） |
| D12 | Teach-back 输入 | 语音解释 → ASR（§18.1） | V1 文本先行，语音后补（决策 #19） |
| D13 | AI 可观测 | Micrometer / OTel / Langfuse（§27.9） | 自建 llm_call_logs 表（决策 #2） |
| D14 | 编排框架 | Spring AI Alibaba StateGraph | LangGraph 编排、禁止超级 Graph（基线 §3.1 红线 #2）；现役三图 = Summary / ReviewMaterial / Chat（chat 以 deepagents 骨架装配，ADR-0018），Tutor / TeachBack / Autopilot / MisconceptionVerification 为后续规划图（P5/P6） |
| D15 | 优先级与阶段 | §6 S+/A+ 评级、§32 Phase 1~7、§37 P0~P3 | 基线 §4.7 阶段映射（F1=P2 … F16=P6）与 §5.1 阶段规划 |
| D16 | 产品定位语境 | 毕业设计 / 项目展示 / 比赛（§33） | 开源、面向个人使用（基线头部） |

> 一句话读法：**机制与交互看本文；边界 / 优先级 / 技术选型 / 表结构看三份权威文档**——《KnowRealm-AI-功能需求基线-v2.7》《技术栈设计与审查-v4.5》《KnowRealm-AI-数据模型-v2.9》。

---

# 1. 文档结论

现有系统已经解决了“如何把一节课堂转化为结构化学习资产”的问题：

```text
课堂录音 / 音频导入 / 文档导入
                ↓
        腾讯云 ASR / 文档解析
                ↓
             转写文本
                ↓
         AI 自动生成总结
                ↓
          HITL 用户确认
                ↓
 ┌──────────────┼──────────────┐
 ↓              ↓              ↓
知识点          习题         Todo / 复习
 ↓              ↓
确认保存       模拟测试
                ↓
             AI 批改

另外：
单课堂 AI 问答 + SSE + Chat Memory
```

下一阶段不建议继续增加大量彼此独立的“AI 生成按钮”，而是增加一层长期运行的 **Learning Brain（学习大脑）**：

```text
课堂与学习数据
      ↓
知识结构化
      ↓
Learning Event / Evidence
      ↓
Mastery / Forgetting / Misconception
      ↓
Learner Digital Twin
      ↓
Next Best Learning Action
      ↓
Tutor / Review / Quiz / Teach-back / Challenge
      ↓
产生新的 Learning Evidence
      ↓
再次更新学习状态
```

最终形成：

> **Observe → Understand → Diagnose → Decide → Teach → Verify → Update**

本最终版不再把所有内容平铺成“15 个同级功能”，而是按七层能力组织：

1. **Learning Data Foundation：学习数据基础**
2. **Course Brain：课程知识大脑**
3. **Learner Brain：学习者状态模型**
4. **Adaptive Learning：自适应学习执行**
5. **AI Learning Autopilot：主动学习决策**
6. **Learning Outcome：学习成果沉淀**
7. **Collaboration Layer：可选协作层**

---

# 2. 现有 PRD 能力：保持不变的基线

> ⚠️ **历史快照（见 §0 对齐声明 D2）**：本章描述的是本文写作时点的旧项目形态（微信小程序 / Spring Boot / MinIO 等）。现行产品形态与功能范围以《功能需求基线 v2.7》§4 为准，**不得把本章当作现行功能清单**。本章的现存价值仅在于说明"M1~M6 模块边界被 Learning Brain 扩展复用"这一结构关系。

以下能力视为已经实现，扩展设计必须建立在这些能力上，不重复建设。

## 2.1 M1 用户与认证

保留：

- 微信授权登录；
- 用户信息；
- 学习统计；
- 深色模式、字体设置；
- Sa-Token + JWT；
- 用户数据隔离。

## 2.2 M2 课程管理

保留：

- 课程 CRUD；
- 每门课程独立 `education_stage`；
- 课程类型；
- 按课程组织课堂记录。

`education_stage` 继续作为所有 AI 功能的重要输入，但后续不再是唯一的个性化上下文。

## 2.3 M3 课堂记录与资料

保留：

- 小程序课堂录音；
- 多段录音；
- 音频上传；
- PDF / DOCX / PPTX / TXT 文档导入；
- MinIO；
- 腾讯云 ASR；
- 句子级时间戳；
- 转写编辑；
- 一条 Record 多文件关联；
- Record 状态机。

## 2.4 M4 AI 智能学习

保留：

- AI Summary；
- Summary HITL；
- Knowledge Point；
- Quiz；
- 模拟测试；
- AI 简答批改；
- Review Material；
- Todo；
- 分享；
- AI 结果重新生成。

## 2.5 M5 AI 问答

保留：

- 单 Record 问答；
- SSE；
- Chat Memory；
- 最近若干轮对话；
- 知识点解释；
- 学习辅导。

## 2.6 M6 系统与消息

保留：

- 状态轮询；
- 上传/AI/ASR 状态；
- 权限与隐私机制。

---

# 3. 本次升级必须遵守的 10 条架构原则

## 3.1 不推翻现有 Record-Centric 流程

课堂仍然是最重要的数据入口。

扩展不是把：

```text
Record → AI Content
```

删除，而是在其上增加：

```text
Record → Learning Evidence → Concept → Learner State
```

---

## 3.2 Knowledge Point 与 Concept 不得混为一谈

### Knowledge Point

课堂级学习资产：

```text
Record 2026-08-10
└── Knowledge Point：Redis AOF
    ├── detail
    ├── tags
    └── 用户可以编辑 / 删除 / 补充
```

它代表：

> “这一节课里，被 AI 和用户确认的知识点”。

继续保留现有 `t_knowledge_point`。

### Concept

课程级规范知识节点：

```text
Course：Redis
└── Concept：AOF
    ├── Record 01 提到
    ├── Record 03 提到
    ├── Record 08 提到
    └── lecture.pdf 提到
```

它代表：

> “跨课堂长期存在、用于掌握度和知识关系建模的规范概念”。

新增：

```text
t_concept
t_concept_relation
t_record_concept
```

### 推荐关系

```text
Record
  ↓
Knowledge Point
  ↓
Concept Resolution / Merge
  ↓
Canonical Concept
```

不能为了 Concept 系统删除或替换现有 Knowledge Point。

---

## 3.3 Learning Event 与 Learning Evidence 必须分层

### Learning Event

记录：

> 用户发生了什么学习行为。

例如：

```text
QUIZ_ANSWERED
TEACH_BACK_COMPLETED
REVIEW_VERIFIED
TUTOR_CHECK_COMPLETED
SUMMARY_CONFIRMED
```

### Learning Evidence

记录：

> 这个行为对某个 Concept 的学习状态提供了什么证据。

例如：

```text
event = QUIZ_ANSWERED
concept = MVCC
difficulty = HARD
result = WRONG
evidence_weight = 0.72
```

推荐闭环：

```text
Learning Event
      ↓
Evidence Builder
      ↓
Learning Evidence
      ↓
Mastery Engine
      ↓
User Concept State
```

---

## 3.4 所有业务功能禁止直接修改 Mastery

禁止：

```text
QuizService → UPDATE mastery_score
TutorService → UPDATE mastery_score
TeachBackService → UPDATE mastery_score
```

统一：

```text
Quiz / Tutor / Teach-back / Review / Challenge
                    ↓
              Learning Event
                    ↓
              Learning Evidence
                    ↓
               Mastery Engine
                    ↓
          t_user_concept_mastery
```

这样才能保证掌握度算法只有一个事实入口。

---

## 3.5 AI 判断必须带 Confidence

例如 Digital Twin 不应该无条件展示：

```text
知识迁移能力 = 62
推理能力 = 69
```

如果证据不足，应该：

```text
知识迁移能力：数据不足
Evidence：1
Confidence：LOW
```

任何诊断型输出至少考虑：

```text
score
confidence
evidence_count
last_updated_at
```

---

## 3.6 Misconception 只能“先怀疑，再验证”

禁止：

```text
用户答错 1 题
→ 认定用户存在概念错误
```

推荐：

```text
异常证据
   ↓
SUSPECTED
   ↓
Quiz / Tutor / Teach-back 验证
   ↓
CONFIRMED / DISMISSED
   ↓
纠错训练
   ↓
RESOLVED
```

---

## 3.7 Autopilot 采用“主动推荐、用户控制执行”

保持原 PRD 的 HITL 思路：

> **Active Recommendation, Human-Controlled Execution**

Autopilot 可以主动：

- 计算风险；
- 排学习优先级；
- 形成今日建议；
- 推荐 Review / Quiz / Teach-back / Tutor；
- 重新规划建议。

Autopilot 不应未经用户确认：

- 自动开始考试；
- 自动进入 Tutor；
- 自动生成大量题目；
- 自动改变用户长期目标；
- 自动认定 Concept 已掌握。

---

## 3.8 AI Synthesis 不是 Evidence

Evidence 优先来自：

```text
课堂录音
课程文档
用户实际答题
Teach-back
Recall Verification
Tutor Check
```

AI 自己生成的解释只是：

```text
AI_SYNTHESIS
```

不能因为“AI 说用户会了”，就成为“用户会了”的证据。

第一阶段不把模型内部知识称为 `External Evidence`。

如果未来真的引入外部资料，应保存：

```text
source_title
source_uri
source_excerpt
retrieved_at
```

---

## 3.9 Todo / Learning Plan / Autopilot Action 必须区分

### Todo

Record-scoped：

> 这一节课之后需要完成什么。

### Learning Plan Item

Goal-scoped：

> 为了某个考试或学习目标，未来几天如何安排。

### Autopilot Action

State-scoped：

> 根据用户此刻状态，现在最值得做什么。

Autopilot 可以引用 Todo/Plan Item，但不能复制成第三套任务系统。

---

## 3.10 Study Pod 不属于 Learning Brain Core

Study Pod 会引入：

- 真人匹配；
- UGC；
- 审核；
- 举报与屏蔽；
- 未成年人安全；
- 实时通信；
- 网络效应。

因此将其定义为：

> **Optional Collaboration Layer**

只有 Learning Brain 核心稳定后再做。

---

# 4. 升级后的模块结构

现有 M1~M6 保持。

新增 M7，但 M7 不是所有扩展功能的“容器”，而是共享智能层。

```text
M1 用户与认证
M2 课程管理

M3 课堂记录与资料
├── Transcript Segment
├── Marker
├── Source Anchor
└── Classroom Timeline

M4 AI 智能学习
├── 现有 Summary / Knowledge / Quiz / Review / Todo
├── Adaptive Assessment
├── Teach-back
└── Transfer Challenge

M5 AI 问答
├── Ask AI
├── Socratic Tutor
└── Course-level Q&A

M6 系统与消息

M7 AI Learning Brain
├── Concept Service
├── Course Brain
├── Learning Event
├── Learning Evidence
├── Mastery Engine
├── Forgetting Engine
├── Misconception Engine
├── Learner Model
├── Learning Planner
└── Autopilot Agent
```

---

# 5. 总体数据与决策闭环

```text
                    ┌─────────────────────┐
                    │ Classroom / Document│
                    └──────────┬──────────┘
                               ↓
                    Transcript / Segment
                               ↓
                     Source / Evidence
                               ↓
        ┌──────────────────────┴──────────────────────┐
        ↓                                             ↓
Knowledge Point                               Learning Event
        ↓                                             ↓
Concept Resolution                              Evidence Builder
        ↓                                             ↓
Course Concept Graph                         Learning Evidence
        └──────────────────────┬──────────────────────┘
                               ↓
                        Mastery Engine
                 ┌─────────────┼─────────────┐
                 ↓             ↓             ↓
             Mastery       Forgetting   Misconception
                 └─────────────┼─────────────┘
                               ↓
                    Learner Digital Twin
                               ↓
                    Next Best Action Engine
                               ↓
                       Autopilot Agent
              ┌────────────────┼─────────────────┐
              ↓                ↓                 ↓
            Tutor            Review            Quiz
              ↓                ↓                 ↓
          Teach-back       Memory Rescue      Challenge
              └────────────────┼─────────────────┘
                               ↓
                         New Evidence
                               ↓
                     Update Learner State
```

---

# 6. 功能升级总览

| 编号 | 能力 | 类型 | 对现有功能的关系 | 优先级 |
|---|---|---|---|---|
| F1 | Transcript Segment + Evidence Timeline | 数据基础升级 | 升级现有 ASR 句子时间戳 | S+ |
| F2 | Classroom Marker | 课堂交互升级 | 扩展现有录音页 | S |
| F3 | Classroom vs Courseware Diff | 新增 | 复用多文件 + Transcript | A+ |
| F4 | Course Brain | 核心新增 | 从单 Record 升级到 Course | S+ |
| F5 | Knowledge GPS | 产品体验新增 | 建立在 Concept + Mastery 上 | S+ |
| F6 | Learning Event + Evidence | 核心数据新增 | 为全部学习行为统一建模 | S+ |
| F7 | Mastery Engine | 核心新增 | 从“做过”升级到“掌握多少” | S+ |
| F8 | Misconception Engine | 核心新增 | 升级错题分析 | S+ |
| F9 | Forgetting Radar + Memory Rescue | 核心新增 | 升级复习系统 | S+ |
| F10 | Learner Digital Twin | 核心新增 | 聚合长期学习状态 | S+ |
| F11 | Adaptive Learning Conversation | AI 问答升级 | 升级现有 M5 | S |
| F12 | Teach-back | 新增学习模式 | 复用 ASR + Chat | S |
| F13 | Adaptive Assessment + Transfer Challenge | 测试升级 | 升级现有模拟测试 | S |
| F14 | Exam-driven Dynamic Planner | 规划新增 | 升级 Todo/复习 | A+ |
| F15 | Personalized Pre-class Preview | 新增 | 复用 Course Brain + 文档 | A+ |
| F16 | AI Learning Autopilot | 核心 Agent | 整合所有 Learning Brain 能力 | S+ |
| F17 | Learning Passport | 成果沉淀 | 升级统计与学习画像 | A |
| F18 | AI Study Pod | 可选协作 | 新增多人能力 | V3.0 |

---

# 7. F1 — Transcript Segment + Evidence Timeline

> **✅ 已实施回写（2026-09-10，F1 六票 + 07 补票完结）**：本章为草案，表结构权威见《数据模型 v2.9》§4.5（无 `t_` 前缀；四表为派生定位/引用结构，无软删列；转写分片时间戳列可空 = 无时间轴来源）。与草案的定案差异：
>
> - **术语定名「来源时间轴」（Source Timeline）**：本章 "Evidence Timeline" 废弃——Evidence 一词专属「学习证据」（Learning Evidence）；
> - **交付边界**：本期 = 数据地基（四表 + 切分管道 + 存量回填）+ 来源时间轴前端；不含音频回放、不含 AI 产物 graph prompt 引用改造、不动搜索索引；
> - **锚点表空表就位**：source_anchors / source_anchor_links 仅结构 + service + 只读 API，零写入者（首个写入者随 A1 检索工具 / A3 Evidence Builder）；§7.4 草案 source_type 缺 CHAT_MESSAGE，定稿为四值；
> - **PPTX 维持不支持**（未来支持导入时随做分片）；文档分片按页/内容块落地，已接入转写页时间轴（PDF 页码徽章，票 03 前旧文档回落行级）；
> - **音频回放（§7.5「点击自动播放」）不在本期**：独立后续票，方向已锁 = Tauri asset protocol（`convertFileSrc`）+ `<audio>`，零后端端点；
> - 已落地交互：浏览态行式时间轴（音频 mm:ss / h:mm:ss、无标记块序号列）+ chat 引用角标句级定位（前端 quote 匹配 → 滚动 + 高亮 + 时间戳徽章，找不到走「原文已变动」兜底）。

## 7.1 现有基础

现有腾讯云 ASR 已经返回带时间戳的句子级转写，前端也支持按句子展示。

下一步不是重新做 ASR，而是把句子级结构正式持久化。

## 7.2 功能目标

把当前“整段转写文本”升级成：

```text
课堂 Record
├── Audio File 01
│   ├── Segment 001 00:00-00:06
│   ├── Segment 002 00:06-00:13
│   └── ...
├── Audio File 02
│   └── ...
└── Document
```

使系统以后可以：

- 点击 AI 总结结论跳回课堂原声；
- 知识点显示“老师在哪一段讲过”；
- Quiz 显示出题来源；
- Tutor 引用课堂证据；
- Misconception 对照老师讲解；
- Course Brain 做语义检索；
- Marker 抽取附近上下文。

## 7.3 数据表

### `t_transcript_segment`

建议字段：

```text
id
transcript_id
record_id
file_id

sequence_no
record_start_ms
record_end_ms
file_start_ms
file_end_ms

speaker
content
content_hash

created_at
updated_at
```

其中：

- `record_start_ms`：整节课堂统一时间轴；
- `file_start_ms`：当前音频文件内部时间；
- 多段录音时两者必须同时存在；
- `speaker` 第一版可为空，未来说话人分离时再使用。

推荐索引：

```text
idx_record_sequence(record_id, sequence_no)
idx_file_time(file_id, file_start_ms)
idx_record_time(record_id, record_start_ms)
```

### `t_document_segment`（推荐）

为了让 PDF / PPTX / DOCX 也支持精确引用，可以增加：

```text
id
record_id
file_id
sequence_no
page_no
section_title
content
start_offset
end_offset
created_at
```

对于不能稳定识别页面的格式，`page_no` 可为空。

## 7.4 Source Anchor

新增：

### `t_source_anchor`

```text
id

source_type
source_id

record_id
file_id
transcript_segment_id
document_segment_id

start_offset
end_offset
page_no

created_at
```

`source_type`：

```text
AUDIO_SEGMENT
DOCUMENT_SEGMENT
USER_NOTE
```

## 7.5 前端交互

课堂详情增加 Timeline：

```text
37:42 老师：
AOF 的优势是数据丢失窗口较小……

[⭐重点]
[作为证据引用]
```

AI 总结：

```text
AOF 通常拥有更小的数据丢失窗口。
[课堂 37:42]
```

点击：

```text
→ 定位课堂 Timeline
→ 自动从 37:42 播放
```

---

# 8. F2 — Classroom Marker：课堂实时标记

## 8.1 功能目标

录音过程中允许学生低成本记录：

```text
[⭐ 重点]
[❓ 没听懂]
[📝 记一下]
```

不要求学生停止听课去写完整笔记。

## 8.2 多段录音时间设计

禁止只保存一个模糊的 `timestamp_ms`。

新增：

### `t_record_marker`

```text
id
user_id
course_id
record_id
file_id

marker_type
record_offset_ms
file_offset_ms

note
status

created_at
```

`marker_type`：

```text
IMPORTANT
CONFUSED
NOTE
```

## 8.3 课后处理

课堂结束后：

```text
Marker
  ↓
根据 record_offset_ms
取前后 60~180 秒 Segment
  ↓
AI Context Analysis
  ↓
生成 Marker Review
```

例如：

```text
你今天标记了 3 个“没听懂”

1. 21:42 MVCC ReadView
   原课堂：[播放]
   AI 判断：可能涉及“快照读”与“当前读”的区别
   [开始解释]

2. 42:13 红黑树旋转
   [播放]
   [开始 3 分钟练习]
```

## 8.4 与 Learning Brain 的关系

`CONFUSED` Marker：

- 只表示用户主观感受；
- 不直接降低 Mastery；
- 可以生成 `Learning Event`；
- 后续通过 Quiz / Tutor / Teach-back 验证。

---

# 9. F3 — Classroom vs Courseware Diff：课堂讲解与课件差异分析

## 9.1 为什么适合当前项目

现有系统已经支持：

```text
Record
├── 多段音频
└── 多个文档
```

因此可以比较：

```text
老师实际讲了什么
VS
课件原本写了什么
```

这是对现有数据资产利用率非常高的升级。

## 9.2 输出内容

### 课件有，但课堂未展开

```text
PPT：Redis Sentinel
课堂讲解：仅简单提及
```

### 老师额外补充

```text
课堂新增：
AOF Rewrite 的生产环境问题
来源：47:18-51:02
```

### 老师重复强调

```text
“这里考试经常考”
来源：32:14
```

### 课件与口头讲法差异

用于帮助学生识别：

- 教师重点；
- 可能考试重点；
- 实际授课范围；
- 课件之外的重要补充。

## 9.3 技术实现

```text
Document Segments
      ↓
Concept Extraction
      ↓
Transcript Segments
      ↓
Concept Extraction
      ↓
Concept Alignment
      ↓
LLM Compare
      ↓
Structured Diff Result
```

建议 AI 输出结构化 JSON：

```json
{
  "covered": [],
  "documentOnly": [],
  "teacherExtra": [],
  "teacherEmphasis": []
}
```

第一版可以不新增独立事实表，结果保存为 `record_analysis` 类型；如果需要长期查询，再增加：

### `t_record_analysis`

```text
id
record_id
analysis_type
result_json
model
version
created_at
```

---

# 10. F4 — Course Brain：从单课堂升级为课程大脑

## 10.1 定义

Course Brain 不是“知识图谱”的另一个名字。

它由四部分组成：

```text
Course Brain
├── Course Knowledge Graph
├── Course Semantic Memory
├── Cross-record Retrieval
└── Concept Evolution
```

## 10.2 与现有 M5 的关系

当前：

```text
Record-level Chat
```

升级后增加：

```text
Course-level Chat
```

两者同时保留。

前端可以明确入口：

```text
当前课堂问答
整门课程问答
```

## 10.3 Course Knowledge Graph

新增：

### `t_concept`

```text
id
course_id

canonical_name
description
concept_type

importance
status
source

created_at
updated_at
```

`source`：

```text
AI_EXTRACTED
USER_CONFIRMED
SYSTEM
```

### `t_concept_relation`

```text
id
course_id
source_concept_id
target_concept_id
relation_type
confidence
evidence_count
status
created_at
```

关系：

```text
PREREQUISITE
PART_OF
RELATED_TO
COMPARE_WITH
CAUSES
APPLIES_TO
```

AI 推断关系建议先：

```text
status = CANDIDATE
```

置信度足够或用户确认后：

```text
status = CONFIRMED
```

### `t_record_concept`

```text
id
record_id
concept_id
knowledge_point_id

relevance
importance
first_start_ms
evidence_count

created_at
```

## 10.4 Course Semantic Memory

推荐使用扩展文档中建议的 Qdrant。

索引对象：

- Transcript Segment；
- Document Segment；
- AI Summary 可用于导航，但不作为原始 Evidence；
- Knowledge Point；
- Concept Description。

Qdrant payload 建议：

```text
user_id
course_id
record_id
file_id
segment_id
source_type
concept_ids
created_at
```

查询必须先按 `user_id + course_id` 过滤，保证数据隔离。

## 10.5 Course-level RAG

用户：

> “老师这学期关于 MVCC 一共讲过几次？”

流程：

```text
Question
   ↓
Query Rewrite
   ↓
Course Filter
   ↓
Qdrant Retrieval
   ↓
Evidence Rerank
   ↓
Context Builder
   ↓
LLM Answer
   ↓
Source Anchor
```

输出：

```text
这门课目前有 3 次重点讲到 MVCC：

Week 3：基本概念 [课堂 28:13]
Week 5：ReadView [课堂 41:02]
Week 8：MVCC 与隔离级别 [课堂 16:25]
```

---

# 11. F5 — Knowledge GPS：学习知识地图

## 11.1 定位

Course Brain 是后端知识能力。

Knowledge GPS 是用户看到的导航体验。

它回答：

> 我学过什么？哪里强？哪里弱？下一步从哪里走？

## 11.2 页面

```text
数据结构

线性表             92%
树                 81%
├── 二叉树         94%
├── AVL            63%
└── 红黑树         42% 🔴

图
├── BFS            87%
└── DFS            76%
```

点击红黑树：

```text
当前掌握度       42%
Confidence       中
遗忘风险         高
最近练习         3 天前
相关误区         1 个待验证

学习来源
- 08-03 课堂 32:18
- lecture-05.pdf P18

推荐
[4 分钟复习]
[Teach-back]
[做 3 道验证题]
```

## 11.3 节点颜色/状态不能只依赖 Mastery

推荐状态：

```text
NOT_ENOUGH_DATA
LEARNING
STABLE
AT_RISK
WEAK
MISCONCEPTION_RISK
```

这样可以避免：

> 只有一条数据就显示 93%。

---

# 12. F6 — Learning Event + Learning Evidence

> **✅ 已实施回写（2026-09-14，learning-evidence 四票完结，ADR-0021）**：本章为草案，表结构权威见《数据模型 v2.9》。与草案的定案差异：
>
> - **四事件先行**（总结确认 / 知识点确认 / 逐题作答 / 交卷），与业务动作同事务写入，统一经 `learning.events.write_learning_event`；幂等键形制 `{event-slug}:{source-id}`（独立 `idempotency_key` 列设想未采用，`event_id` 为 uuid4）；
> - **消费为独立 asyncio 水位循环**：不入 processing_jobs；水位 = SQLite 隐式 rowid 单调扫描、禁 NOT EXISTS、失败 3 次跳过不建死信表；
> - **Evidence 映射集中声明**：QUIZ 0.9/0.8、CONFIRMED → USER_CONFIRMATION 0.3·0.4/0.7、交卷不产证据（防双计）——§12.4 权重表为早期设想；evidence_type 首批落地 QUIZ / USER_CONFIRMATION，RECALL / TEACH_BACK 等随对应功能进入；
> - 证据可由事件流清空重放再生；learning 域提供薄只读查询（按记录 / 课程取证据流，Mastery 与学习上下文中间件的共同底座）；零 LLM / 零前端 / 零新 API；
> - `concept_id` / `source_anchor_id` 恒 NULL，留 P3（Concept）/ P5（细粒度来源）接入。

这是整个升级最重要的数据基础。

## 12.1 `t_learning_event`

建议：

```text
id
user_id
course_id
record_id
concept_id

event_type

source_type
source_id

result
score
difficulty
duration_ms

metadata_json

idempotency_key
schema_version

occurred_at
created_at
```

唯一索引：

```text
uk_learning_event_idempotency(idempotency_key)
```

## 12.2 Event 类型

推荐避免：

```text
QUIZ_ANSWERED
QUIZ_CORRECT
QUIZ_WRONG
```

三个事件重复记录一次答题。

改成：

```text
QUIZ_ANSWERED
result = CORRECT / WRONG
```

核心事件：

```text
SUMMARY_CONFIRMED
KNOWLEDGE_CONFIRMED
QUIZ_ANSWERED
QUIZ_TEST_COMPLETED
TEACH_BACK_COMPLETED
TUTOR_CHECK_COMPLETED
REVIEW_VERIFIED
MARKER_CREATED
MISCONCEPTION_CONFIRMED
MISCONCEPTION_RESOLVED
PLAN_ITEM_COMPLETED
CONCEPT_MASTERED
```

## 12.3 `t_learning_evidence`

```text
id
user_id
course_id
concept_id

event_id
evidence_type

result
score
difficulty
weight
confidence

source_anchor_id

metadata_json

occurred_at
created_at
```

`evidence_type`：

```text
QUIZ
RECALL
TEACH_BACK
TUTOR_CHECK
TRANSFER
CLASSROOM_SIGNAL
USER_CONFIRMATION
```

## 12.4 Evidence 权重

第一版不需要复杂机器学习。

可以使用规则：

```text
普通查看知识点          低权重
简单选择题正确          中低
高难题正确              中高
延迟 Recall 成功        高
Teach-back 通过          高
迁移题通过               高
```

Mastery Engine 读取 Evidence，而不是直接扫描十几张业务表。

---

# 13. F7 — Mastery Engine：长期掌握度模型

## 13.1 目标

从：

```text
用户做了 20 道题
```

升级到：

```text
用户对 MVCC：
Mastery = 0.82
Confidence = 0.76
Memory Strength = 0.71
```

## 13.2 `t_user_concept_mastery`

```text
id
user_id
course_id
concept_id

mastery_score
mastery_confidence

memory_strength
transfer_score
reasoning_score

evidence_count
positive_evidence_count
negative_evidence_count

last_learned_at
last_practiced_at
last_verified_at
next_review_at

version
updated_at
```

## 13.3 初始版本算法

不建议第一版让 LLM 自己“算掌握度”。

可以采用可解释规则：

```text
mastery =
  quiz_component
+ recall_component
+ teach_back_component
+ transfer_component
```

每个 Component 根据：

```text
correctness
difficulty
recency
evidence_weight
```

计算。

LLM 负责：

- 内容理解；
- 答案语义评分；
- Concept 对齐；
- 诊断解释。

数值状态尽量由确定性服务计算。

## 13.4 Confidence

例如：

```text
Evidence 1 条
Mastery 90%
Confidence LOW
```

不能和：

```text
Evidence 18 条
Mastery 85%
Confidence HIGH
```

等价。

---

# 14. F8 — Misconception Engine：认知误区诊断

## 14.1 目标

不只回答：

> “这道题错了。”

而是：

> “多次错误是否来自同一个错误认知？”

## 14.2 第一版类型

推荐：

```text
KNOWLEDGE_GAP
MISCONCEPTION
MEMORY_DECAY
REASONING_GAP
PREREQUISITE_GAP
UNKNOWN
```

暂不建议直接使用：

```text
CARELESS_ERROR
```

因为它很难仅凭学习数据可靠判断。

## 14.3 状态

```text
SUSPECTED
CONFIRMED
RESOLVED
DISMISSED
```

## 14.4 `t_misconception`

```text
id
user_id
course_id
concept_id

type
title
description

confidence
evidence_count

status

first_detected_at
last_detected_at
confirmed_at
resolved_at

created_at
updated_at
```

推荐关联表：

### `t_misconception_evidence`

```text
id
misconception_id
learning_evidence_id
support_score
created_at
```

## 14.5 诊断流程

```text
连续异常 Evidence
       ↓
Pattern Detector
       ↓
LLM Diagnosis
       ↓
SUSPECTED
       ↓
生成验证任务
       ↓
Adaptive Quiz / Tutor / Teach-back
       ↓
CONFIRMED / DISMISSED
```

## 14.6 用户体验

```text
AI 发现一个“可能的理解问题”

你可能把：
数据修改
→ AOF 写入
→ fsync
三个步骤混在了一起。

置信度：68%
证据：2 道题 + 1 次 Tutor

[验证一下]
[这不是我的问题]
```

---

# 15. F9 — Forgetting Radar + Memory Rescue

## 15.1 核心问题

原来的 Review Material 解决：

> “给我一份复习资料。”

新的 Forgetting Engine 解决：

> “我什么时候最需要复习什么？”

## 15.2 Review 不等于“打开页面”

不能：

```text
打开复习资料
→ memory_strength 上升
```

必须尽量有 Recall Verification：

```text
Review
   ↓
Recall Question / Mini Quiz / Teach-back
   ↓
Verification
   ↓
Memory Evidence
   ↓
Scheduler Update
```

## 15.3 `t_review_schedule`

```text
id
user_id
course_id
concept_id

scheduler_type

stability
difficulty
retrievability

last_review_at
next_review_at

last_result
review_count

priority_score

created_at
updated_at
```

## 15.4 FSRS

扩展文档建议使用 FSRS 思路。

推荐逐步实现：

### V1

规则：

```text
priority =
importance
× forgetting_risk
× (1 - mastery)
× exam_weight
```

### V2

引入 FSRS 状态。

## 15.5 Memory Rescue

用户输入：

```text
我只有 12 分钟
```

系统：

```text
1. AOF              4 min
2. 事务隔离级别     5 min
3. 红黑树           3 min
```

不是简单按“最弱”排序，而是考虑：

```text
Forgetting Risk
Mastery
Importance
Exam Weight
Available Time
Misconception
```

---

# 16. F10 — Learner Digital Twin

## 16.1 定义

Digital Twin 不是一张存大 JSON 的“万能表”。

它是：

> 对一个用户当前学习状态的统一 View / Context。

## 16.2 组成

```text
Learner Digital Twin
├── Concept Mastery
├── Memory State
├── Misconception State
├── Difficulty Profile
├── Transfer Evidence
├── Reasoning Evidence
├── Recent Learning Events
├── Learning Goal
└── Observed Learning Preference
```

## 16.3 不建议伪造精确分数

例如：

```text
概念理解      78
记忆保持      71
知识迁移      --
推理能力      69
```

如果迁移 Evidence 不够：

```text
知识迁移：数据不足
Evidence: 1
Confidence: LOW
```

## 16.4 用户偏好

`preferred_learning_mode` 应拆成：

```text
user_selected_preference
observed_learning_preference
observed_confidence
```

因为：

> 用户主动设置偏好

和：

> AI 从行为推测偏好

不是同一类事实。

## 16.5 服务实现

推荐：

```text
LearnerProfileService
  ├── loadMastery()
  ├── loadMemory()
  ├── loadMisconceptions()
  ├── loadRecentEvidence()
  ├── loadGoal()
  └── buildLearnerContext()
```

给 Tutor、Planner、Autopilot 统一调用。

---

# 17. F11 — Adaptive Learning Conversation

## 17.1 不新建第二套 Chat 系统

复用现有：

```text
t_chat_session
t_chat_message
SSE
Chat Memory
```

增加会话模式：

```text
ASK
SOCRATIC_TUTOR
TEACH_BACK
COURSE_QA
```

## 17.2 Ask AI

特点：

- 直接回答；
- 强调 Evidence；
- 可以快速解决问题。

## 17.3 Learn with AI / Socratic Tutor

流程：

```text
Diagnose
   ↓
Question
   ↓
Student Answer
   ↓
Evaluate
   ├── 已理解 → 提高难度 / Check
   └── 未理解 → Hint
                 ↓
              Explain
                 ↓
        Check Understanding
```

## 17.4 Tutor 输入

```text
education_stage
course_context
concept_context
mastery_state
misconception_state
memory_state
recent_evidence
difficulty_profile
```

## 17.5 StateGraph

```text
load_context
   ↓
diagnose
   ↓
choose_teaching_strategy
   ↓
ask_or_explain
   ↓
wait_user
   ↓
evaluate_response
   ↓
verify
   ↓
emit_learning_event
```

---

# 18. F12 — Teach-back：讲给 AI 听

## 18.1 用户流程

```text
选择 Concept
   ↓
点击“讲给 AI 听”
   ↓
语音解释
   ↓
ASR
   ↓
Concept Coverage
   ↓
遗漏 / 混淆 / 推理断层分析
   ↓
AI 追问
   ↓
最终验证
```

## 18.2 结果

```text
你的解释覆盖度：82%

✓ Snapshot
✓ RDB 文件
✓ 恢复机制

遗漏：
△ fork

待确认：
△ SAVE / BGSAVE 区别

追问：
“为什么 BGSAVE 不需要一直阻塞主线程？”
```

## 18.3 数据

不必新建完全独立的“大表体系”。

可以复用 Chat Session，并新增：

### `t_teach_back_attempt`

```text
id
user_id
course_id
concept_id
session_id

transcript
coverage_score
reasoning_score
accuracy_score
confidence

result_json

started_at
completed_at
```

完成后产生：

```text
TEACH_BACK_COMPLETED
→ Learning Evidence
```

---

# 19. F13 — Adaptive Assessment + Transfer Challenge

## 19.1 与现有模拟测试的关系

当前：

```text
固定抽 10 道题
→ 作答
→ 评分
```

升级：

```text
Adaptive Assessment
→ 根据上一题结果决定下一题
```

现有模拟测试继续保留。

## 19.2 Quiz 数据升级

推荐给 `t_quiz` 补充：

```text
concept_id
difficulty
cognitive_level
source_anchor_id
quality_score
```

`difficulty`：

```text
EASY
MEDIUM
HARD
```

`cognitive_level` 可以：

```text
RECALL
UNDERSTAND
APPLY
ANALYZE
TRANSFER
```

## 19.3 选题决策

```text
current mastery
+ confidence
+ previous answer
+ misconception candidate
+ target concept
+ difficulty profile
        ↓
Next Question Selector
```

## 19.4 不建议完全依赖 LLM 决定下一题

优先：

```text
规则/策略层选择：
Concept + Difficulty + Cognitive Level
        ↓
题库有题 → 直接选
题库不足 → LLM 生成
```

这样更稳定、成本更低。

## 19.5 Transfer Challenge

原来的 AI Challenge / Thought Experiment 合并为 Adaptive Assessment 的高级模式：

```text
Predict
↓
Explain
↓
Counterexample
↓
Transfer
↓
Reflect
```

例如：

> 如果 Redis 不使用 fork，而让主线程直接生成 RDB，会发生什么？

它产生：

```text
TRANSFER Evidence
```

而不是单独建设一套 Challenge 系统。

---

# 20. F14 — Exam-driven Dynamic Planner：考试倒推动态学习规划

## 20.1 目标

用户：

```text
考试：数据结构期末
日期：2026-09-10
目标：85
每天：30 分钟
```

系统结合：

```text
Exam Scope
Knowledge Graph
Mastery
Forgetting Risk
Misconception
Quiz History
Daily Time Budget
```

生成动态计划。

## 20.2 Exam Scope 必须有来源

新增来源类型：

```text
USER_CONFIRMED
TEACHER_DOCUMENT
COURSE_SELECTION
AI_INFERRED
```

AI 推断范围必须让用户确认。

## 20.3 数据表

### `t_learning_goal`

```text
id
user_id
course_id

goal_type
title

target_date
target_score
daily_minutes

exam_scope_json
scope_source
scope_confirmed

status

created_at
updated_at
```

### `t_learning_plan`

```text
id
goal_id
user_id
course_id

plan_version
status

generated_at
effective_from
effective_to

created_at
```

### `t_learning_plan_item`

```text
id
plan_id
concept_id

action_type
priority
estimated_minutes

scheduled_date
status

reason_json

created_at
updated_at
```

## 20.4 动态重算

不是每次都把全部计划删除重建。

推荐：

```text
Completed Item
→ 保留

Future Item
→ 根据新状态重新排

User Locked Item
→ 不自动调整
```

## 20.5 Todo 与 Planner

Todo：

> 来自一节课。

Plan：

> 来自一个长期目标。

二者可以互相引用，但不能合表。

---

# 21. F15 — Personalized Pre-class Preview：个性化课前预习

## 21.1 新增理由

现有产品主要覆盖：

```text
课堂中
→ 课后
```

增加预习后形成：

```text
课前
→ 课堂中
→ 课后
→ 长期复习
```

## 21.2 用户场景

用户提前上传下一节课 PPT：

```text
明天：Redis Cluster

你已经掌握：
✓ Redis 基础结构
✓ RDB / AOF

建议先补：
△ 一致性哈希
△ Hash Slot

明天重点听：
1. 为什么是 16384 个槽？
2. 扩容时如何迁移？
```

## 21.3 技术流程

```text
Upcoming Document
   ↓
Concept Extraction
   ↓
Compare with Course Brain
   ↓
Compare with User Mastery
   ↓
Prerequisite Gap
   ↓
Generate Preview Plan
```

## 21.4 数据实现

第一版可以作为 `t_learning_plan_item` 的一种：

```text
action_type = PREVIEW
```

无需马上增加新表。

---

# 22. F16 — AI Learning Autopilot

这是整个升级的主入口和核心 Agent。

## 22.1 定义

不是：

> 自动替用户学习。

而是：

> 持续读取用户学习状态，为用户计算 Next Best Learning Action。

## 22.2 首页体验

原首页：

```text
开始录音
导入音频
最近课堂
统计
```

升级后顶部增加：

```text
AI 今日学习建议

你今天有 18 分钟：

1. AOF 遗忘风险较高            5 min
2. 验证“事务隔离”潜在误区      4 min
3. 完成图论 Adaptive Quiz      7 min

预计效果：
覆盖 3 个高优先级学习风险

[开始今日学习]
[调整时间]
```

原来的录音、最近课堂等入口仍保留。

## 22.3 输入

```text
Mastery
Forgetting
Misconception
Goal
Learning Plan
Todo
Recent Events
Recent Study Load
Available Time
Course Importance
```

## 22.4 Action

结构化输出：

```json
{
  "action": "REVIEW_CONCEPT",
  "conceptId": 1024,
  "reasonCode": "HIGH_FORGETTING_RISK",
  "priority": 92,
  "estimatedMinutes": 5,
  "source": "FORGETTING_ENGINE"
}
```

Action：

```text
REVIEW_CONCEPT
START_ADAPTIVE_ASSESSMENT
VERIFY_MISCONCEPTION
TEACH_BACK
START_TUTOR
READ_EVIDENCE
CONTINUE_PLAN_ITEM
COMPLETE_TODO
REST
```

## 22.5 HITL

```text
Autopilot Recommendation
       ↓
用户：
[接受]
[跳过]
[稍后]
[调整时间]
       ↓
Execute
```

## 22.6 StateGraph

```text
collect_learning_state
        ↓
build_candidate_actions
        ↓
score_candidate_actions
        ↓
select_next_best_actions
        ↓
explain_reason
        ↓
HITL
        ↓
execute
        ↓
verify
        ↓
emit_learning_event
        ↓
update_learner_state
```

## 22.7 数据表

### `t_learning_agent_action`

```text
id
user_id
course_id
concept_id
goal_id
plan_item_id
todo_item_id

action_type
reason_code
priority
estimated_minutes

input_snapshot_json
decision_json

status

recommended_at
accepted_at
started_at
completed_at
```

状态：

```text
RECOMMENDED
ACCEPTED
SKIPPED
DEFERRED
RUNNING
COMPLETED
FAILED
```

### `t_learning_agent_feedback`

```text
id
action_id
user_id

feedback_type
rating
comment

actual_minutes
perceived_helpfulness

created_at
```

---

# 23. F17 — Learning Passport：证据型学习成果

## 23.1 与现有统计页的区别

现有 Statistics：

> 我做了多少。

例如：

```text
学习 12 小时
记录 18 节课
问答 42 次
```

Learning Passport：

> 我真正学会了什么，而且有什么证据。

## 23.2 示例

```text
Java 并发

Mastered Concepts: 26 / 31

synchronized       94%
Evidence
- 3 次 Adaptive Assessment
- 1 次 Teach-back
- 14 天后 Recall 成功

AQS                87%
Evidence
- 课堂 07-12
- 2 次 Transfer Challenge

CAS                69%
Risk
- 最近 2 次迁移题错误
```

## 23.3 Mastered 判定

不能：

```text
AI 说你会了
→ Mastered
```

推荐：

```text
mastery >= threshold
AND mastery_confidence >= threshold
AND evidence_count >= N
AND recent_recall_success
```

## 23.4 数据表

### `t_learning_passport_snapshot`

```text
id
user_id
course_id

snapshot_type
snapshot_date

mastered_count
learning_count
at_risk_count

summary_json
evidence_summary_json

created_at
```

`snapshot_type`：

```text
MONTHLY
SEMESTER
PRE_EXAM
COURSE_COMPLETED
MANUAL
```

## 23.5 与页面关系

建议未来把 Statistics 升级成：

```text
Learning Profile
├── Activity
├── Mastery
├── Risk
└── Passport
```

避免同时存在三个难以理解的页面：

```text
统计
学习画像
学习护照
```

---

# 24. F18 — AI Study Pod：可选协作层

## 24.1 产品边界

不做：

```text
关注
粉丝
朋友圈
自由私聊
```

只做：

> 以知识互补为中心的学习互助。

## 24.2 推荐分两阶段

### V1：异步 Peer Teach-back

```text
用户 A Teach-back
   ↓
AI 脱敏 / 检查
   ↓
推荐给需要该 Concept 的用户 B
   ↓
B 完成验证
```

不做实时聊天，风险最低。

### V2：实时 Study Pod

```text
20 min Session

Round 1
A 向 B 解释 Concept X

Round 2
B 向 A 解释 Concept Y

Round 3
AI 生成交叉验证题

Reflection
```

## 24.3 数据表

### `t_study_pod`

```text
id
course_scope
status
mode
created_at
started_at
ended_at
```

### `t_study_pod_member`

```text
id
pod_id
user_id
role
matched_concepts_json
joined_at
```

### `t_study_pod_task`

```text
id
pod_id
user_id
concept_id
task_type
status
result_json
created_at
```

### `t_study_pod_message`

仅实时版需要。

## 24.4 安全要求

因为产品覆盖初中生：

- 默认不展示真实姓名；
- 禁止暴露不必要资料；
- 必须支持退出；
- 必须有举报/屏蔽；
- 实时版本必须增加 UGC 审核；
- 不建议在 Learning Brain 核心完成前开发。

---

# 25. 推荐数据库升级总览

## 25.1 保留现有核心表

```text
t_user
t_user_settings
t_course
t_record
t_record_file
t_transcript
t_ai_summary
t_knowledge_point
t_quiz
t_review_material
t_todo_item
t_chat_session
t_chat_message
t_share
t_quiz_test
t_quiz_test_item
```

扩展不应重复创建这些业务实体。

---

## 25.2 P0：学习数据基础

```text
t_transcript_segment
t_document_segment          （推荐）
t_source_anchor
t_record_marker

t_learning_event
t_learning_evidence
```

---

## 25.3 P1：Concept / Course Brain

```text
t_concept
t_concept_relation
t_record_concept
```

Qdrant：

```text
Transcript Segment Vector
Document Segment Vector
Knowledge Point Vector
Concept Vector
```

---

## 25.4 P1：Learner Brain

```text
t_user_concept_mastery
t_misconception
t_misconception_evidence
t_review_schedule
```

---

## 25.5 P1：Adaptive Learning / Planning

```text
t_teach_back_attempt

t_learning_goal
t_learning_plan
t_learning_plan_item

t_learning_agent_action
t_learning_agent_feedback
```

现有 `t_quiz / t_quiz_test` 继续升级字段，不另建 Adaptive Quiz 总表。

---

## 25.6 P2：Learning Outcome

```text
t_learning_passport_snapshot
```

`Learning Evidence` 已在 P0，不应因为 Passport 再复制一张 Evidence 表。

---

## 25.7 P3：Study Pod

```text
t_study_pod
t_study_pod_member
t_study_pod_task
t_study_pod_message
```

---

# 26. 建议的关键表关系

```text
t_course
   │
   ├── t_record
   │     ├── t_record_file
   │     ├── t_transcript
   │     │      └── t_transcript_segment
   │     ├── t_document_segment
   │     ├── t_record_marker
   │     ├── t_knowledge_point
   │     └── t_record_concept
   │
   ├── t_concept
   │     ├── t_concept_relation
   │     ├── t_user_concept_mastery
   │     ├── t_misconception
   │     ├── t_review_schedule
   │     └── t_learning_evidence
   │
   ├── t_learning_goal
   │     └── t_learning_plan
   │             └── t_learning_plan_item
   │
   └── t_learning_passport_snapshot

t_learning_event
   └── t_learning_evidence
          └── Mastery Engine

t_source_anchor
   ├── transcript_segment
   └── document_segment
```

---

# 27. 技术实现建议

> ⚠️ **历史快照（见 §0 对齐声明 D6/D7/D8/D13）**：本章 27.1~27.5 与 27.9 的技术选型（Java 系栈 / Qdrant / Redis / RabbitMQ / OTel+Langfuse）**已全部作废**，现行技术选型以《技术栈设计与审查-v4.5》为准。本章仅 27.6（FSRS 分阶段）、27.7（ECharts）、27.8（一期不做 TTS）的方向性结论仍有效。

> 以下技术以现有 PRD 与原扩展设计为基础，不为了“技术炫技”强行增加中间件。

## 27.1 继续使用的现有技术

```text
Java 17
Spring Boot 3.4.5
Spring AI 1.1.5
Spring AI Alibaba Agent Framework
DashScope / qwen-plus
MyBatis-Plus
MySQL
Redis / Redisson
MinIO
Tencent ASR
SSE
Sa-Token
```

---

## 27.2 Qdrant：推荐在 Course Brain 阶段引入

用途：

- Cross-record RAG；
- Transcript Segment Retrieval；
- Document Retrieval；
- Evidence Retrieval；
- Course Semantic Memory。

不把 Qdrant 当主数据库。

MySQL：

> 事实与关系。

Qdrant：

> 语义召回。

---

## 27.3 Neo4j：暂不作为必选

第一阶段：

```text
t_concept
t_concept_relation
```

足够。

当出现大量：

```text
三层前置查询
学习路径搜索
复杂图路径分析
共同薄弱依赖分析
```

再考虑 Neo4j。

---

## 27.4 Redis

继续用于：

- Cache；
- Lock；
- Agent 临时状态；
- 高频 Course Brain 缓存；
- Autopilot 首页推荐缓存；
- Learning Profile 缓存。

不承担长期事实存储。

---

## 27.5 RabbitMQ / 异步任务

如果当前项目已经具备异步任务体系，建议用于：

```text
Transcript Segment Embedding
Concept Extraction
Course Brain Re-index
Learning Event Consumption
Evidence Builder
Mastery Recalculation
Misconception Detection
Passport Snapshot
```

推荐事件流程：

```text
业务事务提交
   ↓
保存 Learning Event
   ↓
异步消费
   ↓
生成 Evidence
   ↓
更新 Mastery
```

需要保证幂等。

---

## 27.6 FSRS

第一版：

> 自己实现简单 Review Priority。

第二版：

> 引入/实现 FSRS 状态更新。

不要一开始把所有复习逻辑绑死在复杂算法上。

---

## 27.7 ECharts

用于：

- Knowledge GPS；
- Mastery Trend；
- Forgetting Radar；
- Learner Profile；
- Passport。

微信小程序端按当前技术体系使用适配方案。

Desktop 端后续可以直接使用 ECharts Web。

---

## 27.8 TTS

Teach-back 第一版不需要。

如果未来做：

```text
AI Tutor Voice
听 AI 复习
口语式教学
```

再增加腾讯 TTS / DashScope TTS。

---

## 27.9 AI Observability

Agent 增加后建议加入：

```text
Micrometer
OpenTelemetry
Langfuse（可选）
```

追踪：

```text
model
prompt_version
token
latency
stategraph_node
retrieval_count
evidence_count
action_accept_rate
recommendation_success_rate
```

---

# 28. 后端服务推荐拆分

```text
learning-brain
├── concept
│   ├── ConceptService
│   ├── ConceptRelationService
│   └── ConceptResolutionService
│
├── evidence
│   ├── LearningEventService
│   ├── EvidenceBuilder
│   └── SourceAnchorService
│
├── mastery
│   ├── MasteryEngine
│   └── MasteryQueryService
│
├── memory
│   ├── ForgettingEngine
│   └── ReviewScheduler
│
├── misconception
│   ├── MisconceptionDetector
│   ├── MisconceptionVerifier
│   └── MisconceptionService
│
├── learner
│   └── LearnerProfileService
│
├── coursebrain
│   ├── CourseRetrievalService
│   ├── CourseKnowledgeGraphService
│   └── CourseMemoryService
│
├── assessment
│   ├── AdaptiveAssessmentService
│   └── QuestionSelector
│
├── planner
│   ├── LearningGoalService
│   └── LearningPlanner
│
└── autopilot
    ├── CandidateActionBuilder
    ├── NextBestActionScorer
    └── AutopilotAgent
```

原 M3/M4/M5 Service 不必整体搬入 M7。

---

# 29. Agent / StateGraph 边界

不建议把整个系统做成一个超级 StateGraph。

建议：

## Summary Graph

继续使用现有：

```text
generate_summary
→ review_summary
```

## Tutor Graph

```text
load_context
→ diagnose
→ teach
→ wait_user
→ evaluate
→ verify
```

## Teach-back Graph

```text
listen
→ extract
→ evaluate
→ ask_followup
→ verify
```

## Autopilot Graph

```text
collect_state
→ candidate_actions
→ score
→ recommend
→ HITL
→ execute
→ verify
```

不同 Graph 可以通过：

```text
Learning Event
Learning Evidence
Learner Profile
```

共享状态，而不是互相嵌套成一个巨大流程。

---

# 30. 推荐 API 分组

不展开全部 REST 细节，但建议按能力分组。

```text
/api/learning/events
/api/learning/evidence

/api/courses/{courseId}/concepts
/api/courses/{courseId}/knowledge-gps
/api/courses/{courseId}/brain/chat

/api/concepts/{conceptId}/mastery
/api/concepts/{conceptId}/misconceptions
/api/review/today
/api/review/rescue

/api/tutor/session
/api/teach-back/session
/api/assessment/adaptive

/api/learning-goals
/api/learning-plans

/api/autopilot/today
/api/autopilot/actions/{id}/accept
/api/autopilot/actions/{id}/skip
/api/autopilot/actions/{id}/complete

/api/passport
```

---

# 31. 前端信息架构建议

## 31.1 首页

升级为：

```text
首页
├── AI 今日建议
├── 开始录音
├── 导入音频 / 文档
├── 最近课堂
├── 今日复习
└── 学习风险摘要
```

---

## 31.2 课程详情

```text
Course
├── Overview
├── Records
├── Course Brain
├── Knowledge GPS
└── Course Chat
```

---

## 31.3 课堂详情

保留 Summary 核心，同时增加：

```text
Record Detail
├── Summary
├── Transcript Timeline
├── Evidence
├── Knowledge Point
├── Quiz
├── Review
├── Todo
└── Ask AI
```

---

## 31.4 Learning Profile

```text
Learning Profile
├── Activity
├── Mastery
├── Forgetting
├── Misconception
└── Passport
```

---

# 32. 推荐开发路线

## Phase 1 — Learning Data Foundation

优先：

1. Transcript Segment；
2. Document Segment；
3. Source Anchor；
4. Marker；
5. Learning Event；
6. Learning Evidence。

**原因**：

后续高级能力几乎全部依赖这一层。

---

## Phase 2 — Course Brain

加入：

1. Concept；
2. Concept Relation；
3. Knowledge Point → Concept Resolution；
4. Qdrant；
5. Course-level RAG；
6. Evidence Chain；
7. Knowledge GPS v1；
8. Classroom vs Courseware Diff。

---

## Phase 3 — Learner Brain

加入：

1. Mastery Engine；
2. Mastery Confidence；
3. Forgetting Engine；
4. Review Scheduler；
5. Misconception Engine；
6. Digital Twin v1。

这是整个升级最关键的一阶段。

---

## Phase 4 — Adaptive Learning

加入：

1. Socratic Tutor；
2. Teach-back；
3. Adaptive Assessment；
4. Transfer Challenge；
5. Memory Rescue；
6. Personalized Preview。

---

## Phase 5 — Planner + Autopilot

加入：

1. Learning Goal；
2. Dynamic Learning Plan；
3. Next Best Action；
4. Autopilot；
5. Autopilot Feedback；
6. Recommendation Success Evaluation。

---

## Phase 6 — Learning Outcome

加入：

1. Learning Profile；
2. Passport；
3. Monthly Snapshot；
4. Semester Snapshot；
5. Course Completion Snapshot。

---

## Phase 7 — Optional Collaboration

根据项目规模决定是否实现：

1. Async Peer Teach-back；
2. Study Pod；
3. 实时多人会话；
4. 审核与安全系统。

---

# 33. 核心创新点最终建议

如果用于毕业设计、项目展示或比赛，不建议平均展示 18 个能力。

建议包装以下 5 个核心创新：

## 创新 1：Evidence-driven Course Brain

> 将课堂录音、文档、知识点转化为可追溯的课程语义记忆和 Concept Graph。

---

## 创新 2：Learner Digital Twin

> 不只记录用户做过什么，而是持续维护 Concept-level Mastery、Memory、Misconception 和 Confidence。

---

## 创新 3：Misconception + Forgetting Diagnosis

> 系统不仅知道“答错”，还判断“为什么没掌握”和“什么时候会忘”。

---

## 创新 4：Adaptive Learning Engine

> Tutor、Teach-back、Adaptive Assessment、Review、Challenge 根据用户状态动态选择教学策略。

---

## 创新 5：AI Learning Autopilot

> AI 根据长期学习状态计算 Next Best Learning Action，但始终由用户确认后执行。

---

# 34. 最终产品定位

## 当前阶段

> **AI课堂助手**  
> 把课堂录音和资料转化为总结、知识点、习题、复习资料，并提供课堂上下文问答。

## 升级阶段

> **AI Personal Learning Brain**  
> 持续理解学生学了什么、掌握了多少、为什么没有掌握、什么时候会忘，以及下一步最值得学习什么。

## 长期定位

> **AI Learning OS**  
> 把课前、课堂、课后、练习、复习、Tutor、考试规划、长期记忆和学习决策组织成一个持续运行的智能学习系统。

核心变化不是：

> AI 能生成更多内容。

而是：

> **AI 开始维护可解释、可验证、可更新的长期学习状态，并基于该状态做下一步学习决策。**

---

# 35. 最终范围边界

本次升级明确不包含：

- 排行榜 / XP 联赛；
- 会员付费；
- OCR；
- 通用社交平台；
- 自由朋友圈；
- 无来源的“AI 自动认定掌握”；
- 未经用户确认的自动学习执行；
- 第一阶段强制引入 Neo4j；
- 第一阶段强制引入复杂推荐模型。

保留的长期可选能力：

- Study Pod；
- TTS Tutor；
- Neo4j；
- 更复杂的个性化决策策略；
- 外部权威资料检索。

---

# 36. 数据与隐私补充

Learning Brain 会比当前 PRD 保存更多行为数据，因此需要额外注意：

1. Learning Event 只能用于学习功能；
2. Course Brain Retrieval 必须带 `user_id` 数据隔离；
3. Study Pod 不可直接暴露对方完整 Learning Profile；
4. Misconception 属于系统推测，前端应使用“可能”“待验证”等措辞；
5. Learner Digital Twin 中的推测属性必须带 Confidence；
6. 用户删除课程/Record 后，应明确对应 Segment、Anchor、Vector、Evidence 的清理策略；
7. Qdrant 向量删除应与 MySQL 软删除/物理删除策略保持一致；
8. 不在日志中保存完整课堂转写、Teach-back 全文或敏感聊天内容。

---

# 37. 最终实施优先级

如果资源有限，只做最关键链路：

```text
P0
Transcript Segment
Source Anchor
Learning Event
Learning Evidence
Concept
Course Brain
Mastery Engine

P1
Knowledge GPS
Forgetting
Misconception
Adaptive Assessment
Teach-back
Digital Twin

P2
Dynamic Planner
Autopilot
Learning Passport
Pre-class Preview

P3
Study Pod
```

最推荐的最小创新闭环：

```text
课堂
 ↓
Segment + Evidence
 ↓
Concept
 ↓
Mastery
 ↓
Forgetting / Misconception
 ↓
Autopilot Recommendation
 ↓
Adaptive Quiz / Review / Teach-back
 ↓
New Evidence
 ↓
Mastery Update
```

只要这个闭环真正跑通，产品就已经不再只是“AI 笔记生成器”，而具备了 **AI Learning Brain** 的核心特征。

---

# 38. 来源与设计边界说明

- 现有业务基线来自旧《AI课堂助手 PRD v2.1》（该文档已删除，有效内容现以《KnowRealm-AI-功能需求基线 v2.7》为准）。
- 原创新方向来自 `AI课堂助手-创新功能扩展设计-v1-去除排行榜.md`。
- 本最终版对原扩展文档做了结构收敛与歧义消除，包括：
  - Knowledge Point 与 Concept 分层；
  - Course Brain 拆分为 Knowledge Graph + Semantic Memory；
  - Learning Event 与 Learning Evidence 分层；
  - Mastery 统一写入口；
  - Misconception 增加 SUSPECTED / CONFIRMED / RESOLVED / DISMISSED；
  - Digital Twin 增加 Confidence 与“数据不足”；
  - Socratic Tutor / Teach-back / Challenge 统一归入 Adaptive Learning；
  - Adaptive Exam 明确为现有 Mock Test 的升级；
  - Todo / Plan / Autopilot Action 明确边界；
  - Autopilot 明确“主动推荐、用户确认执行”；
  - Study Pod 降级为可选 Collaboration Layer；
  - 新增 Classroom vs Courseware Diff；
  - 新增 Personalized Pre-class Preview。
- 本文涉及的新增表、字段与服务属于下一阶段设计建议，不代表当前 PRD 已实现。

---

# 39. 技术评估结论（2026-09-08 评审，2026-09-14 随交付同步）

> **评估性质**：基于《功能需求基线 v2.7》决策 #1~#59、代码库实现现状（backend 19 个 feature-first 模块、21 张迁移、Summary / ReviewMaterial / Chat 三图在产——chat 以 deepagents 骨架装配（ADR-0018）、`learning_events` 四事件写入 + 独立消费循环已落地（ADR-0021））与《chatgpt根据需求文档和扩展功能文档给出的结论.md》，对扩展方向、Agent 架构演进、新业务方向与技术栈的核验裁定。本章为评审记录：**优先级 / 技术选型 / 表结构的权威仍在三份权威文档**，本章结论与之冲突时以权威文档为准（目前零冲突）。

## 39.1 ChatGPT 方案核验

**总体：采纳，与现行基线零冲突。** 其"开发优先级重排"（第一阶段 = Segment / Source Anchor / Learning Event / Evidence / Concept / Mastery）实质是基线 §5.1 阶段规划 P2+P3+P4 数据主链的复述，属第三方确认而非新信息。S 级判断（Evidence+Mastery 为核心、KP≠Concept 分离、Autopilot 勿早做）与红线 #2/#3/#7/#9 一致；过度设计提醒（Digital Twin 前端改称学习画像、Study Pod 降级）与基线 P8 排期一致。

其三个"新增方向"逐项核验：

| 建议 | 核验结果 | 处置 |
|---|---|---|
| Learning Memory Layer（长期学习习惯记忆） | 部分新增——F10.4 已有 `observed_learning_preference`，缺"容易忘什么/惯常混淆什么"的沉淀 | 并入 P4 LearnerProfileService（视图 + 一张轻表）；禁止演化为第二套 Evidence |
| Knowledge Transfer Detection（知识迁移检测） | **设计已有，ChatGPT 漏看**：mastery 表 `transfer_score`、`TRANSFER` evidence 类型、F13 Transfer Challenge 三处已覆盖 | 无需新增，按 P4/P5 既定设计实施 |
| Learning Journey Timeline（学习成长时间线） | 好主意且低成本——本质是 `learning_events` 的时间轴回放 UI | 排 P6/P7，与 Passport 同期产出，不提前 |

对其文档两个盲区的补充：

1. 其建议未做本地优先约束核对——已补核：全部建议兼容本地优先与十二条红线，不要求任何云依赖；
2. 其未讨论闭环真实风险——**风险不是架构而是数据稀疏与算法验收**（个人单用户冷启动期证据量小）：P4 开工须先建 Mastery/遗忘公式黄金样本与 REPL 验证脚本（#46 按阶段评测纪律的延伸），先验算法再接 Graph。

定位建议："Open-source Local-first AI Learning Brain" 可采纳为对外传播语；产品文档定位（基线 §1.1 三阶段演进）不改版。

## 39.2 Agent 架构演进判定

**前置结论：当前架构已具备 Agent 化结构条件，无需提前调整模块划分。** 判据：①interrupt/HITL 已在生产验证跨重启恢复；②"确定性 Service 与 Graph 分离"已是红线 #2；③Graph 间共享状态走业务表（Event / Evidence / Learner Profile）而非运行时编排（§29 定稿）。缺的是 P2 数据层，不是架构改造。

九项 Agent 能力逐项裁定：

| 能力 | 裁定 | 理由与落位 |
|---|---|---|
| ReAct Agent | ✅ 已有 | chat 以 deepagents 骨架装配 `create_agent` 循环（#53；ADR-0018） |
| Agent Tools | ✅ 已落地（P2） | `search_transcript`（2026-09-13，分片级 FTS）+ `web_search`（2026-09-14，Tavily，#53）均已上线；工具=普通 Python 函数 + Pydantic 同源 schema；按域隔离遵守红线 #11（工具仅聊天域，Summary/Tutor/TeachBack 禁联网） |
| RAG | ✅ 已规划 | FTS5+jieba 已交付；sqlite-vec + 混合检索 P2；课程级 RAG P3；不引新框架 |
| Memory | ✅ 分层落地 | 三层：chat memory（已有，逐轮重建）→ learner state（P4 业务表）→ 学习习惯记忆（39.1 并入 LearnerProfileService）；不引 mem0/letta 类记忆框架（单用户场景 SQLite 业务表即记忆） |
| Plan-and-Execute | ✅ 域内实现（P6） | Autopilot Graph 本质即此模式 + HITL；候选动作打分是确定性规则（红线 #8），自制域逻辑不套库模板 |
| Reflection | ⚠️ 域内轻量已有，通用机制延后 | 域内反思已设计：Misconception 验证环、Summary 反馈循环、评分低置信复核（#20）；通用反思循环 token 成本翻倍，BYO-key 用户敏感，仅在评测证明必要处引入 |
| Skills 技能系统 | ❌ 不做通用框架 | YAGNI——七类 prompt + 结构化输出 + prompt_version 已是轻量形态；用户自定义学习模式以"场景包"承载（39.3），不做开发者级 skill 框架 |
| MCP | ⚠️ 延后评估（P3+） | 分两向：MCP client（用户接入外部工具服务器）在 chat 内部工具体系稳定后评估，受红线 #11 约束只能进聊天域；MCP server（对外暴露本产品能力）不符合单机个人数据定位，不做 |
| Multi-Agent | ❌ 否决 | 红线 #2 明令禁止超级 Graph；多 Graph 经 DB 共享状态优于运行时 agent 间通信；DeepAgents 仅取 create_agent + 中间件骨架（ADR-0018），其子 agent / 虚拟文件系统规划不采用 |

需提前建设的基础设施（便宜且 P2 全要用）：

1. **事件消费框架**：✅ 已落地（2026-09-14，ADR-0021）——独立 asyncio 水位消费循环（不入 processing_jobs），`Event → Evidence` 管道定型，Mastery / Misconception / 学习上下文后续全部挂接；
2. **评测资产按阶段扩**：Mastery/遗忘公式黄金样本、agent 工具调用轨迹断言；
3. **卫生项**：✅ 已完成——`CHAT_PROMPT_VERSION` 已随工具交付 bump（v3→v4）、`.claude/rules` 八事件镜像同步。

## 39.3 新增业务方向扩展分析（场景包机制）

五个候选方向（AI 面试助手 / 项目总结分析 / 简历智能修改 / 职业能力分析 / 学习成长规划）共享同一基质：**捕获 → 结构化理解 → 个性化状态 → 推荐**。它们是 Learning Brain 引擎之上的**消费者**，不是五个并列新引擎。落地方案 = **场景包**（prompt 模板资产化 + 会话模式 + goal_type 扩展 + UI 入口），禁止为每个方向建独立领域模块。

| 方向 | 判定 | 依赖与形态 |
|---|---|---|
| 学习成长规划 | 完全融入 | = F14 动态规划 + Autopilot（P6）；CAREER 场景已是 `learning_context` 一等公民，零新增 |
| 项目总结分析 | 完全融入 | 走现有捕获管线（P2 剪藏起自然获得）；增量仅 CAREER 场景 prompt 基调与导出模板 |
| AI 面试助手 | 拆两义 | **面试模拟/练习**：契合度高——Tutor Graph 变体 + 自适应测验 + Transfer Challenge，面试表现天然是 TRANSFER 证据，P5 后以场景包进入；**实时面试外挂（听题喂答案）：明确否决**——违背学习产品价值观，法律/平台风险损毁开源声誉 |
| 职业能力分析 | 契合但依赖地基 | = Knowledge GPS 的 CAREER 技能空间视图（掌握度地图 + 缺口分析）；P3 Concept / P4 Mastery 之前是空壳 |
| 简历智能修改 | 半契合，降级为对话形态 | 简历 = 特殊资料类型 + AI 对话挂载 + 结构化修改建议（对话产物可导出）；"修改简历"是文档编辑工作流、与 Record 学习资产模型不同构，**不建独立简历编辑器** |

架构影响仅三处轻扩展：`goal_type` 枚举扩（INTERVIEW/CAREER 类）、场景包 prompt 资产、CAREER 主题 UI 入口——不触碰模块划分与数据模型主干。

定位风险管理：五方向一次全上会从"学习大脑"漂移成"求职工具箱"，稀释 Evidence/Mastery 壁垒。渐进顺序：**项目总结分析（P2 顺手）→ 职业能力分析（P4 后）→ 面试模拟（P5 后）→ 简历建议（对话形态）**。商业化按 ADR-0014 纪律（运营云服务那天才动账号体系）。

## 39.4 技术栈裁定

| 候选 | 裁定 | 理由 |
|---|---|---|
| FastAPI | 保留 | OpenAPI codegen 契约链在产（#56：40+ 端点单一事实源 + UniApp 未来复用） |
| LangChain / LangGraph | 保留并深耕 | interrupt/HITL 是核心差异化、无等价替代（#56 否决全 Rust 重写的理由）；1.3/1.2 版本组合已核实 |
| LlamaIndex | 不引 | 需求面 = 课程级/全局 RAG，LangChain retriever + sqlite-vec 完全覆盖；两框架 = 两套抽象重复造轮子。重评触发：复杂多格式文档索引管道且 LangChain 侧明显吃力 |
| DeepAgents | ✅ 已引入（chat 骨架，ADR-0018） | 仅取 create_agent + 中间件装配形态；子 agent / 虚拟文件系统规划不采用（红线 #2 禁超级 Graph） |
| Pydantic AI | 不引 | 双 agent 框架违反单栈纪律；其类型安全优势已由 Pydantic 同源 Schema 覆盖；保持观察 |
| 向量数据库 | sqlite-vec（已定案） | Qdrant/pgvector 在不做清单；个人学习数据量远达不到 SQLite 不适区 |
| 工作流引擎（Temporal 等） | 否决 | processing_jobs 自研队列已过后端轮子审计（单人单进程下分布式编排是负资产） |
| 消息队列（Redis/RabbitMQ/Celery） | 否决 | 不做清单明列；事件传播 = SQLite 表 + 进程内 asyncio（#1） |
| 独立搜索引擎（ES） | 否决 | FTS5+jieba 已交付；trigram → sqlite-vec 演进路线已定 |
| Langfuse / OTel | 否决 | 不做清单明列；`llm_call_logs` 一张表已满足个人量级（#2） |
| fsrs（py-fsrs） | P4 引入 | 遗忘引擎 V2（V1 规则公式先行，勿倒置） |
| Tavily API | P2 引入 | chat web_search（#53，SearchProvider 抽象预留博查/智谱） |

重复造轮子核查：沿用 2026-08-29 后端轮子审计定稿——无高优先级替换项；JobRunner / ASR 客户端 / 迁移系统维持自研的论据仍然成立。

## 39.5 开发规划（短 / 中 / 长期）

- **短期（~1-2 月）**：P2 主体已交付——F1 Segment+Source Anchor（09-10）→ A3 Evidence Builder（09-14）→ A1+A2 chat 检索工具与前端呈现（09-13，并行槽）→ B1 web_search（09-14）；plan 20 收尾与 prompt_version 清理已完结。余：资料库 V1 + 网页剪藏首适配器、英文语料验证；sqlite-vec 后移 B5（真实语料召回吃力再进）。
- **中期（3-6 月）**：P3 Course Brain（Concept 抽取消歧、课程级 RAG、Knowledge GPS v1、课件 Diff）；P4 Learner Brain（Mastery 确定性算法黄金样本先行、遗忘 V1 规则、Misconception 状态机、Digital Twin 视图）；职业场景包第一弹（项目总结分析）。
- **长期（6-12 月+）**：P5 Adaptive（Tutor / Teach-back / 自适应测验 + Transfer，面试模拟场景包在此进入）；P6 Planner+Autopilot（最小创新闭环跑通 = 产品分水岭）+ Learning Journey Timeline；P7 Outcome（Passport / Learning Profile 整合）；MCP client 评估（若 chat 工具生态需求成立）；商业化触发评估（ADR-0014）。

## 39.6 必须新增或调整的关键能力（按重要性排序）

1. **P2 数据地基**（Segment / Source Anchor / Evidence Builder）——一切 Agent 决策能力的前提，且 Evidence 不可再生（每晚一天上线，丢失一天不可补的积累），是唯一"越早越好"项；
2. **chat 工具层落地**——从"带上下文的聊天"到"能行动的 Agent"的第一步，架构位已预留（`create_agent` + `tools=[]`）；
3. **事件消费 / Evidence 异步管线**——闭环管道件，P2 定型，Mastery/Misconception 后续全部挂在它上面；
4. **算法评测资产前置**——Mastery/遗忘公式黄金样本（数据稀疏是 P4 真实风险，先验算法再接线）；
5. **场景包机制**——新业务方向的统一容器（goal_type 扩展 + prompt 模板资产化），避免每个新方向长出独立模块；
6. **卫生项**——prompt_version bump 纪律、`.claude/rules` 镜像同步。

---

# 40. Agent 能力建设评估与开发跟进清单（2026-09-09 建立，2026-09-14 随交付同步）

> **评估性质**：基于代码库实际状态（`feat/extend-dev-05`，1df1f3f）对 Agent 化就绪度做的核验，与 §39 裁定及基线 §5.1 阶段规划零冲突。§40.3 的 A 档与 B1/B2/B5 属**基线 P2 已定项的就绪度核验与实施细化**；B3 与「课堂功能降后」为**排期增量建议（⚠️ 待决策）**。本章为评审记录，优先级 / 技术选型 / 表结构的权威仍在三份权威文档。文中代码引用已同步至 B1 交付后（2026-09-14）状态。

## 40.1 架构 Agent 化适配度核验（代码证据）

**结论：架构已具备 Agent 化条件，无需改造模块划分（独立复核确认 §39.2 前置结论）。**

五项已就绪的结构条件：

1. **Agent 循环与工具已在产**：chat 以 deepagents 骨架装配（ADR-0018，`backend/app/modules/agent/graph.py` 的 `build_agent` / `build_chat_agent`）；`AgentConfig.tools` 已挂 `search_transcript`（挂载会话，2026-09-13）与 `web_search`（每请求开关，2026-09-14）两工具；
2. **HITL 已跨重启验证**：Summary / ReviewMaterial 两 graph 的 `interrupt()` 人工确认环（各自 `graph.py`）在生产多版本运行，断点恢复能力已被验证；
3. **检索基建双轨就绪**：全局搜索唯一入口 `SearchService`（`backend/app/modules/search/service.py`，FTS5+jieba、BM25 列权重、写路径同事务 upsert、启动幂等回填）；chat 检索工具按 A1 定稿走分片级 FTS（迁移 0020 `segment_search_index`，命中回业务表取逐字原文，无分片记录退化为全文子串）——未直接包装 SearchService（全局索引 snippet 产自 jieba token 串非逐字原文、索引 body 截断 30,000 字符）；
4. **引用契约前后端闭环且已判别化**：`ChatCitationOut`（`agent/schemas.py`，`[n]` 角标 + 80 字摘录，`source` 判别 record / web）→ 前端 `ChatCitationList` 角标定位高亮（`ChatMessageList.tsx`）+ `useOpenCitation` 打开（record 跳转转写页逐字校验 / web 外链经系统浏览器，B1）；
5. **两条异步管道在产**：JobRunner 自研队列带崩溃恢复（`jobs/runner.py` 的 `recover_running_to_failed` / `recover_interrupted`）；`learning_events` 独立 asyncio 水位消费循环（ADR-0021）。

当前真实缺口（按严重度）：

1. **单记录挂载限制**：`ChatSessionCreate.record_id` 为单值，用户无法跨记录提问（基线 #24 已定 P2 以「@全部资料全局 RAG」解除——B2 已实施，2026-09-14）；
2. **长材料降级保留为保底**：`build_context_messages` 在转写超过 30000 字符时降级为"已确认摘要 + 知识点全文 + 近三轮引用摘录"并告知模型"缺失细节不可推断"；挂载会话细节由 agent 经 `search_transcript` 主动检索找回。

架构洞察：chat 每轮发送前清空 checkpoint、以业务表为唯一记忆源（`stream_chat_reply` 轮初 `adelete_thread`）。这对工具化**有利**——工具循环中间态不跨轮持久，不存在 checkpoint 膨胀与跨轮工具状态泄漏问题。

## 40.2 六大 Agent 能力应用细化（对 §39.2 的代码级补充）

| 能力 | §39.2 裁定 | 代码级细化 |
|---|---|---|
| Agent Tools | ✅ 立即做 | 第一工具 `search_transcript`（2026-09-13 已实施：分片级 FTS + 挂载内单工具；原"直接包装 `SearchService.search`"设想据两代码事实修正，见 §40.3 A1 行）；工具引用结果落 `citations_json` 契约复用前端；挂载会话超 30k 转写保留"降级塞摘要"保底，细节由 agent 主动检索找回 |
| RAG | ✅ 已规划 | FTS5 已覆盖关键词检索，向量不急于上——BM25+jieba 对中文学习语料够用；sqlite-vec 等"同义改写问不出"成为真实抱怨再进（#24 `semantic_embeddings.course_id` 可空已预留） |
| Memory | ✅ 分层，不引框架 | 现状 = 逐轮重放业务表（最近 N 轮 + 字符预算窗口），**跨会话零记忆**；最小可行增量：学习偏好沉淀进 profile（SQLite 业务表即记忆，否决 mem0/letta） |
| Agent Workflow | ✅ 域内 graph | 现有 3 graph 的"确定性 Service 与 Graph 分离"模式正确；Autopilot 的 Plan-and-Execute 留 P6，勿提前 |
| MCP | ⚠️ 延后 | 维持 §39.2 判断，触发条件具体化：**自研工具 ≥3 个且工具调用轨迹评测通过后**再评估 MCP client；MCP server 不做 |
| Multi-Agent / Skills 框架 | ❌ 否决 | 多 graph 经 DB 共享状态优于运行时 agent 通信（红线 #2）；用户自定义学习模式走场景包机制（§39.3），不做开发者级 skill 框架 |

## 40.3 功能分档清单（开发跟进用）

价值图例：★★★ = 核心跃迁 / 长期壁垒；★★ = 显著增益；★ = 增益项。难度为相对工作量估计。

### A 档：立即做（基建全备，P2 主体）

| # | 功能 | 基线对应 | 价值 | 难度 | 落地要点 |
|---|---|---|---|---|---|
| A0 | F1 Segment + Source Anchor（P2 数据地基第一步，2026-09-09 定为先做） | F1（§7）/ §37 P0 第一项 / §39.5 P2 首位 | ★★★ | 中 | 迁移 0019 起：transcript_segments（句子级）、document_segments、source_anchors、source_anchor_links 四张新表（数据模型 v2.9 §4.5，**已实施**——2026-09-10 六票+07 补票完结，见 §7 回写；learning_evidence 随 A3）；转写定稿 / 文档导入时切分写入 + 存量回填；引用从"80 字摘录"升级为转写时间戳 / 文档页码定位（前端跳转高亮已有）；是 A3 的数据前置 |
| A1 | Chat 检索工具（Agent 第一工具） | 基线 §4.7"检索为第一工具"（#53） | ★★★ | 中低 | **已实施（2026-09-13，A1+A2 三票完结）**：实现形态定为「分片级 FTS 索引 + 挂载内单工具 `search_transcript`」（迁移 0020 `segment_search_index`，jieba 分词 + BM25；命中回业务表取逐字原文，无分片记录退化为全文子串）。与 §40.2 原设想「直接包装全局 `SearchService.search`」的差异源于两处代码事实：全局索引 snippet 产自 jieba token 串（非逐字原文，无法通过引用逐字校验）、索引 body 截断在 30,000 字符（覆盖不了 >30k 转写痛点）；`search_library` 留给 B2 连同跨记录范围胶囊一并设计。>30k 降级材料保留保底，`CHAT_PROMPT_VERSION` bump v3 |
| A2 | 工具调用的前端呈现 | ——（基线未细化的实施项） | ★★★ | 中 | **已实施（2026-09-13）**：SSE 增 `tool_call` / `tool_result` 事件（消息流内检索状态卡「正在检索 → 命中 n 条 / 失败」，多次检索逐条陈列）；过程态与流式文本同生命周期、done / 中断后消失，不持久化（历史消息仍只有正文与引用）；右栏工具开关已由 B1 接真（2026-09-14，联网搜索按会话记忆） |
| A3 | 事件消费框架 + Evidence Builder 最小版 | Phase 2 Learning Evidence | ★★★ | 中 | **已实施（2026-09-14，learning-evidence 四票完结，ADR-0021）**：四事件（总结确认 / 知识点确认 / 逐题作答 / 交卷）与业务动作同事务写入（统一经 `learning.events.write_learning_event`，幂等键 `{event-slug}:{source-id}`）；消费为独立 asyncio 水位循环——原「复用 JobRunner」设想按 ADR-0021 修正为不入 processing_jobs（毫秒级纯函数转换，领取协议属过度设计），水位 = SQLite 隐式 rowid 单调扫描（`learning_events.id` 是 uuid4 非单调）、禁 NOT EXISTS、event_id 预查幂等 + 唯一约束兜底、失败 3 次跳过不建死信表；映射集中声明（QUIZ 0.9/0.8、CONFIRMED → USER_CONFIRMATION 0.3·0.4/0.7、交卷不产证据防双计）；证据可由事件流清空重放再生；learning 域薄只读查询按记录/课程取证据流（Mastery / 学习上下文中间件共同底座）；零 LLM / 零前端 / 零新 API；concept_id / source_anchor_id 恒 NULL 留 P3/P5 |

### B 档：P2 后期 ~ P3（依赖 A 档）

| # | 功能 | 基线对应 | 价值 | 难度 | 落地要点 |
|---|---|---|---|---|---|
| B1 | Web search 工具 | #53 / Phase 2 | ★★ | 低 | **已实施（2026-09-14，web-search 两票完结）**：薄 `SearchProvider` Protocol + 仅 Tavily 一家实现（httpx 直连零新依赖，`trust_env=True` 尊重系统代理——与 LLM 端点的动机不同，见票 01 审查备注）；开关 = 每请求 body 参数 `web_search`（默认 false 零迁移、不落库），前端按会话 Zustand 记忆（重启重置），默认自由 ON / 挂载 OFF；无 key 后端无视标志强制不挂工具（前端置灰之外的双保险）；`citations_json` 条目判别化（record 逐字校验不变 / web `{index,source:"web",url,title}` 仅非空检查），前端 web 条目渲染外链经系统浏览器打开；SSE `tool_call`/`tool_result` 零改动复用（工具卡文案按 tool 名分流）；`CHAT_PROMPT_VERSION` bump v4；不做搜索快照持久化（grill Q10 定稿） |
| B2 | 跨记录 / 课程级问答 | #24「@全部资料全局 RAG」（P2 已定） | ★★★ | 中 | **已实施（2026-09-14，cross-record-qa 单票全栈完结）**：`chat_sessions.scope` 显式四档列（迁移 0022，FREE/RECORD/COURSE/ALL，与 mode 轴正交）；COURSE/ALL 会话挂 `search_library` 跨记录工具（分片 FTS top-8 BM25 + FTS 零命中 LIKE 兜底，与 `search_transcript` 互斥挂载）；上下文 = 记录标题清单（约 4000 字符预算，超出取最近并注明）+ 检索指引 + 跨记录引用格式；引用行 `[n] 摘录（来源：标题）`，归属由校验器裁定（标题定位→逐字→仅候选内模糊；无候选全范围逐字兜底、禁全范围模糊对齐），落库携 `record_title` 快照；`CHAT_PROMPT_VERSION` v5；软删过滤沿用查询期回表；范围胶囊 / 新建菜单 / 课程详情对话 Tab 前端接真（记录范围行为零回归） |
| B3 | Tutor / Teach-back 场景包最小形态 | ⚠️ 增量建议（§29 的 Tutor / TeachBack Graph 留 P5） | ★★ | 低 | `ChatMode` 四模式枚举已预留但 `Literal[ChatMode.ASK]` 仅启用一种（`agent/schemas.py`）；**不建独立 Graph**，以 prompt 模板 + 模式开关先行，作为场景包机制（§39.3）首个验证实例；苏格拉底辅导是通用学习工作台最正交的 AI Native 功能 |
| B5 | sqlite-vec 向量混合检索 | #24 / Phase 2 | ★ | 中 | 语义检索增益项，等 BM25 真实吃力再进。**CB-01（2026-09-15）合成评测四维全过 → 维持延后**，触发条件修正为「真实语料词汇不重合失败」；升级路径按优先级：① `concepts.terms` 同义词列 ② query-time LLM 查询扩展 ③ 引入 sqlite-vec（届时新开 CB-VEC 票） |
| B6 | 对话转学习资产 V1（对话转知识点） | 基线 Phase 2 已定项（:261「问→懂→沉淀」闭环） | ★★ | 低~中 | **已实施（2026-09-15，chat-to-knowledge-point 单票全栈完结）**：`POST /chat-sessions/{sid}/messages/{mid}/knowledge-points` 把 AI 回答保存为目标记录知识点；单事务四写（知识点 ACTIVE + 搜索索引 + CHAT_MESSAGE 锚点〔**锚点体系首个写入者**〕+ KNOWLEDGE_POINT/PRIMARY 链接，事务由路由编排层统一管理——校验查询 autobegin 与 Service begin 冲突的定案解）；`KnowledgePointOut.chat_source` 三表 JOIN 派生回溯（不回查会话软删），前端「源自 AI 对话」徽章跳回原会话；全 scope 可保存、目标记录选择器（RECORD 默认挂载记录）、detail 预填聚焦摘要（首段 + 引用句纯函数提取）；**零学习事件**（AI 自述不是 Evidence 红线，防沉淀污染掌握度证据）；零迁移（四表现成）。锚点写入函数落位 `SourceAnchorService`（无独立事务约定，P3 Concept 等后续写入者直接复用） |
| B7 | F4 Course Brain / Concept V1（**原 P3，提前至 P2 期实施**） | 扩展 §10（F4，S+）/ §25.3 | ★★★ | 中高 | **已实施（2026-09-15~16，course-brain-v1 十二票完结，ADR-0022）**：三张 Concept 表（迁移 0023，CONFIRMED 唯一由部分唯一索引库级兜底）+ 课程级 `CONCEPT_EXTRACTION` 构建 job（多来源收集 / 分块 LLM 结构化抽取 / 确定性归一化挂接 / 逐字锚点 / 单事务原子发布，重建不覆盖 CONFIRMED 名称与描述）+ 审核闭环（apply-review 五决策单事务、merge 锚点与出现迁移、合并建议读取期确定性派生、关系候选审核、stale 待归档与关系过期徽章查询期派生、手动创建 / 归档）+ B2 `search_library` 概念增强（Concept FTS top-4 → canonical_name 并跑分片 FTS，occurrences 按 record 去重，`CHAT_PROMPT_VERSION` v6）+ 可观测（`llm_call_logs.retrieval_count` 埋点 / 检索工具体异常 ok=false 不炸流 / apply-review 审计日志）+ 前端 Course Brain 主页面（六态状态机 / 图谱列表双视图 / 候选审核抽屉 / Relation 审核区 / 详情与来源跳转，mock 图谱链删除）。sqlite-vec 维持延后：CB-01 合成评测四维全过（`docs/evaluation/course-brain-retrieval-baseline.md`） |

> 2026-09-09 修正：原 B4（Segment + Source Anchor）即 F1 本体，是 A3 的**数据前置**而非其依赖项，已前移至 A 档 A0——与 §39.5 P2 顺序（Segment+Anchor → Evidence Builder → …）对齐，引用精度升级要点并入 A0 行。

### C 档：P4+（地基依赖，维持既定排期）

Mastery Engine + fsrs 遗忘调度（黄金样本先行）、学习习惯记忆（LearnerProfileService 轻表，§39.1 已并入 P4）、Autopilot（P6 产品分水岭）、MCP client 评估（触发条件见 40.2）、场景包第二弹（项目总结分析，剪藏落地后顺手）。

### 明确不做 / 进一步降后

- §39.4 技术栈裁定维持：Multi-Agent、通用 Skills 框架、mem0/letta、MCP server、LlamaIndex；DeepAgents 已按 ADR-0018 以 chat 骨架形态引入（子 agent / 虚拟文件系统规划仍不采用）；
- ⚠️ **增量建议（待决策）**：从"通用 AI 学习工作台"定位出发，课堂专属功能（F2 课堂实时标记、F3 课件 Diff）进一步降后——§37 关键链路本就不含它们，通用主链 = 捕获 → 结构化理解 → 个性化状态 → 推荐。

## 40.4 下一阶段开发路线（P2 统一序列，2026-09-09 修订）

> 修订说明：本节原为"双轨并行"表述，未标明先后顺序、与 §39.5 短期规划的对齐关系不清，当日修订为统一序列。**起点已定：F1 先做**（2026-09-09 决定，与 §37 P0 第一项、§39.5 P2 顺序一致）。

```text
第 1 步   F1 Segment + Source Anchor（A0）   ← ✅ 已完成（2026-09-10）
第 2 步   A3 Evidence Builder 管道            ← ✅ 已完成（2026-09-14，见 §40.3 A3 行）
  ┆ 并行槽（不依赖 F1 / A3，可随时插入，单独成线）
  ┆   A1 chat 检索工具 → A2 工具调用前端呈现   ← ✅ 已完成（2026-09-13，见 §40.3 A1/A2 行）
第 3 步   B1 web_search（Tavily，#53）        ← ✅ 已完成（2026-09-14，见 §40.3 B1 行）
第 4 步   B2 跨记录 / 全局问答（#24 @全部资料） ← ✅ 已完成（2026-09-14，见 §40.3 B2 行）
第 4.5 步 B6 对话转学习资产 V1（基线 Phase 2 已定项，B2 价值闭环） ← ✅ 已完成（2026-09-15，见 §40.3 B6 行）
+ 插入步  F4 Course Brain / Concept V1（原 P3，提前实施，ADR-0022） ← ✅ 已完成（2026-09-16，见 §40.3 B7 行）
第 5 步   B5 sqlite-vec 混合检索（CB-01 合成评测全过 → 维持延后，真实语料吃力时进）
其后      ~~Concept Mastery 收尾~~ ✅ 已完结（2026-09-18，concept-mastery-v1 六票，ADR-0023，数据模型 v2.9）→ 资料库 V1 + 网页剪藏首适配器（§41/§42）→ 长内容与其他知识起点；B3 继续压后
```

> 2026-09-16 补记：F4 Course Brain / Concept V1 由 P3 提前实施并完结（原计划序列「其后 → P3 Course Brain」已兑现完毕），数据模型随之升 v2.8（§4.6 三表标已实施）；B5 的升级前置评测（CB-01）已先行完成，结论与升级路径见 §40.3 B5 行。

与 §39.5 短期顺序（Segment+Anchor → Evidence Builder → sqlite-vec → chat 工具层+web_search → 剪藏/英文）的唯一差异：**chat 工具层（A1+A2）由串行第 4 位改为并行槽**——它不依赖任何数据层成果（检索入口与引用契约现成），提前插入使 Agent 感知线与数据资产线同时推进；sqlite-vec（B5）相应后移到真实需要时。此为并行化建议，按 §39.5 原序串行执行亦完全成立。

排序理由：

1. **F1 先行**——§37 P0 第一项与 §39.5 既定顺序；A3 与 Mastery 主链的数据地基（Evidence 挂 Segment / Anchor 才有可回跳的细粒度来源）；
2. **A3 紧随 F1**——Evidence 是唯一"每晚一天就永久丢一天"的资产，且 Mastery / Misconception / 复习调度全部挂在它上面；
3. **A1+A2 为并行槽内性价比最高步**——架构位（`tools=[]`）、检索入口（SearchService）、引用 UI（citations 契约）三样全备；F1 落地后检索粒度可从整篇升级为段落级（Segment 命中）；
4. **评测资产同步前置**——工具调用轨迹断言 + 检索 groundedness 评测，复用 `docs/evaluation/` 样本集模式与回归触发纪律（prompt_version / 模型变更触发，见工单 20）。

# 41. 知识起点扩展路线（2026-09-17 grill 定稿，资料库前置修订）

> 评审性质：基于《起点知识库建议》（`docs/起点知识库建议.md`，产品分析输入，随本节一并归档提交）与代码库现状（`feat/extend-dev-06`）的九问定稿，并按后续“资料库必须成为 RAG 与多知识起点共同地基”的产品决策修订。本节为评审记录，优先级与功能口径的权威仍在三份权威文档；真正开工前须按 §42.13 同步 PRD、数据模型与术语。四类起点对象（单一内容 / 复合内容 / 持续来源 / 用户意图）的完整分析见归档文档，本节只记录顺序决策。

## 41.1 波次与排序定案

1. **开工时机**：Concept Mastery V1 六票（`.scratch/concept-mastery-v1/`）完结合并后开工本波次，不与在途工作交错。
2. **第一外部版本 = 资料库 V1 + 网页剪藏首适配器**：资料库不是先造空框架，也不是等所有入口完成后补；内部依赖顺序为「来源资产契约 → 入库/分片/索引/生命周期 → 网页剪藏纵向验证 → 资料库工作台与 RAG Agent 验收」，完整范围见 §42。网页剪藏仍沿用基线 P2 定项：PRD L3 已定「贴 URL → sidecar 抓正文（readability）→ 文档管线」、R10 已定失败降级手动粘贴、`CaptureType.CLIP` 已预留。V1 只存提取后正文快照 + 来源元数据（URL/标题/域名/抓取时间，回跳原网页走系统浏览器），**不存原始 HTML**。抓取采用浏览器式请求头、超时与有限重试；硬反爬站点不引入破解手段，失败降级手动粘贴。浏览器扩展、页面版本对比留后续。
3. **第二站 = 长内容**：`ai-summary/03`（>30k 总结 map-reduce，唯一实质性旧票）作为前置票先做，随后做书籍导入模式（见 §41.2）；书籍与后续起点复用 §42 的来源资产接口，不另建导入孤岛。论文（8~30 页）单 Record 管线现状即可承载，不阻塞。
4. **B3 Tutor 场景包继续压后**（消费端增强，等 Mastery 真实使用反馈再定形态）；B5 sqlite-vec 维持延后不变（触发条件见 §40.3 B5 行）。
5. 其后按序：**课程大纲初始化**（大纲/教材目录 → 建知识空间并建议导入材料，「空间初始化器」非新实体）→ **问题驱动研究会话**（复用自由对话 + web_search + 跨记录引用 + B6 对话转资产，增加「收集来源建立知识空间」出口，不上通用自主 Agent）→ 视频 / 仓库 / 文件夹等再决策。

## 41.2 大 PDF 书籍：拆章多 Record（关键架构定案）

书籍不进单 Record 管线，书籍导入模式按章拆分（对齐归档文档「书 = 一个知识空间 + 多个 Record」映射）：

- **拆章依据三级降级**：PDF 目录书签（PyMuPDF `get_toc()`，最可信）→ 启发式章节标题识别（「第N章 / Chapter N」等）→ 等窗口兜底（按约 30k 字符目标对齐页段，保证每章落在现有管线舒适区）。
- **每章一个 Record、同属一个知识空间**，白拿现有全部资产：页码锚点（`DocumentBlock.page_no` 已有）、分片 FTS、总结、习题、跨记录问答（B2 按章命中）；章内超长（>30k）由 `ai-summary/03` map-reduce 兜底——两票互相咬合。
- **否决整书单 Record 路线**：需同时突破三处现有上限（总结生成无 map-reduce、挂载会话 30k 截断、搜索索引单条 30k 限长），改完仍是巨型 Record 反模式；拆章仅动导入侧、下游管线零改动。文件体积本身不是问题（PyMuPDF 逐页流式解析、原文件落本地 `files/`）。
- **护栏**：扫描版无文本层 PDF 沿用 `NO_EXTRACTABLE_TEXT` 拒绝，OCR 明确不做；页数/字符上限数字拆票时定。EPUB 走同一模式（无页码，章节锚点代替页码锚点）。

## 41.3 明确不做（本波次）

- **不做对象驱动模板系统**（「学一本书 / 研究一个问题」式入口）——等剪藏、长内容、研究会话三个场景真实跑过后（≥3 场景共享逻辑的证据出现）再评估抽象，现在做是为一次性代码建抽象。
- **不翻案视频导入**（基线维持「不做」；本地视频→ffmpeg 提音轨→ASR 的窄票等核心闭环被真实使用后再决策）。
- 不为书 / 论文 / 视频建独立领域模块、不新增第二套知识容器、不先造通用 Connector/Plugin 框架、不把静态解析 Agent 化；资料库是来源资产目录与检索入口，不取代唯一知识容器 Course（与归档文档第六节一致）。

# 42. 资产库 / 资料库与 RAG Agent 完整能力（2026-09-17 决策补充）

> **决策结论**：当前 `/library` 只是基于 `SearchService` 的跨课程搜索视图，`search_library` 只是课程 / 全部资料会话中的分片检索工具；二者不等于已经具备“资料来源统一入库、生命周期治理、RAG 语料管理与 Agent 消费”的完整资料库。资料库 V1 必须在 Concept Mastery V1 收尾后、其他知识起点之前开发，并与网页剪藏作为同一个外部版本交付。内部先建立最小来源资产接口，再用网页剪藏验证，禁止先造没有真实适配器的通用框架。

## 42.1 定位与领域边界

资料库是**本地来源资产目录 + 确定性处理管线 + 可追溯检索接口**，负责回答：

1. 用户拥有哪些原始学习来源；
2. 来源的本地快照、出处、处理状态与派生 Record 是什么；
3. 哪些内容已经完成解析、分片并可进入 RAG；
4. 检索命中如何回到确定的原文位置；
5. 来源归档、删除或重建后，索引与 Agent 可见性如何一致收敛。

它不改变以下既有语义：

- **Course / 知识空间仍是唯一知识容器**；资料库不引入第二套知识空间、文件夹树或“知识库”。
- **资料条目是来源资产，不是学习资产**；Summary、Knowledge Point、Quiz、Todo 等仍归属 Record。
- **Record 是可学习、可总结、可测验的内容单元**；一个来源可以派生多个 Record，一个 Record 也可能由多个来源组成。
- **Segment 是 RAG 的事实粒度，Source Anchor 是引用事实源**；FTS / 向量索引只是可再生定位结构，不能成为引用内容。
- **Agent 只通过受控领域接口读取或提议动作**，不得直接读写资料库、Record、Segment、Concept 等业务表。

## 42.2 知识起点映射

| 知识起点 | 资料库映射 | Record 映射 | 首版处理 |
|---|---|---|---|
| 单个网页 / 论文 / 文件 | 一个资料条目 | 通常一个 Record | 资料入库后进入现有文档管线 |
| 一本书 / 大 PDF / EPUB | 一个资料条目 | 按章多个 Record | 复用 §41.2 拆章规则 |
| 一门课程 | 一个 Course + 多个资料条目 | 按材料 / 章节生成多个 Record | 课程初始化器只编排，不新建容器类型 |
| 一个问题 / 研究主题 | 研究会话先检索外部来源 | 用户确认的来源才进入资料库并派生 Record | 禁止搜索结果静默入库 |
| 音频 / 录音 / 粘贴 / 速记 | 现有正式来源文件或文本来源 | 沿用现有 Record | 通过存量回填进入统一浏览，不重写处理链 |
| RSS / 频道 / 仓库 / 网站 | 持续来源 | 每次确认的版本或增量产生 Record | V1 不做，留后续同步适配器 |

## 42.3 V1 功能范围

### 来源资产

- 导入本地文件、网页 URL 与纯文本；现有录音、音频、文档、粘贴、速记通过幂等回填进入统一视图。
- 保存用户可见、可搬移的本地快照；网页 V1 保存净化后的正文快照，不保存原始 HTML。
- 记录标题、来源类型、原始 URL / 文件名、MIME、大小、内容哈希、抓取时间、创建时间与可选 Course 归属。
- 同内容哈希重复导入时提示已有来源，由用户选择打开已有条目或继续保留；不静默合并。
- 支持重命名、归类 / 取消归类、归档、恢复、删除、失败重试与重建索引。
- 展示来源派生出的 Record、处理任务、分片数量和最近错误；技术状态以 `processing_jobs` / Segment 事实派生，不再复制一套可漂移状态。

### 处理与索引

- 所有适配器收敛到同一确定性管线：`本地快照 → 解析 → Segment → Source Anchor → 检索索引 → 可派生 Record`。
- 复用现有文档解析、转写、`JobRunner`、`document_segments` / `transcript_segments`、`segment_search_index` 与 Source Anchor，不另造第二套 parser、队列和索引写路径。
- 索引写入与 Segment 事实写入保持同事务；启动允许幂等补建，软删 / 归档在查询期强制过滤。
- 解析失败保留来源条目和本地原件，允许用户修正后重试；不得因 AI / ASR / 网络不可用丢失已入库内容。
- 资料内容更新采用显式“重新抓取 / 重新导入”，V1 不后台监控、不静默覆盖旧快照。

### 资料库工作台

- `/library` 从“输入关键词才有结果”的搜索壳升级为默认可浏览的资料工作台。
- 提供全部 / 网页 / 文档 / 音频 / 书籍 / 文本视图，以及 Course、处理可用性、归档状态和时间筛选；筛选条件进入 URL search params。
- 主区支持紧凑列表 / 网格，详情检查器展示来源元数据、本地路径、派生 Record、索引状态、错误与可用动作。
- 支持打开 Record、定位原文、用系统浏览器打开 URL、在 Explorer 中显示本地文件。
- 页面继续遵循固定工作区约束：整页不纵向滚动，仅列表和详情检查器各自滚动。
- 批量操作 V1 只做归类、归档与删除；标签体系、智能收藏夹和自由文件夹树后置。

## 42.4 推荐数据模型

现有 `course_materials` 只是尚未实施的 P5 课程文件草案，`document_segments.course_material_id` 与 `source_anchors.course_material_id` 也只是无外键预留。资料库开工时应在权威数据模型中将该草案**替换为通用来源资产模型**，不得同时建设 `course_materials` 与另一套全局资料表。

推荐采用两个最小事实表（最终表名与迁移编号在 spec 阶段冻结）：

### `library_items`

| 字段组 | 语义 |
|---|---|
| `id` / `course_id?` | 来源身份；允许 Inbox / 全局资料不归属 Course |
| `source_type` | AUDIO / DOCUMENT / WEB / BOOK / TEXT；V1 固定枚举 |
| `title` / `origin_uri?` | 用户可编辑标题与原始 URL / 导入路径标识 |
| `local_path?` / `mime_type?` / `file_size?` | 数据目录内正式快照；纯文本可无文件 |
| `content_hash` | 快照内容哈希，用于幂等与重复提示 |
| `fetched_at?` / `metadata_json` / `schema_version` | 网页抓取时间与来源类型专属小字段；JSON 必须按 source_type 进行 Pydantic 判别校验 |
| `status` | ACTIVE / ARCHIVED；处理状态不复制到此列 |
| `created_at` / `updated_at` / `deleted_at?` | 生命周期与软删 |

### `library_item_records`

| 字段 | 语义 |
|---|---|
| `library_item_id` / `record_id` | 多对多事实；覆盖一本书拆多章与多来源 Record 两个已存在的真实方向 |
| `role` | PRIMARY / SUPPLEMENTAL |
| `sequence_no` | 同一来源派生多个 Record 时保持章节 / 内容顺序 |

配套调整：

- `document_segments` 与 `source_anchors` 的预留 `course_material_id` 在迁移中统一重命名 / 替换为 `library_item_id` 并补外键；不保留同义双列。
- 存量 `record_files` 继续作为 Record 正式来源文件；通过幂等回填创建资料条目与关联，不迁移或复制原文件字节。
- 无 `record_files` 的 PASTE / QUICK_NOTE 生成文本型资料条目；一个 `MULTI_SOURCE` Record 可关联多个资料条目。
- 物理文件清理由现有 tombstone / retention 纪律执行；存在活动 Record 关联时不得误删其唯一正式来源文件。
- `search_index` 保持资产级导航搜索，`segment_search_index` 保持 RAG 片段检索；不合表。

## 42.5 RAG 检索模块

对 Agent 暴露一个深模块 `LibraryRetrievalService`，由它隐藏来源类型、作用域、FTS、Concept 扩展、可选向量召回、去重与锚点组装。外部接口保持小而稳定：

```text
search(scope, query, filters, limit) -> RetrievalResult
```

一次检索内部顺序固定为：

```text
会话作用域与软删过滤
→ 查询规范化
→ Segment FTS / Concept 名称扩展并行召回
→ 条件满足时追加 sqlite-vec 召回
→ 去重与确定性排序
→ 回业务表读取逐字原文和相邻小窗口
→ 组装 Source Anchor、来源标题与定位信息
```

`RetrievalResult` 至少包含：`library_item_id`、可选 `record_id`、来源标题、逐字 quote、受限上下文窗口、anchor / segment id、页码或时间戳、来源类型与召回通道。分数只用于排序，不作为用户可见“可信度”。

关键纪律：

- 最终引用必须来自当前未删除的业务 Segment / Source Anchor，禁止引用 FTS token 串、Embedding、Concept 描述或 AI 摘要。
- COURSE 范围只能读取该 Course 的资料和 Record；ALL 才能读取 Inbox / 全局范围，必须有“跨课程不泄漏”自动化用例。
- 现有 `search_library` 不再自行拼接 Concept 与分片召回逻辑，迁移为调用 `LibraryRetrievalService.search()`；`search_transcript` 保留单 Record 专用接口。
- RAG V1 继续以 FTS + Concept 扩展为默认方案。sqlite-vec 仍遵循 B5 触发条件：真实语料出现词汇不重合导致的召回失败且黄金样本证明向量有净增益后才实施；资料库不能以“先上向量库”作为开工前置。
- Embedding 是可删除、可重建的派生数据；模型 / 维度 / 内容版本必须可识别，来源删除、归档或内容换版后不得继续召回旧向量。

## 42.6 RAG Agent 能力

### V1：受控只读能力

- COURSE / ALL 会话继续只挂一个模型可见工具 `search_library(query)`；作用域由会话运行时绑定，模型不能自行扩大。
- 工具内部消费 `LibraryRetrievalService`，返回结构化命中、逐字引用与定位，不把 SQL、文件路径或索引实现暴露给模型。
- Agent 可以多轮改写关键词、缩小查询、比较不同来源；每轮工具调用次数、每次命中数和总上下文字符均设预算。
- SSE 继续复用 `tool_call` / `tool_result` 呈现检索过程；最终回答沿用现有跨记录引用校验与来源跳转。
- 本地资料无命中时明确说明，不得用联网结果冒充本地资料；开启 `web_search` 时，网络来源与资料库来源保持不同 citation 类型。

### V1.1：研究会话的受控写动作

问题驱动研究会话可以执行：

```text
web_search 找到候选来源
→ Agent 生成“建议保存”提案
→ 用户确认来源、目标 Course 与标题
→ 业务接口创建资料条目并启动确定性入库任务
→ 完成后才能被 search_library 检索
```

- Agent 只有“提出入库 / 归类 / 重新抓取建议”的能力；任何写动作必须经过 HITL，最终由资料库业务接口执行。
- 搜索结果摘要不是资料事实，未成功抓取并形成本地快照前不得进入 RAG，也不得生成 Source Anchor。
- 禁止 Agent 直接写业务表、修改本地任意路径、静默批量抓取或自动订阅来源。

### 后续能力

- sqlite-vec 混合召回：只在 B5 真实评测触发后加入检索模块内部，不新增第二个 Agent 工具。
- 持续来源刷新：RSS / 频道 / 仓库采用显式订阅、差异预览与用户确认，单独设计资源预算和版本模型。
- 浏览器扩展：从用户已登录、已渲染页面捕获 DOM；它是新的入库适配器，不改变资料库核心接口。

## 42.7 入库模块与适配器

资料库只提供一个外部入库接口，具体来源差异由内部 Adapter 消化：

```text
ingest(request) -> LibraryItem + ProcessingJob
```

V1 实际 Adapter：

1. **ExistingCaptureAdapter**：幂等映射现有录音、音频、文档、粘贴、速记，不重跑已成功处理链。
2. **WebClipAdapter**：URL 校验、抓取、正文净化、正文快照落盘、元数据提取与失败降级。
3. **FileAdapter**：复用现有文档 / 音频导入校验与落盘；资料库只编排，不复制解析实现。
4. **BookAdapter**：在 `ai-summary/03` 完成后加入，按 §41.2 拆章并建立一个资料条目到多个 Record 的关联。

只有当第三个真实 Adapter 证明存在相同扩展点时，才提取公开 Connector / Plugin 接口；V1 的 Adapter 保持模块内部接口。

## 42.8 API 与前端交互

后端资源能力按用户任务分组，不暴露底层索引表：

- 列表 / 详情：分页、搜索、来源类型、Course、归档状态与可用性筛选；详情返回来源、派生 Record、处理摘要与可执行动作。
- 入库：URL / 文件 / 文本请求在路由层转为统一判别请求；返回资料条目与 job id。
- 生命周期：重命名、归类、归档 / 恢复、删除、失败重试、显式重新抓取 / 重新导入、重建索引。
- RAG：仅供业务模块调用的检索接口；Agent Tool 调用领域接口，不另开可绕过会话范围的任意查询端点。
- 任务进度：沿用 REST 为事实源、SSE 只做失效通知的既有纪律；断线 / 重启后由 REST 校准。

前端关键交互：

- “添加资料”是统一入口，先选择网页、文件或文本；书籍模式在长内容阶段出现。
- 导入立即创建可见条目；处理未完成时显示确定性状态和重试入口，不用无限 spinner。
- 详情检查器明确区分“原始来源”“派生学习记录”“RAG 可用性”，避免把已导入误解为已生成全部学习资产。
- 删除前展示会受影响的派生 Record 与索引；默认软删且可恢复，物理清理由保留期任务处理。
- 资料库内“询问 AI”新建 COURSE / ALL 范围会话，不新增第二套聊天界面。

## 42.9 安全、隐私与本地优先

- URL 仅允许 HTTP(S)；必须阻止 loopback、私网、链路本地、云元数据地址，并在每次重定向后重新解析与校验，防止 SSRF / DNS rebinding。
- 限制响应体大小、解压后大小、重定向次数、连接 / 读取超时和允许的 Content-Type；不执行网页脚本，不加载第三方子资源。
- 导入文件复制到用户数据目录后再处理；路径操作使用规范化绝对路径并验证仍位于授权目录内。
- HTML 只作为解析输入，V1 不持久化、不直接渲染；正文展示走现有安全 Markdown / 纯文本路径。
- 日志只记录 item / job / adapter id、阶段、耗时与稳定错误码，不记录完整正文、敏感 URL 查询参数、文件路径或供应商原始响应。
- 离线时资料浏览、全文检索、来源定位和导出仍可用；需要联网 / 模型的抓取、Embedding 或 AI 回答明确降级。
- 数据导出 / 导入与滚动备份必须包含资料条目、关联关系和本地快照；Embedding 等派生索引可以重建，不作为不可替代备份内容。

## 42.10 生命周期语义

- **归档**：条目仍保留快照、锚点和派生 Record，但默认不出现在活动资料列表；是否参与 RAG 由显式 `include_archived=false` 统一过滤，Agent 不可绕过。
- **软删**：资料条目立即退出资料列表和独立来源召回；已派生 Record 不自动级联删除，避免一次删除扩大为学习资产丢失。Record 已持有的正式来源文件和 Segment 仍按 Record 生命周期工作。
- **恢复**：恢复条目后校验本地快照与 content_hash；索引缺失则进入幂等重建。
- **重新抓取 / 导入**：创建新内容版本并显式预览影响，V1 不自动覆盖。版本模型在需要首次网页刷新时随票冻结；在此之前只允许“另存为新条目”。
- **Course 移动**：更新资料条目归属时重新计算可见范围；派生 Record 不静默跨 Course 移动，必须由用户单独确认。
- **物理清理**：只有保留期届满且不存在仍引用该唯一文件的活动 Record / 条目时执行；失败可重试并记录结构化错误。

## 42.11 评测与验收

开工前先建立包含中文、英文、同义改写、跨 Course 同名概念、网页 / 文档 / 音频、归档 / 删除来源的真实小语料集，并冻结查询、期望来源与允许命中范围。至少验证：

1. 同一来源重复导入不产生无提示的重复事实；存量回填可重复运行。
2. 任一 RAG 可用来源都能从资料库打开原件 / 快照，并跳到其派生 Record。
3. `search_library` 命中引用能逐字回查当前 Segment，页码 / 时间戳 / URL 定位正确。
4. COURSE 查询零跨课程泄漏；归档、软删与失败来源零错误召回。
5. FTS + Concept 基线记录 Recall@K、MRR、无答案准确率与引用正确率；未达到预先冻结阈值才评估 sqlite-vec。
6. Agent 工具轨迹可断言查询、命中数、失败降级与最终 citation；工具失败不炸毁整轮对话。
7. sidecar 重启后处理中任务按既有恢复纪律收敛，索引重建幂等。
8. Windows / Tauri 真机验证本地文件打开、Explorer 定位、系统浏览器回跳、亮暗主题和窄窗局部滚动；浏览器模拟不能替代该门禁。
9. 数据目录导出 → 空库恢复后，资料条目、快照、关联与引用仍可用；派生索引允许启动重建。

## 42.12 一个外部版本、六张纵向工单

资料库 V1 对外一次性交付，不发布只有表或只有 UI 的半成品；内部按以下依赖顺序拆票：

1. **契约与评测地基**：冻结 LibraryItem / Record / Course 关系、删除语义、RAG 结果结构、真实查询样本；回写 PRD / 数据模型 / CONTEXT，必要时新增 ADR。
2. **存量资料可见闭环**：迁移与幂等回填；现有文档 / 音频 / 文本可在 `/library` 浏览、筛选、打开并显示 RAG 可用性。
3. **网页剪藏闭环**：安全抓取、正文快照、分片索引、来源回跳、失败粘贴降级与工作台状态全部接真。
4. **RAG Agent 闭环**：`LibraryRetrievalService` 统一检索；现有 `search_library` 改由其消费；COURSE / ALL 多轮问答、工具过程与逐字引用验收。
5. **生命周期闭环**：重复提示、归类、归档 / 恢复、删除、重试、索引重建、重启恢复与数据目录导出恢复。
6. **发布收尾**：OpenAPI 类型、中文 / 英文文案、评测基线、全栈自动化、真机清单与 `PROJECT_PROGRESS.md` 同步；验收后再进入 `ai-summary/03` 与书籍 Adapter。

依赖关系：

```text
01 → 02 → 03 → 04 → 05 → 06
```

允许 03 与 04 在 02 完成后内部并行实现，但对外仍以 06 完成作为资料库 V1 可发布判据。

## 42.13 文档与决策门禁

本节补充的是已接受的产品方向与完整开发边界，但当前权威文档仍存在旧口径，**不得直接按本节建表**。工单 01 必须一次性消除以下冲突：

- `CONTEXT.md` 当前把 Library 限定为跨课程搜索视图，需要改为“来源资产目录 + 统一浏览 / 检索入口”，同时保留 Course 唯一知识容器红线。
- 功能基线决策 #12 的 `course_materials` 与数据模型 v2.9 的 P5 课程级草案，需要改为通用资料来源模型，或给出保留原名仍能覆盖全局资料的明确理由。
- 数据模型中的 `document_segments/source_anchors.course_material_id` 预留列必须与最终来源资产表同名、加外键并同步所有交叉引用；历史变更记录保持史实不改。
- §41 的“网页剪藏第一票”已在本次修订为“资料库 V1 + 网页剪藏第一外部版本”；`PROJECT_PROGRESS.md` 必须使用同一顺序。
- 若表名、Course 可空语义、存量回填或删除规则改变既有 ADR，应新增递增编号 ADR，不得默默覆盖。

## 42.14 明确不做（资料库 V1）

- 不创建第二套知识空间、目录树、Notion 式页面系统或块编辑器。
- 不开发通用 Connector SDK、插件市场、MCP server、Multi-Agent 抓取团队或独立爬虫服务。
- 不支持登录墙破解、验证码绕过、反爬对抗、整站镜像或未经用户确认的批量抓取。
- 不后台监控网页 / 仓库 / 文件夹变化，不自动覆盖来源版本。
- 不因“RAG”名义强制引入 sqlite-vec、LanceDB、Qdrant、ElasticSearch 或云端向量服务。
- 不让 Agent 直接写资料库或执行任意文件 / Shell 操作；写动作始终经过业务接口与 HITL。
- 不把 Summary、Concept 描述或 AI 综合文本回灌为来源事实，也不把资料导入本身计为 Mastery Evidence。
