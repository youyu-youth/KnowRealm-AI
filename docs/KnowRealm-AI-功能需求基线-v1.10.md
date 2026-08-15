# KnowRealm-AI 功能需求基线 v1.10

> **文档定位**：KnowRealm-AI 第一版产品需求文档（PRD），覆盖产品定位、功能需求、架构约束、阶段规划与产品决策记录。
>
> 配套文档：
> - 技术选型：`docs/技术栈设计与审查-v3.md`（v3.4）
> - 数据库设计：`docs/KnowRealm-AI-数据模型-v1.10.md`
> - Learning Brain 扩展设计（F1~F18 机制与交互参考）：`docs/AI课堂助手-功能升级与创新扩展设计.md`
> **项目定位**：开源、面向个人使用。所有设计先过两问：能否被现有 Postgres/Supabase 吸收？自部署用户要多跑几个容器？
> **编写日期**：2026-08-14
> **变更记录**：v1.1（2026-08-14）待确认清单收敛——Q1 平台 Windows 先行、Q2 分享=Markdown 本地导出、Q3 离线编辑 V1 不做、Q5 SMTP=Resend、Q8 删除重算策略、Q9 Teach-back 文本先行、Q10 简答低置信复核，均已定稿（决策 #14~#20）；仅 Q4/Q6/Q7 留待实测。
> **变更记录**：v1.2（2026-08-14）产品形态升级为**个人学习工作台（Learning Workbench）**（基于 GitHub 同类开源调研，决策 #21）——新增五级捕获入口（速记/粘贴/剪藏/音频/文档）、收件箱 Inbox（course_id 可空，先捕获后整理）、工作台信息架构（今日焦点/资产库/命令面板）；速记手动升级制；网页剪藏 P2；**数据模型零新表**。
> **变更记录**：v1.3（2026-08-14）新增 **💬 AI 对话一级入口**（ChatGPT 式，决策 #22）：会话列表 + SSE 流式；纯通用与 @课程/@记录 挂载两种模式可切换；自由聊天不建向量索引、不进 Evidence 链；对话转学习资产（P2）；数据模型仅 `chat_sessions.course_id` 改可空，**零新表**。
> **变更记录**：v1.4（2026-08-14）**目标用户泛化为"一切学习知识的人"**（学生+程序员+上班族+终身学习者，决策 #23）：courses 改 `learning_context` + `education_stage`/`depth` 双字段；UI 术语以"学习会话/学习记录"泛称；英文内容 P2；全量数据导出 P2；明确不做视频导入与通用会议笔记。
> **变更记录**：v1.5（2026-08-14）**补齐个人知识库能力**（决策 #24）：`semantic_embeddings.course_id` 改可空（Inbox/未分类内容入向量索引）；AI 对话新增 **@全部资料** 全局 RAG 问答（P2）；"知识空间"文案心智（课程=唯一知识容器，无需独立知识库实体）；**零新表**。
> **变更记录**：v1.6（2026-08-15）文档定稿：清理外部文档交叉引用；§10 更名为"产品与架构决策记录"。
> **变更记录**：v1.7（2026-08-15）**需求评审定稿（27 项拷问决策，§10 新增 #25~#50）**：产品定位定稿"自用优先、开源自部署"（#25）；MVP 拆 Wave A/B 双波次（#26）；§8.1 性能改实测回填 + Summary 硬条件（#27）；向量检索红线改写（#28）；未归类不自动耗 token、升级强制归类（#29）；录音交互流程补齐（#30）；统一转码（#31）；MVP 全文搜索=ILIKE（#32）；confidence 仅 UI + learning_events 提前 MVP（#33）；文档一致性回写（#34）；前端直连边界（#35）；长转写分级总结（#36）；禁用邮箱确认（#37）；无 key 功能级降级（#38）；Record Chat MVP 上下文（#39）；删 Record 不级联对话（#40）；软删 30 天清理（#41）；空态引导卡（#42）；MVP 四事件（#43）；导入上限 5h（#44）；英文边界澄清（#45）；评测按阶段拆分（#46）；手动分发（#47）；阶段启动前详评（#48）；Storage 路径规则（#49）；多设备非同时（#50）。
> **变更记录**：v1.8（2026-08-15）**设置域评审定稿（决策 #51）**：砍"隐私"空壳页（P2 随全量导出上线"数据与隐私"三件套）；录音分片上传+转写成功后即删本地（可选保留开关默认关）；关闭窗口默认驻留托盘 + 开机自启默认关（速记快捷键依赖常驻）；速记快捷键默认 Ctrl+Alt+N 可自定义；设置页新增"服务与用量"分区（#38 健康面板 + 近 30 天 token 用量，Wave B）；简答复核阈值定为部署级配置；user_settings 严格命名列演进（locale V1 隐藏、timezone 默认取 OS/P4 生效）；local_settings V1 八键清单定稿。**ASR 维持腾讯云单引擎（FunASR 双引擎提案否决，用户拍板）**。
> **变更记录**：v1.9（2026-08-15）**角色域定稿（决策 #52）**：档案层 `primary_role`（STUDENT/DEVELOPER/OFFICE_WORKER/OTHER 四选一）+ `about_me`（≤200 字）；首启一次性角色卡（可跳过、不问学段）；建课程按角色预选默认场景；自由聊天系统提示注入角色+自我介绍（挂载会话不叠加、新会话生效不追溯）；原则"**角色改变语气与默认值，不改变能力集**"；角色永不进入课程范围 AI 管线与 Learning Evidence（#23 课程级权威不变）。**追加决策 #53（Agent 工具域）**：工具仅限聊天域（新增红线 #11：Summary/Tutor/TeachBack 禁止联网工具）；Wave A Chat 以 LangGraph agent 循环实现预留（检索为第一工具）；P2 落地 web_search（默认 Tavily、预留博查/智谱国产替代、无 key 按 #38 降级）。
> **变更记录**：v1.10（2026-08-15）**终审修补包（决策 #54，全文档严格复审）**：登录终态 A 案——首启包装"初始化你的工作台"（登录=云上数据的锁+三处直连身份锚，非多用户能力）+ 密码三规则（已登录改密码 V1 支持 / 忘记密码 V1=Supabase Dashboard / 邮箱变更 V1 不做）+ 第三方 OAuth 首选候选 **GitHub**；音频导入改**时长+大小双限**（原始文件建议 ≤500MB，修正 #44 与 Q7 的上传体积冲突）；**热词降级**为课程手动列表（≤100 词，自动同步 P2）；处理中删除竞态规则入 §6.5；多文件定序规则入 §4.3.2；统计入口=今日页底部卡片、AI 总结口径=ai_summaries 行数、角色卡定 Wave B；修正 4 处残留（§3 技术栈版本、§7 OTP、§8.3 loguru、§6.1 转码措辞）；§7 补 signed URL 后端签发校验；新增 §11-Q13 首启连接配置（开发前决策）。

---

## 1. 项目与产品概述

### 1.1 产品定位（三阶段演进）

| 阶段 | 定位 | 一句话 |
|------|------|--------|
| 当前（V1） | **个人学习工作台（AI 学习助手）** | 五级捕获（速记/粘贴/剪藏/音频/文档）把课堂录音、历史音频、课程文档与闪念统一转化为可编辑、可追溯的学习资产（总结/知识点/习题/复习/Todo），并提供基于上下文的 AI 问答 |
| 升级 | **AI Personal Learning Brain** | 持续维护"掌握多少、为什么没掌握、什么时候会忘、下一步学什么" |
| 长期 | **AI Learning OS** | Observe → Understand → Diagnose → Decide → Teach → Verify → Update 的持续学习系统 |

**产品形态（v1.2）**：**个人学习工作台（Learning Workbench）**——顶部快速捕获条 + 左栏工作区导航（今日/收件箱/课程/资产库/学习画像）+ 命令面板（Ctrl+K）。多级捕获（速记/粘贴/剪藏/音频/文档）+ 收件箱整理 + Record 学习管线 + Learning Brain，对标并超越开源生态中的捕获工具（Meetily/memos）与 second brain（Khoj/AnythingLLM）——同类中尚无"捕获+组织+学习状态+自适应"一体化的开源工作台。

### 1.2 目标用户与学习深度策略（v1.4 泛化）

面向**一切学习知识的人**：全学段学生（初中至博士）、程序员、上班族与终身学习者。**每门课程独立设置学习场景与深度**（非用户全局属性），进入所有 AI Prompt 上下文，决定输出风格与深度。

**学习场景 `learning_context`（必填，v1.4 新增）**：

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

> **术语约定（v1.4）**：产品 UI 文案以"**学习会话 / 学习记录**"泛称（覆盖课堂、技术分享会、培训、自学等场景），代码与数据实体仍为 Record；本文档沿用"课堂"处均指学业场景的学习会话。
> **知识空间（v1.5）**：课程是唯一知识容器——学业课程（SCHOOL）、技能空间（CAREER）、主题收藏（INTEREST）在 UI 层统称"**知识空间**"，剪藏/导入/录音汇入即形成个人知识库；配合资产库全局检索与 AI 对话 @全部资料，不设独立知识库实体。
> **用户角色（v1.9，#52）**：档案层 `primary_role`（STUDENT / DEVELOPER / OFFICE_WORKER / OTHER 四选一）+ `about_me`（≤200 字自由文本）——用于首启角色卡、建课程默认值、自由聊天系统提示与文案基调；**角色改变语气与默认值，不改变能力集**，永不进入课程范围 AI 管线与 Learning Evidence；学习场景权威仍在课程（#23 不变）。

### 1.3 产品形态与端范围

| 端 | 状态 | 说明 |
|----|------|------|
| Desktop（Tauri 2 + React） | **V1 实施** | **Windows 为 V1 唯一首发平台**（v1.1 定稿）；macOS 在核心功能稳定后评估——届时录音链路需另适配 WKWebView（Safari 内核不支持 webm/opus 录制）或改 Rust cpal 方案 |
| UniApp App 端 | 暂不实施 | 未来 Vue3 + UniApp；与 React 桌面端仅复用 OpenAPI 类型契约与后端能力，UI 层不复用 |
| 微信小程序 | 不实施 | — |

**微信小程序相关能力**（微信登录/分享卡片/上传限制/轮询）与小程序形态绑定，不纳入 Desktop V1；见 §10 决策记录。

### 1.4 核心用户场景

1. **课堂录音**：学生上课录音 2~3 小时（可打 ⭐重点/❓没听懂/📝记下 标记），下课后自动获得 AI 总结，确认后按需生成知识点/习题/Todo/复习资料
2. **历史音频导入**：导入已录制的 MP3/M4A/WAV 等文件，走同一处理管线
3. **文档导入**：导入 PPT/PDF/DOCX/TXT/MD 课件，跳过 ASR 直接进入 AI 管线；一条记录可同时关联多段音频与多个文档
4. **课后问答**：基于本节课转写文本 + 总结的多轮追问（SSE 流式），答案可溯源到课堂原声位置
5. **长期学习（扩展阶段）**：考前动态规划、遗忘提醒、误区验证、每日学习建议（Autopilot）
6. **闪念速记（v1.2）**：自习/阅读时全局快捷键弹出速记框，一句话/一段文字先存进收件箱，不打断当前学习，事后整理归类
7. **资料剪藏/粘贴（v1.2）**：看到一篇好文章或一段网课文字稿，粘贴（或 P2 起贴链接自动剪藏正文）直接进入 AI 学习管线，生成总结与知识点
8. **程序员（v1.4）**：读技术文档、看技术分享会录音——粘贴/剪藏/录音进管线，生成知识点与习题；AI 对话问代码问题，代码块高亮渲染，聊完一键存为知识点
9. **上班族（v1.4）**：职业培训录音、考证资料导入；考证前用动态规划与遗忘复习安排学习

---

## 2. 核心概念与分层

### 2.1 三层事实边界（不可互相替代）

```
云端业务事实  = Supabase PostgreSQL（唯一权威数据源）
本地工作区    = Desktop SQLite（缓存 + 草稿 + 离线队列 + 本机设置）
Agent 运行态  = LangGraph Checkpoint（Supabase 独立 schema langgraph.*，非业务事实）
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

技术栈详见 `docs/技术栈设计与审查-v3.md`（**v3.4**），此处仅列结论：Tauri 2 + React/TS + TanStack Router/Query + Zustand；FastAPI + LangChain/LangGraph + procrastinate（Postgres 队列，**无 Redis**）；Supabase（Postgres + pgvector + Auth + Storage + Realtime + RLS）；DashScope qwen-plus + text-embedding-v3；腾讯云 ASR + ffmpeg；迁移统一 Supabase CLI。

### 3.1 十一条架构与数据红线

1. **Supabase PostgreSQL 是云端唯一业务事实数据库**；SQLite 不得成为第二事实源、不与云端双主写入。
2. **LangGraph 只编排需要状态、暂停恢复、HITL 或 Agent 决策的流程**；普通 CRUD 与确定性业务逻辑（Course/Quiz/Todo/EvidenceBuilder/MasteryEngine/QuestionSelector 等）保持普通确定性 Python Service；禁止构建超级 Graph（独立 Graph：Summary / Tutor / TeachBack / Autopilot / MisconceptionVerification）。
3. **Mastery 唯一写入口**：业务动作 → Learning Event → Evidence Builder → Learning Evidence → Mastery Engine → `user_concept_mastery`。任何 Quiz/Tutor/Teach-back Service 禁止直写 Mastery。
4. **AI 诊断必须可追溯**：任何 Mastery/Misconception/Digital Twin/Autopilot 输出必须携带 Evidence、Confidence 或 Decision Snapshot；证据不足显示 `NOT_ENOUGH_DATA`，禁止伪造精确分数。
5. **AI 自述不是 Evidence**：`AI_SYNTHESIS` 类输出不参与掌握度计算；Evidence 只来自答题、Teach-back、Recall 验证、Tutor 检查、课堂信号、用户确认。
6. **Misconception 先怀疑再验证**：SUSPECTED → 验证 → CONFIRMED/DISMISSED → 纠错 → RESOLVED；一次答错不得定性。
7. **Autopilot 只推荐不执行**：任何动作经用户 Accept/Skip/Defer/Adjust 后才运行；不得自动开考、自动生成大量题目、自动认定掌握。
8. **数值计算与 LLM 分工**：Mastery、遗忘风险、复习优先级、下一题选择由确定性规则计算；LLM 只做内容理解、语义评分、Concept 对齐、诊断解释。
9. **概念分层与任务分层不可破坏**：KP（Record 级）≠ Concept（Course 级）；Todo / Learning Plan Item / Autopilot Action 三表分立。
10. **迁移唯一权威** = `supabase/migrations/*.sql`（Supabase CLI）；LangGraph Checkpoint ≠ 业务事实，长期事实必须落业务表；`record.status` 表达用户可理解业务状态，技术任务状态在 `processing_jobs`。
11. **Agent 工具仅限聊天域**：联网搜索等工具只进入聊天会话（自由聊天默认可用、挂载会话可选）；Summary / Tutor / TeachBack Graph **禁止联网工具**，产出只基于用户资料——总结与教学的可信度根基（#53）。

---

## 4. 功能模块与详细需求

> 优先级标注：MVP = Phase 1 交付；P2~P6 = 扩展阶段（见 §5）。

### 4.1 M1 — 用户、认证与设置

| 功能 | 需求要点 | 优先级 |
|------|---------|--------|
| 登录认证 | **邮箱 + 密码**（V1 **禁用邮箱确认**——注册即用、零 SMTP 依赖，#37）；首启包装为"**初始化你的工作台**"——登录定位 = **云上个人数据的锁 + 三处直连（RLS/Realtime/Storage）的身份锚**，非多用户能力（#54）；会话本地持久化+自动续期，登录界面一生一次；**密码管理（#54）**：已登录改密码 V1 支持（updateUser 免邮件）/ 忘记密码 V1 = Supabase Dashboard 手动重置（部署文档写明）/ 邮箱变更 V1 不做；OTP/邮箱确认/Resend 于"对外发布"里程碑启用；**第三方 OAuth 预留，首选候选 GitHub**（对外发布时评估，#54）；Supabase Auth 签发 JWT，FastAPI JWKS 验签注入 user_id；微信登录不适用于桌面端，不实现 | MVP |
| 用户信息 | 昵称、头像（Storage `avatars` 桶）、**角色（primary_role 四选一 + about_me ≤200 字，#52；账户设置可随时修改）**；不保存密码，认证事实属 Supabase Auth | MVP |
| 退出登录 | 清除本地会话 | MVP |
| 学习统计 | 累计学习时长 / 记录数 / 课程数 / AI 总结次数 / 习题生成与完成次数 / 问答轮次——**由业务表聚合，不建独立事实表**；口径：AI 总结次数 = ai_summaries 行数（生成次数，含重新生成版本，#54）；入口 = "今日"页底部统计卡片区（#54，Wave B） | MVP |
| 偏好设置 | **云端 `user_settings`（跨设备漫游）**：深色模式（LIGHT/DARK/SYSTEM）、字体大小、时区（默认取 OS 可覆盖，复习提醒 P4 生效）、语言（V1 仅中文，设置页隐藏语言项）——严格命名列演进，不加 jsonb 兜底；**本机 `local_settings`（不漫游，#51）**：关闭窗口行为（默认驻留托盘）/ 开机自启（默认关）/ 速记快捷键（默认 Ctrl+Alt+N 可改）/ 上传后保留本地音频副本（默认关）/ 缓存目录 / UI 记忆（上次学习场景、习题数量） | MVP |
| 服务与用量 | **健康检查面板**（各外部服务状态与缺 key 提示，#38）+ **近 30 天 token 用量与调用次数**（llm_call_logs 聚合、按 model 分组；不做计价展示）——设置页"服务与用量"分区（#51） | MVP（Wave B） |

### 4.2 M2 — 课程管理

| 功能 | 需求要点 | 优先级 |
|------|---------|--------|
| 课程 CRUD | 名称必填；`learning_context`（SCHOOL/CAREER/INTEREST，v1.4）；SCHOOL 场景必填 `education_stage`（5 枚举），CAREER/INTEREST 场景必填 `depth`（BEGINNER/INTERMEDIATE/ADVANCED）——均进 AI 上下文；`course_type`（MAJOR/GENERAL/ELECTIVE，**可空**——职业/兴趣场景可不填）；软删除并级联处理关联数据；**新建课程按用户角色预选默认场景**（STUDENT→SCHOOL，DEVELOPER/OFFICE_WORKER→CAREER，可改，#52） | MVP |
| 查询 | 按教育阶段/类型筛选、名称搜索 | MVP |
| 课程详情 | Overview / Records / Course Brain / Knowledge GPS / Course Chat（后三项扩展阶段） | MVP(Overview+Records) |

### 4.3 M3 — 课堂记录与资料（数据入口模块）

#### 4.3.0 捕获入口矩阵与收件箱（v1.2 新增）

**五级捕获入口**（轻→重，全部收敛为 Record 实体，统一管线）：

| 级别 | 入口 | 交互 | 默认去向 | 默认 AI 处理 | 阶段 |
|------|------|------|---------|-------------|------|
| L1 | ⚡ 速记/闪念 | 全局快捷键（默认 Ctrl+Alt+N，可自定义，#51）→ 输入框（一句话~几段） | Inbox（NOTE 状态） | **无**——纯存储，手动升级制 | MVP |
| L2 | 📋 粘贴长文本 | 粘贴框 → 直接成 Record | Inbox 或选定课程 | **选定课程=直接进总结管线；未选课=仅存储**（等同速记，手动升级，#29） | MVP |
| L3 | 🔗 网页剪藏 | 贴 URL → 后端抓正文（readability）→ 文档管线 | Inbox 或选定课程 | 同 L2 | P2 |
| L4 | 🎵 音频导入 / ▶ 课堂录音 | 现有流程 | Inbox 或选定课程 | ASR → 总结管线 | MVP |
| L5 | 📄 文档导入 | 现有流程 | Inbox 或选定课程 | 解析 → 总结管线 | MVP |

**收件箱（Inbox）规则**：
- 所有捕获**可以先不选课程**（records.course_id 可空 = Inbox），时间流展示，事后三种动作：**归类到课程（填 course_id，不触发 AI 管线）/ 升级（触发 AI 管线）/ 删除**
- **升级必须先归类课程**（#29）：总结的 AI 上下文（learning_context/education_stage/depth）是硬依赖，无课程不总结
- **未归类内容不自动消费 token**（#29）：速记（NOTE 状态）与未选课粘贴均为纯存储，手动点"生成学习资产"才进入总结 HITL 管线（省 token，符合个人成本定位）
- 已选课程的录音/导入/粘贴仍走原即时管线（不强制先进 Inbox）

#### 4.3.1 录音

| 项 | 需求 |
|----|------|
| 能力 | 开始 / 暂停 / 继续 / 结束；实时时长显示；异常中断尽量保留已录数据 |
| 时长上限 | 3 小时（180 分钟） |
| 技术链路（硬约束） | WebView2 MediaRecorder 录制 `audio/webm;codecs=opus`，**每 5~10 分钟分片落盘本地**（防中断全损、防后台节流）→ 本地暂存 → 上传 Storage → **worker 用 ffmpeg 转 `ogg-opus`（16kHz 重采样，腾讯云 ASR 不支持 webm 容器，此转码环节不可省略）** → 提交 ASR |
| 前置条件 | Tauri 防系统休眠；录音 POC（§11-Q6）必须在开发前通过 |
| 桌面端优势声明 | 不再受小程序后台杀死/100MB 上传限制约束；单文件上限待 POC 后定值（建议 ≤300MB，见 §11-Q7） |

**交互流程（v1.7 补齐，#30）**：开始录音前弹最小对话框（标题可空 + 课程选择器，默认"不选 → 收件箱"）；结束录音后自动进入本地暂存与上传队列（无需手动提交）；未选课程的录音 **ASR 照常执行**（转写是事实记录，与课程无关），完成后停于 SUMMARY_PENDING，等待用户归类 + 升级触发总结（状态机零改动）。录音分片在上传成功且云端转写完成后**即删本地暂存**（失败重试期间不删）；可选"上传后保留本地副本"开关默认关闭（#51）。

#### 4.3.2 音频/文档导入

- 音频格式：MP3、AAC、WAV、M4A（+ 录音产生的 webm/ogg-opus）；**双限（#54）**：时长 ≤5 小时（对齐 ASR 供应商上限；录音上限 3 小时不变，#44）**且原始文件 ≤ 上限值（Q7 实测定，建议 500MB——统一转码发生在云端之后，原始体积不受转码缩小）**；任一超限即拒收并提示切分/压缩（WAV 建议先转 MP3/M4A）
- 文档格式：PDF、DOCX、PPTX、TXT、MD（解析：PyMuPDF / python-docx / python-pptx / 原生文本；OCR 不在范围）
- 一条 Record 可关联**多段音频 + 多个文档**（record_files，sequence_no 定序），转写文本按序合并；**定序规则（#54）**：按导入先后自动定序，CONTENT_PROCESSING 开始后不可重排——要改顺序 = 删除文件重新导入

#### 4.3.3 ASR 转写

腾讯云录音文件识别（标准版）：最长 5 小时、句子级时间戳、**热词（V1 = 课程设置里手动维护的热词列表，可空，≤100 词，#54；"知识点 → 热词自动同步"推迟 P2——总结确认后才有知识点，首课永远无热词可用）**；上传成功后异步自动触发；结果持久化为 Transcript（合并文本，快速展示）+ Transcript Segments（句子级，可溯源事实，Phase 2 起）。**V1 仅普通话语音；英文文本（粘贴/文档导入）V1 正常处理、输出中文（#45）；P2"英文支持"仅指两件事——ASR 识别英文语音、输出语言可选英文（决策 #23/#45）。**

#### 4.3.4 Record 状态机（业务态与技术态分离）

```
NOTE（速记/未选课粘贴，纯存储）
  └─ 升级（须先归类课程，#29）→ SUMMARY_PENDING
DRAFT → UPLOADING → CONTENT_PROCESSING（统一转码 #31 + ASR/文档解析并行）
      → SUMMARY_PENDING → SUMMARY_PROCESSING → SUMMARY_READY（HITL 等待确认）→ COMPLETED
轻捕获已选课（粘贴/文档）→ 直接进入 SUMMARY_PENDING（无上传与 ASR 环节）
未选课录音：ASR 照做，CONTENT_PROCESSING 完成后停于 SUMMARY_PENDING，等待归类+升级（#30）
任一关键步骤失败 → FAILED（可重试）
```

业务态共 **9 个**：NOTE / DRAFT / UPLOADING / CONTENT_PROCESSING / SUMMARY_PENDING / SUMMARY_PROCESSING / SUMMARY_READY / COMPLETED / FAILED——与数据模型 `records.status` 枚举一致（#34）。

- `record.status` 只表达**用户可理解的业务状态**
- ASR / 文档解析 / Embedding / Concept 抽取等**技术任务状态一律写 `processing_jobs`**（多文件并行处理时业务态不会互相冲突）
- 状态变更通过 **Supabase Realtime 推送**桌面端（轮询作兜底）

### 4.4 M4 — AI 智能学习

#### 4.4.1 AI 课堂总结（唯一自动触发点 + HITL）

- ASR/解析完成后自动生成：课程主题（一句话）+ 摘要（500~1000 字）+ 结构化总结（分点）；输出经 Pydantic 结构化 Schema 校验入库
- **HITL 循环**：生成 → 展示 → 用户【确认】（解锁后续按钮）或【调整】（输入反馈如"更简洁些/侧重某主题"→ 重新生成，次数不限）
- 每次生成记录 model / prompt_version / latency / token / version_no（可回溯版本链）
- **超长转写分级（#36）**：转写 ≤3 万字单次生成；超过则按语义段落分块 map-reduce 分级总结；**禁止静默截断**（§8.4 评测集含长转写回归样本）
- 用户编辑转写文本后可基于新文本重新触发

#### 4.4.2 后续 AI 能力（总结确认后按需触发，各自 HITL）

| 功能 | 输出与 HITL | 优先级 |
|------|------------|--------|
| 知识点提取 | 名称/详情/标签/重要度/来源锚点；用户删除/编辑/补充后确认保存 | MVP |
| 习题生成 | 题型多选（选择题/判断题/简答题）→ AI 建议 3/5/10 道 → 生成；必含字段：题干/选项/答案/解析（简答题为参考答案） | MVP |
| 模拟测试 | 从题库抽题组卷、作答、评分；简答题 AI 语义评分但**最终分值与评分依据必须保存**；评分低置信（<0.7，**部署级可配置** `SHORT_ANSWER_REVIEW_THRESHOLD`，不进用户 UI，#51）时标记"建议人工复核"（v1.1 定稿）——confidence 为 **LLM 结构化输出自评字段，仅用于 UI 复核标记，禁止参与掌握度计算**（#33）；每次作答落 learning_events（QUIZ_ANSWERED / QUIZ_TEST_COMPLETED，#43） | MVP |
| 复习资料 | 考前速记 + Top 重点清单 + **Markdown 大纲思维导图**（树形渲染，不做图形导图） | MVP |
| Todo 清单 | AI 生成 + 手动增删改，TODO/DONE，Record 级 | MVP |
| Markdown 导出 | 总结/复习资料/知识点一键导出为 `.md` 文件到本地（v1.1 定稿，替代分享卡片）；不做链接分享、不建 shares 表 | MVP |
| 全量数据导出 | 全部业务数据打包 JSON（含掌握度/证据链/学习事件），用于备份与迁移——开源个人工具的数据自主权标配（v1.4 定稿） | P2 |
| 课件差异分析 | 课堂讲解 vs 课件内容：已覆盖/课件有未讲/老师额外补充/重复强调/疑似考点，结构化结果 + 版本记录 | P3 |
| 重新生成 | 所有 AI 产出支持基于反馈或编辑后文本重新生成，不限制次数 | MVP |

### 4.5 M5 — AI 问答

| 能力 | 需求 | 优先级 |
|------|------|--------|
| **AI 对话（ChatGPT 式一级入口，v1.3）** | 左栏一级入口：会话列表（新建/历史/重命名/删除）+ SSE 流式；**纯通用聊天**（系统提示注入用户角色 + 自我介绍，#52）与**挂载上下文**（@记录=Record Chat、@课程=Course Chat、**@全部资料=全局 RAG**〔v1.5，个人量级 pgvector 全局检索〕）模式可切换；自由聊天不建向量索引、不进 Learning Evidence 链（红线 #5，闲聊不产生证据）；P5 起 Tutor/Teach-back 会话同界面以模式呈现 | MVP（@课程挂载 P3 生效；@全部资料 P2 生效） |
| Record Chat | 基于当前 Record（转写/总结/片段/知识点）多轮对话；SSE 流式（首事件 ≤3s）；Chat Memory（近 10 轮）；**MVP 上下文组装（#39）：转写全文常驻 + 溢出按对话轮数递减（保留摘要+知识点+近 3 轮引用的转写段）；P2 起改为摘要+知识点常驻 + 按问题向量检索转写片段**；答案携带引用（Source Anchor，可点击跳转课堂时间点）；答案引用溯源 P2 起完整 | MVP（溯源 P2） |
| 对话转学习资产（v1.3） | 聊明白后一键"存为知识点 / 生成习题"挂到某课程，形成问→懂→沉淀闭环；转换产物复用现有表，对话片段经 Source Anchor（USER_NOTE / CHAT_MESSAGE）溯源 | P2 |
| 知识点解释 | 点击知识点进入针对该知识点的教学式对话 | MVP（简化）/P5（Tutor 完整版） |
| Course Chat | 课程级 RAG 问答："这学期讲过几次 MVCC"——query 理解 → user_id+course_id 过滤 → pgvector 召回 → 上下文构建 → LLM → 答案+来源；**与 Record Chat 共用 chat_sessions/chat_messages，不建第二套消息模型**（mode 区分：ASK / COURSE_QA / SOCRATIC_TUTOR / TEACH_BACK） | P3 |
| 工具扩展（联网搜索，#53） | Chat 实现为 **LangGraph agent 循环**（检索为第一工具——Wave A 形态预留，单工具时行为等同纯 RAG 管线）；**P2 落地 web_search**：后端 SearchProvider 抽象，默认 Tavily（免费档），预留博查/智谱国产替代；无 key 按 #38 降级（搜索置灰，聊天照常）；搜索来源经 citations_json 引用（URL 直挂，WEB 来源正式锚点 P2+ 详评定）；仅聊天域可用（红线 #11） | P2 |

### 4.6 M6 — 消息与状态通知

- 处理状态（上传/ASR/AI 生成）实时反馈：**Supabase Realtime 推送为主，轮询兜底**
- 失败提示与重试入口

### 4.7 M7 — Learning Brain（共享智能层，扩展阶段）

> 详细设计以扩展文档为准，此处为基线摘要与验收约束。

| 能力 | 摘要 | 阶段 |
|------|------|------|
| F1 Segment+证据时间轴 | 句子级 Segment 持久化（record/file 双时间轴）；AI 结论可回跳原声 | P2 |
| F2 课堂标记 | 录音中 ⭐/❓/📝 快速标记；CONFUSED 仅主观信号，经验证才影响状态 | P2 |
| F6 Event+Evidence | 全部学习行为统一事件化（幂等）；Evidence 分层 | P2 |
| F4 Course Brain | Concept 图谱（concept/concept_relation/record_concepts）+ 语义记忆（semantic_embeddings+pgvector）；V1 无 Neo4j | P3 |
| F5 Knowledge GPS | 掌握度地图；节点状态六枚举（NOT_ENOUGH_DATA/LEARNING/STABLE/AT_RISK/WEAK/MISCONCEPTION_RISK），禁止只按 Mastery 数字着色 | P3 |
| F7 Mastery | 可解释确定性算法（quiz/recall/teach_back/transfer 四分量 × 正确性/难度/新近度/权重）；带 confidence 与 evidence_count | P4 |
| F8 Misconception | SUSPECTED→验证→CONFIRMED/DISMISSED→纠错→RESOLVED；带置信度与证据计数 | P4 |
| F9 遗忘雷达 | V1 规则公式 priority = importance × forgetting_risk × (1-mastery) × exam_weight；V2 再评估 FSRS；"打开复习页≠记忆增强"，复习须有 Recall 验证 | P4 |
| F10 Digital Twin | 运行时视图（非大 JSON 表），聚合 Mastery/Memory/Misconception/偏好；推测项必带 confidence | P4 |
| F11 Socratic Tutor | 苏格拉底式诊断-提问-评估循环（LangGraph Tutor Graph） | P5 |
| F12 Teach-back | 讲给 AI 听：覆盖率/遗漏/混淆分析 → 追问 → 验证 → Evidence；一期无 TTS；**V1 文本输入先行，语音后补**（复用 ASR 链路，v1.1 定稿） | P5 |
| F13 自适应测验 | 依掌握度+置信+前答+误区候选选题；规则优先选库、库不足才 LLM 生成；Transfer Challenge 为高级模式 | P5 |
| F14 动态规划 | 考试目标（日期/分数/每日分钟/考纲）；考纲来源四类，AI_INFERRED 必须用户确认；计划版本化，完成项保留、锁定项不动 | P6 |
| F15 课前预习 | 上传下节课课件 → 概念抽取 → 对比课程脑与个人掌握 → 前置缺口 → 预习建议（落地为 plan_item.action_type=PREVIEW，依赖 `course_materials` 课程级资料表） | P5 |
| F16 Autopilot | 每日 Next Best Action 推荐（结构化输出：action/concept/reasonCode/priority/minutes/confidence）；必须 HITL 后执行 | P6 |
| F17 Passport | 证据型学习成果快照；Mastered 判定 = mastery+confidence+evidence_count+近期 recall 四条件，不由 LLM 决定 | P7 |
| F18 Study Pod | 可选协作层，P8，当前不做 | — |

---

## 5. MVP 与功能阶段边界

### 5.1 阶段规划

| 阶段 | 内容 | 出口标准 |
|------|------|---------|
| **S0 POC（先行）** | 录音全链路（MediaRecorder→分片→上传→ffmpeg ogg-opus→ASR→带时间戳文本）；Supabase 国内连通实测；额度方案拍板 | Windows 真实课堂录音跑通；延迟可接受 |
| **Phase 0 工程基础** | Monorepo、FastAPI、Supabase 本地（supabase start）、Auth（**V1 禁用邮箱确认、零 SMTP**，#37）、迁移体系、Tauri 壳、SQLite、OpenAPI 类型生成、procrastinate worker、日志/错误模型、CI、发布流水线（GitHub Releases `.msi` 手动分发，#47） | 登录→建课→列表闭环 |
| **Phase 1 = MVP · Wave A（学习闭环主干）** | 课程 CRUD；录音/导入/上传（统一转码 #31）；ASR+文档解析；Transcript（整段）；总结+HITL（长转写分级 #36）；知识点/习题/Todo/Markdown 导出；**AI 对话一级入口（自由聊天 + @记录挂载，SSE；上下文组装 #39）**；速记/粘贴捕获 + **Inbox 最小闭环**（时间流 + 归类/升级/删除——未选课录音依赖升级解锁总结，#29/#30）；learning_events 四事件（#43） | **一节真实课堂（录音或导入）当日走通：转写 → 总结确认 → 知识点确认 → 习题作答 → 导出 .md；未归类内容可归类升级进同一闭环** |
| **Phase 1 = MVP · Wave B（工作台完善）** | 模拟测试（简答 AI 评分 + 低置信复核标记）；复习资料；Inbox 整理增强（批量/筛选）；命令面板 Ctrl+K（ILIKE 搜索，#32）；学习统计；设置漫游/深色模式；空态引导卡（#42）；无 key 降级 + 健康检查面板（#38） | **本基线 §4.1~§4.6 MVP 项全量可用 + 工作台形态达成** |
| Phase 2 学习数据基础 | Transcript/Document Segment、Source Anchor、Marker、Learning Evidence（Learning Event 已提前至 MVP，#33）、pgvector、**网页剪藏（正文抓取）**、**对话转学习资产**、**@全部资料全局 RAG**、**英文内容支持（ASR en + 输出语言可选，#45）**、**Chat 联网搜索工具（Tavily，#53）**、**全量数据导出（JSON）** | AI 结论可回跳课堂原声 |
| Phase 3 Course Brain | Concept 抽取与消歧、课程级 RAG、Knowledge GPS v1、课件 Diff | "讲过几次 X"可答且带来源 |
| Phase 4 Learner Brain | Mastery、Forgetting（V1 规则）、Misconception、Digital Twin v1 | 事件→证据→掌握度闭环 |
| Phase 5 Adaptive | Socratic Tutor、Teach-back、自适应测验+Transfer、Memory Rescue、课前预习 | 三种学习模式产生 Evidence |
| Phase 6 Planner+Autopilot | Goal/动态计划、Next Best Action、今日建议+HITL、反馈 | 最小创新闭环跑通 |
| Phase 7 Outcome | Learning Profile、Passport、快照 | — |
| Phase 8 可选协作 | Study Pod（仅在核心稳定后） | — |

> **阶段启动门槛（#48）**：每个阶段（P2 起）开工前，先补该阶段详细设计评审（含 PRD 增补与缺口回填，如 P4 的 Mastery confidence 计算公式）再进入开发——本 PRD 对扩展阶段仅承载摘要级设计与验收约束，不承载实现细节。

### 5.2 明确不做 / 暂缓清单

排行榜/XP、会员付费、OCR、通用社交、自由朋友圈、无来源 AI 认定掌握、未经确认的 Autopilot 自动执行、Neo4j、Qdrant、TTS Tutor（一期）、Study Pod 实时版、复杂 ML 推荐模型、双主写入、同时维护两套对象存储、RabbitMQ/Kafka/Redis/Celery、Sentry/OTel/Langfuse 自托管、Stronghold、微信生态能力（登录/分享卡片）、**视频导入（MP4 抽音轨，v1.4 拍板不做）、通用会议笔记工具（Meetily 领域，偏离学习定位）**。

---

## 6. 核心业务流程

### 6.1 主流程：课堂 → 学习资产

```
录音(分片 webm/opus，本地暂存) / 导入音频 / 导入文档
        ↓ 上传 Storage（桌面端直传，私有桶）
[worker] ffmpeg → ogg-opus@16kHz（全部音频，统一转码 #31） → 腾讯云 ASR / 文档解析
        ↓
Transcript（整段）+（P2起）Segments
        ↓ 自动触发
AI 总结（qwen-plus，结构化输出）
        ↓
HITL：确认 ✅ / 调整反馈 🔄（不限次循环，跨重启可恢复）
        ↓ 确认后解锁
知识点(HITL筛选) / 习题(选题型→数量3/5/10) / Todo(HITL增删) / 复习资料 / 模拟测试
```

### 6.2 HITL 暂停与恢复（LangGraph interrupt）

Summary Graph：`generate_summary → interrupt(review_summary) → 确认:COMPLETED | 调整:循环`。图状态持久化于 Supabase（langgraph schema），**应用重启、隔天确认均可恢复**；Checkpoint 只存运行态，业务事实（确认结果、版本链）落业务表。

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

### 6.4 本地与云端同步（分级策略）

```
L1 只读缓存：courses/records/summaries/transcripts 增量拉取（updated_at 游标），SQLite 缓存 + TanStack Query 请求层
L2 本地先行写：录音会话/本地文件 → local_files 上传队列 → 联网后注册到云端 record_files；分片上传成功且云端转写完成后即删本地（#51）
L3 离线业务编辑：V1 不做（v1.1 定稿）——离线仅缓存查看 + 录音上传队列；version/sync_outbox 架构已预留，未来开放只需扩展
冲突：表结构保留 version 乐观锁字段，后端更新时校验，冲突返回 409 由用户决策，不默认 Last-Write-Wins
```

### 6.5 删除链（Record 为例）

软删除父表 → Storage 对象异步物理清理 → 向量标记删除后物理清理 → 该 Record 产生的 Learning Evidence 排除出掌握度计算（按 record_id 过滤），受影响 Concept 由 Mastery Engine 异步重算（v1.1 定稿，原 §11-Q8）。

**补充（v1.7）**：挂载该 Record 的 chat 会话**不级联删除**——会话保留可读、挂载标记"原记录已删除"失效态，仅显式删除会话才删消息（#40）；业务行软删 **30 天后异步物理清理**（与 Storage/向量清理同批次；V1 无恢复 UI，删除弹窗明示"不可恢复"，#41）。

**处理中删除（#54）**：worker 每个写入步骤前校验 `record.deleted_at`，发现软删即终止链路并丢弃产物（不触发总结、不入库）；处理中允许删除，删除即隐式取消。

### 6.6 轻捕获 → 收件箱 → 整理（v1.2 新增）

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

## 7. 权限、RLS 与数据安全

| 项 | 要求 |
|----|------|
| 认证 | Supabase Auth（邮箱+密码；V1 禁用邮箱确认/OTP，#37/#54）；JWT 经 JWKS 验签；Service Role Key 仅限后端必要管理操作，不下发桌面端、不进前端环境变量、不写日志 |
| RLS | 所有含 user_id 业务表启用 `user_id = auth.uid()` 策略（Defense in Depth）；后端普通业务用**最小权限数据库角色**+ service 层数据访问代码强制 user_id 过滤（不单设 Repository 层，2026-08 定稿；service_role 绕过 RLS，不能依赖 RLS 替代后端校验） |
| 检索隔离 | 向量检索**恒定强制前置过滤 `user_id + deleted_at IS NULL`**；course_id 仅在课程/记录范围检索时附加（@全部资料全局检索省略 course_id）；禁止任何不含 user_id 的裸向量查询（#28，对齐 `docs/rules/langchain-langgraph.md`） |
| 存储 | 私有桶（recordings/documents/avatars），signed URL 访问；路径规则 `{bucket}/{user_id}/{course_id}/{record_id}/{file_id}`——**course_id 为空（Inbox）时省略该段**：`{bucket}/{user_id}/{record_id}/{file_id}`；归类课程后不迁移已上传文件（路径仅作定位，归属以表字段为准，#49）；**signed URL 由后端签发并校验资源归属**（#54） |
| 前端直连边界 | 前端仅允许两处直连 Supabase：① Storage signed URL 直传；② Realtime 订阅（anon key + RLS）。**一切业务数据读写必须经 FastAPI（JWT 验签）**（#35） |
| 日志隐私 | 禁止记录完整转写/Teach-back 全文/敏感对话/密钥/Token；可记录 record_id、segment_id、token 数、latency、model、prompt_version、error code |
| Token 存储 | supabase-js 默认 localStorage（v3.2 定稿，不引入 Stronghold；不写入 SQLite 明文表） |

---

## 8. 非功能需求

### 8.1 性能（产品指标，需压测验证）

| 指标 | 目标（v1.7 改版：实测回填，#27） |
|------|------|
| 普通接口 | P95 = **S0 实测国内→Supabase 基线 RTT + 300ms 余量**（§11-Q12 回填前不承诺绝对值——国内访问 Supabase 未实测，写死数字不可验收） |
| AI Chat 首个流式事件 | ≤ 3s |
| Summary 任务提交 | **提交后 2s 内返回 job_id 且 processing_jobs 可查询**；生成 90s 超时标记 FAILED 可重试（无"或"式后门） |
| Desktop 首屏 | ≤ 2s（本地渲染 + 缓存，含会话恢复） |
| 长任务 | 必须可查询状态（processing_jobs），不阻塞普通请求 |
| ASR（1h 音频） | 供应商配额强相关，作监控目标而非绝对 SLA |

### 8.2 可靠性

后台任务可重试且幂等；AI/ASR 失败不产生重复 Event（idempotency_key 唯一）；上传有校验（content_hash）；重要写入事务化；worker 连接串用 session/direct 端口（procrastinate LISTEN/NOTIFY 约束）。

### 8.3 可观测（轻量方案，v3.2 定稿）

自建 `llm_call_logs` 表记录：request_id、graph_name/node、model、prompt_version、embedding_model、token_usage、latency、retrieval_count、evidence_count、interrupt_count、error_code；结构化日志（loguru，v3.3 定稿）承载非 LLM 观测；Autopilot 接受率/推荐成功率由业务表聚合。

### 8.4 测试策略

- 后端 pytest：Event 幂等、Evidence Builder、Mastery 唯一写入口、Misconception 状态机、RLS、删除重算、同步冲突
- 前端 Vitest+RTL：记录创建、离线录音草稿、上传失败恢复、Summary HITL、Chat SSE、冲突 UI、深色模式；Playwright 仅关键路径冒烟（可选）
- **AI 评测集（按阶段拆分，#46）**：MVP 仅建**总结质量黄金样本（20 条真实课堂转写 + 人工标准总结）+ 人工评审 checklist**（含长转写回归样本，#36）；习题 Groundedness 样本随 Wave B；引用准确性/Concept 抽取精度/简答评分一致性/误报率/推荐接受率随对应阶段（P2~P6）补建

---

## 9. 桌面端信息架构与 API 分组

### 9.1 信息架构（v1.2 工作台布局）

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
知识空间（课程/技能空间/主题收藏，v1.5 统称）：Overview / Records / Course Brain(P3) / Knowledge GPS(P3) / Course Chat(P3)
资产库 Library：跨课程统一检索（MVP=记录/知识点全文搜索；P2+=向量语义检索）
学习画像(P7)：Activity / Mastery / Forgetting / Misconception / Passport
Record 详情：Summary(默认,HITL) / Transcript Timeline / Evidence(P2) / 知识点 / 习题 / 复习 / Todo / Ask AI
命令面板 Ctrl+K：开始录音 / 新速记 / 搜索一切资产 / 跳转课程与记录（MVP）
设置：账户 / 偏好(主题/字号/快捷键/托盘行为) / 服务与用量(健康检查+token 用量) / 退出〔"数据与隐私"页（导出/日志说明/删除账号）P2 上线，#51〕
空态引导卡：各空区域显示引导卡（"创建第一个知识空间 / 按 ▶ 录一节课 / Ctrl+K 试试命令面板"），不做向导流程、不做示例数据（#42，MVP/Wave B）
首启角色卡：登录后一次性四选一（可跳过），选完进空态引导；角色与自我介绍在 设置→账户 可改（#52，Wave B）
今日页统计卡：学习统计（Wave B）以卡片置于"今日"页底部，不新增左栏项（#54）
```

### 9.2 API 分组（FastAPI，OpenAPI 自动生成 TS 类型）

```
/api/auth /api/profile /api/settings
/api/courses .../records    /api/records/{id}/(files|transcript|summary|knowledge|quiz|review|todo)
/api/chat/sessions .../messages（SSE：事件区分 token/status/citation/interrupt/done/error）
/api/learning/events|evidence    /api/courses/{id}/(concepts|knowledge-gps|brain/chat)
/api/concepts/{id}/(mastery|misconceptions)    /api/review/(today|rescue)
/api/tutor/sessions /api/teach-back/sessions /api/assessment/adaptive
/api/learning-goals /api/learning-plans
/api/autopilot/today /api/autopilot/actions/{id}/(accept|skip|defer|complete)
/api/passport    /api/sync/*
```

---

## 10. 产品与架构决策记录

> 本节汇总记录本项目的产品与架构关键决策，后续开发以本表为准。

| # | 决策点 | **决策** | 理由 |
|---|--------|---------|------|
| 1 | 任务队列 | **procrastinate（PG 队列），无 Redis；不建 outbox_events 表** | 开源+个人定位（用户已拍板）；procrastinate `defer` 在业务事务内提交，天然具备 Transactional Outbox 语义，无需独立 outbox 表 |
| 2 | AI 可观测 | **自建 `llm_call_logs` 表**，承接 LLM 调用追踪所需全部字段（见 §8.3） | 个人项目自托管 Sentry/Langfuse 过重；追踪需求一张表满足 |
| 3 | 登录方式 | **邮箱+密码/OTP，OAuth 预留**（不再是待确认项） | 用户已拍板（D3） |
| 4 | Embedding 维度 | **定 1024 维**；表内保留 embedding_model 字段备换模型（换模型=全量重嵌入，已知成本） | 建表必需定值；预留可演进 |
| 5 | ffmpeg 用途 | **首要用途：webm/opus → ogg-opus@16kHz 转码**（ASR 不支持 webm 容器） | 实测事实（腾讯云文档），这是链路成立的前提 |
| 6 | 桌面平台 | **V1 首发 Windows**（macOS 后评估，最终定稿见决策 #14） | 用户环境与 POC 成本 |
| 7 | Record 状态机 | **业务态/技术态分离**：record.status 只表达业务状态，技术任务状态入 processing_jobs | 多文件并行处理时单状态字段无法表达 |
| 8 | 状态推送 | **Realtime 为主，轮询兜底** | 组件已在 Supabase 内，零成本 |
| 9 | 分享 | **Desktop V1 不做分享；导出/分享形态见决策 #15（已定稿）** | 微信卡片为小程序形态能力 |
| 10 | 同步模型 | **分级**：L1 只读缓存 + L2 上传队列先行；L3 离线编辑不做（决策 #16）；version 字段与乐观锁保留（零成本预留） | 个人使用离线编辑需求有限，避免过度工程 |
| 11 | Stronghold / token 存储 | **砍 Stronghold**；token 走 supabase-js localStorage，不进 SQLite 明文表 | 用户已拍板（v3.2） |
| 12 | 新增表 | course_materials / record_analyses / source_anchor_links / semantic_embeddings / processing_jobs / learner_preferences / user_settings **全部采纳** | 分别支撑 F15 课前资料 / F3 Diff / 多来源引用 / 统一向量生命周期 / 技术任务态 / 偏好双分离 / 偏好漫游，均为既有功能所必需，非新增功能 |
| 13 | 性能表述 | **弱化 ASR SLA**（作监控目标而非绝对承诺） | 供应商指标不可本地承诺 |
| 14 | V1 平台范围 | **Windows 唯一首发平台**，macOS 稳定后评估 | WKWebView 不支持 webm/opus 录制，双平台=两条录音链路（用户 v1.1 拍板） |
| 15 | 分享/导出形态 | **Markdown 本地导出（MVP）**；不做链接分享、不建 shares 表 | 桌面文件系统天然支持，零新表零公开访问面（用户 v1.1 拍板） |
| 16 | 离线编辑 L3 | **V1 不做**（仅 L1 缓存 + L2 上传队列）；架构预留 version/sync_outbox | 个人使用离线编辑需求有限，避免过度工程（用户 v1.1 拍板） |
| 17 | SMTP 供应商 | **Resend**（免费档 3000 封/月，接入最简） | Supabase 内置限额无法支撑 OTP（用户 v1.1 拍板） |
| 18 | 删除重算粒度 | **删除 Record → 其 Evidence 按 record_id 排除出掌握度计算，受影响 Concept 异步重算** | 防止已删数据静默影响 Mastery；Evidence 行保留作审计（v1.1 定稿） |
| 19 | Teach-back 输入 | **V1 文本先行，语音后补** | 少一条 ASR 依赖链路，Phase 5 减负（v1.1 定稿） |
| 20 | 简答评分复核 | **AI 评分低置信（<0.7，可配置）标记"建议人工复核"** | 平衡自动化与可信度（v1.1 定稿） |
| 21 | 产品形态/入口（原：仅"录音+文档"双入口） | **升级为个人学习工作台**：五级捕获入口（速记/粘贴/剪藏/音频/文档）、收件箱 Inbox（先捕获后整理，course_id 可空）、今日焦点/资产库/命令面板；速记手动升级制；剪藏 P2 | GitHub 调研显示同类开源（Meetily/memos/Khoj/AnythingLLM）无一同时覆盖"捕获+组织+学习状态"；且原有"先选课才能录"摩擦高、轻捕获缺失（用户 v1.2 拍板；**数据模型零新表**，全部复用 records/transcripts） |
| 22 | 独立 AI 聊天界面（原：聊天仅作为 Record/Course 上下文二级功能） | **新增 💬 AI 对话一级入口**：会话列表 + 自由聊天/挂载上下文（@课程/@记录）双模式可切换；对话转学习资产（P2）；自由聊天不建索引、不进 Evidence 链 | 非绑定课堂的一般学习提问此前无处承载；"打开即聊天"是 AI 产品事实心智（用户 v1.3 拍板）；仅 `chat_sessions.course_id` 改可空，**零新表** |
| 23 | 目标用户范围（原：仅全学段学生） | **泛化为"一切学习知识的人"**（学生+程序员+上班族+终身学习者）：courses 改 `learning_context` + `education_stage`/`depth` 双字段（course_type 改可空）；UI 术语以"学习会话/学习记录"泛称（实体 Record 不变）；英文内容 P2；全量数据导出 P2；不做视频导入与通用会议笔记 | v1.2/v1.3 工作台化后产品形态已自然溢出学生场景（用户 v1.4 拍板；数据模型仅 courses 加两列一约束） |
| 24 | 个人知识库（原：RAG 仅课程范围，未分类内容不入索引） | **补齐**：`semantic_embeddings.course_id` 改可空（Inbox 内容入向量索引，检索仍强制 user_id 过滤）；AI 对话 @全部资料 全局 RAG（P2）；"知识空间"文案心智（课程=唯一知识容器）；**不引入独立 knowledge_bases 实体** | 泛化用户群（程序员/上班族）的资料常不属任何"课"；个人量级（万级 segment）pgvector 全局检索无压力；多空间多对多模型对当前场景属过度设计（用户 v1.5 拍板） |
| 25 | 产品定位（v1.7 需求评审） | **作者本人是第一用户，开源供愿意自部署的同类人**；Windows-only 维持；OTP/Resend/邮箱确认推迟到"对外发布"里程碑；部署文档列四个外部依赖（DashScope/腾讯 ASR/Resend/Supabase）及无 key 降级行为 | 自用优先，砍掉为虚拟公众用户设计的负担；开源受众按"愿意自备密钥的同类人"设定 |
| 26 | MVP 交付结构 | **Wave A（学习闭环主干）/ Wave B（工作台完善）双波次**，各自设验收线，MVP 出口标准不变 | 单人项目一次性交付全量 MVP 风险高；Wave A 达成即产品可用（见 §5.1） |
| 27 | 性能指标 | **§8.1 改为 S0 实测回填**；Chat 首 token ≤3s 保留；Summary 改硬条件（提交 2s 内返回 job_id；生成 90s 超时 FAILED 可重试） | 国内访问 Supabase 未实测，写死数字不可验收；"30s 或后台任务"存在达标后门 |
| 28 | 向量检索红线 | **user_id + deleted_at IS NULL 恒定强制前置过滤；course_id 仅课程/记录范围检索附加；禁止任何不含 user_id 的裸向量查询**（PRD §7/§13、数据模型 §2、技术栈同步改写） | 决策 #24 全局 RAG 与旧表述"强制 user_id+course_id"冲突；对齐 `docs/rules/langchain-langgraph.md` 既有规则 |
| 29 | 未归类内容 AI 处理 | **未选课不自动消费 token**（粘贴=仅存储，同速记）；**升级强制先归类课程**（AI 上下文硬依赖，无课程不总结）；归类不触发管线，升级才触发 | 堵住 Inbox 粘贴自动烧 token 的口径；learning_context 缺失则总结无从设定风格 |
| 30 | 录音交互流程 | 开始前最小对话框（标题可空+课程选择默认 Inbox）；结束自动上传；**未选课录音 ASR 照做、停 SUMMARY_PENDING 等归类+升级** | 交互流程此前缺失；ASR 是事实记录与课程无关，停点复用现有状态机零改动 |
| 31 | 音频转码范围 | **全部音频统一 ffmpeg → ogg-opus@16kHz**（含 MP3/M4A 导入）再进 ASR | 单一管线、体积可控（5h≈160MB）、上传上限好定；按需转码留两条分支徒增复杂度 |
| 32 | 全文搜索（MVP） | **ILIKE 子串匹配**（资产库/命令面板）；P2 向量语义检索接管；不引入中文分词扩展 | Supabase 托管版无 zhparser/pg_jieba，pg_trgm 对中文无效；个人量级 ILIKE 足够且符合中文直觉 |
| 33 | 简答评分置信度 & 事件提前 | confidence = **LLM 结构化输出自评字段，仅 UI 复核标记，禁止参与掌握度计算**；**learning_events 提前至 MVP 建表**并记录做题事件 | 模型自评不可靠，不得进入数值链；否则 MVP 做题历史永久丢失、P2 无法回放构建 Evidence |
| 34 | 文档一致性回写 | 状态机统一 **9 态**（含 NOTE）；§1.1 定位表、§13 验收清单（按阶段标注）等旧文对齐现行决策；技术栈 10 态/redis/arq 残留清理 | 三份文档三个状态数（8/9/10）；验收清单混阶段无法对照出口标准 |
| 35 | 前端直连边界 | 前端仅 **Storage signed URL 直传 + Realtime 订阅** 两处直连 Supabase；**一切业务数据读写必须经 FastAPI（JWT 验签）**（写入 §7） | 收敛 anon key 暴露面与 RLS 依赖，边界成文 |
| 36 | 长转写总结 | 转写 ≤3 万字单次生成；**超过按语义段落分块 map-reduce**；禁止静默截断 | 5h 导入逼近 qwen-plus 窗口且长上下文中部注意力衰减；截断静默丢内容违反溯源精神 |
| 37 | 邮箱确认 | **V1 禁用邮箱确认**（注册即用、零 SMTP）；OTP/确认/Resend 于"对外发布"里程碑启用 | Supabase 确认邮件走内置 SMTP 限额极低；自用场景确认无意义 |
| 38 | 无 key 降级 | **功能级降级 + 启动健康检查面板**（对应入口置灰并提示缺失项）；不做月度 token 熔断（仅 llm_call_logs 统计展示） | 自部署用户未必配齐外部服务；熔断会造成"课录完了总结没了"的更坏体验 |
| 39 | Record Chat MVP 上下文 | **转写全文常驻** + 溢出按对话轮数递减（保留摘要+知识点+近 3 轮引用的转写段）；P2 起改为摘要+知识点常驻+按问题向量检索 | MVP 无 pgvector；细节追问（"第 40 分钟讲的公式"）必须转写在上下文中 |
| 40 | 删 Record × 对话 | **不级联删 chat**：会话保留可读、挂载标"原记录已删除"失效态；仅显式删会话才删消息（数据模型 §9.1 同步） | 对话有独立价值（P2 转资产前别处不存在），连带删除违背用户预期 |
| 41 | 软删语义 | V1 无恢复 UI、删除弹窗明示"不可恢复"；**业务行软删 30 天后异步物理清理**（与 Storage/向量清理同批次，写入 §6.5） | 无恢复入口的软删等价硬删且数据永久堆积 |
| 42 | 空态引导 | 各空区域**引导卡**（一张卡片一个动作）；不做向导流程、不做示例数据 | 示例数据污染真实学习数据，违背唯一事实源心智 |
| 43 | MVP 事件范围 | 落地 **SUMMARY_CONFIRMED / KNOWLEDGE_CONFIRMED / QUIZ_ANSWERED / QUIZ_TEST_COMPLETED** 四事件（幂等键规则同步生效） | 其余枚举对应功能 P4+ 才有写入方，保留定义暂不落地 |
| 44 | 导入音频上限 | **5 小时**（对齐 ASR 供应商上限）；录音维持 3 小时；超长提示切分 | 讲座/培训导入长于课堂是常态；统一转码后体积仍在 ≤300MB 内 |
| 45 | 英文支持边界 | **英文文本（粘贴/文档）V1 正常处理、输出中文**；P2"英文支持"仅指 ASR 英文语音识别 + 输出语言可选 | 程序员粘贴英文技术文档是 V1 主路径，不得被"P2 英文"误伤 |
| 46 | AI 评测落地 | **按阶段拆分**：MVP 仅总结黄金样本 20 条 + 人工 checklist；习题 Groundedness 随 Wave B；其余随对应阶段补建（§8.4） | 七类评测对应 P2~P6 功能，一次建全套既做不了也不必要 |
| 47 | 分发与更新 | **GitHub Releases 手动 `.msi`**；应用内"检查更新"仅链接跳转；Tauri updater（签名基建）后置 | updater 需更新服务器与签名密钥管理，个人阶段徒增负担 |
| 48 | 阶段启动门槛 | **每阶段（P2 起）启动前先补该阶段详细设计评审（含 PRD 增补）再开工**（§5.1 备注） | 0.7 阈值无来源等缺口证明摘要级 PRD 覆盖不到实现细节（如 P4 Mastery confidence 公式） |
| 49 | Storage 路径 | course_id 为空（Inbox）时**省略该段**：`{bucket}/{user_id}/{record_id}/{file_id}`；归类后不迁移（路径仅作定位，归属以表字段为准） | 路径规则写死于 course_id 恒存在时代；不定则实现随手长出多种写法 |
| 50 | 多设备 | **单人、多设备、非同时**；不做设备间并发协调（乐观锁 409 兜底）；测试只覆盖单设备主用+偶尔换机 | user_settings 漫游隐含多设备假设，明示后收敛测试面 |
| 51 | 用户设置域（v1.8 设置评审） | **砍"隐私"空壳页**（P2 随全量导出上线"数据与隐私"：导出/日志说明/删除账号）；录音分片**上传+转写成功后即删本地**（可选保留开关默认关）；关窗默认**驻留托盘**+开机自启默认关——速记快捷键依赖常驻；速记快捷键默认 **Ctrl+Alt+N** 可改；设置页新增**"服务与用量"分区**（#38 健康面板 + 近 30 天 token 用量，不做计价，Wave B）；简答复核阈值定**部署级配置**（SHORT_ANSWER_REVIEW_THRESHOLD，不进用户 UI）；user_settings **严格命名列演进**（locale V1 隐藏、timezone 默认取 OS/P4 生效）；local_settings V1 八键定稿（数据模型 §5） | L1 速记与"关窗即退"逻辑矛盾；分片无清理策略磁盘必满（R4）；空壳隐私页不如不占位；0.7 阈值开放给普通用户只会改坏；ASR 维持腾讯云单引擎同批拍板（FunASR 否决） |
| 52 | 用户角色（v1.9 角色评审） | 档案层 `profiles.primary_role`（STUDENT/DEVELOPER/OFFICE_WORKER/OTHER 四选一）+ `about_me`（≤200 字）；首启一次性角色卡（可跳过、不问学段）；建课程按角色预选默认场景（可改）；**自由聊天系统提示注入角色+自我介绍**（挂载会话不叠加、新会话生效不追溯）；原则"**角色改变语气与默认值，不改变能力集**"——不进课程 AI 管线与 Evidence | 自由聊天此前零个性化、onboarding 缺锚点；对齐主流 AI 产品首启模式（ChatGPT 场景选择等）；枚举收窄 + 自由文本兜底防长尾膨胀；多帽子论证（#23）保持课程级权威 |
| 53 | Agent 工具域（v1.9 追加） | **工具仅限聊天域**（自由聊天默认、挂载会话可选；新增红线 #11：Summary/Tutor/TeachBack 禁止联网工具）；**Wave A Chat 以 LangGraph agent 循环实现**（检索为第一工具，单工具行为等同纯 RAG——零功能变更的形态预留）；**P2 落地 web_search**：SearchProvider 抽象，默认 Tavily（免费档 1000 次/月），预留博查/智谱国产替代，不选 SearXNG（国内后端不可达其搜索源）；无 key 按 #38 降级；引用走 citations_json | 框架/协议/数据模型均支持（SSE status/citation 事件现成）；纯管线实现会导致 P2 加工具=重构；总结若允许联网将毁掉溯源根基 |
| 54 | 终审修补包（v1.10 全面审计） | **登录终态（A 案）**：邮箱+密码保留，首启包装"初始化你的工作台"——登录定位 = 云上数据的锁 + 三处直连（RLS/Realtime/Storage）身份锚，非多用户能力；会话持久化一生登录一次；密码三规则（已登录改密码 V1 支持 / 忘记密码 V1 = Supabase Dashboard / 邮箱变更 V1 不做）；**第三方 OAuth 首选候选 GitHub**（对外发布评估）；**音频双限**：≤5h 且原始文件 ≤Q7 实测上限（建议 500MB），超限拒收提示切分——修正 #44 与 Q7 的上传体积冲突；**热词降级**：V1 = 课程手动热词列表（≤100 词，courses.hot_words），知识点自动同步 P2（首课无知识点可用）；**处理中删除竞态**：worker 每步写前校验 deleted_at，软删即终止丢弃；**多文件定序**：导入先后定序，处理开始后不可重排；**统计**：入口 = 今日页底部卡片，AI 总结口径 = ai_summaries 行数；角色卡定 Wave B；C1~C4 残留修正（§3 技术栈 v3.4 / §7 OTP / §8.3 loguru / §6.1 转码措辞）；§7 补 signed URL 后端签发校验归属；**首启连接配置（§11-Q13）开发前再决策**（用户指示） | 全面严格复审揪出：忘记密码死路（#37 衍生）、5h×300MB 上传冲突（#44 引入的矛盾，如实修正）、热词鸡生蛋 + 隐含整套同步流程、处理中删除竞态、统计无 UI 入口等 11 项（用户逐项拍板） |

---

## 11. 待确认问题清单

> v1.1 收敛：Q1/Q2/Q3/Q5/Q8/Q9/Q10 已定稿（见 §10 决策 #14~#20）。以下四项**依赖实测**，在 S0 POC 完成后回填；Q13 为**开发前决策项**：

| # | 问题 | 影响范围 | 前置条件 |
|---|------|---------|---------|
| Q4 | Supabase 区域与付费档（免费档 500MB 库/1GB 存储/50MB 单文件不够用） | 成本与国内连通性 | S0 实测东京/新加坡延迟后定；预算默认按 Pro |
| Q6 | 录音 POC 结果回填：WebView2 后台节流对 MediaRecorder 定时器影响、分片策略实测、异常退出恢复 | 录音方案锁定 | S0 必做，最高优先 |
| Q7 | 上传单文件上限定值（**原始文件**上限，建议 500MB，#54；转码后 ogg-opus 3h≈100MB 供参考） | Storage 策略 | Q6 完成后 |
| Q12 | 性能基线回填（§8.1 普通接口 P95 公式定值，#27） | §8.1 性能指标 | S0 与 Q4 同批实测（国内→Supabase RTT） |
| Q13 | 自部署首启连接配置形态（桌面端如何获知后端地址/Supabase URL/anon key——候选：仅填一个后端地址，余者经 `/api/config` 下发） | §4.1 首启流程 | Phase 0 开发前决策（#54 记录，用户指示后续再议） |

---

## 12. 风险清单

| # | 风险 | 等级 | 缓解 |
|---|------|------|------|
| R1 | 录音→ASR 格式链路（webm 不被 ASR 支持；WebView2 AAC 编码不完整） | **高** | S0 POC 先行；ffmpeg ogg-opus 转码为硬约束写入设计；运行时 isTypeSupported 探测兜底 |
| R2 | Supabase 国内访问延迟/稳定性 | 高 | S0 实测；备选自托管 |
| R3 | Supabase 免费额度不足 | 高 | Pro 档预算或自托管（§11-Q4） |
| R4 | 3 小时长录音稳定性（系统休眠/WebView 节流/磁盘占满） | 高 | 分片落盘、防休眠、POC 验证 |
| R5 | LangChain/LangGraph 1.x API 变动 | 中 | 锁版本；仅用四个子包 |
| R6 | procrastinate 小众依赖 | 低 | 任务表结构简单，可替换（退回 arq 仅动 worker 层） |
| R7 | LLM 输出质量漂移 | 中 | 固定评测集 + prompt 版本化 + llm_call_logs 追踪 |
| R8 | 同步冲突 UX 复杂度 | 中 | V1 限制离线写范围（L1+L2），冲突场景最小化 |
| R9 | 个人使用下 LLM/ASR 调用成本 | 中 | qwen-plus 统一模型；llm_call_logs 可统计消耗；速记手动升级制避免无谓 token |
| R10 | 网页剪藏（P2）依赖目标站可达性与正文解析质量 | 中 | readability 容错 + 失败降级为"手动粘贴"；仅 httpx 服务端抓取，无无头浏览器 |

---

## 13. 验收清单（关键项，v1.7 按阶段重排，#34）

**S0 / Phase 0**

- [ ] Supabase 唯一事实源 / SQLite 边界 / Auth 方案落地
- [ ] 迁移唯一权威 = supabase/migrations；Service Role Key 不出后端
- [ ] V1 禁用邮箱确认，密码注册即用、零 SMTP 依赖（#37）
- [ ] 前端仅 Storage 直传 + Realtime 订阅两处直连 Supabase，业务读写一律经 FastAPI（#35）
- [ ] llm_call_logs 可追踪 model/prompt/token/latency/node

**Phase 1 = MVP（Wave A → Wave B）**

- [ ] 录音 POC（Windows）+ ffmpeg ogg-opus **统一转码**链路通过；ASR 任务可重试（S0/#31）
- [ ] Wave A 验收线：真实课堂当日走通 录音→转写→总结确认→知识点确认→习题作答→导出 .md；未归类内容可归类升级进同一闭环（#26）
- [ ] LangGraph Checkpointer 可暂停恢复；Summary HITL 跨重启恢复
- [ ] 结构化输出全部经 Pydantic Schema；超长转写分级总结无静默截断（#36）
- [ ] learning_events 建表并落地四事件，幂等键唯一（#33/#43）
- [ ] 日志不含转写/对话全文；同步冲突返回 409 非静默覆盖（P0 起持续）
- [ ] Wave B 验收线：§4.1~§4.6 MVP 项全量可用 + 工作台形态达成；简答 AI 评分 confidence 仅作 UI 复核标记（#33）
- [ ] 总结质量黄金样本 20 条 + 人工评审 checklist 建立并纳入回归（#46）
- [ ] 无 key 功能级降级 + 健康检查面板（#38）
- [ ] 核心流程有集成测试

**Phase 2+（随阶段验收）**

- [ ] 检索恒定强制 user_id + deleted_at 过滤，course_id 仅范围检索附加；向量删除与业务删除一致（#28）
- [ ] Mastery 单一写入口；Misconception 默认 SUSPECTED（P4）
- [ ] Learning Brain 固定评测集随阶段补建（P4 起，#46）
