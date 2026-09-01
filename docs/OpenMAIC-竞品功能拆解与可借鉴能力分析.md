# OpenMAIC 竞品功能拆解与可借鉴能力分析

> **分析对象**：[THU-MAIC/OpenMAIC](https://github.com/THU-MAIC/OpenMAIC)（Open Multi-Agent Interactive Classroom）
> **版本基线**：v1.0.0（2026-08-27 发布），克隆时点 2026-08-31，仓库仍高频活跃（当日有新提交）
> **分析方法**：源码级分析（浅克隆全仓 2827 文件 + 四路并行深挖：编排/运行时、生成流水线/场景、回放/互动、基建/外围）
> **写作目的**：为 KnowRealm-AI 的产品设计、Agent 能力建设与技术架构优化提供参考
> **规模速览**：约 2320 个 TS/TSX 文件、51.7 万行；6 个 `@openmaic/*` 工作包子包；26 个提示词模板；660 个单元测试文件 + 23 个 Playwright E2E spec + 4 套评测 harness

---

## 1. 执行摘要

OpenMAIC 是清华大学 MAIC 团队开源的 **AI 多智能体互动课堂平台**（有 JCST'26 论文背书，MIT 协议），能将任意主题或文档一键转化为"AI 老师 + AI 同学"实时授课的完整课堂：幻灯片、测验、交互式模拟、项目制学习（PBL），配合语音讲解与白板绘图。它是目前开源教育 AI 领域工程完成度最高的项目之一。

对 KnowRealm 而言，它的价值不在"做一个课堂产品"（定位完全不同），而在于：

1. **直接可用**：简答题 LLM 判分契约、防御性 JSON 解析管道、用量归账——低成本即可落进模拟测试评分与供应商面板；
2. **方向印证**：它把"生成前可编辑大纲"做成显式阶段，验证了 KnowRealm"AI 总结（人工确认）"闭环的产品正确性；
3. **架构参照**：提示词模板资产化、技能（SKILL.md + 硬约束校验）三件套、分阶段模型路由、校验式 AI 编辑——都是 KnowRealm 后续演进可以直接抄作业的成熟范式；
4. **边界清晰**：课堂回放引擎、视频导出、多 IM 集成等重基建与 KnowRealm 本地优先个人工具定位不符，明确不做。

---

## 2. 项目概览

### 2.1 定位与核心目标

一句话：**把任何主题或文档，一键生成"多智能体真人感课堂"，并可持续互动、编辑、导出。**

- **核心命题**（论文《From MOOC to MAIC》）：用 LLM 驱动的多智能体重塑在线教学——MOOC 是"看录像"，MAIC 是"有老师同学在场的课"。
- **两条产品主线**：
  1. **经典路径**：输入主题/文档 → 两阶段自动生成整堂课 → 播放（回放态）→ 随时打断进入实时讨论（live 态）；
  2. **Pro 工作台（v1.0 新增）**：聊天式建课 Agent（持久会话 + 20+ 工具 + 23 个教学法技能），对话中规划、生成、修订整个课程。

### 2.2 基本信息

| 维度 | 内容 |
|---|---|
| 技术栈 | Next.js 16 + React 19 + TypeScript 5 + Tailwind 4 + Zustand + Vercel AI SDK + **LangGraph JS 1.1**（编排）+ `@earendil-works/pi-agent-core`（Pro 建课 Agent 循环） |
| 形态 | Web 应用（Vercel 一键部署 / Docker / 本地），默认浏览器端持久化（IndexedDB），服务端持久化（Postgres）与视频渲染（独立容器）均为 opt-in |
| 模型接入 | 16 个内置 LLM provider（OpenAI/Azure/Anthropic/Bedrock/Gemini/GLM/Qwen/DeepSeek/Kimi/MiniMax/豆包/腾讯混元/小米/OpenRouter/Ollama/Lemonade）+ 10 个 TTS + 6 个 ASR + 8 个图片 + 6 个视频 + 8 个搜索 |
| 许可 | MIT（v0.3.0 起，原 AGPL-3.0）；`mathml2omml` 子包 LGPL 例外 |
| 团队 | 清华大学 THU-MAIC（论文作者 20+ 人），社区活跃（Discord/飞书群），已上架 ClawHub |

### 2.3 版本演进脉络（产品节奏）

| 版本 | 时间 | 关键增量 |
|---|---|---|
| 0.1.0 | 2026-03 | 首发核心闭环：生成→播放→讨论；OpenClaw IM 集成；建立 Vitest+Playwright |
| 0.2.0 | 2026-04 | **深度交互模式**（3D/仿真/游戏/图解/在线编程 5 种交互场景）；白板代码元素 |
| 0.2.2 | 2026-06 | **MAIC Editor v0**（手动编辑幻灯片）；**生成前可编辑大纲**；离线资源包 |
| 0.3.0 | 2026-06 | **AGPL→MIT**；PBL v2；`@openmaic/*` SDK 上 npm；**分阶段模型路由**；职业任务引擎 |
| 0.3.1 | 2026-07 | **MP4 视频导出**；服务端存储契约；编辑器直接操纵（拖/缩/旋/多选）；**校验式 JSON Patch 编辑** |
| 0.3.2 | 2026-08 | 服务端持久化收尾（一键 Postgres 栈）；`@openmaic/generation` 包化；技能上 ClawHub |
| **1.0.0** | 2026-08-27 | **Agent Workbench（聊天式建课）**、**持久化 Agent Runtime**（会话跨重启/事件回放）、技能系统 |

演进规律很有参考性：**先播放体验 → 再生成能力 → 再编辑器 → 再存储/导出等重型基建 → 最后 agent 化**。每一版都在补 provider 目录与 i18n，安全（SSRF/出口封锁）从第一天起持续加固。

### 2.4 应用场景

- 零基础快速入门（"30 分钟学会 Python"）；论文/新技术解析；分析类话题（配 web 搜索）；桌游等兴趣学习；K12/职业/大师课/工作坊等教学法（技能系统覆盖）；内网离线课堂（导出 ZIP 全资源内联）。

---

## 3. 整体架构与模块关系

### 3.1 架构分层

```
┌─────────────────────────── 前端（Next.js App Router）───────────────────────────┐
│ 页面：首页(生成入口) / classroom/[id](课堂) / workbench(Pro建课) / eval          │
│ 组件：slide-renderer(Canvas编辑器+9类元素渲染) scene-renderers(quiz/interactive/ │
│       pbl) whiteboard(SVG) chat(圆桌讨论) agent(头像/配置) settings(服务商面板)   │
│ 状态：useStageStore(课程文档) useCanvasStore(画布+特效) useSettingsStore(设置)    │
├────────────────────────── 核心引擎层（lib/）────────────────────────────────────┤
│ playback/ 回放状态机(idle→playing→paused→live) ←→ action/ 动作引擎(21种动作)     │
│ chat/agent-loop 客户端驱动讨论循环（前端与 eval 共用的纯逻辑）                    │
│ choreography/ 编舞规范层(时序常量/时间轴/动画描述符, eslint 强制纯度)              │
│ edit/ 幻灯片操作原语(immer undo/redo) export/ PPTX/HTML/ZIP 导出                 │
│ video-export/ 课堂→VideoTimeline IR 纯编译器                                    │
├────────────────────────── 包契约层（packages/@openmaic/*）──────────────────────┤
│ dsl(单一真相源:幻灯片10元素/动作21种/quiz/interactive/pbl) generation(两阶段流水线 │
│ +26个提示词模板,AICallFn模型接缝) renderer editor importer storage(KV/Doc/Asset) │
├────────────────────────── 服务端（app/api/*, Next Route Handlers）──────────────┤
│ generate-classroom(异步job) generate/*(大纲流式/场景) chat(导演图SSE) agent/*(Pro)│
│ quiz-grade pbl/v2/* transcription web-search parse-pdf persistence usage …      │
│ ai/llm.ts callLLM/streamLLM 统一入口(usage归账+重试验证+thinking注入)             │
│ server/model-routes 分阶段模型路由   server/agent-runtime Pro建课运行时           │
├────────────────────────── 独立服务/外围 ────────────────────────────────────────┤
│ render-service(Docker: headless Chromium 逐帧+FFmpeg→MP4)  Postgres栈(opt-in)    │
│ skills/openmaic(OpenClaw SOP) skills/agent-runtime(23个教学法技能)               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 三套 Agent 体系辨析（易混点，务必分清）

| 体系 | 目录 | 用途 | 编排技术 |
|---|---|---|---|
| ① 课堂多智能体（经典） | `lib/orchestration/` + `lib/chat/agent-loop.ts` + `app/api/chat/` | AI 教师/同学授课与讨论 | LangGraph 状态机（服务端单轮）+ 客户端串行循环 |
| ② Pro 建课 Agent | `lib/agent/`(pi harness) + `lib/server/agent-runtime/` + `app/api/agent/*` | 聊天式规划/生成/修订课程 | pi agent 持久会话 + 20+ 显式工具 + 技能系统 |
| ③ Pi 课堂实验路径 | `lib/chat/pi/` + `app/api/chat/pi/` | 把①重写为服务端单 agent 工具调用循环（PoC，feature flag） | pi loop，非 LangGraph |

另注：`lib/choreography/` 名字像"课堂编排"，实际是**播放时间轴/视频导出共享的纯语义层**（时长常量、语速估算、动画描述符），与 Agent 无关。

### 3.3 三条关键数据流

1. **生成流**：主题/文档 →（可选 web 搜索 + agent 人设生成）→ **大纲生成**（单次 LLM 调用，流式增量解析 SSE）→ 用户可编辑大纲 → **逐场景生成**（内容 + 授课动作脚本，媒体以占位符异步回填，TTS 串行保跨页衔接）→ 完整课堂（stage + scenes）。
2. **播放流**：`PlaybackEngine` 按 `(sceneIndex, actionIndex)` 游标逐动作执行 → `speech` 动作等 TTS 播完再走下一个（音画同步锚点）→ 遇 `discussion` 动作延时 3s 弹"加入讨论"卡。
3. **讨论流**：用户插话/加入讨论 → 客户端循环 POST `/api/chat`（无状态，`directorState` 随请求旅行）→ 服务端 LangGraph 跑"导演决策→单 agent 发言"一拍 → SSE 事件流（agent_start/text_delta/action/cue_user/done）→ 客户端 `StreamBuffer` 以打字节奏放文本、`ActionEngine` 实时执行白板动作。

---

## 4. 功能清单全拆解

> 本章为功能全集清单，标注实现位置（相对 OpenMAIC 仓库根目录）。

### 4.1 课堂生成

| 功能 | 实现要点 |
|---|---|
| 两阶段流水线 | `packages/@openmaic/generation/`：大纲生成（`outline-generator.ts`）→ 逐场景内容+动作（`scene-generator.ts`，1910 行核心）。包只提供"契约+提示词资产"，经 `AICallFn` 接缝注入模型调用，不绑供应商、不做存储——生成逻辑可独立测试、跨宿主复用 |
| 提示词模板资产化 | 26 个模板 = 13 组 `templates/<id>/{system,user}.md`，支持 `{{#if xxx}}` 条件块与 `{{snippet:xxx}}` 片段引用（如图片/视频指令、媒体安全准则按开关注入） |
| 输入形态 | 自由文本需求、文档（文本截断 5 万字符上限 + 最多 20 张图走多模态视觉，其余降级文本描述、按 visionPriority 排序）、可选 web 搜索上下文、教师人设上下文 |
| 大纲 Schema | `SceneOutline`：`type(slide/quiz/interactive/pbl)` + `title/description/keyPoints[]/teachingObjective/estimatedDuration/order` + `suggestedImageIds`（指派文档图片）+ `mediaGenerations[]`（图片/视频占位请求）+ `quizConfig`（题数/难度/题型）+ `pblConfig` + `widgetType/widgetOutline`（按交互类型携带结构化子大纲） |
| 大纲质量守卫 | `applyOutlineFallbacks`：交互场景缺配置→降级 slide；PBL 缺配置→降级 slide；未启用的 widget 类型→降级 diagram。语言推断规则写进 system prompt（外语课用母语教、跨语言文档以需求语言为准） |
| 生成前可编辑大纲 | v0.2.2 起，大纲流式返回后可人工修改再进入场景生成 |
| Agent 人设生成 | `generateAgentProfiles()`：教学设计专家提示词产出 3-5 个 `{name, role, persona}`，**硬校验恰好 1 个 teacher、≥2 个 agent**，失败回退 6 个内置默认人设 |
| 异步生成 job | `POST /api/generate-classroom` → 202 + jobId → JSON 文件原子写 + `after()` 后台执行 → 轮询返回 `status(queued/running/succeeded/failed)` + `step(initializing→researching→generating_outlines→generating_scenes→generating_media→generating_tts→persisting→completed)` + progress 0-100。可靠性：per-job 互斥锁串行读改写、30 分钟无更新判 stale→failed（进程重启可恢复）、每步 `withGenerationRetry`（5 次指数退避 1s→16s） |
| 流水线并发 | 内容 fetch 限并发预热但**按序消费**；actions+TTS 严格串行以维护 `previousSpeeches`（跨页讲解连贯）；媒体生成完全不阻塞主链路 |
| 分阶段模型路由 | `MODEL_ROUTES` 环境变量（JSON），20 个可路由阶段（`scene-content:quiz` 等复合键），最长前缀匹配回退；路由压倒客户端所传模型/key（防止串 key），惰性解析（路由配置错误不拖垮主流程） |

### 4.2 四类场景

**① 幻灯片（slide）** — `packages/@openmaic/dsl/src/slides.ts`

- **10 种元素**：text（HTML 富文本/竖排/行高字距）、image（滤镜/裁剪/羽化/色罩）、shape（20 种参数化形状公式，缩放重算 SVG path）、line（实/虚/点线+箭头+折线+贝塞尔曲线）、chart（8 种图型，`{labels, legends, series}` 三字段极简数据）、table（colspan/rowspan/四边独立边框）、latex（生成时 KaTeX 服务端预渲染成 html）、video、audio、code（语法高亮+每行稳定 id）。
- 页面级：`viewportSize:1000, ratio:0.5625`（16:9）、主题、背景、入场/退场/强调动画、`type: cover|contents|transition|content|end`、讲者备注 script。
- 生成端修复管线：`stripNulls`（null 视缺省）→ `normalizeElement`（fail-loud，畸形元素丢弃）→ 图片按真实宽高校正纵横比 → KaTeX 渲染 → `img_N` 引用解析、`gen_img_N` 占位保留异步回填。

**② 测验（quiz）**

- 题型：单选/多选/简答，难度三档，题量题型由大纲 `quizConfig` 控制。
- 生成归一化：选项字符串/对象统一 `{value:'A', label}`；答案字段名容错（answer/correctAnswer/correct_answer）；简答题**不存标准答案到前端**（`hasAnswer:false`）。
- **AI 判分**（`app/api/quiz-grade/route.ts`）：客观题本地比对；简答题走 LLM，契约 `{score: 0..points 整数, comment}`，**解析失败兜底给 50% 分数**+提示参考标准答案，score clamp；`quiz-grade` 阶段可独立路由模型（重活用好模型）。
- 作答状态持久化 + 课程完成页（v0.2.1）。

**③ 交互式模拟（interactive）** — 深度交互模式

- 6 种 widget：`simulation`（模拟实验）/ `diagram`（流程图/思维导图/层级图/系统图）/ `code`（在线编程）/ `game`（知识游戏）/ `visualization3d`（Three.js 3D）/ `procedural-skill`（职业技能流程训练）。
- 形态：**单文件自包含 HTML**，前端 `iframe srcDoc` 渲染；稳定挂载的 iframe 池（`interactive-iframe-pool.ts`）实现场景切换零重载、状态保留。
- **postMessage 动作协议**：HTML 必须实现 `SET_WIDGET_STATE / HIGHLIGHT_ELEMENT / ANNOTATE_ELEMENT / REVEAL_ELEMENT` 监听——AI 教师的授课动作（`widget_setState/widget_highlight/widget_annotation/widget_reveal`）可从 iframe 外驱动页面，把静态生成物变成"可授课的教具"。
- 配置块协议：HTML 内嵌 `<script type="application/json" id="widget-config">`，生成后抽出存档。
- 动作编排闭环：`extractInteractiveElements()` 解析 HTML 提取**真实选择器清单**（过滤 Tailwind 工具类，上限 60/30/30），让 LLM 编排动作时引用真实存在的元素而非凭空猜。
- 公式支持：post-processor 把 `$$..$$/$..$` 规范化后注入 KaTeX CDN + auto-render + MutationObserver 防抖重渲染。

**④ 项目制学习（PBL v2）** — `packages/@openmaic/dsl/src/pbl.ts` + `lib/pbl/v2/`

- 结构：项目 = 角色 + 里程碑 + 微任务 + 交付物 + 评估 + 会话线程。
- 角色类型：`user/instructor/evaluator/mentor/collaborator/simulator/system`；设计期产出 1 个 Instructor（命名须带"教练/导师"词根）；角色扮演型另有场景人物卡（persona/situation/boundaries/openingLine）。
- 里程碑：`locked/active/completed` 状态机（首 active 余 locked）；每里程碑 2-4 个微任务（hints 1-3 条）、briefing 开场、**completionCriteria 完成判据**、debrief 收尾、核心概念触发逆向提问。
- 规划提示词的硬规则（`prompts-pbl/planner-single-call-system.md`）：定义 5 大失败模式（答案泄漏/工作表碎片化/假交付物/无判据完成态/引用不存在资源）+ 16 条硬规则——**hint 只引导不解答**（"学员能否直接复制进编辑器通过？能就重写"）；每任务必须有可判定 done，按三性分类（收敛型/可评开放型/开放反思型）；按水平分层。
- 运行时（无状态架构）：客户端持有 project 副本随请求发送，服务端变异后以 SSE `project_patch` 返回；Instructor 工具**只有** `record_observation` 和 `adjust_difficulty`——**不给推进工具**，任务完成只能走右侧提交面板（防 AI 代做）；Evaluator 三模式（任务反馈/里程碑反思/最终 `stars` 总结）独立 SSE；失败降级链：单次调用规划器 → agentic 循环规划器（供应商错误时跳过）。

### 4.3 多智能体互动

| 功能 | 实现 |
|---|---|
| 角色与人设 | 三种角色 `teacher/assistant/student`，动作权限映射 `ROLE_ACTIONS`（教师独占 spotlight/laser/play_video）；6 个内置人设：AI 老师、AI 助教、显眼包（谐星）、好奇宝宝（追问）、笔记员（总结）、思考者（唱反调）；生成式人设按课程挂载、不跨课堂泄漏。`AgentConfig{id,role,persona,avatar,color,allowedActions,priority(导演权重1-10),voiceConfig(音色绑定)}` |
| 角色行为约束 | 提示词长度预算分档：教师 100 字符/助教 80/学生 50——"你的回答若和老师一样长就是错的"，机制上防学生抢戏 |
| 导演图 | `lib/orchestration/director-graph.ts`：LangGraph 状态图 `START→director→(agent_generate)→END`，**图内不循环**——每请求只跑"决策→一人发言"一拍，多 agent 轮次由客户端串行驱动，`directorState{turnCount, agentResponses, whiteboardLedger}` 随请求旅行，服务端零会话状态可水平扩展。"拓扑即上限"，无 maxTurns 魔法数字 |
| 导演调度规则 | `lib/prompts/templates/director/system.md`：教师通常先答；发起者先说→教师引导→学生补充；禁连续同角色；凭"已发言预览"禁重复解释；**白板状态感知**（元素>5 派 agent 整理）；**规则 13（CRITICAL）**：学生提问未被实质回答时必须派教师、禁止用 cue_user 把沉默甩回用户、"答非所问/没听懂"是硬性重派触发词 |
| 轮次终止 | 客户端循环（`lib/chat/agent-loop.ts`，纯逻辑可被 eval 复用）退出条件：cue_user（交还话筒）/ end / aborted / **连续 2 次空响应熔断** / 流断开 |
| 点名机制 | 导演输出 `{"next_agent":"USER"}` → SSE `cue_user{fromAgentId, prompt?}` → 前端居中"Your turn"提示，会话保持 active |
| 打断 | 播放中用户发言 → 保存断点（**`actionIndex-1`，恢复时重播被打断那句**）→ 进 live → 讨论结束自动恢复讲课游标；软关闭倒计时 + 满足条件自动续课 |
| Agent 输出协议 | **不用 function calling**，模型输出 JSON 数组 `[{"type":"action",...},{"type":"text","content":"口语"}]`，动作与语音任意交错；`jsonrepair→partial-json` 增量解析支持边流边执行；**残渣抑制**：截断/畸形结构化输出一律吞掉，绝不漏进聊天气泡 |
| 每智能体视角消息重映射 | 发给当前 agent 时，其他 agent 历史转 `role:'user'` 加 `[名字]:` 前缀（每个 agent 自视为 assistant、同伴为用户），自己的旧回复保留 assistant 当 few-shot |
| 虚拟白板账本 | `whiteboardLedger` 按动作重放出白板当前元素摘要（含代码行级 id 与共享行预算），下一个 agent 不看真实 DOM 也知道画布上有什么，实现多 agent 协作画板 |
| live 白板并发控制 | 每个写工具必须回传 `expectedLastSeq` 版本号，与服务端版本比对，冲突报错让模型重读——乐观并发防覆盖 |
| 防御纵深 | 动作白名单双保险：角色级 `ROLE_ACTIONS` + 按当前场景类型二次过滤（非 slide 场景剥掉 spotlight/laser）；导演遇未知 agent id 一律 END |

### 4.4 播放与回放引擎

- **四态状态机**（`lib/playback/engine.ts`）：`idle → playing ⇄ paused`，`playing/live ⇄ paused`；live↔回放切换保存/恢复讲课游标。
- **21 种动作**（`packages/@openmaic/dsl/src/action.ts`，README 的"28+"是历史口径）：fire-and-forget 2 种（`spotlight` 聚光灯、`laser` 激光笔，5s 自动清除）+ 同步 19 种（`speech` 讲解、`play_video`、白板 12 种 `wb_open/wb_draw_text/wb_draw_shape/wb_draw_chart/wb_draw_latex/wb_draw_table/wb_draw_line/wb_draw_code/wb_edit_code/wb_clear/wb_delete/wb_close`、`discussion`、widget 4 种）。DSL 里有**编译期穷尽性检查**——新增动作漏登记直接编译失败。
- **音画同步**：`speech` 等音频播完再走下一动作；无预生成音频时降级链：浏览器 TTS（按句 chunk 规避 Chrome 15s 截断 bug）→ 阅读计时器（CJK 150ms/字、英文 240ms/词，与视频导出共用同一估时函数保证一致）。
- **代数令牌取消**：`playbackGeneration` 令牌让所有过期异步回调幂等失效，替代满天飞的 AbortController。
- **安全跳转分类学**：断点/进度跳转只在"可重建前缀"内允许——白板动作可 `silent:true` 静默重放，视频/讨论/widget 列为 UNSAFE 禁止跳转。
- 讨论动作：延时 3s 弹 ProactiveCard，5s 无人交互自动跳过（常量由 `lib/choreography/timing.ts` 统一供给 UI 倒计时与时间轴，防漂移）。

### 4.5 编辑器（三层编辑能力）

| 层 | 能力 |
|---|---|
| 手动 Canvas 编辑 | 拖拽/八点缩放/旋转/框选多选/对齐线/标尺/网格/右键菜单/拖画插入；9 类元素渲染器（Prosemirror 富文本、ECharts 图表、KaTeX 公式、SVG 形状描线动画…）；操作原语层 `lib/edit/slide-ops.ts`（immer，undo/redo 50 步）+ 渲染器整帧快照 diff 回规范 ops（保证撤销/持久化/PPTX 往返一致） |
| Edit with AI | **校验式编辑而非改黑盒**（`lib/server/agent-runtime/dsl-tools.ts`）：`set/remove`（JSON Pointer 路径白名单：仅 `/content/`、`/actions/`，越界报可读错误）+ `str_replace`（唯一锚点精确替换，内置智能引号/Unicode 归一模糊匹配）+ `add_element/delete_element`（逐字段 schema 校验）；**文本改了自动作废旧音频**（clearStaleSpeechAudio）防止播旧配音 |
| Agent Workbench（Pro） | 聊天式建课：持久会话（控制面先落盘再执行，崩溃零丢失；SSE 是 durable log 的尾巴，`Last-Event-ID` 重放恢复）+ 20+ 显式工具（read_stage/patch_stage/generate_scene/set_roster…）+ 23 个技能 + `ask_user` 极简 HITL（终止当前 run，答案即下一条普通消息，"故意不做关联 ID"） |

### 4.6 技能系统（23 个教学法技能）— `skills/agent-runtime/`

架构三件套：

1. **SKILL.md**（模型可见：name/description + 正文方法论）与 **outline-constraints.json**（机器可查硬约束：场景数、类型白名单、typeMix 比例、必需 widget、禁连续同 widget）刻意分离；
2. **按需加载**：system prompt 只列技能清单，模型用受限 `read` 工具（realpath 校验，限制在技能目录内）按需读全文；"成功 read"即激活记录，写入 durable transcript（崩溃后重放日志恢复，零平行状态机）；`sourceHash` 三条件判定防重复注入；
3. **生成后校验**：对照 constraints 产出**诊断而不改写**（"机械翻转场景类型会像 linter 拼装出来的"），violation 交回 agent 自行决定重规划；用户自建技能强制包降权前言（防提示注入）。

技能清单（23 个）：课堂设计（基线）、系列课规划、深度交互、深度调研、事实核查、**费曼学习法**、K12 核心素养、学会学习（元认知）、大师讲授、互动工作坊、职业实训、螺旋式课程（Bruner）、理解本位设计 UbD、社会情感学习 SEL、名师风格克隆（从录像/讲义提炼）、名师版式克隆、PPTX 导入、页面克隆、专业编辑、页面设计法则（slide-craft）、幻灯 DSL 手册（slide-dsl）、课堂文档结构（stage-dsl）、创建个人技能。

### 4.7 导出

| 格式 | 实现要点 |
|---|---|
| PPTX | 纯浏览器生成（vendored pptxgenjs）；自研 HTML 解析器→AST→逐元素转换；**LaTeX→OMML 管线**（temml→MathML→mathml2omml→PPTX 后处理：注 Cambria Math 字体、清 DOCX-only xmlns）——公式是可编辑原生公式而非图片 |
| 交互 HTML | 自包含网页；离线版把 KaTeX/Three.js/Tailwind CDN/Google Fonts/图片全部内联为 data: URI，导出即完全离线可播 |
| 课堂 ZIP | 完整课程结构+媒体，可备份/导入/内网分发 |
| MP4 视频 | 课堂→`VideoTimeline` IR（纯编译器多 pass，eslint 强制只依赖 DSL/choreography/zod）→ Hyperframes 工程 ZIP → render-service（独立容器：headless Chromium 逐帧捕获+FFmpeg 编码；BeginFrame 比截图快 43%；ZIP 炸弹四限位防护；iptables fail-closed 出口封锁；资源画像超配即启动失败）→ MP4。**未部署 render-service 时优雅降级为下载 ZIP 本地渲染**；SRT/VTT 字幕可选烧录 |
| 讲稿 | Markdown/DOCX 导出 |

### 4.8 语音（TTS/ASR）

- TTS 10 个内置 provider：OpenAI/Azure/GLM/Qwen/**VoxCPM2（自托管音色克隆：Auto/Prompt/Clone 三模式，Clone 音频存 IndexedDB 每次合成上传）**/豆包/ElevenLabs/MiniMax/Lemonade（本地）/浏览器原生；每 agent 绑定音色（voiceConfig + 3 层 voiceDesign 描述）。
- ASR 6 个：OpenAI Whisper/浏览器原生/Qwen/**FunASR（本地，SenseVoice/Paraformer/Fun-ASR-Nano，无需 key）**/Lemonade/Azure。
- 安全与归账：服务端托管凭证不下发浏览器；`isServerProviderDisabled` 强制 403；自定义 baseUrl 过 SSRF 校验（含 DNS rebinding，`redirect:'manual'` 防重定向绕过）。

### 4.9 媒体生成与文档解析

- 图片 8 provider（Seedream/GPT-Image/Qwen/Nano Banana/MiniMax/Grok/ComfyUI/Lemonade）、视频 6 provider（Seedance/Kling/Veo/MiniMax/Grok/HappyHorse），异步任务型统一 submit-poll 驱动器；前端编排器串行调 API（尊重媒体接口并发限制）不阻塞内容生成。
- 文档解析（`lib/document/`）：MIME 注册表唯一真相源（PDF/Office 全家桶/图片/音视频，防扩展名伪装）；**能力模型** `DocumentExtractorCapabilities{text/images/tables/formulas/layout/ocr/async}` 按需选 provider（unpdf 本地/MinerU 自托管与云/阿里 DocMind/纯文本）；输出统一 `DocumentArtifact{blocks(带页码 bbox), assets, citations, diagnostics}`；音视频走 ffmpeg/ASR 抽取路径。

### 4.10 模型接入与用量

- 16 provider 静态注册表（`lib/ai/providers.ts`，2400 行），每模型携带 `contextWindow/outputWindow/capabilities{streaming/tools/vision/thinking}`。
- **ThinkingConfig 统一抽象**：把 8 家各异的心智控制参数（`reasoning_effort`/`thinking:{type}`/`enable_thinking`+`thinking_budget`…）归一为能力描述（`control: 'effort'|'level'|'toggle'|…` + requestAdapter + effortValues + budgetRange），元数据守卫防注册表漂移；兼容网关两条注入通道（原生 SDK 走 providerOptions / 网关走 fetch body 改写，AsyncLocalStorage 跨层传递）。
- **兼容网关 reasoning 抢救**：fetch 层把 `reasoning_content` 流改写为 `<think>` 块再拆回一等 reasoning part——任何 OpenAI 兼容网关都获得原生思考面板体验。
- 统一入口 `callLLM/streamLLM`（ESLint 元测试强制全部走这两个函数）：usage 归账（**先记账再验证**，失败重试那次也计费）、验证失败重试与网络重试分离、阶段标签日志分组。
- 用量仪表盘：按月 JSONL 落盘，按模型/天/模态聚合，token 拆 input/output/cacheRead/cacheCreation，**只算用量不算成本**。

### 4.11 持久化与部署

- 客户端优先：IndexedDB（Dexie：课堂文档/媒体/音频）+ localStorage（设置/provider 配置）；存储代际（storage-generation）防跨后端分叉；文档锁串行变更。
- 服务端 opt-in：`docker compose --profile server-persistence` 一条命令起 Postgres 16 栈；owner 绑定文档存储；**内容寻址资产层**（Postgres 列或 S3，字节 GET 可 302 短时签名 URL，配置错误降级直出并大声警告——绝不拖垮主链路）。
- 部署形态：Vercel 一键 / Docker 多阶段（国内镜像构建参数）/ Compose 三 profile 组合（主应用 / +render-service / +Postgres）/ 纯浏览器零后端可用。
- 站点访问码：`ACCESS_CODE` 常时比较 + httpOnly cookie，保护共享部署。

### 4.12 质量与评测体系

- 660 个 vitest 单元测试（含**元测试**：`lint-llm-entry-guard` 强制 LLM 调用只走统一入口；SSRF 安全测试；i18n key 对齐检查）。
- 23 个 Playwright E2E（完整用户旅程 + issue 号回归）。
- **4 套评测 harness**：编排提示词回归（**确定性判官**：pre-fix vs post-fix 双提示词构建比较 END 率差值，无 LLM-as-judge，可进 CI 门槛）/ 大纲语言一致性 / 白板布局（Playwright 截图 + LLM 评分，记录总分 5.4→6.1）/ PBL 规划器对比（HTML 可视化报告）。
- i18n：12 个 locale；暗色模式。

### 4.13 OpenClaw 集成（IM 内生成课堂）

`skills/openmaic/SKILL.md` 是"**轻量路由层 + 确认规则 + 按需加载 SOP**"的范本：SKILL.md 本体只有触发词与规则（约 100 行），SOP 按阶段拆到 `references/*.md` 按需加载；确认规则把权限边界写死（绝不代写 API key、绝不引导往聊天里贴 key、一次只走一个 Phase、发现已有本地状态先展示再问）；同时反向平衡——设置完成后用户明确要生成时不许二次确认。

---

## 5. 特色设计亮点提炼

### 5.1 产品设计层面

1. **"生成前可编辑大纲"**——把人工确认插在大纲与全量生成之间，成本最低的控制点；
2. **多智能体课堂的"人味"设计**——谐星/好奇宝宝/思考者等人设不是装饰：学生角色强制 50 字符短发言防抢戏；导演"规则 13"把"学生提问必须被回应"写成一票否决级规则；
3. **讨论卡（ProactiveCard）的节奏控制**——讲解中延时 3s 弹卡、5s 无人理自动跳过，互动不打断不想互动的人；
4. **被打断重播一句**（actionIndex-1）+ 输入即"声音冻结、缓冲继续"的 Level-1 暂停——对话体验的细节打磨；
5. **hint 只引导不解答**（PBL）+ **Instructor 无推进工具**（防 AI 代做）——教学产品的克制；
6. **解析失败兜底 50% 分数**——AI 判分失败的体验兜底而非报错中断。

### 5.2 交互设计层面

1. 生成进度可视化：大纲流式逐条出现（增量 JSON 解析）→ 逐场景生成进度 → 媒体占位骨架屏异步回填；
2. 白板元素入场交错动画、清空级联飞出、代码打字动画——"AI 在讲课"的感知营造；
3. cue_user 居中"该你了"提示；课程完成页 + 作答状态持久化。

### 5.3 技术实现层面

1. **`AICallFn` 模型接缝 + 提示词模板资产化**：生成逻辑纯包化，模板是带条件块/片段引用的 markdown 资产——可测试、可复用、可独立演进；
2. **无状态编排（拓扑即上限）**：LangGraph 图内不循环，状态随请求旅行，服务端零会话状态；轮长由 LLM 导演语义控制，仅保留"连续 2 次空响应"熔断；
3. **JSON 数组输出协议 + jsonrepair/partial-json 容错解析 + 残渣抑制**：比 function calling 更适合"动作与语音交错"的流式场景；
4. **动作 DSL 单一契约贯穿三条路径**（流式/live、离线回放、视频导出）+ 编译期穷尽性守卫 + choreography 纯度层（eslint 边界强制）防双实现漂移；
5. **技能三件套**（SKILL.md / outline-constraints.json / 生成后校验出诊断不改写）+ "激活即 transcript read"的零状态恢复；
6. **校验式 AI 编辑**：路径白名单 + 唯一锚点 + schema 校验 + 旧音频自动作废；
7. **分阶段模型路由**：一个环境变量、最长前缀回退、路由压倒客户端（连 key 都隔离）；
8. **ThinkingConfig 统一抽象**与兼容网关 reasoning 抢救；
9. **确定性判官的提示词回归评测**进 CI 门槛；
10. **降级链设计哲学**贯穿全仓：媒体生成失败不阻塞、render-service 缺失降 ZIP、Postgres 配错降直出、PBL 规划失败降循环——"配置错误绝不能拖垮主链路"。

---

## 6. 与 KnowRealm-AI 的对照分析

### 6.1 定位差异

| 维度 | OpenMAIC | KnowRealm-AI |
|---|---|---|
| 形态 | Web 平台（Vercel/Docker 部署，多租户倾向） | Tauri 2 桌面应用 + FastAPI sidecar，本地优先、零部署、无登录 |
| 核心闭环 | 主题/文档 → 生成课堂 → 播放/互动 | 捕获（录音/导入/粘贴/速记）→ ASR → AI 总结（人工确认）→ 知识点/习题/Todo → AI 问答 |
| 用户角色 | 学习者（被动接收生成好的课） | 学习者（**自己资产的主人**：可编辑、可追溯学习资产） |
| AI 形态 | 多智能体课堂（教师+同学演绎） | 单 agent 任务链（总结/出题/判分/问答），LangGraph Python |
| 数据 | 浏览器 IndexedDB 默认 / Postgres opt-in | SQLite 唯一事实源 |
| 内容形态 | 幻灯片/交互 HTML/课堂视频 | 总结/知识点/习题/复习资料 |

**关键判断**：两者在"内容生成流水线、LLM 工程化、AI 编辑"上高度同构，在"课堂演绎（回放/动作/白板/语音合成）"上正交。后者是 OpenMAIC 最重的基建，也是 KnowRealm **最不应该抄**的部分。

### 6.2 明确不建议借鉴的部分

| 能力 | 不借鉴理由 |
|---|---|
| 回放引擎/动作系统/白板/聚光灯 | 服务于"AI 授课演绎"形态；KnowRealm 无课堂场景，重基建（估 5 人月级）与定位不符 |
| MP4 视频导出 + render-service | 同上；KnowRealm 导出方向是 PDF（候选库 fpdf2），非视频 |
| TTS 音色克隆/多 TTS provider 矩阵 | KnowRealm 无语音播报需求；闪念速记是录音输入（ASR 已有） |
| OpenClaw IM 集成 | 面向多平台分发的增长手段，桌面单机应用无此场景 |
| 多 provider 接入矩阵（16 家） | KnowRealm plan 14 已定"单 active 供应商"决策，供应商体系按自己的票走；仅在将来接入新供应商时可参考其兼容网关 thinking 注入细节 |
| 三套 Agent 体系并存 | OpenMAIC 自己也在过渡（LangGraph→Pi 实验路径）；KnowRealm 后端 LangGraph 单栈即可，无需多运行时 |

### 6.3 可借鉴能力清单（按优先级）

> 优先级综合"应用价值 × 实现难度 × 与当前路线契合度"。P0 = 现有票内即可落地；P1 = 下一两个迭代值得排票；P2 = 长线方向，先立决策不急实现。

#### P0（低成本、直接可用）

| # | 借鉴项 | 应用价值 | 难度 | 落地建议 |
|---|---|---|---|---|
| 1 | **简答题 LLM 判分契约**（`app/api/quiz-grade`） | 正对模拟测试 04 评分结果页：`{score:0..points 整数, comment}` 严格 JSON 契约、clamp 边界、**解析失败兜底给 50% 分+提示参考标准答案**（体验兜底而非报错）、判分阶段可独立配模型 | 低 | 15 计划评分 job（LangGraph）内实现；把"兜底 50%"写进评分 prompt 工单的边界条款 |
| 2 | **防御性 JSON 解析管道**（jsonrepair → stripNulls → fail-loud normalize → 局部降级） | KnowRealm 所有 LLM 结构化输出（总结/KP/习题/判分）都受益：坏输出不再炸整个任务，"丢一个元素降级一页，留着炸整个场景"的哲学 | 低 | Python 侧引入 `json-repair` 库；在后端 LLM 输出解析层统一封装一次 |
| 3 | **Usage 用量归账**（按月 JSONL、token 拆分、只算用量不算成本） | 桌面端用户自带 key，供应商面板显示"本月已用多少 token"是低成本高感知功能 | 低 | SQLite 起一张 usage 表（或复用现有 job 记录），供应商设置页加聚合视图 |
| 4 | **LCO 佐证**：生成前可编辑大纲 | 印证 KnowRealm"AI 总结（人工确认）"闭环的正确性；OpenMAIC 同样发现全量生成后返工成本高，把确认点上移到大纲层 | — | 无需开发；总结结构（章节/要点先行确认）已符合此模式，可放心坚持 |

#### P1（方向契合、中等成本）

| # | 借鉴项 | 应用价值 | 难度 | 落地建议 |
|---|---|---|---|---|
| 5 | **提示词模板资产化**（markdown 模板 + `{{#if}}` 条件块 + `{{snippet:}}` 片段引用） | KnowRealm 后端提示词若散在 Python 代码里，随提示词膨胀会难维护；模板文件化后可评审、可 diff、可被 eval 复用 | 低-中 | 后端建 `prompts/` 目录 + 一个极简模板组装函数；先迁移总结/出题两个高频 prompt |
| 6 | **分阶段模型路由**（stage 键 + 最长前缀回退 + 服务端配置压倒客户端默认） | 与 plan 14"单 active 供应商"不冲突——是**供应商内的模型分槽**：总结用强模型、判分/改写用快模型，成本与质量兼得 | 中 | 供应商配置加"任务槽位→模型"映射；先只开 总结/判分 两个槽位验证 |
| 7 | **知识点交互可视化**（单文件 HTML widget：思维导图/模拟/流程图 + iframe srcDoc + `<script id="widget-config">` 配置块 + postMessage 动作协议） | KnowRealm"个人学习大脑"方向的内容形态升级：KP 不只是文字卡片，可生成可探索的思维导图/模拟；Tauri WebView 对 iframe srcDoc 支持良好 | 中-高 | 先做一个 widget 类型（diagram-思维导图）试点：后端 LangGraph 出单文件 HTML + 配置块，前端 iframe 渲染；postMessage 动作协议可后置 |
| 8 | **校验式 AI 编辑**（路径白名单 JSON Patch + str_replace 唯一锚点 + 改动作废旧产物） | KnowRealm 核心卖点是"可编辑可追溯"；AI 优化总结/KP 时**局部 Patch 而非整体重写**，保留用户未触碰部分、可审查可拒绝 | 中-高 | 后端先做"AI 建议差异预览（diff 视图）+ 用户逐项接受"的弱版本；Patch 协议作为其强版本演进 |
| 9 | **hint 纪律与任务三性分类**（PBL 规划规则：hint 只引导不解答；任务分收敛型/可评开放型/开放反思型） | 习题生成的区分度：KnowRealm 习题目前偏客观题，简答/开放题引入"可判定 done"分类能提升判分与复习价值 | 低-中 | 写进出题 prompt 的约束段；配合 #2 的解析管道 |

#### P2（长线方向，先立决策）

| # | 借鉴项 | 应用价值 | 难度 | 备注 |
|---|---|---|---|---|
| 10 | **技能三件套**（SKILL.md 方法论 + 机器可查硬约束 + 生成后校验出诊断不改写） | 若 KnowRealm 将来支持"自定义总结/出题风格"（如费曼式、应试式），这套"模型可见/机器校验分离 + 诊断不代改"是最成熟的范式 | 中-高 | 触发条件：出现第二个以上可配置的生成风格需求 |
| 11 | **双角色学习对话**（轻量版导演：讲解者+追问者双 agent，长度预算分档、"学生提问必须被回应"规则） | AI 问答从"单轮答疑"升级为"苏格拉底式对话"，是差异化体验点 | 高 | 需要产品决策（问答是否引入第二角色）；后端 LangGraph 已具备多节点能力，主要是 prompt 工程与流式协议工作量 |
| 12 | **提示词回归评测**（确定性判官：改提示词前后跑 N 采样比较行为指标，进 CI） | KnowRealm 提示词迭代目前无量化护栏；OpenMAIC 证明"确定性判官 + 差值门槛"可以很便宜 | 中 | 触发条件：某个核心 prompt（如总结）频繁调优且出过回归 |
| 13 | **文档解析能力模型**（`{text/images/tables/formulas/layout/ocr/async}` 能力位 + 按 MIME 与能力选 extractor + 统一 Artifact 输出） | 捕获模块导入格式的扩展框架：新增解析器（如 MinerU 类）时按能力位路由而非 if-else 堆叠 | 低-中 | 触发条件：捕获导入需要表格/公式级解析时 |
| 14 | **里程碑式学习**（locked/active/completed 里程碑 + 微任务 + 完成判据） | "个人学习大脑"的复习计划可升级为目标导向的学习路径 | 高 | 远期；与 fsrs 复习调度路线图（未来候选库）合并考虑 |

### 6.4 推荐落地节奏

1. **本迭代（模拟测试 04 评分结果页）**：直接吸收 #1 判分契约与 #2 解析管道——不新增票，作为 04 工单的实现细节写入。
2. **下一迭代**：#3 用量归账（小票）；#5 提示词模板资产化（重构票，顺手做）；#6 模型槽位路由（需先与 plan 14 供应商决策对表）。
3. **立决策不排期**：#7 交互可视化与 #8 校验式编辑分别对应"内容形态升级"与"资产编辑体验"两个产品方向，建议先在需求基线里占位（决策表条目），触发条件到了再立项。
4. **持续留意**：OpenMAIC 更新很勤（当日仍有提交），其 `@openmaic/generation` 包与技能系统值得隔季度回看一次 CHANGELOG。

---

## 7. 附录：OpenMAIC 关键文件索引

| 主题 | 路径 |
|---|---|
| 幻灯片/动作/PBL DSL（单一真相源） | `packages/@openmaic/dsl/src/{slides,action,pbl,interactive,stage}.ts` |
| 两阶段生成流水线 | `packages/@openmaic/generation/src/{outline-generator,scene-generator,scene-builder}.ts` |
| 提示词模板资产 | `packages/@openmaic/generation/templates/`（13 组）、`prompts-pbl/` |
| 导演图（LangGraph） | `lib/orchestration/director-graph.ts`、`lib/prompts/templates/director/system.md` |
| 客户端讨论循环 | `lib/chat/agent-loop.ts`、`lib/chat/summarizers/{message-converter,peer-context,whiteboard-ledger}.ts` |
| 回放引擎/动作引擎 | `lib/playback/engine.ts`、`lib/action/engine.ts`、`lib/choreography/timing.ts` |
| Pro 建课 Agent 运行时 | `lib/server/agent-runtime/{skills,dsl-tools,roster-tools}.ts` |
| 校验式编辑 | `lib/server/agent-runtime/course-edit/`、`lib/edit/slide-ops.ts` |
| LLM 统一入口/路由 | `lib/ai/llm.ts`、`lib/ai/providers.ts`、`lib/ai/model-metadata.ts`、`lib/server/model-routes.ts` |
| 异步生成 job | `lib/server/classroom-generation.ts`、`lib/server/classroom-job-store.ts` |
| quiz 判分 | `app/api/quiz-grade/route.ts` |
| 交互 widget 协议 | `packages/@openmaic/generation/templates/{simulation,diagram,code,game,visualization3d,procedural-skill}-content/`、`lib/interactive/logical-viewport.ts` |
| PPTX 公式导出 | `lib/export/latex-to-omml.ts`、`packages/mathml2omml/` |
| 视频渲染服务 | `render-service/src/{render-coordinator,render-executor,resource-profile}.ts` |
| 教学法技能 | `skills/agent-runtime/*/SKILL.md` |
| OpenClaw SOP skill | `skills/openmaic/SKILL.md` + `references/` |
| 评测 harness | `eval/{orchestration,outline-language,whiteboard-layout,pbl-v2-planner}/` |
