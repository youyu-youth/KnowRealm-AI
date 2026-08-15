# KnowRealm-AI

面向"一切学习知识的人"的个人学习工作台：捕获学习素材，转化为可编辑、可追溯的学习资产，并长期维护学习状态。本文件是项目唯一术语表——只定义语言，不含实现细节。需求见 `docs/KnowRealm-AI-功能需求基线-v1.10.md`，数据模型见 `docs/KnowRealm-AI-数据模型-v1.10.md`。

## Language

### 知识容器

**知识空间（Knowledge Space）**:
课程在 UI 层的统称——学业课程、技能空间、主题收藏。课程是系统里唯一的知识容器，不存在独立的"知识库"实体。
_Avoid_: 知识库、笔记本、文件夹

**课程（Course）**:
唯一的知识容器实体，携带学习场景与深度设定，进入所有 AI Prompt 上下文。
_Avoid_: 科目（仅学业场景的口语说法）

**学习场景（Learning Context）**:
课程的必填属性：SCHOOL（学业，含 education_stage）/ CAREER（职业）/ INTEREST（兴趣），决定 AI 输出风格与深度。它是课程级设置，不是用户全局属性。
_Avoid_: 用户画像、偏好

**角色（Primary Role）**:
档案层的个性化字段——学生/程序员/职场人/其他 + 一段自我介绍。决定语气、默认值与文案基调；不改变能力集，永不进入课程范围 AI 管线与学习证据。
_Avoid_: 身份、用户画像（对比：角色=你是谁；学习场景=这门课在学什么，后者才是 AI 输出权威）

### 捕获与整理

**学习会话 / 学习记录（Record）**:
一次完整的学习行为单元——一节课、一次技术分享、一份导入的文档、一段速记。UI 泛称"学习会话/学习记录"，代码与数据实体一律叫 Record。
_Avoid_: 课堂（仅学业场景适用）、笔记（与速记混淆）

**捕获（Capture）**:
把任何素材变成 Record 的动作，共五级入口（轻→重）：速记 / 粘贴 / 剪藏 / 音频 / 文档。
_Avoid_: 上传（仅指文件传输环节）

**速记（Quick Note）**:
最轻的捕获——一句话到几段文字，仅存储不触发 AI（NOTE 状态）。
_Avoid_: 闪念、memo

**收件箱（Inbox）**:
course_id 为空的 Record 集合——"先捕获后整理"的缓冲区。
_Avoid_: 草稿箱、未分类

**归类（File）**:
给 Inbox 中的 Record 填上 course_id；不触发 AI 管线。
_Avoid_: 移动、归档

**升级（Upgrade）**:
对未处理内容触发 AI 管线（总结 HITL 等）；必须先归类——无课程的 Record 不总结。
_Avoid_: 处理、分析

### 转写与溯源

**转写（Transcript）**:
Record 的当前合并全文，快速展示用；轻捕获内容直接写入，无需音频文件。

**片段（Segment）**:
句子级（音频）或分片级（文档）的可溯源事实单元。
_Avoid_: 与"转写"混用

**来源锚点（Source Anchor）**:
AI 结论与原始出处（音频片段/文档页/用户笔记/对话消息）的定位关系；一切"可追溯"由此成立。
_Avoid_: 引用（口语说法，正式用语为锚点/锚点链接）

### 学习资产与概念

**知识点（Knowledge Point / KP）**:
Record 级资产——一次学习会话内被 AI 与用户确认的知识点。
_Avoid_: 概念（那是 Course 级实体）

**概念（Concept）**:
Course 级规范概念，跨记录长期存在，用于掌握度建模。与 KP 不得混同或互并。
_Avoid_: 标签、主题、知识点

### 学习状态

**学习事件（Learning Event）**:
用户发生的一个学习行为，带幂等键，一行为一事件。
_Avoid_: 日志、记录

**学习证据（Learning Evidence）**:
事件对某 Concept 学习状态的证据（带权重/置信度）。**AI 自述（AI_SYNTHESIS）不是证据**——证据只来自答题、Teach-back、Recall 验证、Tutor 检查、课堂信号、用户确认。
_Avoid_: 数据、信号

**掌握度（Mastery）**:
学习者对某 Concept 的掌握状态。唯一写入口是 Mastery Engine（事件 → 证据 → 引擎），任何业务功能禁止直写。
_Avoid_: 分数、正确率

**误区（Misconception）**:
先怀疑再验证的 learner 状态：SUSPECTED → 验证 → CONFIRMED/DISMISSED → 纠错 → RESOLVED。一次答错不得定性。

**业务态 / 技术态**:
`record.status` 只表达用户可理解的业务状态（9 态，含 NOTE）；ASR/解析/嵌入等任务进度一律在 processing_jobs。两者不得混写。

**HITL**:
Human-in-the-loop——AI 产出经用户确认/调整后才落定并解锁后续动作；Autopilot 只推荐不执行亦源于此。

### 任务分层

**Todo（Record 级）/ 计划项（Plan Item，目标级）/ 智能动作（Agent Action，此刻最优动作）**:
三表分立、可引用、不合并。
_Avoid_: 任务（泛称，指代不明时禁用）
