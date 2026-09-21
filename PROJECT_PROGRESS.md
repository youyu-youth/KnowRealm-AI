# PROJECT_PROGRESS.md — 项目进度总览（Agent 交接文档）

> **用途**：任何 Agent（或人）接手开发前先读本文档，即可在不重读全部文档/代码的情况下恢复项目上下文。
> **更新规约**：完结工单、合并分支、落定重大决策时，同步更新本文档对应小节；只保留当前有效信息，过期信息直接删除。
> **最后更新**：2026-09-21（**通用 Agent 操作化第一阶段工单 01+02 全栈完结（.scratch/general-agent-v1/，剩用户真机验收）**：01 统一运行时上下文（`agent/runtime.py` 单 ContextVar 承载会话工厂/范围/挂载/页面快照/工具预算，四工具旧绑定对收敛单对 bind/reset）+ `search_courses` 只读课程查询工具（名称子串→候选，恒挂载全部会话类型）+ 页面快照契约（`ChatMessageCreate.page` 五值枚举，后端重校验失效静默降级、注入 SYSTEM 框定为"提示非授权"、不落库不扩读取范围）；02 **公共执行链随首个写动作落地**：`agent/operations/` 注册表（OperationSpec：action→proposal_type/payload_schema/applier + `submit_operation_proposal` 公共提案入口，零领域专属分支）+ `create_course` 薄工具（入参宽松签名、必填与条件校验由注册项 `CourseCreatePayload`〔继承 HTTP 契约仅收紧 extra=forbid〕在提案创建时执法、结构化缺失项 `{ok,missing,detail}` 返回供模型转述追问、每轮操作提案上限 5 超限拒绝）+ 迁移 0028（agent_proposals 整表重建：CHECK 放开 COURSE_CREATE + `result_json` 操作回执列）+ `CourseService.create_core` 事务内核心（HTTP 路由与提案应用器共用，既有路由测试零改动通过）+ 提案框架最小扩展（`register_payload_schema` 反向注册、confirm 中应用器返回值同事务写 result_json、`AgentProposalOut.result` 输出）+ done 载荷 `operation_proposals`（零新 SSE 事件类型）+ 前端 `ChatOperationProposalCard` 确认卡（payload 完整参数预览，复用 spaces 表单枚举翻译）+ APPLIED 回执卡（`/spaces/$courseId` 跳转）+ 断线/重启经 `libraryKeys.proposals("PENDING")` 恢复；prompt bump v10/v11；门禁=后端 **744 passed 满绿**+ruff+pyright 0 错+OpenAPI `--check` 零 diff、前端 vitest 523 绿（1 失败为 CourseBrainMastery 既有并发抖动单跑绿）+lint+build+i18n 防线、api-types regenerate、双轴 code-review 过（Standards 采纳 queryKey 工厂收敛/删死代码/注释补齐，Spec 采纳同源防线测试）。此前同日（工单入库）：四工单 01~04 与 spec 定稿落 .scratch（f643366）。此前 2026-09-20（**研究会话 V1 工单 01 全栈完结（.scratch/research-session-v1/，剩用户真机验收）**：mode=RESEARCH 全链路——创建矩阵仅 ALL/COURSE/FREE（RECORD/LIBRARY_ITEM 组合 422=`CHAT_RESEARCH_SCOPE_INVALID`，错误码清单+zh/en 已登记）+ **迁移 0027**（chat_sessions 整表重建放开 mode CHECK，`legacy_alter_table=ON` 防 FK 改写；spec「零迁移」因 0014/0026 的 CHECK 物理拦截不成立，已在票内备案）+ 研究 prompt 五节结构（无证据拒答、web 与本地 citation 不冒充、FREE 明示无本地资料范围），prompt 版本 `chat-research-scope-v9`（普通会话 `chat-library-scope-v8` 不变）+ 新工具 `propose_ingest` 仅 RESEARCH 挂载（照 propose_memory 先例，5 条上限超限拒绝）→ done 载荷 `research_proposals`（零新 SSE 事件类型）→ 前端新建菜单研究会话弹窗 + 列表行「研究」徽章 + 就地提案确认卡；评测黄金集 `docs/evaluation/research-session-golden-set.md` 就位（10 题四类+四指标门禁，真机首跑待用户）；门禁=后端 **721 passed 满绿**、前端 89/89 批跑绿、双轴 code-review 过。同日**资料库 / RAG + Learner Memory V1 波次七票代码全部完结（07 发布收口过门禁，剩用户真机验收）**；同日收件箱真实数据对接完结。**此前 2026-09-20 为工单 06 Learner Memory V1 完结、资料库 V1 工单 05 生命周期与 AI 整理完结（全栈）**；Concept Mastery V1 六票、F4 Course Brain V1、对话转学习资产 V1、B2、B1、A3 均已完结，细节见 §3/§5 对应行。）

## 1. 项目概述

**KnowRealm-AI** 是开源的**本地优先**个人学习工作台（Tauri 2 桌面应用 + FastAPI sidecar）：把课堂录音、音频导入、文档、粘贴文本、闪念速记统一「捕获」，经 ASR 转写与 AI 总结（人工确认）转化为可编辑、可追溯的学习资产（总结 / 知识点 / 习题 / 模拟测试 / Todo / 复习资料），并提供基于记录内容的 AI 对话问答与全局搜索。

- **给谁用**：一切学习知识的人（学生、程序员、上班族、终身学习者）。
- **产品铁律**：零部署（.msi 即用）、无账号、桌面端永不强制登录（ADR-0014）；数据全部落在用户可见可搬移的本地目录。**新能力先过两问**：① 数据是否落在本地可见可搬移的目录？② 是否要求用户多装任何东西？
- **核心闭环**：捕获 → ASR 转写 → AI 总结（人工确认）→ 知识点 / 习题 / Todo → AI 问答。
- **长期方向**：「学习助手」→「个人学习大脑」（掌握度 / 遗忘复习 / 自适应学习），路线见扩展设计文档 §39/§40。

---

## 2. 当前开发阶段

**基线功能已全部实现，处于「扩展功能（F 系列）+ 质量收尾」阶段。**

- 基线（PRD 决策表 #1~#59 绝大多数）代码完结，约 15 个功能波次仅剩**用户真机验收**（按惯例由用户执行，Agent 验证止于自动化门禁，不代勾）。
- 扩展 F1「转写分片 / 来源时间轴」**六票 + 07 补票全部完结**（06 文档收尾：数据模型升 v2.4 重命名——现 v2.9、扩展文档 §7 回写、全库交叉引用同步、backend/AGENTS.md 0019）；锚点两表空表就位，剩用户真机验收。
- **Chat Agent 骨架已迁移 deepagents**（ADR-0018，2026-09-13）：`create_agent` → `create_deep_agent` 严格空骨架 + `AgentConfig` 轻工厂，模型可见面与迁移前严格一致（423 测试全绿），为 Tools/Skills/Memory/RAG 预留官方架构入口；summary/review 两图维持裸 LangGraph 形态。2026-09-14 `chat/` 模块升级为统一 `agent/` 模块（ADR-0020，行为零变更）：装配落 `graph.py`、上下文组装落 `context.py`、引用校验落 `citations.py`，能力子包 `tools/`+`middleware/` 就位。
- Desktop 全局框架与 `/`「今日」页已按新版 `DESIGN.md` 完成重设计：冷中性设计令牌、分层应用壳、课程侧栏、紧凑 Command 入口、Toast / Tooltip / 状态标签与今日页「学习链 → 行动/资产 → 统计」阅读顺序均已落地；范围外页面只继承主题基础，不改业务布局。
- `/inbox` 已改为高密度桌面工作区：真实统计、来源/状态筛选、URL 可恢复搜索与分页、多选批量归类/升级/删除、Transcript 预览及宽屏常驻右栏/窄屏 Dialog 均已落地；并按用户提供的视觉参考强化彩色统计图标、分组筛选按钮、列标题、独立圆角记录行、约 30% 宽右侧检查器及主次操作按钮。数据已全部对接真实接口（2026-09-20）：`GET /api/inbox` 返回 `InboxRecordOut`（含文件大小和/正文字数），行副标题按来源展示「时长+大小 / 大小 / 字数」元信息，本地示意数据机制已移除。
- `/spaces`「知识空间」已按视觉参考完成重设计：标题 + 场景/状态胶囊筛选 + 排序 + 「更多筛选」子菜单（收纳教育阶段/课程类型）+ 网格/列表视图切换；课程卡片含场景图标、状态徽章、统计三格（记录/知识点/最近更新）、学习进度条与打开/编辑/⋯删除；右栏四模块（知识空间统计 / 最近活跃课程 / 待归类内容 / 最近活动）；新建课程改为右侧 Sheet 抽屉（学习场景三卡片按钮 + 只读初始状态 + 简介 200 字计数）。筛选/排序/视图全部在客户端完成（一次全量拉取，URL search params 可恢复），后端零改动。课程级聚合统计与周活跃、待归类、活动流后端暂无接口，按惯例用确定性示意数据并以「示意」标签明示（`spacesInsights.ts`，统计域接入后整体替换）；右栏「待归类内容」唯一真实入口为 `/inbox`。卡片「编辑」经 `/spaces/$courseId?edit=1` 直达编辑态。
- `/spaces` 动效与材质打磨（对齐 DESIGN.md §5/§11/§13）：进度条一次性生长（560ms，`transform: scaleX`，`prefers-reduced-motion` 下瞬时到位）为唯一传入动画；网格/列表切换 150ms 淡入 + 4px 位移并统一顶部间距；卡片/列表行 hover 改为 120ms 边框/色面过渡并移除常驻阴影（面板改 `surface-raised`，暗色 hover 仅边框增强以避免"凹陷"观感）；Sheet 出入场 160/180ms；元数据由 `text-ink-faint` 提至 `text-ink-muted` 满足 4.5:1。收件箱暂保留旧柔阴影语言，待后续统一。
- `/spaces/$courseId`「课堂详情」学习链已独立为「学习链」Tab（位于概览之后，`?tab=chain` 可恢复），头部不再常驻轨道（固定区更紧凑）；Tab 内为 **ECharts 桑基流图**「学习链流转」：主脉 捕获→转写→总结→确认 + 分支 未开始处理 / 转写中 / 生成中 / 待确认 / 处理失败，宽度=真实记录数，单色明度阶（确认与待确认 ink-strong、停留项 faint、失败用语义危险色），配右侧文字摘要（阶段与转化率、停留分布、失败口径说明）与数据来源注记；派生口径见 `courseLearningChain.ts`（到达=进入阶段、进行中也算；失败记录不保存失败阶段，只作捕获侧分支并明示；流转守恒有单测断言），空课程给捕获引导空态。概览「知识概念图谱」固定为主题灰阶南丁格尔玫瑰图；「课程脑图」固定为可拖拽、缩放、邻接高亮且自动隐藏重叠标签的力布局关系图；两处共用确定性多记录示意知识点聚合（同名合并、Top 12，玫瑰图含「其他」）和权重文字摘要，不再提供力导图/树状图切换，保留全屏。本页其余结构沿用上轮（固定工作面 + 局部滚动、概览分区节奏、右栏结构列 + 窄屏 Sheet），后端与 API 零改动。
- 课堂详情门禁：`pnpm test -- --maxWorkers=4` 421/421、`pnpm lint`、前端触及文件 Prettier、`pnpm build`（内嵌 tsc）均通过；真实 Tauri sidecar 经 WebView2 CDP 目检：学习链 Tab 桑基图亮/暗两态、java实现（5 条含失败分支）与 1111（单条）两个真实课程数据形态、脑图/GPS/记录等 Tab 与概览回归；知识图谱玫瑰图/关系图亮暗两态、全屏、关系节点拖拽、画布缩放、悬浮邻接提示，以及常规动效 / `prefers-reduced-motion` 均通过；1440×900、1280×800、1099×720 CSS viewport 无页面横向溢出。空课程空态由 jsdom 用例覆盖（本机数据目录无 0 记录课程）。
- `/chat`「AI 对话」已按视觉参考重设计为**三栏工作区**（对话记录 | 对话 | 上下文面板）：左栏筛选胶囊（全部/今天/本周/已收藏）+ 会话行 ⋯ 菜单（收藏/重命名/删除）；中栏标题栏（收藏/⋯）、范围胶囊、空会话建议卡、流式消息与图 1 输入区；右栏当前挂载上下文 / 来源引用 / 工具状态 / 小提示。回答与流式 Markdown 改用 **Streamdown**（`@streamdown/code|cjk|math`：代码高亮、中文换行、KaTeX 公式、`animated` 动画；`[n]` 引用角标经 remark 插件转链接后由 `components.a` 渲染为可点击角标）。`ChatMessageList` / `ChatComposer` 重构，旧 `ChatPage`/`ChatSessionPage`/`ChatSessionList` 由 `ChatWorkspace` 三栏替代；路由与 URL 不变（`/chat`、`/chat/$sessionId`、`?prompt=` 知识点讲解入口保留）。后端零改动；图 1 独有而后端暂无的能力（会话收藏、右栏工具开关、输入区附件/设置图标）为本地示意状态并以禁用/tooltip 明示，课程/全部资料范围胶囊禁用提示「即将支持」。
- AI 对话重设计门禁：`pnpm test -- --maxWorkers=4` 424/424、`pnpm lint`、前端触及文件 Prettier、`pnpm build`（内嵌 tsc）通过；chat 测试 19 项（原 16 项行为断言保留，重命名/删除改走 ⋯ 菜单路径；新增筛选/收藏、建议卡/工具开关与多回答引用聚合用例）。真机 Tauri sidecar + WebView2 CDP 目检：亮/暗两态、根字号 18px（L 档）无横向溢出、1200px 窄窗右栏自动收起且左栏保留、引用聚合（多回答 [n] 去重）与工具开关（chat-accent）实测正常。
- 右栏「来源引用」列表收口（2026-09-16）：超过 4 条只预览前 4 条，列表下方「查看全部 N 条」按钮打开 Dialog 滚动展示全部引用，条目点击行为与右栏一致（record 跳转写页定位、web 经系统浏览器）。新增 `ChatCitationsDialog.tsx`（复用 `ChatCitationList` / `useOpenCitation` 与 `components/ui/dialog`），i18n zh/en 同交，后端零改动。门禁：`pnpm test -- --maxWorkers=4` 460/460（chat.test.tsx 新增截断+弹窗用例）、`pnpm lint`、触及文件 Prettier、`pnpm build`（内嵌 tsc）通过；真机目检待用户验收。
- 下一扩展方向（扩展文档 §40.4「P2 统一序列」）：F1 ✅ → **A1+A2 ✅ 已交付**（2026-09-13 三票完结，剩用户真机验收）：票 01「分片 FTS 索引地基」✅（迁移 0020 `segment_search_index` FTS5 表、search 模块 `SegmentSearchService` 维护+检索服务、finalizer/realign/存量回填三处写路径同事务挂点、main.py 启动幂等回填、`tests/test_segment_search.py` 7 项，user_version 断言 11 处同步 19→20）；票 02「检索工具与 SSE 工具事件」✅（`agent/tools/search_transcript.py` `search_transcript`：FTS top-8 逐字命中 + 时间戳/页码，无分片回退 transcript 子串；挂载变体 `MOUNTED_CHAT_AGENT_CONFIG`、`tool_call`/`tool_result` SSE 事件、usage 跨模型调用累加、>30k 工具指引、`CHAT_PROMPT_VERSION`=chat-mount-cite-v3）；票 03「前端工具状态卡 + 文档收尾」✅（SSE 两新事件分发、`useChatStream` 工具状态临时态、消息流内检索过程卡三态逐条陈列、done/中断后消失；数据模型升 v2.5、扩展文档 §40 A1/A2 回写、CONTEXT.md 增「分片索引」「检索过程」词条）→ A3 ✅（2026-09-14 四票完结，ADR-0021，见 §3「学习事件/证据」行）→ **B1 web_search ✅**（2026-09-14 两票完结，见 §3「AI 对话」行与扩展文档 §40.3 B1 行）→ **B2 跨记录问答 ✅（2026-09-14 单票全栈完结，.scratch/cross-record-qa/，后端 488 + 前端 440 绿）**：scope 四档显式列（迁移 0022）、`search_library` 跨记录工具（FTS+LIKE 兜底、互斥挂载）、标题清单上下文、跨记录引用（校验器裁定归属+record_title 快照）、web_search 挂载语义延伸、前端范围胶囊/新建菜单/课程对话 Tab/右栏接真；数据模型升 v2.7、错误码清单 +3。**F4 Course Brain V1 已完结（2026-09-15~16，.scratch/course-brain-v1/ 十二票，ADR-0022，数据模型 v2.8，见 §3）**；「对话转学习资产 V1」已完结（2026-09-15，.scratch/chat-to-knowledge-point/，基线 Phase 2 已定项）。B3「Tutor 场景包」待决策；B5 sqlite-vec 结论已定=延后（CB-01 评测），触发条件=真实语料词汇不重合失败。

---

## 3. 已完成功能（代码已实现、自动化门禁通过）

> 状态标签说明：工单状态存在四代变体 `done` / `completed` / `resolved` / `in-review`，**均视为已完成**（历史惯例差异，见 §8 漂移说明）。下列各项除特别注明外，均剩「用户真机验收」。

| 域 | 功能 | 备注 |
| --- | --- | --- |
| 捕获 | 课堂录音（托盘/全局快捷键）、音频导入、单文件文档导入、文本捕获+闪念速记、捕获收件箱（归类/升级/移交总结）、全局快捷键+托盘 | 录音文件不经云端（ADR-0002/0004），云 ASR 前强制同意（ADR-0006） |
| 转写 | 腾讯云 ASR 管道、密封批次生命周期、失败重试恢复、文档删除清理 | ASR 管道已接句级时间戳（F1 票 02） |
| **F1 分片** | 迁移 0019 四表 + source_anchor 模块；ASR 句级时间戳→JSONL→`/records/{id}/segments`；文档分片 DocumentBlock + document-segments 端点；存量回填 + 编辑对齐重切；**前端来源时间轴（三态浏览视图、quote 内联高亮+时间戳徽章、分片重拉三处）+ chat 引用句级定位**；文档记录接入块级时间轴（07 补票） | 票 01~07 完结；文档收尾=数据模型 v2.4（现 v2.9）、扩展文档 §7 回写；降级双场景（无时间戳/无分片）已处理 |
| 总结 | Provider 优先的总结生成、调整/确认/恢复（人工确认制） | LangGraph 图之一；>30k 长文的 map-reduce **未做**（见 §5） |
| 知识点 | 候选生成、人工审核确认、重生成与转写联动 | |
| 习题 | 四题型生成/采纳/重生成、客观题作答、简答题完成 | |
| 模拟测试 | 五题型建卷、作答面、逐题 LLM 评分+交卷、结果页+摘要侧栏、崩溃恢复重评 | QUIZ_TEST_COMPLETED 幂等；失败题排除分母 |
| Todo | 手动 CRUD、生成/采纳/修剪、用户接管语义 | 接管即脱离批次（ADR-0011） |
| 复习资料 | 生成（上下文=转写全文+总结辅助）、HITL 确认对话框、版本链编辑、导出接入 | LangGraph 图之二；RAG 已否决 |
| AI 对话 | 档案（角色+自我介绍）、会话管理、流式自由对话、记录挂载上下文、引用（citations）+转写失效联动、知识点讲解入口；**三栏工作区（对话记录/对话/上下文面板）+ Streamdown 流式 Markdown（代码高亮/CJK/公式/引用角标）**；**B1 联网搜索已接真（2026-09-14 两票）**：`web_search` 工具（Tavily，无 key 双保险不挂载）、发消息带 `web_search` 标志（右栏开关+输入区 Globe 按会话记忆，自由 ON/挂载 OFF）、citations web 条目「标题+域名+外链」经系统浏览器打开、工具卡文案分流、设置页搜索供应商卡（key/测试）、`CHAT_PROMPT_VERSION` v4；**B2 跨记录/课程级问答已接真（2026-09-14 单票全栈）**：`chat_sessions.scope` 四档（FREE/RECORD/COURSE/ALL，迁移 0022，course_id 启用语义、课程软删→会话只读）、COURSE/ALL 会话挂 `search_library`（跨记录分片 FTS top-8 + LIKE 兜底，与 search_transcript 互斥）、上下文=记录标题清单（约 4000 字符预算）+检索指引、跨记录引用「[n] 摘录（来源：标题）」+record_title 快照+校验器裁定归属（禁全范围模糊对齐）、web_search 视同挂载默认关、前端范围胶囊（点其它=新建会话）/新建菜单四入口/课程详情对话 Tab/右栏范围卡/工具卡与引用标题接真、`CHAT_PROMPT_VERSION` v5（RECORD 范围零回归）；**对话转学习资产 V1 已接真（2026-09-15 单票全栈，基线 Phase 2 已定项）**：AI 回答「保存为知识点」（全 scope，目标记录选择器默认挂载记录）、单事务四写（知识点 ACTIVE + 搜索索引 + CHAT_MESSAGE 锚点〔锚点体系首个写入者〕+ KNOWLEDGE_POINT/PRIMARY 链接，事务由路由编排层管理）、detail 预填聚焦摘要（首段 + 引用句纯函数提取）、知识点列表「源自 AI 对话」徽章跳回原会话（`chat_source` 三表 JOIN 派生）、零学习事件（不污染证据）、零迁移；错误码 +2（CHAT_MESSAGE_NOT_FOUND/NOT_ASSISTANT）+ RECORD_COURSE_MISSING 复用 | LangGraph 图之三：deepagents `create_deep_agent` 骨架（ADR-0018）；挂载会话注入 `search_transcript` 检索工具（A1），SSE 增 `tool_call`/`tool_result` 事件并在消息流内呈现检索过程卡（A2：正在检索 → 命中 n 条 / 失败，逐条陈列、done 后消失、不落库）；图 1 独有交互（收藏/其余三工具开关）为本地示意假数据，未接后端 |
| 课程 | 工作台骨架、课程 CRUD、发现页、详情编辑、归档退出 | ARCHIVED 前置护栏三道闸门已校验；归档/恢复 UI 未做（有意推迟） |
| 记录 | 真实记录列表、记录详情（总结/转写面板化）、记录删除退出 | |
| **学习事件/证据（A3）** | 迁移 0021 `learning_evidence` + learning 域（`events.write_learning_event` 统一写入 / `consumer.py` 独立 asyncio 水位消费循环 / `queries.py` 薄只读查询按记录/课程取证据流）；四事件（总结确认/知识点确认/逐题作答/交卷）与业务动作同事务写入 | ADR-0021：不入 processing_jobs、水位=隐式 rowid 单调扫描、禁 NOT EXISTS、失败 3 次跳过、映射集中声明（QUIZ 0.9/0.8、CONFIRMED→USER_CONFIRMATION 0.3·0.4/0.7、交卷不产证据防双计）；零 LLM/零前端/零新 API；concept_id 已由票 01/02 接通（source_anchor_id 仍留后续） |
| **Concept Mastery V1（票 01~06）** | 迁移 0024 `quizzes.concept_id`（生成只从同课程 CONFIRMED 概念建议主概念、作答前可改/清空、作答后锁定，逐题 Event 固化 concept_id）+ 迁移 0025 `user_concept_mastery`（每 Concept 唯一快照，只存 V1 字段）+ `learning/mastery.py` 确定性算法（12 条窗口/四条半衰/有效计数 Confidence/NOT_ENOUGH_DATA·WEAK·LEARNING·STABLE，黄金样本冻结；`window_evidence` 为重算与详情共享的唯一窗口口径）+ Evidence Builder 复制 Event 概念、Consumer 同轮触发全量重算（失败重试后记结构化错误）+ `GET /api/courses/{id}/mastery` 只读（覆盖率/四态计数/状态筛选/无写 API）+ `GET /api/courses/{id}/mastery/concepts/{cid}` 详情（snapshot + algorithm_version + 窗口内 Evidence 按时间倒序；来源区分普通 Quiz〔record_id+标题+quiz_id〕与模拟测试逐题〔metadata.test_id+sequence_no〕，无定位只给时间不造假链接）+ 前端 Knowledge GPS 真实列表（URL 可恢复筛选）与概览卡接真、行打开详情 Dialog 与来源跳转（`?tab=quiz` / tests 结果页）、章级示意掌握度与模拟课程掌握度删除 + **票 04 生命周期**：Record/Course 软删除返回受影响概念并由端点同步全量重算（历史 Event/Evidence 保留审计）、归档概念退出聚合与活跃查询（详情 404）但快照证据保留且不接收新证据、启动 `recover_snapshots` 重建缺失/版本过期快照（幂等、零新队列）、物理删除经 FK CASCADE 清快照 + **票 05 Course Brain 标记（纯前端 df4b628）**：Tab 查询层组合 `useCourseMastery`（与概览卡共享缓存）派生单一 `masteryByConceptId` 映射，图谱节点标签 token 色状态点（`masteryDotCssVars` 与 `masteryDotClassNames` 同源）+ tooltip「掌握状态」行（节点主色仍为重要度灰阶）、列表 CONFIRMED 行复用 `ConceptMasteryBadge`、详情 aside 掌握行 + 「掌握详情」复用既有 Evidence 弹窗；加载中/查询失败诚实无标记，候选行永不显示；`CourseBrainMastery.test.tsx` 5 项（列表标记/tooltip+标签/详情入口/失败降级/零概念） | 票 01~06 done（06 于 2026-09-18：ADR-0023 + 数据模型现已升 v3.0 + PRD/扩展设计/CONTEXT/技术栈交叉引用收口；真机验收清单在票 06，剩用户验收）；票 03 顺带修复票 02 缺陷=模拟测试逐题（record_id 空）证据被 inner join records 误排除、永不参与 Mastery，现 LEFT JOIN + deleted_at 过滤；「后台计算中」状态未单列（与证据落库同轮完成，见工单 02 实施备注）；窗口内证据计数封顶 12；**重算失败闭环**（2026-09-18 架构评审 C1 修复）：重算 3 次失败→快照 `algorithm_version` 钉 `stale` 哨兵（重启恢复按版本不匹配重建、重算成功自愈自清，失败窗口保留最后已知值）+ 失败概念交 `EvidenceConsumer` 内存 pending ≤30s 重试（删除路由/consumer/启动恢复三处喂入，重启即清由哨兵接回恢复闭环），`recompute_concepts`/`recover_snapshots` 改返回失败集合，AST 防线测试 `test_soft_delete_recompute_guard` 防新增删除入口漏接线；零迁移零前端，594 绿 |
| **F4 Course Brain V1** | 迁移 0023 三表（concepts/concept_relations/record_concepts，CONFIRMED 部分唯一索引）+ `course_brain` 模块（六态快照/概念与关系列表/来源回溯/手动创建/`apply-review` 五决策单事务/archive）+ 构建 Worker（`CONCEPT_EXTRACTION`：多来源收集/分块 LLM 结构化抽取/确定性归一化挂接/逐字锚点/单事务原子发布/重建不覆盖 CONFIRMED）+ B2 `search_library` 概念增强（Concept FTS top-4→canonical_name 并跑分片 FTS、occurrences 按 record 去重、`CHAT_PROMPT_VERSION` v6）+ 可观测（`llm_call_logs.retrieval_count` 埋点/检索工具体异常 ok=false/审计日志）+ 前端 map Tab=Course Brain 主页面（六态/图谱列表双视图/候选审核抽屉/Relation 审核区/详情与来源跳转/手动创建/归档），mock 图谱链删除 | ADR-0022；CB-00~12 十二票完结（2026-09-16）+ **CB-13 P1 遗留修复**（2026-09-16：来源跳转 segment_id 精确定位、课程移动读取期防护、零证据三层闸门+错误码 COURSE_BRAIN_CONCEPT_NO_EVIDENCE）；sqlite-vec 延后（CB-01 合成评测四维全过，`docs/evaluation/course-brain-retrieval-baseline.md`）；数据模型 v2.8；剩用户真机验收（工单 12/13 清单） |
| 学习统计 | 后端七口径统计端点、前端统计带+5 图（真实数据） | 七口径=JOIN records+子表 deleted_at 双过滤 |
| Desktop 界面 | 全局 `canvas → sidebar → paper` 框架、224/64px 响应式侧栏、52px 顶栏、课程快捷入口、Base UI Tooltip / Toast / 状态标签；「今日」页学习链、行动/资产双列、真实六指标 + 7/30 天趋势与次级洞察图；「收件箱」统计筛选、多选批量操作、紧凑列表与响应式内容预览；「知识空间」胶囊筛选 + 网格/列表视图、课程卡片（统计/进度）与右栏洞察、新建课程 Sheet 抽屉；「课堂详情」固定工作面 + 局部滚动、七标签、「学习链」Tab 桑基流转图（真实记录派生 + 文字摘要）、概览知识点权重玫瑰图、课程脑图力布局关系图（自动标签避让）+ 权重摘要 + 全屏、概览分区节奏、结构列课程信息（窄屏 Sheet，编辑 Sheet / 删除保留） | 无后端、API 或数据结构变更；无后端支持区域（右栏统计/活动、卡片聚合统计、课程级概览、图谱玫瑰图、相关推荐）以确定性示意数据 + 「示意」标签明示且只读（学习链/最近记录/相关资源/知识 GPS 掌握度为真实数据）；筛选/排序/视图/标签为客户端实现，URL 可恢复；整页不滚动、滚动只在明确局部容器内（DESIGN.md §4/§13） |
| 全局搜索 | FTS5+jieba 应用层分词（ADR-0016）、写路径同事务同步 11 挂点、Ctrl+K 命令面板、`/library` 资产库视图 | 统一索引表；软删查询期回表过滤；启动幂等回填 |
| **资料库 / RAG V1（01~07）** | `/library` 统一资产工作台（左导航智能视图〔含归档/回收站〕+领域分类+URL 可恢复筛选+三对象检查器）；统一入库三路（web 剪藏/file/text，判重 409+allow_duplicate、失败降级）；五档 RAG 检索（LibraryRetrievalService 单一 search_library、LIBRARY_ITEM「AI 解读」会话、citations library 条目）；生命周期全套（重命名/归类不级联/归档恢复/软删回收站 30 天/物理删 409 防线/重试/refetch 新条目/索引重建 Worker）；AI 整理（确定性扫描+LLM 建议→ORGANIZE 提案逐项确认）+ RESEARCH_INGEST（web 引用「建议保存」→确认后业务入库）；提案框架（PENDING/APPLIED/REJECTED/FAILED、confirm 接受 FAILED 重试、payload 判别清洗、跨重启持久化）；**Learner Memory V1（learner 域，ADR-0025）**：学习画像「AI 记忆」（显式偏好直编/观察偏好带置信度证据数时间/外发开关）、Learner Context 确定性注入（agent SYSTEM 末尾，Course 不越界/ALL 最小集合/预算 2000）、MEMORY 提案 HITL（对话「记住…」propose_memory 工具→done 载荷 memory_proposals→就地确认卡；观察零覆盖显式）、注入前提=外发开关 AND consent 指纹有效、硬门禁 17 例全绿 | ADR-0024/0025；迁移 0026（数据模型 v3.1）；**七票代码全部完结，07 收口过全部门禁（2026-09-20，后端 704 满绿/黄金集复跑绿/双轴 review 过），剩用户真机验收**（03/04/05 清单在各工单、06 清单归 07、通用+记忆两块真机清单在 07） |
| **研究会话 V1** | mode=RESEARCH 全栈（工单 01/02，零新表零新列）：创建矩阵仅 ALL/COURSE/FREE（RECORD/LIBRARY_ITEM 组合 422=`CHAT_RESEARCH_SCOPE_INVALID`，清单+zh/en 登记）+ **迁移 0027**（chat_sessions 整表重建放开 mode CHECK，`legacy_alter_table=ON` 防 FK 改写）；研究 prompt 五节固定结构（已有证据/来源差异/冲突与缺口/暂定结论/建议保存的来源）+ 无证据拒答 + web/本地 citation 不冒充 + FREE 明示无本地资料范围，`chat-research-scope-v9`（普通会话 v8 不变，按 mode 分流埋点）；`propose_ingest` 仅 RESEARCH 挂载（ContextVar 先例，5 条上限超限拒绝，RESEARCH_INGEST 提案 COURSE 自动带课程 id、ALL/FREE 落 None、溯源 session_id）；done 载荷 `research_proposals`（零新 SSE 事件类型）；前端：新建菜单研究会话弹窗（研究问题必填 `?prompt=` 预填/范围默认 ALL/联网默认 ON 无 key 降级提示）、列表行与标题栏「研究」徽章、研究特化建议卡、就地提案确认卡（临时态，确认走既有 RESEARCH_INGEST 应用器）；评测黄金集 `docs/evaluation/research-session-golden-set.md`（10 题四类+四指标门禁+`score_research_structure` 结构评分脚本）；CONTEXT.md 词条修订+新增、错误码清单登记、数据模型 :301 值域同步（升版重命名待拍板） | 剩用户真机验收 + 黄金集真机首跑；spec「零迁移」不成立已备案 |
| **通用 Agent 操作化（第一阶段 01~02）** | **01 统一上下文与课程查询**：`agent/runtime.py` 单 ContextVar（AgentRuntimeContext：会话工厂/会话 id/范围/挂载对象/模式/联网供应商/页面快照/ToolCallBudget）收敛四工具旧绑定对，`stream_chat_reply` 单 runtime 参数；`search_courses` 只读工具（名称子串→候选 id/名称/状态/场景/阶段或深度/更新时间，上限 8 截断明示，恒挂载全部会话类型，与 search_library 共用每轮 6 次预算）；页面快照（`ChatPageSnapshot` 五值枚举随消息请求、不落库、后端 `_validate_page_snapshot` 重校验失效静默降级、`PageHint` 注入 SYSTEM 框定"提示非指令非授权"、FREE 挂载矩阵不变）；前端 `derivePageSnapshot()` + streamMessage 可选 page + 工具卡 courseSearch 文案。**02 自然语言创建课程（公共执行链落地）**：`agent/operations/` 注册表（OperationSpec：action→proposal_type/payload_schema/applier + `register_operation` 同步注册进提案框架 + `submit_operation_proposal` 公共提案入口：schema 校验→每轮 5 条上限拒绝→ProposalService.create，零领域专属分支）；`create_course` 薄工具（入参宽松可选签名，必填与条件校验由注册项 `CourseCreatePayload`〔继承 CourseCreate 仅收紧 extra=forbid 同源零漂移〕在提案创建时执法，结构化缺失项 `{ok,missing,detail}` 供模型转述追问，同源防线测试钉住）；**迁移 0028** agent_proposals 整表重建（CHECK 放开 COURSE_CREATE + `result_json` 操作回执列）；`CourseService.create_core` 事务内核心（HTTP 路由与提案应用器共用、既有路由测试零改动通过）；提案框架最小扩展（`register_payload_schema` 反向注册〔library 不依赖 agent〕+ confirm 应用器返回值同事务写 result_json + `AgentProposalOut.result`）；幂等=APPLIED/REJECTED 终态双确认 409（沿用框架）、未确认零创建、回执持久化可查明；done 载荷 `operation_proposals`（零新 SSE 事件类型）；prompt bump `chat-library-scope-v10`/`chat-research-scope-v11`；前端 `ChatOperationProposalCard`（确认卡完整参数预览复用 spaces 表单枚举翻译、APPLIED 回执卡 `/spaces/$courseId` 跳转、断线/重启经 `libraryKeys.proposals("PENDING")` 恢复与当轮去重合并）+ zh/en 同步；门禁=后端 744 满绿+ruff+pyright 0 错+OpenAPI 零 diff、前端 523 绿+lint+build+i18n 防线、api-types regenerate、双轴 code-review 过 | 工单 01/02 done（.scratch/general-agent-v1/）；03 文本记录（复用 operations 验证扩展性）→ 04 综合验收待开工；剩用户真机验收 |
| 设置 | 偏好（外观/通用/关闭行为/自启/快捷键自定义/重启恢复）、档案（昵称/头像）、LLM/ASR 供应商卡+连通性手动测试、数据目录（切换/迁移/重启，desktop.json）、全量导出/导入/滚动备份、首启向导四步、**服务与用量分区（30 天 LLM 用量聚合+趋势图+缺 key 徽章）** | 单 active 供应商；连通性仅手动（真实计费） |
| 界面语言 | 中英全量切换（含首启向导语言步）、en.json 全量真译+一致性防线、后端错误码化（ADR-0017 附加字段）、前端错误码翻译消费+壳层命令码化 | 内容语言与界面语言解耦（prompt 固化指令） |
| 导出 | 总结/知识点本地导出、习题/Todo 本地导出（markdown） | 聚合导出验收待用户（ready-for-human） |
| 评测 | 习题 Groundedness 评测样本集与评审 checklist（docs/evaluation/） | 样本采集待用户（阻塞项） |

---

## 4. 进行中 / 部分完成

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 用户真机验收 | 约 16 个波次 | account-profile / preferences(04 恢复) / 模拟测试 / 复习资料 / 学习统计 / 全局搜索 / 服务用量 / 界面语言 / F1 分片 / **F4 Course Brain** 等，验收项在各工单内单列，**不代勾**（preferences 05 整票=验收票，deferred） |

---

## 5. 待开发 / 规划中

**明确待做（已有工单）：**

- ~~`concept-mastery-v1/06`~~（✅ 2026-09-18 完结，ADR-0023）。**Concept Mastery V1 链整体完结**，资料库 V1 + 知识起点扩展波次（扩展文档 §41/§42）已解锁待开工。
- `ai-summary/03-long-summary-quality-recovery`（**deferred**，2026-09-20 用户拍板先不做）：>30k 长总结 map-reduce、90s 超时/不自动重试语义、手动重试复用 Job、ACTIVE 校验、llm_call_logs 字段补全、评测样本。现状仍是 chat 侧对 >30k 转写做降级提示（`agent/context.py` CHAT_TRANSCRIPT_MAX_CHARS=30000），总结侧无长文处理；重新开工前按当时现状复核票面。
- `markdown-export/03` 聚合导出（`ready-for-human`，代码完成仅剩用户验收后关票）。

**规划中（未拆票，勿直接开工）：**

- 扩展文档 §40.4「P2 统一序列」：F1（✅ 2026-09-10）→ A1+A2（✅ 2026-09-13）→ A3（✅ 2026-09-14 四票，ADR-0021，.scratch/learning-evidence/）→ B1 web_search（✅ 2026-09-14 两票，.scratch/web-search/）→ B2 跨记录/课程级问答（✅ 2026-09-14 单票全栈，.scratch/cross-record-qa/，数据模型 v2.7）→ B6 对话转学习资产 V1（✅ 2026-09-15 单票全栈，.scratch/chat-to-knowledge-point/）→ **F4 Course Brain V1（✅ 2026-09-16 十二票完结，原 P3 提前实施，.scratch/course-brain-v1/，ADR-0022，数据模型 v2.8：迁移 0023 三表 + 构建 Worker + 审核闭环（apply-review 五决策/合并建议/归档/stale 派生徽章）+ B2 search_library 概念增强（prompt v6，occurrences 按 record 去重）+ 可观测（retrieval_count 埋点/检索工具异常 ok=false/审计日志）+ 前端 Course Brain 主页面与审核工作台（mock 图谱链删除）；详见 §3 行与扩展文档 §40.3 B7 回写）**。B3「Tutor 场景包」待决策；B5 sqlite-vec 维持延后（CB-01 合成评测四维全过，`docs/evaluation/course-brain-retrieval-baseline.md`），触发条件=真实语料词汇不重合失败（届时新开 CB-VEC 票）。
- **资料库 / RAG Agent / Learner Memory V1 已定稿并完结（2026-09-18 定稿，扩展文档 §41~§43，ADR-0024/0025）**：一个外部版本按七张纵向工单交付：契约与评测 → schema/幂等回填/工作台 → 网页剪藏（httpx + trafilatura）→ LibraryRetrievalService + LIBRARY_ITEM 范围 → 生命周期/提案/导出恢复 → Learner Memory V1 → 发布门禁。**工单 01~07 已全部完结（07 于 2026-09-20 收口过门禁，见 §3）**：01 契约与评测地基（contract.md 冻结 0026 DDL/工具预算/错误码，黄金集 20 查询四指标全过、sqlite-vec 不触发、英文无需补分词，评测资产可复跑）；02 Schema+存量回填+工作台（数据模型 v3.1、提案框架、联邦两枚只读端点、前端 features/library 重构）；03 统一入库与网页剪藏（三路 ingest、WebClipAdapter 受限抓取、WEB_FETCH Worker、判重与失败降级，真机验收过含两轮修复）；04 RAG Agent 闭环（`library/retrieval.py` 五档隔离、单一 search_library、LIBRARY_ITEM 会话、citations library 条目、AI 解读入口）；05 生命周期/AI 整理/提案闭环（§3 行详述；contract.md 有 05 实施记录七条备案）；06 Learner Memory V1（learner 域四端点+确定性注入+propose_memory 工具+确认卡+硬门禁 17 例）。**波次整体剩用户真机验收（07 票内两块清单：通用 6 项 + Learner Memory 10 项，不代勾）**。LibraryItem 只表示来源，Record/学习资产保持独立；Agent 只见 `search_library`，写动作持久化提案后经 HITL + 领域 Service；Learner Memory 复用 `learner_preferences` 并聚合既有事实，普通聊天不得静默记忆；sqlite-vec 只由真实黄金集净增益触发。后续按序（2026-09-21 用户拍板顺序再变更，扩展文档 §41.1/§44 已回写）：**问题驱动研究会话 V1（✅ 2026-09-20 工单 01 全栈完结，.scratch/research-session-v1/，见 §3）** → **通用 Agent 操作化（2026-09-21 设计采纳完整插队，扩展文档 §44 + ADR-0026，主稿 = `docs/KnowRealm-AI-通用Agent设计-4.md` 采纳版；第一阶段课程查询/创建与文本记录〔默认档、首批不含 Todo〕→ 第二阶段修改/批量+三档授权 → 第三阶段多资料/课程计划/恢复 → 第四阶段条件式生态；[开发计划](docs/KnowRealm-AI-通用Agent设计开发计划方案.md)为 grill 入口，冻结主稿 §11 五项事项及最小能力接入/结果/版本契约；仅收拢本阶段业务入口与事务，可靠性随首个动作实施，能力尚未上线，勿直接开工）** **工单 01~02 已完结（2026-09-21，.scratch/general-agent-v1/，见 §3 通用 Agent 行）** → 剩 03 向课程添加文本记录（复用 operations 验证扩展性）与 04 单步可靠性综合验收 → 书籍拆章（超长章兜底随拆票 grill 定案；map-reduce〔ai-summary/03〕维持 deferred）→ 课程大纲初始化。
- 习题 Groundedness：待用户采集真实样本（阻塞项）+ 06 总结黄金样本另议；回归触发=prompt_version/模型变更。⚠️ prompt_version 至今未 bump，启用评测前需处理。
- 未来候选库路线图（带触发条件，见记忆/后端轮子审计）：检索维持 FTS+Concept 基线，真实黄金集证明净增益后才加 sqlite-vec；复习调度 fsrs、导出 fpdf2、pytest-cov/timeout；APScheduler/LanceDB/本地 whisper 已否决。
- 产品层扩展方向五新场景包：见扩展文档 §39.4（仅评审记录，**非用户已批准**）。

---

## 6. 项目架构现状

```
KnowRealm-AI（pnpm workspace + uv 后端，无根 package.json）
├─ apps/desktop/          Tauri 2 + React + TS 桌面端
│  ├─ src/pages/          TanStack Router 文件路由（今日 index、inbox、chat.*、library、
│  │                      onboarding、records.$recordId、settings、spaces.* 课程与测试）
│  ├─ src/features/       14 个功能域（chat/courses/records/search/settings/today/library/
│  │                      recording/audio-import/document-import/text-capture/inbox/
│  │                      quiz-tests/onboarding）
│  ├─ src/styles/         tokens.css(@theme) / theme.css / globals.css / animations.css 分层
│  └─ src-tauri/          Rust 壳：sidecar 拉起、托盘、全局快捷键、数据目录解析（ADR-0013）
├─ backend/               FastAPI sidecar（uv 管理，py312，feature-first 模块化单体 ADR-0015）
│  ├─ app/modules/        22 模块：agent/capture/course/course_brain/data/jobs/knowledge_point/
│  │                      learner/library/learning/llm/profile/quiz/record/review_material/
│  │                      search/settings/source_anchor/summary/today/todo/transcript
│  ├─ app/shared/         deps/errors(带码 HTTPException)/events/prompts/schemas
│  ├─ app/core/           data_dir/logging/loop/version
│  ├─ app/db/             engine/base/migrations（SQL 迁移执行器，PRAGMA user_version 推进）
│  └─ migrations/         0001~0026 手写 SQL，四位编号连续递增不可跳号
├─ packages/api-types/    OpenAPI → TS 类型生成（后端 schema 变更后必须重新 generate）
├─ docs/                  权威文档 + ADR + 评测 + 规则镜像（正本在 .claude/rules/）
└─ .scratch/              工单 tracker（25 个 feature 目录）
```

**LangGraph（后端三图）**：`summary/graph.py`（总结生成）、`review_material/graph.py`（复习资料）、`chat/graph.py`（deepagents `create_deep_agent` 主骨架，ADR-0018：严格空骨架 + `AgentConfig` 轻工厂，tools/subagents/skills/backend/middleware 五扩展点预留）。无独立 agent 服务，「Agent 能力」以工具挂载形式演进（见扩展文档 §40）。

**任务系统**：`modules/jobs` JobRunner——SQLite 单属主任务循环（ADR-0012），ASR/总结/KP/习题/复习/评分/回填等全走此通道；崩溃恢复与幂等由各 worker 自理。

**数据库**：SQLite 单文件（knowrealm.db），唯一事实源；软删（deleted_at）贯穿；写路径搜索索引同事务 upsert。



## 7.  技术债务 / 文档漂移

**技术债务 / 临时实现：**

- **AI 对话右栏「工具状态」其余三开关（knowledgeBase/codeRun/documentParse）与「会话收藏」为图 1 对齐的本地示意状态**（Zustand 内存，不落库、不触发请求）。webSearch 开关已随 B1 接真（按会话记忆，发消息带 `web_search` 标志；无 key 置灰+设置页配置）；范围胶囊与课程/全部资料问答已随 B2 接真（点其它胶囊=新建对应范围会话）。
- **总结侧无长文 map-reduce**（仅 chat 侧有 >30k 降级提示）；`prompt_version` 从未 bump，评测回归机制启用前需补。
- 供应商连通性测试用腾讯 `GetAsrVocabList` 只读接口近似（LLM 测试=真实计费生成，故仅手动）。
- 前端全量测试默认并发时，资源竞争会使不同用例偶发超时（失败文件每轮随机轮换：TodoPanel / CourseBrain 三件套 / chat 均出现过），失败文件单跑均通过；稳定证据口径 = 失败文件单跑全绿 + `npx vitest run <files>` 批跑绿（票 06 门禁实测：全量多轮 473~475/476，失败轮换，单跑批 28/28、44/44 全绿）（本地 `format:check` 会因 `core.autocrlf=true` 的 CRLF 工作区对全库报 warn，CI/LF 检出下正常；验收格式以触及文件为准）。
- 分支未合并堆积：`feat/extend-dev-05` 领先 main 34 提交；本地尚存多个历史 feature 分支（feat/dev-01~04、arch-opt 等）。

**本机环境坑（跑门禁前必读，详见 §9 命令）：**

- 后端 pytest **必须** `--basetemp=.pytest-tmp`（系统临时目录 WinError 5 拒绝访问）。
- 日常开发只跑 `pnpm --filter @knowrealm/desktop tauri dev`（壳自动拉 sidecar）；手动跑后端必须独立 data-dir。壳已用 Windows Job Object（`KILL_ON_JOB_CLOSE`，`sidecar.rs`）托管 sidecar：壳被 Ctrl+C/任务管理器强杀时 sidecar 随句柄关闭自动终止，不再留孤儿进程占数据目录锁。若在旧构建上仍遇到「sidecar health check timed out」+ `DATA_DIRECTORY_IN_USE`，用 taskkill 清理残留 python，查 `logs\backend.log`。

---

## 8. 其他

**常用命令：**

```bash
# 后端（backend/ 下，uv 管理）
uv run pytest --basetemp=.pytest-tmp          # 全量测试（测完删临时目录）
uv run ruff check . && uv run ruff format --check .
uv run pyright                                 # strict
uv run python -m scripts.export_openapi ../packages/api-types/openapi.json --check

# 前端（apps/desktop/ 下）
pnpm test && pnpm lint && pnpm format:check && pnpm build   # build 内嵌类型检查
pnpm --filter @knowrealm/desktop tauri dev     # 完整壳（自动拉后端+ffmpeg 预备）

# 契约生成（后端 schema 变更后）
pnpm --filter @knowrealm/api-types generate
```
