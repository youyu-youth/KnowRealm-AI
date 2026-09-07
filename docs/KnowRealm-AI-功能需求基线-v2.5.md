# KnowRealm-AI 功能需求基线 v2.5

> **文档定位**：KnowRealm-AI 第一版产品需求文档（PRD），覆盖产品定位、功能需求、架构约束、阶段规划与产品决策记录。
>
> 配套文档：
> - 技术选型：`docs/技术栈设计与审查-v4.5.md`
> - 数据库设计：`docs/KnowRealm-AI-数据模型-v2.3.md`
> - Learning Brain 扩展设计（F1~F18 机制与交互参考）：`docs/AI课堂助手-功能升级与创新扩展设计.md`
> - 存储范式决策：`docs/adr/0001-local-first-storage.md`
> **项目定位**：开源、面向个人使用、**本地优先**。所有设计先过两问：**数据是否落在用户可见、可整体搬移的本地目录？这项能力是否要求用户多装任何东西（容器/账号/付费云服务）？**
> **编写日期**：2026-08-17
> **实施顺序澄清（2026-08-17）**：桌面工程壳已初始化；开发从可见页面与真实业务纵切开始，不设独立 S0 或全量 Phase 0 前置阶段。录音 POC 随录音功能实施，sidecar 打包冒烟随首次可分发版本实施。
> **变更记录**：v2.5（2026-09-07）**学习统计口径与范围定稿（#54，plan 17 grill）**——七项指标口径全部定死：累计学习时长=SUM(records.duration_ms) 仅音频类捕获；记录数=软删外全量（含 FAILED/NOTE/收件箱未归类）；课程数含 ARCHIVED；AI 总结次数=ai_summaries 行数（含重新生成版本）；习题生成=quizzes 行数（含历史批次）、习题完成=answered_at 非空（模拟测试交卷不计）；问答轮次=chat_messages USER 行数（过滤软删会话）；一致性原则=删除记录/课程后名下指标同步回落。**趋势图表拉进本功能范围**（原「Wave B 出口线之外后续可加」表述作废）：学习时长趋势折线面积图，真数据按捕获日聚合，近 7 天 / 近 30 天两档（echarts，无假数据）。入口形态由「统计卡片区」改定为**统计带**（趋势图 + 六格指标带单分节，非卡片仪表盘）；§4.1 学习统计行 / §9.1 信息架构行连锁改写。
> **变更记录**：v2.4（2026-08-30）**Q15 登录侧定稿（ADR-0014：账号=可选云身份层）**——桌面端**永不强制登录**；"账号"重新定义为未来可选云身份层（Raycast/Obsidian/Zen 模型：登录仅 gate 云服务与会员权益，数据永不出本地，#55 存储范式不变）；多人数据/偏好隔离确认由 OS 用户账户天然覆盖（`desktop.json` 与默认数据目录均按 OS 用户分置，零开发）；偏好形态=邮箱+密码+GitHub OAuth，触发时按成本梯度复核（托管 Auth/纯 OAuth 优先，不自建密码体系）；触发条件=决定运营云服务/启动商业化那天；桌面端不预埋代码钩子。Q15 分享形态仍搁置待决；#3/§7 认证行/§5.2 排除清单连锁改写。
> **变更记录**：v2.3（2026-08-22）**音频导入与转写合同定稿（决策 #58，ADR-0002~0006）**——Capture Batch 一次提交封口、混合来源使用 MULTI_SOURCE、整批成功后才原子发布 Transcript；录音分片由 03 暂存恢复，04 统一合并/转码/正式注册；腾讯 ASR 采用本地 `<5MB` 切片，不引入 COS，首次外发须独立同意；缺 key/离线/未同意保持可恢复等待；SSE 仅作失效通知、REST 为事实源；Transcript 编辑以 source_version 防冲突并使旧 Summary 过时；ffmpeg 使用可审计 LGPL 构建随包分发。
> **变更记录**：v2.2（2026-08-20）**文档导入实施边界定稿**——05 单文件支持 TXT/MD/PDF/DOCX，要求 ACTIVE 课程，止于 Transcript + SUMMARY_PENDING；06 承接总结/HITL，04 承接多文件、混合来源与 SSE，11 承接未选课文档；processing_jobs 增加 CANCELLED 与可重试分类；同一数据目录以进程生命周期排他锁保证单 sidecar；同步明确 Transcript 提取、失败、重复导入与归档竞态语义。
> **变更记录**：v2.1（2026-08-17）**后端通信形态定稿（决策 #56）**——维持 FastAPI sidecar（localhost HTTP+SSE；三案对比否决自造 Rust/IPC 双协议层与全 Rust 重写，论证入技术栈 v4 §二）；**localhost 加固升为 Phase 0 硬性项**（随机端口 + 壳注入启动令牌 + 仅绑 127.0.0.1）；§11 新增 **Q15（分享形态与登录必要性——搁置待决，未拍板）**。
> **变更记录**：v2.0（2026-08-17）**存储范式转向：本地优先（决策 #55，ADR-0001）**——本地磁盘成为唯一业务事实源（数据目录：SQLite + 原始文件），后端改为 Tauri sidecar（PyInstaller 随 `.msi` 分发，UI 走 localhost）；LLM 开放自选任意 OpenAI 兼容端点（DashScope 默认预设，供应商卡交互），Embedding V1 固定，ASR 腾讯不变；登录/认证/邮件整体作废，首启改为"选数据目录 → 配供应商 key → 角色卡"三步；多设备降级为全量导出→导入；V1 提供全量导出（Wave B），P2 可选快照备份（WebDAV/S3 单向推送），**双向同步永不做**；Supabase 全家桶（Auth/Storage/Realtime/RLS/pgvector/托管）除名；状态机 9 态→**8 态**（UPLOADING 消解）；pgvector→sqlite-vec、procrastinate→自研 SQLite 队列；数据目录布局与启动滚动备份定稿；受影响决策（#1/#3/#8/#10/#11/#16/#17/#25/#27/#28/#32/#34/#35/#37/#44/#49/#50/#51/#54）已按新范式改写。v1.1~v1.10 变更史见 git（文件 v1.10 于本版删除）。

---

## 1. 项目与产品概述

### 1.1 产品定位（三阶段演进）

| 阶段 | 定位 | 一句话 |
|------|------|--------|
| 当前（V1） | **个人学习工作台（AI 学习助手）** | 五级捕获（速记/粘贴/剪藏/音频/文档）把课堂录音、历史音频、课程文档与闪念统一转化为可编辑、可追溯的学习资产（总结/知识点/习题/复习/Todo），并提供基于上下文的 AI 问答 |
| 升级 | **AI Personal Learning Brain** | 持续维护"掌握多少、为什么没掌握、什么时候会忘、下一步学什么" |
| 长期 | **AI Learning OS** | Observe → Understand → Diagnose → Decide → Teach → Verify → Update 的持续学习系统 |

**产品形态**：**个人学习工作台（Learning Workbench）**——顶部快速捕获条 + 左栏工作区导航（今日/收件箱/课程/资产库/学习画像）+ 命令面板（Ctrl+K）。多级捕获（速记/粘贴/剪藏/音频/文档）+ 收件箱整理 + Record 学习管线 + Learning Brain，对标并超越开源生态中的捕获工具（Meetily/memos）与 second brain（Khoj/AnythingLLM）——同类中尚无"捕获+组织+学习状态+自适应"一体化的开源工作台。

**数据形态（v2.0）**：**本地优先桌面软件**（Obsidian/思源/AnythingLLM 桌面版形态）——全部数据活在用户磁盘上用户可见的数据目录里，用户自配 API key（BYO-key），云端仅为可选备份通道。除 LLM/ASR 等显式外呼外，任何数据不出本机。

### 1.2 目标用户与学习深度策略（v1.4 泛化）

面向**一切学习知识的人**：全学段学生（初中至博士）、程序员、上班族与终身学习者。**每门课程独立设置学习场景与深度**（非用户全局属性），进入所有 AI Prompt 上下文，决定输出风格与深度。

**学习场景 `learning_context`（必填）**：

| 场景 | 说明 | 深度字段（二选一必填） |
|------|------|----------------------|
| SCHOOL | 学业学习（初中~博士） | `education_stage`：MIDDLE_SCHOOL / HIGH_SCHOOL / UNDERGRADUATE / GRADUATE / DOCTORAL |
| CAREER | 职业技能（程序员进阶、职业认证、公司内训/技术分享） | `depth`：BEGINNER / INTERMEDIATE / ADVANCED |
| INTEREST | 兴趣自学 | `depth`：BEGINNER / INTERMEDIATE / ADVANCED |

**SCHOOL 场景 AI 输出策略**：

| 教育阶段 | AI 输出策略 |
|---------|------------|
| MIDDLE_SCHOOL | 通俗浅显，习题偏基础记忆理解 |
| HIGH_SCHOOL | 适度专业，强调考点标注 |
| UNDERGRADUATE | 专业体系化，知识点建层级 |
| GRADUATE | 学术深度，侧重逻辑与方法论 |
| DOCTORAL | 前沿研究与方法创新 |

**CAREER / INTEREST 场景 AI 输出策略**：depth 决定深度——BEGINNER=通俗+实操示例、INTERMEDIATE=原理+适用边界与权衡、ADVANCED=边界条件+底层实现细节；程序员场景 AI 输出默认包含代码块，渲染层须支持**代码高亮**。

> **术语约定**：产品 UI 文案以"**学习会话 / 学习记录**"泛称（覆盖课堂、技术分享会、培训、自学等场景），代码与数据实体仍为 Record。
> **知识空间**：课程是唯一知识容器——学业课程（SCHOOL）、技能空间（CAREER）、主题收藏（INTEREST）在 UI 层统称"**知识空间**"，剪藏/导入/录音汇入即形成个人知识库；配合资产库全局检索与 AI 对话 @全部资料，不设独立知识库实体。
> **用户角色（#52）**：档案层 `primary_role`（STUDENT / DEVELOPER / OFFICE_WORKER / OTHER 四选一）+ `about_me`（≤200 字自由文本）——用于首启角色卡、建课程默认值、自由聊天系统提示与文案基调；**角色改变语气与默认值，不改变能力集**，永不进入课程范围 AI 管线与 Learning Evidence；学习场景权威仍在课程。

### 1.3 产品形态与端范围

| 端 | 状态 | 说明 |
|----|------|------|
| Desktop（Tauri 2 + React + Python sidecar） | **V1 实施** | **Windows 为 V1 唯一首发平台**；macOS 在核心功能稳定后评估——届时录音链路需另适配 WKWebView（Safari 内核不支持 webm/opus 录制）或改 Rust cpal 方案 |
| UniApp App 端 | 暂不实施 | 未来 Vue3 + UniApp；与 React 桌面端仅复用 OpenAPI 类型契约与后端能力，UI 层不复用 |
| 微信小程序 | 不实施 | — |

### 1.4 核心用户场景

1. **课堂录音**：学生上课录音 2~3 小时（可打 ⭐重点/❓没听懂/📝记下 标记），下课后自动获得 AI 总结，确认后按需生成知识点/习题/Todo/复习资料
2. **历史音频导入**：导入已录制的 MP3/M4A/WAV 等文件，走同一处理管线
3. **文档导入**：导入 TXT/MD/PDF/DOCX 课件，跳过 ASR 形成 Transcript 后进入 AI 管线；一条记录可同时关联多段音频与多个文档
4. **课后问答**：基于本节课转写文本 + 总结的多轮追问（SSE 流式），答案可溯源到课堂原声位置
5. **长期学习（扩展阶段）**：考前动态规划、遗忘提醒、误区验证、每日学习建议（Autopilot）
6. **闪念速记**：自习/阅读时全局快捷键弹出速记框，一句话/一段文字先存进收件箱，不打断当前学习，事后整理归类
7. **资料剪藏/粘贴**：看到一篇好文章或一段网课文字稿，粘贴（或 P2 起贴链接自动剪藏正文）直接进入 AI 学习管线，生成总结与知识点
8. **程序员**：读技术文档、看技术分享会录音——粘贴/剪藏/录音进管线，生成知识点与习题；AI 对话问代码问题，代码块高亮渲染，聊完一键存为知识点
9. **上班族**：职业培训录音、考证资料导入；考证前用动态规划与遗忘复习安排学习

---

## 2. 核心概念与分层

### 2.1 三层事实边界（不可互相替代）

```
本地业务事实  = 数据目录（SQLite knowrealm.db + files/ 原始文件）——唯一权威数据源
Agent 运行态  = LangGraph Checkpoint（langgraph.db，独立文件，非业务事实）
云端（可选）  = 快照备份 / 导出物（只读副本，P2；永不双向同步）
```

### 2.2 核心领域概念

| 概念 | 定义 | 层级 |
|------|------|------|
| Record | 一节课堂或一次完整学习记录 | 用户工作单元 |
| Transcript / Segment | 转写文本（快速展示）/ 句子级分片（可溯源事实） | Record 级 |
| Source Anchor | AI 结论 ↔ 原始来源（音频片段/文档页/用户笔记）的定位关系 | 溯源基础 |
| Knowledge Point | 一节课内被 AI 与用户确认的知识点 | **Record 级资产** |
| Concept | 跨课堂长期存在的课程规范概念（用于掌握度建模） | **Course 级**，与 KP 不得混同或互并 |
| Learning Event | 用户发生的学习行为（带幂等键，一行为一事件） | 事实入口 |
| Learning Evidence | 事件对某 Concept 学习状态的证据（带权重/置信度） | 掌握度输入 |
| Mastery / Misconception / Forgetting | 掌握度 / 认知误区 / 遗忘状态 | 学习者状态 |
| Todo / Plan Item / Agent Action | 课堂任务 / 目标级计划项 / 此刻最优动作 | 三表分立，可引用不合并 |

---

## 3. 技术基线与架构红线

技术栈详见 `docs/技术栈设计与审查-v4.5.md`，此处仅列结论：Tauri 2 + React/TS + TanStack Router/Query + Zustand；FastAPI **sidecar**（PyInstaller 打包随 `.msi` 分发，UI 走 localhost）+ LangChain/LangGraph + **自研 SQLite 任务队列（processing_jobs 即队列，无任何中间件）**；SQLite（WAL）+ **sqlite-vec**；LLM 默认 DashScope qwen-plus（**可自选任意 OpenAI 兼容端点**）+ text-embedding-v3（V1 固定）；腾讯云 ASR + 随包 ffmpeg（本地执行）；迁移统一 `backend/migrations/*.sql`（user_version 编号）。

### 3.1 十二条架构与数据红线

1. **本地数据目录 = 唯一业务事实源**（SQLite + files/）；云端任何制品（快照备份/导出物）仅为只读副本，**永不回写、永不双向同步**。
2. **LangGraph 只编排需要状态、暂停恢复、HITL 或 Agent 决策的流程**；普通 CRUD 与确定性业务逻辑（Course/Quiz/Todo/EvidenceBuilder/MasteryEngine/QuestionSelector 等）保持普通确定性 Python Service；禁止构建超级 Graph（独立 Graph：Summary / Tutor / TeachBack / Autopilot / MisconceptionVerification）。
3. **Mastery 唯一写入口**：业务动作 → Learning Event → Evidence Builder → Learning Evidence → Mastery Engine → `user_concept_mastery`。任何 Quiz/Tutor/Teach-back Service 禁止直写 Mastery。
4. **AI 诊断必须可追溯**：任何 Mastery/Misconception/Digital Twin/Autopilot 输出必须携带 Evidence、Confidence 或 Decision Snapshot；证据不足显示 `NOT_ENOUGH_DATA`，禁止伪造精确分数。
5. **AI 自述不是 Evidence**：`AI_SYNTHESIS` 类输出不参与掌握度计算；Evidence 只来自答题、Teach-back、Recall 验证、Tutor 检查、课堂信号、用户确认。
6. **Misconception 先怀疑再验证**：SUSPECTED → 验证 → CONFIRMED/DISMISSED → 纠错 → RESOLVED；一次答错不得定性。
7. **Autopilot 只推荐不执行**：任何动作经用户 Accept/Skip/Defer/Adjust 后才运行；不得自动开考、自动生成大量题目、自动认定掌握。
8. **数值计算与 LLM 分工**：Mastery、遗忘风险、复习优先级、下一题选择由确定性规则计算；LLM 只做内容理解、语义评分、Concept 对齐、诊断解释。
9. **概念分层与任务分层不可破坏**：KP（Record 级）≠ Concept（Course 级）；Todo / Learning Plan Item / Autopilot Action 三表分立。
10. **迁移唯一权威** = `backend/migrations/*.sql`（user_version 编号推进）；LangGraph Checkpoint ≠ 业务事实（langgraph.db），长期事实必须落业务表；`record.status` 表达用户可理解业务状态，技术任务状态在 `processing_jobs`。
11. **Agent 工具仅限聊天域**：联网搜索等工具只进入聊天会话（自由聊天默认可用、挂载会话可选）；Summary / Tutor / TeachBack Graph **禁止联网工具**，产出只基于用户资料——总结与教学的可信度根基（#53）。
12. **数据外呼白名单（v2.0）**：个人数据离开本机仅限三类显式通道——LLM/Embedding/ASR API 调用、P2 剪藏正文抓取、P2 快照备份推送；此外禁止任何出网传输。供应商密钥不出本机（导出包默认不含）。

---

## 4. 功能模块与详细需求

> 优先级标注：MVP = Phase 1 交付；P2~P6 = 扩展阶段（见 §5）。

### 4.1 M1 — 档案、配置与设置（v2.0：无登录）

| 功能 | 需求要点 | 优先级 |
|------|---------|--------|
| 首启流程（v2.0） | 三步：**① 选择数据目录**（默认 `%USERPROFILE%\KnowRealm\`，可改；检测 OneDrive/网盘接管并提示改选）→ **② 配供应商 key**（供应商卡式：DashScope 预设 / 自定义 OpenAI 兼容端点（base_url+key+model）/ 腾讯云 ASR；可跳过=功能级降级 #38）→ **③ 角色卡**（#52，可跳过）。**无登录、无账号、无邮件**（#55） | MVP |
| 用户档案 | 昵称、头像（数据目录本地文件）、**角色（primary_role 四选一 + about_me ≤200 字，#52；档案设置可随时修改）**；存本地 `profile` 表 | MVP |
| 数据目录管理 | 设置页：打开数据目录 / 更改数据目录（移动+重启）/ **全量导出**（zip：db 快照 + files + config，默认不含密钥，可选勾选含）/ 从导出包导入（换机恢复） | MVP（导出/导入 Wave B） |
| 学习统计 | **统计带**（#54，Wave B）：上「学习趋势」折线面积图（真数据按捕获日聚合音频时长，近 7 天 / 近 30 天两档，echarts）+ 下六格指标带（累计学习时长 / 记录数 / 课程数 / AI 总结次数 / 习题（已作答 / 生成）/ 问答轮次）——**由业务表实时聚合，不建独立事实表、无缓存**。口径（v2.5 定稿）：学习时长 = SUM(records.duration_ms) 仅音频类；记录数 = 软删外全量（含 FAILED / NOTE / 收件箱未归类）；课程数含 ARCHIVED；AI 总结次数 = ai_summaries 行数（含重新生成版本）；习题生成 = quizzes 行数（含历史批次），完成 = answered_at 非空（模拟测试交卷不计）；问答轮次 = chat_messages USER 行数（过滤软删会话）；**删除记录 / 课程后名下指标同步回落**。入口 = "今日"页底部（不新增左栏项） | MVP |
| 偏好设置 | **单一本地配置 `config/settings.json`（v2.0 合并原 user_settings/local_settings，无漫游概念）**：深色模式（LIGHT/DARK/SYSTEM）、字体大小、时区（默认取 OS，复习提醒 P4 生效）、语言（V1 仅中文，设置页隐藏）、关窗行为（默认驻留托盘）/ 开机自启（默认关）/ 速记快捷键（默认 Ctrl+Alt+N 可改）/ 上次学习场景 / 习题数量 / 窗口记忆 | MVP |
| 服务与用量 | **健康检查面板**（各外部服务状态与缺 key 提示，#38）+ **近 30 天 token 用量与调用次数**（llm_call_logs 聚合、按 model 分组；不做计价展示）——设置页"服务与用量"分区 | MVP（Wave B） |

### 4.2 M2 — 课程管理

| 功能 | 需求要点 | 优先级 |
|------|---------|--------|
| 课程 CRUD | 名称必填；`learning_context`（SCHOOL/CAREER/INTEREST）；SCHOOL 场景必填 `education_stage`（5 枚举），CAREER/INTEREST 场景必填 `depth`（BEGINNER/INTERMEDIATE/ADVANCED）——均进 AI 上下文；`course_type`（MAJOR/GENERAL/ELECTIVE，可空）；状态为 ACTIVE/ARCHIVED，**只有 ACTIVE 课程可接受新捕获、归类、升级或 AI 触发**；软删除并级联处理关联数据；**新建课程按用户角色预选默认场景**（STUDENT→SCHOOL，DEVELOPER/OFFICE_WORKER→CAREER，可改，#52） | MVP |
| 查询 | 按教育阶段/类型筛选、名称搜索 | MVP |
| 课程详情 | Overview / Records / Course Brain / Knowledge GPS / Course Chat（后三项扩展阶段） | MVP(Overview+Records) |

### 4.3 M3 — 课堂记录与资料（数据入口模块）

#### 4.3.0 捕获入口矩阵与收件箱

**五级捕获入口**（轻→重，全部收敛为 Record 实体，统一管线）：

| 级别 | 入口 | 交互 | 默认去向 | 默认 AI 处理 | 阶段 |
|------|------|------|---------|-------------|------|
| L1 | ⚡ 速记/闪念 | 全局快捷键（默认 Ctrl+Alt+N，可自定义）→ 输入框（一句话~几段） | Inbox（NOTE 状态） | **无**——纯存储，手动升级制 | MVP |
| L2 | 📋 粘贴长文本 | 粘贴框 → 直接成 Record | Inbox 或选定课程 | **选定课程=直接进总结管线；未选课=仅存储**（等同速记，手动升级，#29） | MVP |
| L3 | 🔗 网页剪藏 | 贴 URL → sidecar 抓正文（readability）→ 文档管线 | Inbox 或选定课程 | 同 L2 | P2 |
| L4 | 🎵 音频导入 / ▶ 课堂录音 | 现有流程 | Inbox 或选定课程 | ASR → 总结管线 | MVP |
| L5 | 📄 文档导入 | 现有流程 | Inbox 或选定课程 | 解析 → 总结管线 | MVP |

**收件箱（Inbox）规则**：
- 所有捕获**可以先不选课程**（records.course_id 可空 = Inbox），时间流展示，事后三种动作：**归类到课程（填 course_id，不触发 AI 管线）/ 升级（触发 AI 管线）/ 删除**
- **升级必须先归类课程**（#29）：总结的 AI 上下文（learning_context/education_stage/depth）是硬依赖，无课程不总结
- **未归类内容不自动消费 token**（#29）：速记（NOTE 状态）与未选课粘贴均为纯存储，手动点"生成学习资产"才进入总结 HITL 管线
- 已选课程的录音/导入/粘贴仍走原即时管线（不强制先进 Inbox）
- **实施边界（#57/#58）**：plan 05 的单文档纵切要求选择 ACTIVE 课程；plan 04 的 audio-only/录音可不选课，但批次只要含 document 就必须选择 ACTIVE 课程；未选课文档及未选课混合批次仍由 plan 11 定稿，04/05 不提前创建不可重新发现的 Inbox Record。

#### 4.3.1 录音

| 项 | 需求 |
|----|------|
| 能力 | 开始 / 暂停 / 继续 / 结束；实时时长显示；异常中断尽量保留已录数据 |
| 时长上限 | 3 小时（180 分钟） |
| 技术链路（硬约束） | WebView2 MediaRecorder 录制 `audio/webm;codecs=opus`，**每 5~10 分钟分片直接落盘 `cache/staging/`**；03 只维护 recording_sessions、分片清单、恢复与 finalize。04 接棒后合并、以随包 ffmpeg 转 `ogg-opus`（16kHz）、原子注册最终 AUDIO/RECORDED record_file 并清理 webm，再切成 `<5MB` 片提交腾讯 ASR。原始 webm 不外发；用户同意后仅转码音频片段外发。 |
| 前置条件 | Tauri 防系统休眠；录音 POC（§11-Q6）通过后 03 才进入生产实现；04 的真实腾讯请求 P0 独立验证；**磁盘剩余空间防呆**（开始前校验 ≥2× 预估体积，不足提示） |
| 离线/缺配置 | 本地捕获、合并与转码照常；未同意、缺 key 或离线时 Record 保持 CONTENT_PROCESSING、ASR Job 保持 PENDING 且不消耗重试次数，条件满足后自动继续 |

**交互流程（#30）**：开始录音前弹最小对话框（标题可空 + 课程选择器，默认"不选 → 收件箱"）；结束录音后自动进入本地处理队列（无需手动提交）；未选课程的录音 **ASR 照常执行**（转写是事实记录，与课程无关），完成后停于 SUMMARY_PENDING，等待用户归类 + 升级触发总结。

#### 4.3.2 音频/文档导入

- 音频格式：MP3、AAC、WAV、M4A（+ 录音产生的 webm/ogg-opus）；录音会话 ≤3 小时，一个 Capture Batch 内**全部音频总时长 ≤5 小时**；不设文件数或原件体积硬限，正式注册前按整批原件总字节校验至少 2× 可用磁盘空间
- 文档格式：TXT、MD、PDF、DOCX（解析：原生文本 / PyMuPDF / python-docx；DOC、PPT/PPTX、OCR 不在范围）
- plan 05 先交付**单文件**导入：TXT/MD 仅接受 UTF-8/UTF-8 BOM 并保留 Markdown 标记；PDF 按页顺序提取文本层、非空页以空行合并，不伪造页码或启发式删除页眉页脚；DOCX 按原顺序提取正文段落与表格，排除页眉页脚、脚注/尾注、批注、文本框、嵌入对象、修订删除文字与图片文字。
- 文档 Transcript 保留源文本、不翻译；V1 不做语言检测，`language=und`。0 字节文件在 API 边界拒绝；非零但无可提取文本的文件保留为 FAILED Record（`NO_EXTRACTABLE_TEXT`），不提供同文件重试。
- `POST /api/capture-batches` 一次接收完整有序文件集：先逐文件流式落临时文件并完成整批格式/时长/磁盘校验，再用一个事务注册 Record、全部 record_files 与 Jobs；任一失败清理整批临时文件，不创建部分 Record。现有 `/api/document-imports` 保留为 05 的稳定窄入口并复用同一注册服务。
- Capture Batch 提交即封口，不持久化 batch 实体；提交后不得追加或重排，顺序由选择数组写入 `sequence_no=0..N-1`。单一来源沿用 DOCUMENT_IMPORT/AUDIO_IMPORT/RECORDING；混合来源写 `MULTI_SOURCE`。单文件标题取 stem，多文件标题为“首文件 stem + 等 N 个文件”。
- 导入原件**原样保留在 files/**；录音最终 ogg-opus 是正式原件。转码/ASR 切片与临时正文只放 cache：失败时为恢复保留，成功或取消后清理，启动时清理不再被非终态 Job 引用的孤儿 cache。
- 相同 `content_hash` 允许再次导入并创建独立 Record；hash 只用于完整性校验与重复检测，不阻止导入、不复用物理文件。

#### 4.3.3 ASR 转写

腾讯云录音文件识别（标准版）由 worker 调用。每个音频建立 `AUDIO_TRANSCODE → ASR` 两个 Job；ASR Job 把标准化音频切成目标 ≤5 分钟且严格 `<5MB` 的有序片，V1 每次只提交一个腾讯任务，不引入 COS/公网 URL/切片表/并发。`input_json` 固化切片清单及热词/模型/地域快照，凭据不复制入 Job；`result_json` 持久化 task id、切片状态和恢复游标，重启后成功片跳过、已提交片恢复轮询、未提交片才创建任务。首次外发前须独立告知并取得同意；配置 key 不等于同意，同意结果独立持久化在 `config/settings.json`。

V1 只持久化一份合并 Transcript：按 `sequence_no` 连接各来源正文，分隔符固定两个换行，不注入文件名、时间戳或人造标题；纯普通话音频写 `language=zh-CN`，含文档或混合来源写 `und`。腾讯返回的句子时间范围不在 V1 持久化或展示，Transcript Segments/时间轴仍属 P2。空音频以 `NO_SPEECH_DETECTED` 使整批失败。**V1 仅普通话语音；英文文本正常处理、输出中文（#45）；P2 英文支持指英文 ASR 与输出语言可选。**

#### 4.3.4 Record 状态机（业务态与技术态分离，v2.0 八态）

```
NOTE（速记/未选课粘贴，纯存储）
  └─ 升级（须先归类课程，#29）→ SUMMARY_PENDING
DRAFT → CONTENT_PROCESSING（本地转码 + ASR 提交/轮询 或 文档解析）
      → SUMMARY_PENDING → SUMMARY_PROCESSING → SUMMARY_READY（HITL 等待确认）→ COMPLETED
轻捕获已选课（粘贴）→ 直接进入 SUMMARY_PENDING（无转码与 ASR 环节）
已选 ACTIVE 课程的文档 → CONTENT_PROCESSING（解析）→ Transcript → SUMMARY_PENDING
未选课录音：ASR 照做，CONTENT_PROCESSING 完成后停于 SUMMARY_PENDING，等待归类+升级（#30）
最终失败 → FAILED（仅可恢复故障提供同文件重试）
```

业务态共 **8 个**：NOTE / DRAFT / CONTENT_PROCESSING / SUMMARY_PENDING / SUMMARY_PROCESSING / SUMMARY_READY / COMPLETED / FAILED——与数据模型 `records.status` 枚举一致。v1.x 的 UPLOADING 态随云端上传环节消解（#55）。

- `record.status` 只表达**用户可理解的业务状态**
- 转码 / ASR / 文档解析 / Embedding / Concept 抽取等**技术任务状态一律写 `processing_jobs`**（PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED）；文件关联表不重复保存技术状态。
- 文档解析的临时 I/O、SQLite busy、worker 意外中断每轮最多尝试 3 次（首次计入）；自动重试耗尽后允许用户手动重试。损坏、密码保护、纯图片/无可提取文本、格式伪装属于确定性失败：立即 FAILED，不自动重试、不显示同文件重试，只允许删除后重新选择文件；不提供 PDF 密码输入，不做 OCR。手动重试复用原 Job、开启新一轮额度，并原子执行 `Record → CONTENT_PROCESSING` 与 `Job → PENDING`、清理旧错误信息。
- 音频批次中任一 Job 终态失败后暂停领取该 Record 的后续 PENDING Job，其他 Record 不受影响；失败来源修复后再继续。全部来源成功前不得发布部分 Transcript；最后一个来源完成时单事务写 Transcript、终态 Job 与 Record→SUMMARY_PENDING。
- ASR 已取得 task id 后的轮询超时/限流/腾讯内部错误可自动退避，最多 3 次；提交超时且未取得 task id 标记 `ASR_SUBMIT_UNKNOWN`，不得自动重提。鉴权/额度/输入错误不自动重试。手动重试复用原 Job，保留成功切片与仍有效 task id，只重置失败/过期/未提交片；不使用 Job 级 `idempotency_key`。
- `GET /api/records/{record_id}/jobs` 返回底层 Jobs 与近似聚合进度（各 Job progress 简单平均）；URL 不携带 job id，也不增加父 Job。
- `GET /api/records/{record_id}/events` 使用可携带启动令牌的 fetch-stream，仅发“Record 已变化”通知。事件、重连或窗口恢复后统一 REST 重取；断线时仅非终态 Record 以 2 秒轮询兜底，不做事件持久化或重放。

### 4.4 M4 — AI 智能学习

#### 4.4.1 AI 课堂总结（唯一自动触发点 + HITL）

- ASR/解析形成 Transcript 后，由 plan 06 创建 Summary Job 并自动生成：课程主题（一句话）+ 摘要（500~1000 字）+ 结构化总结（分点）；触发前再次校验课程仍为 ACTIVE，输出经 Pydantic 结构化 Schema 校验入库。plan 04/05 只推进到 `SUMMARY_PENDING`，不自行实现 Provider、Summary Graph 或 HITL。
- **HITL 循环**：生成 → 展示 → 用户【确认】（解锁后续按钮）或【调整】（输入反馈如"更简洁些/侧重某主题"→ 重新生成，次数不限）
- 每次生成记录 model / prompt_version / latency / token / version_no（可回溯版本链）
- **超长转写分级（#36）**：转写 ≤3 万字单次生成；超过则按语义段落分块 map-reduce 分级总结；**禁止静默截断**（§8.4 评测集含长转写回归样本）
- Transcript 仅在内容处理成功且 Summary 未处理中时显式编辑保存；`PATCH /api/records/{id}/transcript` 携带 `expected_source_version`，冲突返回 409。保存成功使旧 Summary 标记 SUPERSEDED、Record 回 SUMMARY_PENDING；重新生成由用户明确触发，Summary 写回前校验绑定的 transcript_source_version。旧 KP/Quiz/Todo/作答/Event 不自动删除或覆盖。

#### 4.4.2 后续 AI 能力（总结确认后按需触发，各自 HITL）

| 功能 | 输出与 HITL | 优先级 |
|------|------------|--------|
| 知识点提取 | 名称/详情/标签/重要度/来源锚点；用户删除/编辑/补充后确认保存 | MVP |
| 习题生成 | 题型多选（选择题/判断题/简答题）→ AI 建议 3/5/10 道 → 生成；必含字段：题干/选项/答案/解析（简答题为参考答案） | MVP |
| 模拟测试 | 从题库抽题组卷、作答、评分；简答题 AI 语义评分但**最终分值与评分依据必须保存**；评分低置信（<0.7，**部署级可配置** `SHORT_ANSWER_REVIEW_THRESHOLD`，不进用户 UI）时标记"建议人工复核"——confidence 为 **LLM 结构化输出自评字段，仅用于 UI 复核标记，禁止参与掌握度计算**（#33）；每次作答落 learning_events（QUIZ_ANSWERED / QUIZ_TEST_COMPLETED，#43） | MVP |
| 复习资料 | 考前速记 + Top 重点清单 + **Markdown 大纲思维导图**（树形渲染，不做图形导图） | MVP |
| Todo 清单 | AI 生成 + 手动增删改，TODO/DONE，Record 级 | MVP |
| 学习资产 Markdown 导出 | 总结/知识点/习题/Todo/复习资料可单项或聚合导出为 `.md` 文件到本地（用户自选位置；只包含当前已生成且符合条件的内容） | MVP |
| 全量数据导出 | 数据目录打包 zip（db 快照 + files + config，默认不含密钥）——数据自主权与换机迁移载体（**提前至 V1，原 P2**，#55） | MVP（Wave B） |
| 课件差异分析 | 课堂讲解 vs 课件内容：已覆盖/课件有未讲/老师额外补充/重复强调/疑似考点，结构化结果 + 版本记录 | P3 |
| 重新生成 | 所有 AI 产出支持基于反馈或编辑后文本重新生成，不限制次数 | MVP |

### 4.5 M5 — AI 问答

| 能力 | 需求 | 优先级 |
|------|------|--------|
| **AI 对话（ChatGPT 式一级入口）** | 左栏一级入口：会话列表（新建/历史/重命名/删除）+ SSE 流式；**纯通用聊天**（系统提示注入用户角色 + 自我介绍）与**挂载上下文**（@记录=Record Chat、@课程=Course Chat、**@全部资料=全局 RAG**〔个人量级 sqlite-vec 全局检索〕）模式可切换；自由聊天不建向量索引、不进 Learning Evidence 链（红线 #5）；P5 起 Tutor/Teach-back 会话同界面以模式呈现 | MVP（@课程挂载 P3 生效；@全部资料 P2 生效） |
| Record Chat | 基于当前 Record（转写/总结/片段/知识点）多轮对话；SSE 流式（首事件 ≤3s）；Chat Memory（近 10 轮）；**MVP 上下文组装（#39）：转写全文常驻 + 溢出按对话轮数递减（保留摘要+知识点+近 3 轮引用的转写段）；P2 起改为摘要+知识点常驻 + 按问题向量检索转写片段**；答案携带引用（Source Anchor，可点击跳转课堂时间点） | MVP（溯源 P2） |
| 对话转学习资产 | 聊明白后一键"存为知识点 / 生成习题"挂到某课程，形成问→懂→沉淀闭环；转换产物复用现有表，对话片段经 Source Anchor（USER_NOTE / CHAT_MESSAGE）溯源 | P2 |
| 知识点解释 | 点击知识点进入针对该知识点的教学式对话 | MVP（简化）/P5（Tutor 完整版） |
| Course Chat | 课程级 RAG 问答——query 理解 → 范围过滤 → sqlite-vec 召回 → 上下文构建 → LLM → 答案+来源；**与 Record Chat 共用 chat_sessions/chat_messages，不建第二套消息模型**（mode 区分） | P3 |
| 工具扩展（联网搜索，#53） | Chat 实现为 **LangGraph agent 循环**（检索为第一工具——单工具时行为等同纯 RAG 管线）；**P2 落地 web_search**：SearchProvider 抽象，默认 Tavily（免费档），预留博查/智谱国产替代；无 key 按 #38 降级（搜索置灰，聊天照常）；搜索来源经 citations_json 引用；仅聊天域可用（红线 #11） | P2 |

### 4.6 M6 — 消息与状态通知

- 处理状态（转码/ASR/AI 生成）实时反馈：**Record 级 sidecar SSE 只发送失效通知，UI 收到后以 REST 重取**；断线时仅非终态 Record 条件轮询。plan 05 在 plan 04 接入 SSE 前可仅对 PENDING/RUNNING 文档任务条件轮询。
- 失败提示按 `error_code` 区分可恢复与确定性失败；只有可恢复失败显示同文件重试入口。

### 4.7 M7 — Learning Brain（共享智能层，扩展阶段）

> 详细设计以扩展文档为准，此处为基线摘要与验收约束。

| 能力 | 摘要 | 阶段 |
|------|------|------|
| F1 Segment+证据时间轴 | 句子级 Segment 持久化（record/file 双时间轴）；AI 结论可回跳原声 | P2 |
| F2 课堂标记 | 录音中 ⭐/❓/📝 快速标记；CONFUSED 仅主观信号，经验证才影响状态 | P2 |
| F6 Event+Evidence | 全部学习行为统一事件化（幂等）；Evidence 分层 | P2 |
| F4 Course Brain | Concept 图谱（concept/concept_relation/record_concepts）+ 语义记忆（semantic_embeddings + sqlite-vec）；V1 无 Neo4j | P3 |
| F5 Knowledge GPS | 掌握度地图；节点状态六枚举，禁止只按 Mastery 数字着色 | P3 |
| F7 Mastery | 可解释确定性算法（quiz/recall/teach_back/transfer 四分量 × 正确性/难度/新近度/权重）；带 confidence 与 evidence_count | P4 |
| F8 Misconception | SUSPECTED→验证→CONFIRMED/DISMISSED→纠错→RESOLVED；带置信度与证据计数 | P4 |
| F9 遗忘雷达 | V1 规则公式 priority = importance × forgetting_risk × (1-mastery) × exam_weight；V2 再评估 FSRS；复习须有 Recall 验证 | P4 |
| F10 Digital Twin | 运行时视图（非大 JSON 表），聚合 Mastery/Memory/Misconception/偏好；推测项必带 confidence | P4 |
| F11 Socratic Tutor | 苏格拉底式诊断-提问-评估循环（LangGraph Tutor Graph） | P5 |
| F12 Teach-back | 讲给 AI 听：覆盖率/遗漏/混淆分析 → 追问 → 验证 → Evidence；**V1 文本输入先行，语音后补** | P5 |
| F13 自适应测验 | 依掌握度+置信+前答+误区候选选题；规则优先选库、库不足才 LLM 生成 | P5 |
| F14 动态规划 | 考试目标（日期/分数/每日分钟/考纲）；计划版本化，完成项保留、锁定项不动 | P6 |
| F15 课前预习 | 上传下节课课件 → 概念抽取 → 对比课程脑与个人掌握 → 前置缺口 → 预习建议 | P5 |
| F16 Autopilot | 每日 Next Best Action 推荐（结构化输出）；必须 HITL 后执行 | P6 |
| F17 Passport | 证据型学习成果快照；Mastered 判定四条件，不由 LLM 决定 | P7 |
| F18 Study Pod | 可选协作层，P8，当前不做 | — |

---

## 5. MVP 与功能阶段边界

### 5.1 阶段规划

| 阶段 | 内容 | 出口标准 |
|------|------|---------|
| **首个真实功能里程碑（Wave A-0）** | 工作台壳、导航、路由与真实空态；最小课程；单文件 TXT/MD/PDF 导入→Transcript→AI 总结→HITL 确认；单一 active LLM Provider；由首次消费者带入数据目录、SQLite 迁移、localhost API 加固、最小 worker 与日志 | 真实文件经本地 API 落盘并完成总结确认；错误可恢复；`SUMMARY_READY` 跨重启可继续；不以 mock 数据或静态页面冒充功能完成 |
| **Phase 1 = MVP · Wave A（学习闭环主干）** | 课程 CRUD；录音/导入（统一转码 #31）；ASR+文档解析；Transcript（整段）；总结+HITL（长转写分级 #36）；知识点/习题/Todo/Markdown 导出；**AI 对话一级入口（自由聊天 + @记录挂载，SSE；上下文组装 #39）**；速记/粘贴捕获 + **Inbox 最小闭环**（#29/#30）；learning_events 四事件（#43） | **一节真实课堂（录音或导入）当日走通：转写 → 总结确认 → 知识点确认 → 习题作答 → 导出 .md；未归类内容可归类升级进同一闭环** |
| **Phase 1 = MVP · Wave B（工作台完善）** | 模拟测试（简答 AI 评分 + 低置信复核标记）；复习资料；Inbox 整理增强（批量/筛选）；命令面板 Ctrl+K（LIKE 搜索，#32）；学习统计；设置完善/深色模式；空态引导卡（#42）；无 key 降级 + 健康检查面板（#38）；**全量数据导出/导入** | **本基线 §4.1~§4.6 MVP 项全量可用 + 工作台形态达成** |
| Phase 2 学习数据基础 | Transcript/Document Segment、Source Anchor、Marker、Learning Evidence（Learning Event 已提前至 MVP，#33）、**sqlite-vec 语义检索**、**网页剪藏（正文抓取）**、**对话转学习资产**、**@全部资料全局 RAG**、**英文内容支持**、**Chat 联网搜索工具（Tavily，#53）**、**可选快照备份（WebDAV/S3，单向推送）** | AI 结论可回跳课堂原声 |
| Phase 3 Course Brain | Concept 抽取与消歧、课程级 RAG、Knowledge GPS v1、课件 Diff | "讲过几次 X"可答且带来源 |
| Phase 4 Learner Brain | Mastery、Forgetting（V1 规则）、Misconception、Digital Twin v1 | 事件→证据→掌握度闭环 |
| Phase 5 Adaptive | Socratic Tutor、Teach-back、自适应测验+Transfer、Memory Rescue、课前预习 | 三种学习模式产生 Evidence |
| Phase 6 Planner+Autopilot | Goal/动态计划、Next Best Action、今日建议+HITL、反馈 | 最小创新闭环跑通 |
| Phase 7 Outcome | Learning Profile、Passport、快照 | — |
| Phase 8 可选协作 | Study Pod（仅在核心稳定后） | — |

> **阶段启动门槛（#48）**：每个阶段（P2 起）开工前，先补该阶段详细设计评审再进入开发。

#### 5.1.1 实施顺序与验证节奏

- **页面优先不是静态页面批量铺设**：先完成应用壳、导航、路由和真实空态，再按 `桌面端 → localhost API → 数据` 纵切接通功能；未接通的入口不得伪装成功。
- **工程基础按首次消费者拉取**：第一个持久化功能同步落数据目录与 SQLite 迁移；第一个 API 同步落实随机端口、启动令牌和仅绑定 `127.0.0.1`；第一个后台任务同步落最小 worker/`processing_jobs`；第一个 AI 功能同步落 Provider 配置、`llm_call_logs` 与 Checkpointer。CI、发布流水线和 `.msi` 不作为页面开发前置。
- **首个实现顺序**：最小课程 → Record 工作台 → 05 单文件文档导入（Transcript + SUMMARY_PENDING）→ 06 AI 总结与 HITL；再由 04 扩展音频导入/ASR、多文件/混合来源与 SSE，由 03 承接录音捕获，由 11 承接未选课文档及 Inbox。AI 总结对上游来源采用“至少一条真实来源已接通”，不要求音频与文档同时完成。
- **首个 Provider 切片**：仅支持一个 active LLM Provider；DashScope 预设或自定义 OpenAI 兼容端点，最小字段为 `kind/api_key/base_url/model`。连接测试必须用保存的 model 做一次最小真实结构化生成，正式总结复用同一客户端。读取接口不返回原 key；空 key 更新默认保留，清除须显式操作；自定义地址仅接受不含内嵌凭据的绝对 `http/https` URL，默认校验 TLS，跨主机重定向不得携带 Authorization；前端不得直连 Provider。
- **缺 Provider 可恢复**：Record 保持 `SUMMARY_PENDING`，页面引导配置后继续；不得新增业务状态或把可恢复缺配置写成永久失败。完整多 Provider 管理、健康面板与用量统计仍归 Wave B。
- **验证跟随功能**：非平凡逻辑随实现留下最小可运行检查；一个较大业务闭环完成后再做集中集成与浏览器关键路径验证。sidecar 打包、冷启动、杀毒误报和新机 `.msi` 安装冒烟只在首次可分发里程碑执行。
- **完成口径**：Wave A-0 是 tracer bullet，不等于 plan 05/06 全部完成；DOCX 属于 05 完整出口，多文件/音频混合与 SSE 属于 04，超长文档 map-reduce 与完整黄金样本属于 06。各 plan 只按自己的出口独立宣称完成。

### 5.2 明确不做 / 暂缓清单

排行榜/XP、会员付费（本地功能永不设墙；云服务订阅形态见 Q15/ADR-0014）、OCR、通用社交、自由朋友圈、无来源 AI 认定掌握、未经确认的 Autopilot 自动执行、Neo4j、Qdrant、**Supabase 全家桶（Auth/Storage/Realtime/RLS/托管）**、**服务端部署形态（docker compose/云主机）**、**MySQL/Redis/Celery/RabbitMQ**、**双向同步**、**登录/账号体系/邮件（SMTP/OTP/Resend）**（桌面端永不做；未来云服务的可选云身份层见 Q15/ADR-0014）、Sentry/OTel/Langfuse 自托管、Stronghold、微信生态能力、视频导入、通用会议笔记工具、静态加密（SQLCipher P3+ 评估）。

---

## 6. 核心业务流程

### 6.1 主流程：课堂 → 学习资产（v2.0 全本地管线）

```
录音(分片 webm/opus，cache/staging 本地暂存) / 导入音频 / 导入文档
        ↓ 文件落入数据目录（files/ 或 staging 待合并注册）
[sidecar worker] ffmpeg → ogg-opus@16kHz（全部音频统一转码 #31）→ 腾讯云 ASR / 文档解析
        ↓
Transcript（整段）+（P2起）Segments
        ↓ 自动触发
AI 总结（默认 qwen-plus 或用户自选端点，结构化输出）
        ↓
HITL：确认 ✅ / 调整反馈 🔄（不限次循环，跨重启可恢复）
        ↓ 确认后解锁
知识点(HITL筛选) / 习题(选题型→数量3/5/10) / Todo(HITL增删) / 复习资料 / 模拟测试
```

### 6.2 HITL 暂停与恢复（LangGraph interrupt）

Summary Graph：`generate_summary → interrupt(review_summary) → 确认:COMPLETED | 调整:循环`。图状态持久化于 langgraph.db（SqliteSaver），**应用重启、隔天确认均可恢复**；Checkpoint 只存运行态，业务事实（确认结果、版本链）落业务表。

### 6.3 Learning Brain 闭环（P2+）

```
学习行为(答题/Teach-back/复习验证/标记)
   → Learning Event（幂等）
   → Evidence Builder → Learning Evidence（权重/置信度/来源锚点）
   → Mastery Engine（确定性）→ user_concept_mastery + confidence
   → Forgetting / Misconception 检测
   → Autopilot 候选动作打分 → 推荐（HITL）
   → Tutor / Review / Quiz / Teach-back 执行
   → 新 Evidence → 状态更新（闭环）
```

### 6.4 本地数据管理（v2.0：备份、导出与换机）

```
日常运行：knowrealm.db（WAL 模式，单写者=sidecar）+ files/ 原始文件
滚动备份：app 启动时将 db 快照至 backups/（每日一份 × 7，自动清理超出份）
全量导出：任意时刻 → exports/ 生成 zip（db 快照〔VACUUM INTO〕+ files/ + config；
         默认不含 providers.json 密钥，可选勾选包含）
换机恢复：新机安装 → 首启选空数据目录 → "从导出包导入" → 校验后落位
         （向量索引在 db 文件内，随包一体迁移——sqlite-vec 单文件红利）
P2 快照备份：可选配置 WebDAV/S3 → 定期单向推送导出 zip；永不双向同步（#55）
```

### 6.5 删除链（Record 为例）

软删除父表 → 数据目录关联文件（files/ 下该 record 目录）异步物理清理 → 向量标记删除后物理清理 → 该 Record 产生的 Learning Evidence 排除出掌握度计算（按 record_id 过滤），受影响 Concept 由 Mastery Engine 异步重算（#18）。

**补充**：挂载该 Record 的 chat 会话**不级联删除**——会话保留可读、挂载标记"原记录已删除"失效态，仅显式删除会话才删消息（#40）；业务行软删 **30 天后异步物理清理**（与文件/向量清理同批次；V1 无恢复 UI，删除弹窗明示"不可恢复"，#41）。

**处理中删除（#54）**：worker 每个写入步骤前校验 `record.deleted_at`，发现软删即终止链路并丢弃产物（不触发总结、不入库）；处理中允许删除，删除即隐式取消。删除事务将该 Record 的非终态 Job 置为 CANCELLED；已 SUCCEEDED/FAILED 的历史 Job 不改写。业务行与 `files/{record_id}/` 在 30 天清理批次物理删除。

### 6.6 轻捕获 → 收件箱 → 整理

```
速记(快捷键) / 粘贴文本(未选课) / [P2]贴链接抓正文
        ↓
   收件箱 Inbox（course_id 为空的 Record，时间流）
        ↓  用户事后整理（三种动作）
   ├─ 归类到课程（填 course_id，不触发 AI 管线）
   ├─ 升级：强制先归类课程 → 触发 AI 管线（NOTE → SUMMARY_PENDING → 总结 HITL → …）
   └─ 删除
粘贴长文本/剪藏若捕获时已选课程 → 跳过 Inbox 直接进管线
```

---

## 7. 数据安全与隐私（v2.0：本地单用户模型）

| 项 | 要求 |
|----|------|
| 认证 | **无登录、无账号**（本地单用户，#55）；桌面端**永不强制登录**，未来"账号"仅作可选云身份层（Q15/ADR-0014）；如需防他人开启，依赖 OS 用户账户（多人共用一台电脑=各自 OS 账户天然隔离：`desktop.json` 与默认数据目录均按用户分置）；应用锁（本地 PIN/Windows Hello）P3+ 可选评估 |
| 数据隔离 | 无 RLS（本地单用户库）；sidecar 仅监听 `127.0.0.1`；UI 不直读/直写数据目录与数据库文件（一切经 sidecar API，单写者） |
| 检索隔离 | 向量检索**恒定强制前置过滤 `deleted_at IS NULL`**；course_id/record_id 仅课程/记录范围检索时附加；禁止裸向量查询（#28 v2.0 版） |
| 文件存储 | 数据目录 `files/` 明文存放原始音频与文档（数据可见哲学，对齐 Obsidian；静态加密 V1 不做，SQLCipher P3+ 评估） |
| 通信边界 | UI ↔ sidecar 仅 localhost，**随机端口 + 启动令牌校验**（壳 spawn 时注入，中间件校验请求头，#56）；**数据外呼白名单见红线 #12**：LLM/Embedding/ASR API、P2 剪藏抓取、P2 快照备份——此外任何数据不出本机。ASR 首次外发独立同意：原始导入文件/WebM 不外发，仅转码音频片段发送腾讯云 |
| 日志隐私 | 禁止记录音频字节、原始/转码路径、SDK 原始请求响应、完整转写/Teach-back/敏感对话、密钥/Authorization/Token、可访问音频 URL；可记录内部 record/job/file ID、阶段、耗时、model/prompt_version、稳定 error_code |
| 密钥存储 | 供应商密钥明文存于 `config/providers.json`（用户可见、可随可选勾选进导出包；文档明示明文风险）；P3+ 评估 Windows 凭据管理器 |

---

## 8. 非功能需求

### 8.1 性能（产品指标）

| 指标 | 目标 |
|------|------|
| 普通接口 | P95 ≤ **300ms**（localhost 无网络 RTT；首个真实闭环实测回填定值） |
| AI Chat 首个流式事件 | ≤ 3s |
| Summary 任务提交 | **提交后 2s 内返回 job_id 且 processing_jobs 可查询**；生成 90s 超时标记 FAILED 可重试 |
| Desktop 首屏 | ≤ 2s（本地渲染，含 sidecar 冷启动） |
| 长任务 | 必须可查询状态（processing_jobs），不阻塞普通请求 |
| ASR（1h 音频） | 供应商配额强相关，作监控目标而非绝对 SLA |

### 8.2 可靠性

后台任务按稳定错误分类重试；Learning Event 以 `idempotency_key` 唯一，processing_jobs 不复用该业务幂等键。文件落盘有 content_hash、临时文件+rename 与整批失败补偿；ASR task id/游标在进入下一片前持久化，重启与手动重试不得重复成功片。重要写入事务化；SQLite **WAL 模式**；worker = sidecar 进程内 asyncio 任务池（V1 并发度 1，无外部队列）；同一数据目录由 sidecar 持有进程生命周期操作系统排他锁；**启动滚动备份**（backups/ 每日×7）防单文件损坏全损。

### 8.3 可观测（轻量方案）

自建 `llm_call_logs` 表记录：request_id、graph_name/node、model、prompt_version、embedding_model、token_usage、latency、retrieval_count、evidence_count、interrupt_count、error_code；结构化日志（loguru）承载非 LLM 观测；Autopilot 接受率/推荐成功率由业务表聚合。

### 8.4 测试策略

- 测试不是独立的开工阶段：最小检查随功能实现；较大闭环完成后集中跑集成、浏览器关键路径与回归；`.msi` 安装验证仅在首次可分发里程碑执行
- 后端 pytest：Event 幂等、Evidence Builder、Mastery 唯一写入口、Misconception 状态机、删除重算、**迁移升级链（user_version 逐版本）**
- 前端 Vitest+RTL：记录创建、录音草稿恢复、处理失败重试、Summary HITL、Chat SSE、深色模式；Playwright 仅关键路径冒烟（可选）
- **AI 评测集（按阶段拆分，#46）**：MVP 仅建**总结质量黄金样本（20 条真实课堂转写 + 人工标准总结）+ 人工评审 checklist**（含长转写回归样本）；习题 Groundedness 样本随 Wave B；引用准确性/Concept 抽取精度/简答评分一致性/误报率/推荐接受率随对应阶段补建

---

## 9. 桌面端信息架构与 API 分组

### 9.1 信息架构

```
┌────────────────────────────────────────────────────────────┐
│ [⚡速记] [📋粘贴] [🎵导入音频] [📄导入文档] [▶录音]   🔍搜索 Ctrl+K │ ← 快速捕获条（常驻）
├──────────┬─────────────────────────────────────────────────┤
│ 今日      │ 今日焦点：待确认总结(HITL待办) / 复习队列(P4) /      │
│ 收件箱📌  │          今日建议(P6) / 学习风险摘要(P4)              │
│ 💬 AI 对话│ ChatGPT 式会话列表：自由聊天 或 @课程/@记录/@全部资料挂载 │
│ 知识空间 ▾│ 最近资产时间流（记录/知识点/习题）                     │
│ 资产库    │                                                 │
│ 学习画像  │                                                 │
└──────────┴─────────────────────────────────────────────────┘
收件箱 Inbox：未分类捕获时间流 → 归类 / 升级 / 删除（MVP）
知识空间：Overview / Records / Course Brain(P3) / Knowledge GPS(P3) / Course Chat(P3)
资产库 Library：跨课程统一检索（MVP=记录/知识点全文搜索；P2+=向量语义检索）
学习画像(P7)：Activity / Mastery / Forgetting / Misconception / Passport
Record 详情：Summary(默认,HITL) / Transcript Timeline / Evidence(P2) / 知识点 / 习题 / 复习 / Todo / Ask AI
命令面板 Ctrl+K：开始录音 / 新速记 / 搜索一切资产 / 跳转课程与记录（MVP）
设置：档案与供应商(档案/供应商卡/数据目录/全量导出) / 偏好(主题/字号/快捷键/托盘行为) / 服务与用量(健康检查+token 用量)〔"数据与隐私"细化 P2〕
空态引导卡：各空区域显示引导卡，不做向导流程、不做示例数据（#42，Wave B）
首启角色卡：三步首启的最后一步，四选一（可跳过）；角色与自我介绍在 设置→档案 可改（#52，Wave B）
今日页统计带：学习统计（Wave B）= 学习趋势图（近 7 / 30 天）+ 六格指标带，置于"今日"页底部（#54）
```

### 9.2 API 分组（FastAPI sidecar，OpenAPI 自动生成 TS 类型）

```
/api/profile /api/settings /api/providers（供应商卡 CRUD + 连接测试）
/api/courses .../records    /api/records/{id}/(files|transcript|summary|knowledge|quiz|review|todo)
/api/chat/sessions .../messages（SSE：事件区分 token/status/citation/interrupt/done/error）
/api/learning/events|evidence    /api/courses/{id}/(concepts|knowledge-gps|brain/chat)
/api/concepts/{id}/(mastery|misconceptions)    /api/review/(today|rescue)
/api/tutor/sessions /api/teach-back/sessions /api/assessment/adaptive
/api/learning-goals /api/learning-plans
/api/autopilot/today /api/autopilot/actions/{id}/(accept|skip|defer|complete)
/api/passport    /api/data/(export|import|backup[P2])
```

---

## 10. 产品与架构决策记录

> 本节汇总记录本项目的产品与架构关键决策，后续开发以本表为准。v2.0 起受范式转向（#55）影响的行已按新范式改写（标注"v2.0 改写"）。

| # | 决策点 | **决策** | 理由 |
|---|--------|---------|------|
| 1 | 任务队列（v2.3 补充） | **自研 SQLite 队列**：processing_jobs 即队列表（status/attempts/next_run_at）+ sidecar 单 worker；技术态含 CANCELLED；按稳定 error_code 区分可重试性，文档/音频安全瞬态失败每轮最多 3 次，手动重试复用原 Job与可恢复检查点；无父 Job/切片表/外部中间件 | 单人单进程下分布式队列是负资产；Job JSON 检查点已覆盖 V1 顺序切片恢复 |
| 2 | AI 可观测 | **自建 `llm_call_logs` 表**，承接 LLM 调用追踪所需全部字段 | 个人项目自托管 Sentry/Langfuse 过重；追踪需求一张表满足 |
| 3 | 登录方式（v2.0 改写；v2.4 补充） | **无登录、无账号**——本地单用户，首启三步（目录→key→角色卡）取代注册登录；桌面端**永不强制登录**，未来"账号"仅作可选云身份层（Q15/ADR-0014） | #55：本地优先下认证无存在理由；v2.4：登录的对象是未来云服务，不是本地应用 |
| 4 | Embedding 维度 | **定 1024 维**；表内保留 embedding_model 字段备换模型（换模型=全量重嵌入，已知成本） | 建表必需定值；预留可演进 |
| 5 | ffmpeg 用途 | **全部音频统一转 ogg-opus@16kHz 并切片**；Tauri `externalBin` 随包携带关闭 GPL/nonfree 组件的 LGPL-compatible 构建，锁定来源/版本/配置/SHA-256/许可证，生产禁止依赖 PATH；ffprobe 仅测试使用 | 零部署与许可证可审计同时成立；不多带无生产消费者的二进制 |
| 6 | 桌面平台 | **V1 首发 Windows**（macOS 后评估） | 用户环境与 POC 成本 |
| 7 | Record 状态机 | **业务态/技术态分离**：record.status 只表达业务状态（8 态），技术任务状态只入 processing_jobs；record_files 不保存 processing_status | 多文件并行处理时单状态字段无法表达；双写会产生漂移 |
| 8 | 状态推送（v2.3 补充） | **Record 级 SSE 仅作失效通知，REST/SQLite 为事实源**；事件、重连、窗口恢复后 REST 校准，断线时非终态 Record 条件轮询；不做重放日志 | 避免 SSE 复制业务状态，同时满足启动令牌请求头与断线收敛 |
| 9 | 分享 | **Desktop V1 不做分享；Markdown 本地导出（#15）** | 分享卡片为小程序形态能力 |
| 10 | 迁移唯一权威（v2.0 改写） | **`backend/migrations/*.sql`（user_version 编号推进）**；LangGraph Checkpoint ≠ 业务事实（langgraph.db 独立文件） | Supabase CLI 随范式移除；SQL 文件目录保住"迁移单一权威"精神 |
| 11 | 密钥存储（v2.0 改写） | **供应商密钥明文存 `config/providers.json`**（可见、可随勾选进导出包；文档明示风险）；P3+ 评估 Windows 凭据管理器 | 无 token/会话可存；对齐同类工具（cc-switch/Cherry Studio）通行做法 |
| 12 | 新增表 | course_materials / record_analyses / source_anchor_links / semantic_embeddings / processing_jobs / learner_preferences **采纳**；~~user_settings~~（v2.0 并入 config 文件） | 均为既有功能所必需 |
| 13 | 性能表述 | **弱化 ASR SLA**（作监控目标而非绝对承诺） | 供应商指标不可本地承诺 |
| 14 | V1 平台范围 | **Windows 唯一首发平台** | WKWebView 不支持 webm/opus 录制 |
| 15 | 分享/导出形态 | **Markdown 本地导出（MVP）** | 桌面文件系统天然支持 |
| 16 | 离线能力（v2.3 补充） | **捕获/录音/转码/浏览/搜索/导出均可离线**；ASR 未同意、缺 key 或离线时 Job=PENDING、Record=CONTENT_PROCESSING，不消耗重试次数，条件满足后自动继续 | 等待条件不是执行失败；本地素材不可因云服务缺失丢失 |
| 17 | 邮件（v2.0 改写） | **整体作废**——无账号体系即无邮件场景（Resend/SMTP/OTP 全删） | #55 衍生 |
| 18 | 删除重算粒度 | **删除 Record → 其 Evidence 按 record_id 排除出掌握度计算，受影响 Concept 异步重算** | 防止已删数据静默影响 Mastery |
| 19 | Teach-back 输入 | **V1 文本先行，语音后补** | 少一条 ASR 依赖链路 |
| 20 | 简答评分复核 | **AI 评分低置信（<0.7，部署级可配置）标记"建议人工复核"** | 平衡自动化与可信度 |
| 21 | 产品形态/入口 | **个人学习工作台**：五级捕获入口、收件箱 Inbox、今日焦点/资产库/命令面板；速记手动升级制；剪藏 P2 | 同类开源无"捕获+组织+学习状态"一体化；轻捕获降摩擦 |
| 22 | 独立 AI 聊天界面 | **💬 AI 对话一级入口**：会话列表 + 自由聊天/挂载上下文双模式；自由聊天不建索引、不进 Evidence 链 | "打开即聊天"是 AI 产品事实心智 |
| 23 | 目标用户范围 | **泛化为"一切学习知识的人"**；courses `learning_context` + `education_stage`/`depth`；UI 术语泛称；英文内容 P2；不做视频导入与会议笔记 | 工作台化后产品形态自然溢出学生场景 |
| 24 | 个人知识库能力 | `semantic_embeddings.course_id` 可空（Inbox 内容入向量索引）；@全部资料全局 RAG（P2）；课程=唯一知识容器 | 泛化用户群的资料常不属任何"课"；个人量级全局检索无压力 |
| 25 | 部署与外部依赖（v2.0 改写） | **零部署**：安装 `.msi` 即用；外部依赖 = DashScope（或自选 OpenAI 兼容 LLM）+ 腾讯云 ASR（+P2 可选 Tavily / WebDAV·S3）；各自备 key、可缺省降级（#38） | 作者本人是第一用户，开源供愿意自备密钥的同类人；无容器/账号/付费云服务 |
| 26 | MVP 交付结构 | **Wave A / Wave B 双波次**，各自设验收线 | 单人项目分波降风险 |
| 27 | 性能指标（v2.0 改写） | 普通接口 P95 ≤300ms（localhost，首个真实闭环回填）；Chat 首 token ≤3s；Summary 硬条件（2s 返回 job_id；90s 超时 FAILED） | 本地通信无网络变量，指标可硬 |
| 28 | 向量检索红线（v2.0 改写） | **恒定强制前置过滤 `deleted_at IS NULL`；course_id/record_id 仅范围检索附加；禁止裸向量查询** | user_id 列已删（单用户库）；软删过滤不变 |
| 29 | 未归类内容 AI 处理 | **未选课不自动消费 token**；**升级强制先归类 ACTIVE 课程**；05 不实现未选课文档，入口及状态由 11 承接 | AI 上下文硬依赖；省 token；避免创建当前 UI 无法重新发现的 Record |
| 30 | 录音交互流程 | 开始前最小对话框；结束自动进**本地处理队列**；未选课录音 ASR 照做、停 SUMMARY_PENDING | ASR 是事实记录与课程无关 |
| 31 | 音频转码范围 | **全部音频统一 ffmpeg → ogg-opus@16kHz** 再进 ASR（v2.0 本地执行） | 单一管线、体积可控 |
| 32 | 全文搜索（MVP） | **LIKE 子串匹配**（SQLite）；P2 向量语义检索接管；不引入中文分词 | 个人量级子串匹配足够且符合中文直觉 |
| 33 | 简答评分置信度 & 事件提前 | confidence 仅 UI 复核标记，禁止参与掌握度计算；**learning_events 提前至 MVP 建表** | 模型自评不可靠；否则做题历史永久丢失 |
| 34 | 文档一致性回写（v2.0 改写） | 状态机统一 **8 态**（含 NOTE，UPLOADING 消解） | 全文档对齐现行决策 |
| 35 | 前后端边界（v2.2 补充） | **UI 仅经 localhost sidecar API**；不直读/直写数据目录与数据库文件；同一数据目录由 sidecar 持有进程生命周期操作系统排他锁，确保最多一个写者 | 收敛写入口，保住"一个事实源一份写入逻辑"；避免多应用实例抢占任务与迁移 |
| 36 | 长转写总结 | ≤3 万字单次生成；超过分块 map-reduce；**禁止静默截断** | 长上下文注意力衰减；截断违背溯源精神 |
| 37 | 邮箱确认（v2.0 改写） | **作废**（无注册流程） | #55 衍生 |
| 38 | 无 key 降级（v2.3 补充） | **功能级降级 + 启动健康检查面板**：缺 LLM key 时对应 AI 入口置灰；缺腾讯 key、离线或未同意时仍可捕获/导入/转码，ASR Job 进入不耗 attempts 的 PENDING 等待并在条件满足后自动继续。首个 AI 闭环先实现就地恢复，完整健康面板在 Wave B；不做月度 token 熔断 | 等待条件不是业务失败；本地素材不能因云服务缺失丢失 |
| 39 | Record Chat MVP 上下文 | **转写全文常驻** + 溢出按轮数递减；P2 起改摘要+检索 | MVP 无向量；细节追问必须转写在上下文 |
| 40 | 删 Record × 对话 | **不级联删 chat**：会话保留可读、挂载标失效态 | 对话有独立价值 |
| 41 | 软删语义 | V1 无恢复 UI、删除弹窗明示"不可恢复"；删除 Record 时非终态 Job→CANCELLED，已终态 Job 不改写；**业务行与文件软删 30 天后异步物理清理**（与向量清理同批次） | 无恢复入口的软删等价硬删且数据永久堆积；取消不能伪装成失败 |
| 42 | 空态引导 | 各空区域**引导卡**；不做向导流程、不做示例数据 | 示例数据污染真实学习数据 |
| 43 | MVP 事件范围 | 落地 **SUMMARY_CONFIRMED / KNOWLEDGE_CONFIRMED / QUIZ_ANSWERED / QUIZ_TEST_COMPLETED** 四事件（幂等键规则生效） | 其余枚举对应功能 P4+ 才有写入方 |
| 44 | 导入上限（v2.3 补充） | **录音会话 ≤3h；一个 Capture Batch 全部音频总时长 ≤5h**；不设文件数/原件体积硬限，正式注册前整批校验至少 2× 原件总字节可用空间；腾讯本地 ASR 片严格 `<5MB` | 防多文件绕过费用/时延边界；本地存储与供应商传输限制分别表达 |
| 45 | 英文支持边界 | **英文文本 V1 原样处理、AI 输出中文**；文档 Transcript V1 不做语言猜测，`language=und`；P2"英文支持"仅指 ASR 英文语音 + 输出语言可选 | 程序员粘贴英文文档是 V1 主路径；源文本语言不能被错误标成 zh-CN |
| 46 | AI 评测落地 | **按阶段拆分**：MVP 总结黄金样本 20 条 + 人工 checklist；其余随阶段补建 | 一次建全套既做不了也不必要 |
| 47 | 分发与更新 | **GitHub Releases 手动 `.msi`**（v2.0 含 sidecar，体积 +150~250MB）；打包、安装与冷启动冒烟在首次可分发里程碑执行，不阻塞此前页面与业务闭环；应用内"检查更新"仅链接跳转；Tauri updater 后置 | updater 需更新服务器与签名基建 |
| 48 | 阶段启动门槛 | **每阶段（P2 起）启动前先补详细设计评审再开工** | 摘要级 PRD 覆盖不到实现细节 |
| 49 | 文件路径规则（v2.0 改写） | 数据目录 `files/{record_id}/{file_id}.{ext}`（course 段不进路径）；归类课程后不迁移（归属以表字段为准） | 本地目录无需 user/course 分层；record_id 已唯一 |
| 50 | 多设备（v2.0 改写） | **单机为主；换机 = 全量导出 → 导入**；设置漫游概念删除（单一本地配置随导出包走） | 无云端即无漫游；快照满足"非同时多设备" |
| 51 | 设置域（v2.3 补充） | **单一本地配置**：`config/settings.json`（偏好+本机行为+外部处理同意）+ `config/providers.json`（供应商卡）；关窗默认驻留托盘+开机自启默认关；速记快捷键默认 **Ctrl+Alt+N** 可改；设置页“服务与用量”分区（#38 面板 + 30 天 token 用量）；简答复核阈值=部署级配置（sidecar .env）；录音 webm 分片=中间产物（cache/，最终 Ogg 原子注册后删），**存档原件=转码后 ogg-opus**；导入文件原件全保留 | v1.8 十二项中“上传后删本地”“漫游”等云端语义项随 #55 消解；外部处理同意与供应商凭据分立 |
| 52 | 用户角色 | 档案层 `profile.primary_role`（四选一）+ `about_me`（≤200 字）；首启一次性角色卡（可跳过）；建课程按角色预选默认场景；**自由聊天系统提示注入角色+自我介绍**；"角色改变语气与默认值，不改变能力集" | 自由聊天个性化锚点；课程级权威不变 |
| 53 | Agent 工具域 | **工具仅限聊天域**（红线 #11）；**Wave A Chat 以 LangGraph agent 循环实现**（检索为第一工具）；**P2 落地 web_search**：SearchProvider 抽象，默认 Tavily，预留博查/智谱；无 key 按 #38 降级 | 纯管线实现会导致 P2 加工具=重构 |
| 54 | 终审修补包（v2.3 补充） | **登录终态部分作废（#55 取代）**；维持项：音频时长见 #44；热词=课程手动列表（≤100 词，Job 创建时冻结）；处理中删除竞态（每步写前校验 deleted_at，非终态 Job→CANCELLED）；Capture Batch 提交封口，提交后不可追加/重排；统计与角色卡边界不变；~~signed URL~~ 作废 | 原 A 案登录为云端前提；封口批次使聚合完成条件唯一 |
| 55 | **存储范式（v2.2 补充，ADR-0001）** | **本地磁盘 = 唯一业务事实源**（数据目录：SQLite + files/，用户可见可搬移）；后端 = Tauri sidecar（PyInstaller 随 .msi，UI 走 localhost），同一数据目录由进程生命周期排他锁保证最多一个 sidecar；**LLM 自选任意 OpenAI 兼容端点**（DashScope 默认预设，供应商卡交互），Embedding V1 固定 text-embedding-v3，ASR 腾讯；云端降级为可选增强——V1 全量导出、P2 可选快照备份（WebDAV/S3 单向）、**双向同步永不做**；Supabase 全家桶除名；登录作废、首启三步；多设备=导出→导入；状态机 8 态；user_id 列全删；数据目录布局定稿（knowrealm.db/files/cache/exports/backups/config + langgraph.db）；启动滚动备份（每日×7）；导出默认不含密钥；静态加密 V1 不做 | v1.x"云端唯一事实源"源于先选 Supabase 后谈定位的顺序错误；free 档装不下（50MB 单文件 vs 3h 录音）、东京机房代理依赖、Pro $25/月、自部署须跑 docker——对"开源、个人使用"全是不符点；BYO-key 本地桌面是同类开源主流（Obsidian/思源/AnythingLLM 桌面版/Jan/Cherry Studio）；课堂录音不可再生故 P2 保留可选异地备份；决策时点代码沉没成本≈0 |
| 56 | 后端通信形态（v2.1 定稿） | **维持 FastAPI sidecar（localhost HTTP+SSE）**；否决自造 Rust/stdio 双协议层（两套手写契约、无 OpenAPI 类型生成、SSE 自造）与全 Rust 重写（LangGraph interrupt/HITL 无 Rust 等价物=核心差异化不可迁移，PyMuPDF/LangChain 生态全弃）；**localhost 加固随首个 localhost API 同步落地**：随机端口（壳分配注入）+ 一次性启动令牌（中间件校验请求头）+ 仅绑 127.0.0.1，不作为页面开发前的独立阶段 | 本机回环 HTTP 单次调用 ~0.1–1ms，相对 LLM/ffmpeg/ASR 的秒~分钟级耗时是噪声——性能不构成区分度，区分度在契约维护：40+ 端点 OpenAPI codegen 单一事实源 + Pydantic 同源 Schema（API 请求响应与 LLM 结构化输出共用一套）+ UniApp 端未来契约复用（§1.3）；完整对比入技术栈 v4.3 §二 |
| 57 | 文档导入实施合同（v2.2） | 05=单文件 TXT/MD/PDF/DOCX、ACTIVE 课程、Transcript+SUMMARY_PENDING；06=Summary/HITL；04=多文件/音频混合/SSE；11=未选课文档/Inbox。相同文件可重复导入；导入成功直达 Transcript；确定性解析失败不可重试；处理中课程归档不丢弃已受理解析，06 触发 AI 前再校验 ACTIVE | 消除 05 对 04/06/11 的循环出口与不可验收范围；保持首个真实纵切诚实可关闭 |
| 58 | 音频导入与转写合同（v2.3，ADR-0002~0006） | 04=封口 Capture Batch、MULTI_SOURCE、随包 ffmpeg、本地 `<5MB` 腾讯切片、可恢复 ASR Job、Record 级 SSE 通知+REST、整批 Transcript 原子发布与版本化编辑；03=录音 staging/恢复/finalize；06=完整总结出口。未同意/缺 key/离线等待不失败；原件不外发，转码音频须独立同意；不引入 COS、父 Job、切片表或 V1 Segment | 在本地优先、供应商限制、隐私、费用与最小实现之间形成可验收边界 |

---

## 11. 待确认问题清单

> v2.0 收敛：原 Q1/Q2/Q3/Q5/Q8/Q9/Q10（v1.1 定稿）、Q4/Q12/Q13（随 #55 作废——无 Supabase 区域/性能基线/连接配置问题）。仅剩：

| # | 问题 | 影响范围 | 前置条件 |
|---|------|---------|---------|
| Q6 | 录音 POC 结果回填：真实 WebView2 麦克风在最小化/隐藏/锁屏下的节流、分片连续性与异常退出恢复 | 录音捕获方案锁定 | plan 03 首张实现票；04 的随包 ffmpeg与真实腾讯分片请求另设本 plan P0，不互相阻塞 |
| Q14 | sidecar 打包冒烟结果回填：PyInstaller 体积/杀毒误报率/冷启动时间 | 打包与分发方案 | 首次可分发 `.msi` 的准入条件，不与录音 POC 捆绑 |
| Q15 | **分享形态与登录必要性**——**登录侧（v2.4 定稿，ADR-0014）**：桌面端**永不强制登录**；"账号"=未来**可选云身份层**（Raycast/Obsidian/Zen 模型——登录仅 gate 云服务与会员权益，数据永不出本地，#55 存储范式不变）；偏好形态=邮箱+密码+GitHub OAuth（触发时按成本梯度复核：托管 Auth/纯 OAuth 优先，不自建密码体系）；触发条件=**决定运营 KnowRealm 云服务/启动商业化那天**；桌面端不预埋代码钩子（ADR-0013"一安装一数据目录"天然支持"一云账号↔一本地数据目录"）。**分享形态仍搁置待决**——候选：(i) 单文件 HTML 导出（P2，零服务零账号，文件即可分享）；(ii) GitHub Gist·Pages 发布渠道（P3，供应商卡 BYO PAT——GitHub 角色是"发布渠道"非"登录"）；(iii) 均不做（`.md` 导出已覆盖"发给同学"场景） | 分享/导出体系（§4.4.2）；P3 若落地发布渠道，红线 #12 白名单须增补"发布推送"通道。登录侧调研（2026-08-30）：ChatGPT/Warp/opencode 登录对象均为厂商云服务、本地核心匿名可用（Warp 2024-11 撤销强制登录；opencode Zen 官方标注 completely optional）；多人数据/偏好隔离由 OS 账户天然覆盖（`desktop.json` 与默认数据目录均按用户分置，零开发） | 登录侧 2026-08-30 grilling 定稿（ADR-0014）；分享侧未重启，仍以本行为起点 |

---

## 12. 风险清单

| # | 风险 | 等级 | 缓解 |
|---|------|------|------|
| R1 | 录音/导入→ASR 格式与供应商传输限制（webm 不支持；本地请求 ≤5MB；提交超时无幂等键） | **高** | 03 POC验证真实录音；04 P0 用随包 ffmpeg+真实中文语音验证 `<5MB` 切片、边界文本、腾讯提交/轮询与重启恢复；无 task id 的未知提交不自动重提 |
| R2 | sidecar 打包（PyInstaller 体积 +150~250MB / 杀毒误报 / 冷启动时间） | **高** | 首次可分发 `.msi` 前完成冒烟（§11-Q14）；UPX 关闭换取误报率；启动预热 |
| R3 | SQLite 单文件损坏（断电/磁盘错误） | 中 | WAL 模式；启动滚动备份 backups/（每日×7）；引导用户导出习惯 |
| R4 | 数据目录被 OneDrive/同步盘接管（锁冲突+上传风暴） | 中 | 首启检测已知同步目录并提示改选 |
| R5 | 3 小时长录音稳定性（系统休眠/WebView 节流/磁盘占满） | 高 | 分片落盘、防休眠、磁盘防呆、POC 验证 |
| R6 | LangChain/LangGraph 1.x API 变动 | 中 | 锁版本；仅用四个子包 |
| R7 | LLM 输出质量漂移（自选端点尤甚） | 中 | 固定评测集（以 qwen-plus 为基准）+ prompt 版本化 + llm_call_logs 追踪；文档声明评测基线只对默认预设负责 |
| R8 | sqlite-vec 成熟度/性能（生态弱于 pgvector） | 低 | 个人万级 segment KNN 足够；量级余量大 |
| R9 | 腾讯云 ASR SDK 同步阻塞 | 中 | 仅在 worker 任务内使用，不进 API 主进程 |
| R10 | 网页剪藏（P2）依赖目标站可达性与正文解析质量 | 中 | readability 容错 + 失败降级"手动粘贴"；仅 httpx 服务端抓取 |
| R11 | 多应用实例同时打开同一数据目录，抢占迁移或 processing_jobs | 高 | sidecar 在迁移和 worker 启动前获取操作系统非阻塞排他锁；失败实例明确提示目录正被使用并退出；进程退出/崩溃由 OS 自动释放锁 |

---

## 13. 验收清单（关键项）

**首个真实功能里程碑（Wave A-0）**

- [ ] 工作台壳、导航、路由与真实空态可用；未接通入口不伪造成功
- [ ] 最小课程创建/列表与 Record 工作区使用真实本地数据
- [ ] 真实 TXT/MD/PDF 单文件经本地 API 落盘并生成 Transcript
- [ ] 单一 active LLM Provider 可保存并跨重启读取；GET 仅返回掩码/已配置态，不返回原 key
- [ ] 连接测试使用保存的 model 完成最小真实结构化生成；错误 key、错误 model、超时均可识别并重试
- [ ] 未配置 Provider 时 Record 保持 `SUMMARY_PENDING`，配置后可继续，不丢失 Transcript
- [ ] 真实 Transcript → 结构化总结 → 调整 → 确认；`SUMMARY_CONFIRMED` 事件幂等，`ai_summaries` 版本链可查
- [ ] `SUMMARY_READY` 时重启应用仍可继续 HITL 确认
- [ ] 数据目录、SQLite WAL 与迁移体系由首个持久化功能同步落地
- [ ] UI 仅经 localhost sidecar API，不直读数据目录（#35）
- [ ] localhost 加固生效：随机端口 + 启动令牌校验，同机无令牌进程调用被拒；仅绑 127.0.0.1（#56）
- [ ] 第二个 sidecar 打开同一数据目录时在迁移/worker 启动前被明确拒绝；首个 sidecar 退出或崩溃后锁可自动释放
- [ ] `llm_call_logs` 可追踪 model/prompt/token/latency/node，且日志不含 key、Authorization、Transcript 或总结全文

**Phase 1 = MVP（Wave A → Wave B）**

- [ ] plan 04 P0 以随包 ffmpeg 和真实腾讯请求验证音频导入、`<5MB` 顺序切片、边界文本、检查点恢复与不重复成功片；运行时不依赖系统 PATH（#31/#58）
- [ ] plan 03 完成真实 WebView2 麦克风在最小化/隐藏/锁屏下的长录音、分片连续性与强杀恢复 POC（Q6）
- [ ] Wave A 验收线：真实课堂当日走通 录音→转写→总结确认→知识点确认→习题作答→导出 .md；未归类内容可归类升级进同一闭环（#26）
- [ ] LangGraph Checkpointer（langgraph.db）可暂停恢复；Summary HITL 跨重启恢复
- [ ] 结构化输出全部经 Pydantic Schema；超长转写分级总结无静默截断（#36）
- [ ] learning_events 建表并落地四事件，幂等键唯一（#33/#43）
- [ ] 日志不含转写/对话全文
- [ ] Wave B 验收线：§4.1~§4.6 MVP 项全量可用 + 工作台形态达成；简答 AI 评分 confidence 仅作 UI 复核标记（#33）
- [ ] **全量导出→空目录导入→数据完整**闭环通过（含向量索引随 db 迁移）
- [ ] 总结质量黄金样本 20 条 + 人工评审 checklist 建立并纳入回归（#46）
- [ ] 无 key 功能级降级 + 健康检查面板（#38）
- [ ] 核心流程有集成测试

**首次可分发里程碑**

- [ ] sidecar 打包冒烟通过：体积/杀毒误报/冷启动可接受（§11-Q14）
- [ ] Windows `.msi` 在干净环境完成安装、启动、退出与再次启动冒烟
- [ ] CI / GitHub Releases 手动发布流水线可重复执行

**Phase 2+（随阶段验收）**

- [ ] 检索恒定强制 deleted_at 过滤，范围字段按需附加；向量删除与业务删除一致（#28）
- [ ] 快照备份单向（无任何回写路径）
- [ ] Mastery 单一写入口；Misconception 默认 SUSPECTED（P4）
- [ ] Learning Brain 固定评测集随阶段补建（P4 起，#46）
