# OpenMAIC 项目全景功能分析报告

> **分析对象**：[THU-MAIC/OpenMAIC](https://github.com/THU-MAIC/OpenMAIC)（Open Multi-Agent Interactive Classroom，清华大学 MAIC 团队，MIT 协议，JCST'26 论文背书）
> **版本基线**：v1.0.1（2026-09-06 发布）；克隆时点 2026-09-11（最新提交 85ef52d，当日仍在活跃开发）
> **分析方法**：源码级全景分析——浅克隆全仓（2918 文件）+ 三路并行深挖（生成流水线与场景 DSL / 三套 Agent 体系 / 播放编辑导出与基建），结合 README、CHANGELOG、SECURITY.md 与关键源码逐文件核验
> **本文定位**：项目全景报告（定位 / 模块 / 流程 / 功能入口 / 分档），与既有两份文档互补——《OpenMAIC-竞品功能拆解与可借鉴能力分析.md》（v1.0.0 基线，借鉴清单视角）、《OpenMAIC-竞品功能拆解与可借鉴能力分析-chatgpt分析.md》（外部对照）。本文 §9 的借鉴建议已按 KnowRealm-AI 当前进度（2026-09-11）更新。

---

## 1. 执行摘要

OpenMAIC 是一个 **AI 多智能体互动课堂平台**：把任意主题或文档，一键生成"AI 老师 + AI 同学"实时授课的完整课堂——幻灯片、测验、交互式模拟、项目制学习（PBL），配合语音讲解与白板绘图，可随时打断进入实时讨论，可编辑、可导出。

v1.0.0（2026-08-27）是分水岭：在经典"一键生成器"之上新增 **Pro 工作台（Agent Workbench）**——聊天式建课的持久会话 Agent，官方口号从"一键生成课堂"升级为 **"One prompt in, a whole course out — and now you can steer"**。v1.0.1（2026-09-06）为安全加固版（4 个 GHSA 公告修复 + 全环境出口防护）。

三个关键判断：

1. **演进重心已明确转向服务端 durable agent**：v1.0.x 的功能投入几乎全部落在 Pro 工作台一侧（durable 会话、40 个课程工具、23 个技能、素材体系、元素引用），经典路径本版只修了加载性能与播放细节；
2. **工程完成度极高**：DSL 编译期穷尽性检查、确定性判官评测进 CI、无状态编排可水平扩展、降级链设计贯穿全仓、安全纵深（SSRF/重定向逐跳/容器出口封锁 fail-closed）持续加固；
3. **对 KnowRealm 的价值在"LLM 工程化范式"而非产品形态**：课堂演绎（回放/动作/白板/视频导出）是其最重基建，也是与 KnowRealm 学习资产路线最正交的部分，明确不借鉴。

---

## 2. 项目定位与核心目标

| 维度 | 内容 |
|---|---|
| 一句话定位 | 把任何主题或文档，生成"多智能体真人感课堂"，并可持续互动、编辑、导出 |
| 核心命题 | 论文《From MOOC to MAIC》：MOOC 是"看录像"，MAIC 是"有老师同学在场的课" |
| 两条产品主线 | ① 经典路径：输入主题/文档 → 两阶段自动生成整堂课 → 播放（回放态）⇄ 打断进入实时讨论（live 态）；② Pro 工作台：聊天式建课 Agent（持久会话 + 40 工具 + 23 技能），对话中规划、生成、修订整个课程 |
| 技术栈 | Next.js 16 + React 19 + TypeScript 5 + Tailwind 4 + Zustand + Vercel AI SDK + LangGraph JS 1.1（经典编排）+ `@earendil-works/pi-agent-core@0.78.0`（pin 死，Pro/Pi 的 agent 循环底座） |
| 形态 | Web 应用（Vercel 一键部署 / Docker / 纯浏览器零后端可用）；浏览器 IndexedDB 默认持久化，Postgres 与视频渲染均为 opt-in |
| 用户角色 | 学习者（消费生成好的课）；Pro 模式下兼任课程制作者 |
| 版本节奏 | 先播放体验 → 再生成能力 → 再编辑器 → 再存储/导出重型基建 → 最后 agent 化；每一版补 provider 目录与 i18n，安全从第一天持续加固 |

**模型接入面（内置注册表，均支持 custom-* 开放扩展）**：LLM 19 家（OpenAI/Azure/Anthropic/Bedrock/Gemini/GLM/Qwen/DeepSeek/Kimi/MiniMax/豆包/腾讯混元/小米/OpenRouter/Grok/SiliconFlow/AtlasCloud/Ollama/Lemonade）、TTS 10 家、ASR 6 家、图片 8 家、视频 6 家、Web 搜索 9 家（v1.0.1 新增 Exa）。含本地化路径：Lemonade（本地 LLM/TTS/ASR/图片）、FunASR（本地 ASR）、VoxCPM2 / Qwen（音色克隆）、ComfyUI（自托管图片）。

---

## 3. 整体架构与模块地图

```text
┌─────────────────────────── 前端（Next.js App Router）───────────────────────────┐
│ 页面：/(首页生成+Pro入口) /generation-preview(生成流水线) /classroom/[id](课堂)   │
│       /workspace(Pro工作台,三栏) /workbench/new(兼容桥) /eval(评测)              │
│ 组件：slide-renderer(Canvas编辑+10类元素) scene-renderers(quiz/interactive/pbl)  │
│       whiteboard(SVG) chat(圆桌讨论) canvas(播放画布) workbench(工作台全家桶)    │
│ 状态：useStageStore(课程文档) useCanvasStore(画布) useSettingsStore(设置)        │
├─────────────────────────── 核心引擎层（lib/）────────────────────────────────────┤
│ playback/ 四态回放状态机 ←→ action/ 动作执行引擎(21种)                            │
│ chat/agent-loop 客户端驱动讨论循环（前端与 eval 共用纯逻辑）                      │
│ choreography/ 播放时序纯语义层（时序常量/时间轴/语速估算，eslint 强制纯度）        │
│ edit/ 幻灯片操作原语(immer undo/redo)   export/ PPTX/HTML/ZIP/讲稿导出           │
│ video-export/ 课堂→VideoTimeline IR 纯编译器   rag/ 词法检索地基(零消费方,预留)  │
│ orchestration/ LangGraph导演图   chat/pi/ Pi实验路径   agent/ pi运行时共用底座    │
├─────────────────────────── 包契约层（packages/@openmaic/*）────────────────────┤
│ dsl(单一真相源:幻灯10元素/动作21种/4类场景/stage) generation(两阶段流水线         │
│ +13组26个提示词模板,AICallFn模型接缝) renderer editor importer storage           │
│ (KV/Doc/Asset,浏览器与PG双后端)   另有 vendored: mathml2omml / pptxgenjs         │
├─────────────────────────── 服务端（app/api/*，Next Route Handlers）─────────────┤
│ generate-classroom(异步job) generate/*(大纲流式/场景/图/视频/TTS/人设)           │
│ chat(导演图SSE) chat/pi(实验) agent/*(Pro会话/技能/SSE事件流) quiz-grade(判分)    │
│ pbl/v2/* transcription web-search parse-pdf extract-document persistence         │
│ usage(用量聚合) verify-*(连通性测试) skills materials folders stages export-video│
│ ai/llm.ts callLLM/streamLLM 统一入口(usage归账+重试验证+thinking注入+SSRF防护)    │
│ server/model-routes 分阶段模型路由(21阶段键) server/agent-runtime Pro运行时      │
├─────────────────────────── 独立服务/外围 ──────────────────────────────────────┤
│ render-service(Docker: headless Chromium逐帧+FFmpeg→MP4; /render+/preview)       │
│ Postgres栈(opt-in)   skills/agent-runtime(23个教学法技能) skills/openmaic(OpenClaw)│
└────────────────────────────────────────────────────────────────────────────────┘
```

**模块职责与依赖方向**（关键设计：依赖箭头严格单向，dsl 零依赖）：

- `@openmaic/dsl` 是全仓单一真相源：幻灯片 10 种元素、21 种动作（带编译期穷尽性断言——新增动作漏登记直接构建失败）、4 种场景类型（slide/quiz/interactive/pbl）、PBL 项目契约。渲染器、编辑器、导入器、视频导出全部消费同一契约，杜绝三处漂移；
- `@openmaic/generation` 是纯生成包：只提供"契约 + 提示词资产"，模型调用经 `AICallFn` 接缝 `(systemPrompt, userPrompt, images?) => Promise<string>` 由宿主注入——不绑供应商、不读环境、不做存储，可独立测试、跨宿主复用；
- `lib/choreography` 是播放与视频导出共享的时序纯语义层（中文 150ms/字、英文 240ms/词的语速估算等），eslint 强制纯度，防 App 与导出器双实现漂移；
- `lib/agent/runtime`（build-agent、tool-timeout、stream-fn）同时服务 Pi 课堂路径与 Pro runtime，是两套服务端 agent 的合流底座；经典 LangGraph 路径则保持独立（AI SDK 适配桥）。

---

## 4. 功能全景：核心 / 辅助 / 实验性

### 4.1 核心功能（产品主张的直接构成）

#### C1 两阶段课堂生成流水线

| 能力 | 实现要点 |
|---|---|
| 大纲生成 | `outline-generator.ts`：需求 + 文档文本/图片（vision 切片受上限约束）→ 课程标题 + 逐场景大纲（`SceneOutline`：类型/标题/要点/教学目标/时长/序号 + 图片指派 + 媒体占位请求 + quiz/pbl/widget 配置），流式 SSE 增量解析 |
| 生成前可编辑大纲 | 大纲流式返回后可人工修改再进入场景生成（v0.2.2 起）——把人工确认插在成本最低的控制点 |
| 逐场景生成 | `scene-generator.ts`：场景内容 + 授课动作脚本；媒体以占位符异步回填；TTS 串行保跨页讲解连贯（`previousSpeeches`） |
| 大纲质量守卫 | `applyOutlineFallbacks`：交互场景缺配置降级 slide、PBL 缺配置降级 slide、未启用 widget 降级 diagram；语言推断规则写进 system prompt |
| Agent 人设生成 | 3–5 个 `{name, role, persona}`，硬校验恰好 1 个 teacher、≥2 个 agent，失败回退 6 个内置默认人设 |
| 异步生成 job | 202 + jobId → JSON 文件原子写 + `after()` 后台执行 → 轮询 8 步状态链（initializing→researching→generating_outlines→generating_scenes→generating_media→generating_tts→persisting→completed）+ progress 百分比；per-job 互斥锁串行读改写、30 分钟无更新判 stale→failed、每步 5 次指数退避重试 |
| 提示词模板资产 | 13 组 × (system.md + user.md) = 26 个模板文件 + 7 个可复用 snippet（`{{snippet:id}}`）+ 10 个条件键（`{{#if x}}`）；`PromptId` 联合与常量表双向约束；另有 3 个 PBL 规划器模板 |
| 分阶段模型路由 | `MODEL_ROUTES` 单一 JSON 环境变量，**21 个阶段键**（13 基础 + `scene-content:{slide|quiz|interactive|pbl}`、`pbl-v2-runtime:{instructor|open-task|evaluate|simulator}` 8 复合键）；最长前缀回退；路由压倒客户端所传模型/key（防串 key） |

#### C2 四类教学场景（DSL 定义，renderer/editor/importer/video-export 五路共用）

| 场景 | 能力 |
|---|---|
| 幻灯片 slide | 10 种元素（text/image/shape/line/chart/table/latex/video/audio/code）、22 种参数化形状、8 种图表、5 种页面类型、入场/退场/强调动画、讲者备注；生成端修复管线：stripNulls → fail-loud normalize → 图片纵横比校正 → KaTeX 预渲染 → `img_N`/`gen_img_N` 引用解析 |
| 测验 quiz | 单选/多选/简答三题型、难度三档；选项归一化、答案字段名容错；**简答题不存标准答案到前端**；AI 判分（`/api/quiz-grade`）：客观题本地比对，简答题 LLM 契约 `{score, comment}`，解析失败兜底 50% 分数 + 提示参考标准答案，判分阶段可独立路由模型；作答状态持久化 + 课程完成页 |
| 交互模拟 interactive | 6 种 widget（simulation/diagram/code/game/visualization3d/procedural-skill）；**单文件自包含 HTML + iframe srcDoc**；稳定挂载 iframe 池实现场景切换零重载；postMessage 动作协议（SET_WIDGET_STATE/HIGHLIGHT/ANNOTATE/REVEAL）让 AI 教师从 iframe 外驱动页面变成"可授课教具"；`extractInteractiveElements` 解析 HTML 提取真实选择器清单（上限 60/30/30）供 LLM 编排动作引用 |
| 项目制 PBL v2 | 项目 = 7 种角色 + 里程碑（locked/active/completed 状态机）+ 微任务（2–4 个/里程碑，hints 1–3 条）+ 交付物 + 评估；规划提示词定义 5 大失败模式 + 16 条硬规则（**hint 只引导不解答**——"学员能否直接复制进编辑器通过？能就重写"；每任务必须有可判定 done，按收敛型/可评开放型/开放反思型三性分类）；运行时无状态架构（客户端持副本随请求发送，SSE `project_patch` 返回）；Instructor 工具**只有** record_observation 和 adjust_difficulty——不给推进工具防 AI 代做 |

#### C3 多智能体课堂互动（经典路径，详见 §5.1）

AI 教师/助教/学生三角色实时授课与讨论：导演调度、角色长度预算、白板协作、点名、打断恢复。

#### C4 播放与回放引擎

- **四态状态机** `idle → playing ⇄ paused`、`playing/live ⇄ paused`；live⇄回放切换保存/恢复讲课游标；
- 21 种动作按 `(sceneIndex, actionIndex)` 游标逐个执行；`speech` 等音频播完再走下一个（音画同步锚点）；
- 无预生成音频时降级链：浏览器 TTS（按句 chunk 规避 Chrome 15s 截断）→ 阅读计时器（与视频导出共用同一估时函数保证一致）；
- **代数令牌取消**（generation 计数器）让所有过期异步回调幂等失效，替代满天飞的 AbortController；
- **安全跳转分类学**：断点/进度跳转只在"可重建前缀"内允许——白板动作静默重放，视频/讨论/widget 列为 UNSAFE 禁止跳转；
- 讨论动作延时 3s 弹 ProactiveCard、5s 无人交互自动跳过；游标持久化到 localStorage（consumed-discussions 按决策保持易失）；被打断重播一句（`actionIndex-1`）。

#### C5 三层编辑能力

| 层 | 能力 |
|---|---|
| 手动 Canvas 编辑 | 拖拽/八点缩放/旋转/框选多选/对齐参考线/标尺网格/右键菜单/成组/快捷键全家桶；规范操作词汇（slide.update / element.add/delete/reorder/duplicate/align…）经纯几何内核编译；undo/redo 50 步 + IndexedDB 快照；v1.0.1 新增**双击空白处插入文本** |
| Edit with AI（校验式） | Agent 对话内 `patch_stage`：5 种 op（set/remove/str_replace/add_element/delete_element）；**路径白名单**（仅 `/content/`、`/actions/`，越界报可读错误）；str_replace 唯一锚点 + 智能引号/Unicode 归一模糊匹配；整批原子性（任一 op 失败整批拒绝）；**文本改了自动作废旧音频**；read_stage 支持 tree/source/text 三种 detail 与 12000 字符分页；grep_stage 字素簇级搜索（NFKC 折叠） |
| Agent Workbench（Pro） | 聊天式建课：见 §5.2 |

#### C6 五格式导出

| 格式 | 要点 |
|---|---|
| PPTX | 纯浏览器生成（vendored pptxgenjs）；自研 HTML→AST→逐元素转换；**LaTeX→OMML 管线**（temml→MathML→mathml2omml→后处理）——公式是可编辑原生公式而非图片 |
| 交互 HTML | 自包含网页；离线版把 KaTeX/Three.js/Tailwind CDN/字体/图片全部内联为 data: URI |
| 课堂 ZIP | 完整课程结构 + 资产清单 + 媒体，可备份/导入/内网分发 |
| MP4 视频 | 课堂→VideoTimeline IR（多 pass 纯编译器，eslint 强制只依赖 dsl/choreography）→ Hyperframes 工程 ZIP → render-service 独立容器（headless Chromium 逐帧 + FFmpeg；资源画像 standard/low-memory 双档；iptables 出口默认 DROP fail-closed；ZIP 炸弹四限位）；未部署时优雅降级为下载 ZIP 本地渲染；SRT/VTT 字幕可选烧录；v1.0.1 新增 `POST /preview` 单页 PNG 预览端点（独立准入闸 + 429 机读原因） |
| 讲稿 | Markdown / 真 OOXML DOCX |

### 4.2 辅助功能（支撑层）

| 功能 | 要点 |
|---|---|
| Provider 注册表与连通性测试 | 五类 provider 静态注册表（providers.ts 2554 行），逐模型携带 contextWindow/outputWindow/capabilities{streaming/tools/vision/thinking}；`verify-model / verify-image-provider / verify-video-provider / verify-pdf-provider` 四组连通性端点（轻量探测不生成媒体 / LLM 发一句 'Say OK'，错误映射人话） |
| ThinkingConfig 统一抽象 | 把各家心智控制参数归一为 `{mode, enabled, effort, level, budgetTokens}` + requestAdapter 映射 + budget clamp；**兼容网关 reasoning 抢救**：fetch 层把 `reasoning_content` 流改写为 `<think>` 块再拆回一等 reasoning part——任何 OpenAI 兼容网关都获得原生思考面板 |
| 用量归账 | `callLLM/streamLLM` 统一入口（ESLint 元测试强制全部走这两个函数）；按月 JSONL 落盘（kind 五类：llm/image/video/tts/asr）；token 拆 input/output/cacheRead/cacheCreation（+reasoning 仅展示）；**先记账再验证**（失败重试那次也计费）；聚合 API（totals/byModel/byDay/byKind，cache 单列不重复累加）；**只算用量不算成本**；Settings 内用量仪表盘 |
| 文档解析 | MIME 注册表唯一真相源（PDF/Office 全家桶/图片/音视频，防扩展名伪装）；能力模型 `{text/images/tables/formulas/layout/ocr/async}` 按需选 provider（unpdf 本地 / MinerU 自托管与云 / 阿里 DocMind / 纯文本）；统一输出 `DocumentArtifact{blocks(带页码 bbox), assets, citations, diagnostics}` |
| 媒体生成 | 图片 8 / 视频 6 provider；异步任务型统一 submit-poll 驱动器（14 个适配器）；**每课媒体趟次完全串行**（尊重媒体接口并发限制）且不阻塞内容生成主链路；服务端 agent 工具的视频生成为分离式后台作业（poll 预算 15 分钟、字节上限 200MB，完成后经免租约 store 写回 + `media_ready` 事件自愈） |
| TTS/ASR | TTS 10 家含 VoxCPM2/Qwen 音色克隆（三模式：Auto/Prompt/Clone）；每 agent 绑定音色（voiceConfig + 3 层 voiceDesign 描述）；ASR 6 家含本地 FunASR（无 key）；服务端托管凭证不下发浏览器 |
| 持久化双模式 | 默认浏览器：IndexedDB 文档库（写入过 DSL 校验门禁）+ localStorage KV + 存储代际防跨后端分叉；opt-in Postgres：owner 绑定文档存储（claim/墓碑/行锁）、**DB 触发器维护单调修订号**（"写了但未通知"不可表达）、内容寻址资产层（S3 时 302 短命签名 URL，配错降级直出并大声警告）、每 owner 配额与崩溃上传回收 |
| 访问码与安全 | `ACCESS_CODE` HMAC-SHA256 签名 cookie（常量时间比对）；SSRF 全家桶（详见 §4.3 安全行）；技能 zip 解压上限；`import_pptx` 尺寸上限 + 超时 |
| i18n / 暗色模式 | 12 个 locale（v1.0.0 增德语）；i18n key 对齐元测试 |
| 质量与评测 | 660+ vitest 单测（含元测试：LLM 调用只走统一入口 / SSRF / i18n 对齐）；23 个 Playwright E2E；**4 套评测 harness**——编排提示词回归（**确定性判官**：改提示词前后跑 N 采样比较行为指标，无 LLM-as-judge，可进 CI 门槛）、大纲语言一致性、白板布局（截图 + LLM 评分）、PBL 规划器对比 |
| 设置面板 | 11 区：general / token-plan(含用量仪表盘) / providers(模型路由) / agents(人设) / tts / asr / pdf / image / video / web-search / **skills（技能列表/下载/删除/上传）**；v1.0.1 起 TTS 与媒体生成可在设置页直接开启 |

### 4.3 实验性 / 扩展能力

| 能力 | 状态 | 说明 |
|---|---|---|
| **Pi 课堂路径**（`lib/chat/pi/`） | 实验中，feature flag `NEXT_PUBLIC_PI_CHAT_ENABLED` 默认关 | 把经典课堂多智能体链重写为**服务端单 agent 工具调用循环**：一次 POST 携带状态快照，服务端 director-loop 跑完整多轮；导演变成 pi agent + 工具（call_agent/cue_user/close_session/read_scene/web_search/原生动作执行）；预算：每 agent 上限 6 轮、每 agent 8 动作。与 Pro runtime 共享 pi 底座——**经典课堂编排向 pi 迁移的中间试验田** |
| **RAG 词法检索地基**（`lib/rag/`） | 纯地基，**零生产消费方**（唯一下游是测试） | 文档分块（1200 字素簇上限，CJK 友好）→ 摄取建档（四级 lineage 血缘 + resourceVersionId 指纹哈希）→ 进程内词法索引（CJK 逐字 + 拉丁连串 tokenizer，覆盖率打分 + 短语加成）；`vector` 能力位仅在类型上预留（唯一实现 `vector: false`）——为将来 agent 检索工具准备的接缝 |
| **OpenClaw 集成**（IM 内建课） | 已上架 ClawHub | SKILL.md = "轻量路由层 + 确认规则 + 按需加载 SOP"范本：本体只有触发词与 6 阶段 SOP 索引，8 篇 references/*.md 按阶段惰性加载；确认规则写死权限边界（绝不代写 API key、一次只走一个 Phase）；含二开流程（extend） |
| **render-service 预览端点** | v1.0.1 新增 | `POST /preview`：JSON(scene+stage+viewport)→PNG 单页预览，独立准入闸（并发/每用户/JSON 上限/超时），429 机读原因——为 agent 工具 `render_scene_preview` 服务 |
| **Lemonade 本地 AI 路径** | 已支持 | 本地 LLM/TTS/ASR/图片全家桶，无 key 可用 |
| **v1.0.1 安全四公告**（GHSA） | 已修复 | ① 课堂持久化路径逃逸（stage id 白名单补到写路径 + 存储层 resolve 断言）；② slide HTML 白名单消毒（读写双向，KaTeX 独立策略防压平）；③ 出口 URL guard 从仅 production 扩到**全环境全调用点**（配仓库扫描元测试防回退，破坏性变更：开发环境连本地 Ollama 也需 `ALLOW_LOCAL_NETWORKS=true`）；④ 重定向逐跳重校验（manual redirect + 每跳 SSRF 复验，上限 5 跳，**跨 origin 剥凭证头**，所有 provider 含服务端托管统一走它） |

---

## 5. Multi-Agent 能力与协作机制（三套体系）

> 三套体系务必分清（README Project Structure 明文并列），按"无状态 → 实验性服务端化 → 完全 durable 服务端"谱系排列：

| 体系 | 目录 | 用途 | 编排技术 | 状态 |
|---|---|---|---|---|
| ① 课堂多智能体（经典） | `lib/orchestration/` + `lib/chat/` + `app/api/chat/` | 课堂进行时的多角色授课与讨论 | LangGraph 状态机（服务端单拍）+ 客户端串行循环 | 稳定在产 |
| ② Pro 建课 Agent | `lib/agent/` + `lib/server/agent-runtime/` + `app/api/agent/` + `app/workspace/` | 建课时的聊天式规划/生成/修订 | pi-agent-core 持久会话 + 40 工具 + 23 技能 | v1.0.0 落地，演进重心 |
| ③ Pi 课堂实验路径 | `lib/chat/pi/` + `app/api/chat/pi/` | 把①重写为服务端单 agent 工具循环 | pi loop（非 LangGraph） | feature flag，PoC |

### 5.1 经典课堂多智能体（①）

**核心模式：无状态编排，拓扑即上限。**

- 导演图是两节点 LangGraph 图（`START → director → agent_generate → END`），**图内不循环**——每请求只跑"导演决策 → 一人发言"一拍，多 agent 轮次由客户端串行驱动多次请求；`DirectorState{turnCount, agentResponses, whiteboardLedger}` 随请求旅行，服务端零会话状态、可水平扩展；无 maxTurns 魔法数字，轮长由导演语义控制，仅保留"连续 2 次空响应"熔断；
- 导演双策略：单 agent 时纯代码逻辑零 LLM 调用；多 agent 时 LLM 决策 + 代码快速路径（turn 0 直接派发触发 agent）。导演输出仅 `{"next_agent": "<id>"|"USER"|"END"}`；
- **导演规则 13（CRITICAL，学生提问必须被回应）**：看最近一条用户行，若其后没有任何 agent 实质回应，输出必须是 teacher 角色的 agent——不得 USER（点名会让学生面对沉默）、不得 END、不得派学生"换个角度"；"答非所问/我没听懂/我问的是 X 不是 Y"等中文不满信号是硬性重派触发词。其他规则：禁连续同角色、凭已发言预览禁重复解释、白板拥挤不再派画图 agent、白板打开时 spotlight/laser 无效；
- **角色行为约束（长度预算）**：teacher 总语音约 100 字符 / assistant 80 / student 50（1–2 句）——"你的回答若和老师一样长就是错的"，机制上防学生抢戏；
- **Agent 输出协议**：不用 function calling，模型输出 JSON 数组 `[{"type":"action",...},{"type":"text","content":"口语"}]`，动作与语音任意交错；`jsonrepair → partial-json` 增量解析支持边流边执行；**残渣抑制**锚定缓冲区开头检测结构化签名，截断/畸形尾巴宁可吞掉也不漏进聊天气泡（刻意锚定开头，避免误杀正文里提及 JSON 例子的自然语言）；
- **每智能体视角消息重映射**：发给当前 agent 时，同伴历史转 `role:'user'` 加 `[名字]:` 前缀（每个 agent 自视为 assistant），自己的旧回复保留 assistant 当 few-shot；
- **虚拟白板账本（whiteboardLedger）**：按动作重放出白板当前元素摘要（含代码行级 id 与共享行预算），下一个 agent 不看真实 DOM 也知道画布上有什么——多 agent 协作画板的关键；
- **点名（cue_user）**：导演输出 USER → SSE `cue_user` 事件 → 前端居中 "Your turn" 提示，会话保持 active；
- **打断与恢复**：播放中用户发言 → 保存断点（`actionIndex-1`，恢复时重播被打断那句）→ 进 live；服务端打断 = 客户端 abort fetch → `req.signal` 级联取消；
- **防御纵深**：动作白名单双保险——角色级 `ROLE_ACTIONS` + 按当前场景类型二次过滤（非 slide 场景剥掉 spotlight/laser）；导演遇未知 agent id 一律 END。

### 5.2 Pro 建课 Agent / Agent Workbench（②，v1.0.0 重点）

**核心模式：durable agent runtime——日志即真相，SSE 只是尾巴。**

入口门控：`NEXT_PUBLIC_PRO_WORKBENCH_ENABLED` + `OPENMAIC_AGENT_RUNTIME_ENABLED` + `DATABASE_URL`（Pro 的 `maic-agent-driver` 阶段必须显式模型路由，"intentionally no fallback"）。

**持久会话机制**：

- **控制面先落盘**：sessions 路由只写库，请求返回后由后台 worker 认领执行；"A client connection is never part of the execution lifetime"（客户端连接不属于执行生命周期）；
- **SSE 重放**：durable 事件日志是唯一真相，live 流只是它的尾巴；支持 `Last-Event-ID` 重放（重放时修剪中间 token 帧）、`caught_up` 具名事件、LISTEN/NOTIFY 唤醒 + 轮询兜底、25s 心跳；断线 EventSource 自动带 Last-Event-ID 走同一条重放路径；
- **后台 runner**：任何应用进程都可跑扫描循环（1s），PostgreSQL 是 claim/租约/事件序/取消/恢复的唯一权威；心跳 2s、租约 TTL 10s、maxAttempts 5；
- **崩溃恢复**：截断的 transcript 归一为可接续形状；悬空工具调用补"interrupted"结果——**工具执行 at-least-once，因此全系统工具必须幂等**（putScene 按 (stageId, sceneId)、scene id 由 outline 条目派生而非新铸）；
- **claim fence**：存在未回答 `user_question` 的会话不得被认领（ask_user 围栏）；cancel_requested 在 claim 锁下直接 settle，"never resurrect a cancelled session"；
- **取消与超时**：取消只落盘请求（202），租约持有者观察并写终态；每个工具调用竞速硬预算（默认 10 分钟，长工具有 override）+ AbortSignal 级联，超时转结构化错误、会话不死。

**工具清单（40 个唯一名，5 个条件注册）**：

| 分组 | 工具 |
|---|---|
| HITL | `ask_user`（问题先 durable 落盘再终止当前 run；答案就是下一条非空普通用户消息，**刻意无 answer-correlation id**） |
| 检索 | `web_search`、`fetch_url`（每次过 per-session URL trust gate） |
| 技能 | `create_skill`、`read_skill`、`patch_skill`、`read`（pi 原生，限定读已装技能资源） |
| 材料 | `list_materials`、`read_material`、`search_material`、`extract_material`、`wait_for_materials` |
| DSL 读写 | `read_stage`、`patch_stage`（原子补丁）、`grep_stage` |
| 页面生成/导入 | `generate_scene`（v1.0.1 支持传 widgetType/widgetOutline）、`list_scenes`、`generate_actions`、`duplicate_scene`、`import_pptx`、`generate_image`、`generate_video`（v1.0.1 改异步占位 + media_ready 自愈）、`generate_tts`、`edit_deck`、`use_material_media` |
| 课程库 | `create_stage`、`create_folder`、`move_to_folder`、`rename_stage`、`list_folder_stages`、`read_stage_outline` |
| 预览 | `render_scene_preview`（配了 render service 才在） |
| 花名册/音色 | `list_voices`、`set_roster`、`clip_audio`、`register_voice` |
| 个人历史 | `search_classrooms`、`read_classroom`、`search_chats`、`read_chat` |

写者治理：所有文档写工具声明 `executionMode: 'sequential'` 由调度器串行化，防"最后写者静默覆盖"；带 stageId 的工具过 owner 门（owned/foreign/missing/tombstoned）。

**技能系统（23 个教学法技能，三件套）**：

1. **SKILL.md（模型可见方法论）与 outline-constraints.json（机器可查硬约束）刻意分离**——后者 8 字段模式（场景数/类型白名单/typeMix/必需 widget/禁连续同 widget），当前 23 个技能中 9 个带约束文件；
2. **按需加载**：system prompt 只列技能名册，模型用受限 `read` 工具按需读全文；**激活状态就是 transcript 里的 read 记录**（非并行状态机，崩溃后重放日志即恢复）；`readProvesCoverage` 三条件（从头读到尾 + content hash 匹配当前文件）防分页读误判；用户敲 `/handle` 视为必须加载，以三帧合成进持久 transcript；
3. **生成后校验出诊断不改写**——"机械翻转场景类型会像 linter 拼装出来的"，violation 交回 agent 自行决定是否重规划，永不回滚已持久化页面；用户自建技能强制降权前言（防提示注入）。

技能清单：curriculum-planner（系列课规划）、deep-research（深度调研）、deep-interactive（深度交互）、**fact-check（事实核查，v1.0.1 新增**：仅核查 shortlist、首遍 6–8 次 web_search、报告格式 A 明确错误/B 不严谨/C 需核实三分类、与已批准材料冲突时强制 ask_user）、feynman-learning（费曼学习法）、spiral-curriculum（螺旋式）、lecture/workshop/vocational 风格、slide-craft、slide-dsl、stage-design、stage-dsl、pro-editing、pptx-import、page-clone、style-clone、teacher-style-clone、understanding-by-design（UbD）、k12-core-literacy-planning、learning-to-learn（元认知）、social-emotional-learning（SEL）、build-personal-skill（创建个人技能）。

**会话生命周期事件**：session_start / session_resumed / checkpoint / session_end / session_interrupted / user_message（steer 或 queued）/ trace / thinking_end / material_extraction / user_question / stage_link / library_changed / media_ready。

**v1.0.1 新增**：聊天中**引用单个 PPT 元素**（画布套索选中 → 引用 pills 进消息，每消息上限 10 个，hover 联动画布 pin）；**会话标题自动生成**（独立 stage、禁 thinking、64 token、防注入——把用户消息当数据）。

### 5.3 三套体系的演进方向

- Pro 工作台是"经典一键生成器之外的并列层"（README 明示非替代），可随时切回经典模式；
- `lib/agent/runtime/` 底座被 Pi 课堂路径与 Pro runtime 共用，`lib/agent/VENDOR.md` 记录了"需要改 loop 时 vendoring pi-agent-core"的意图——**合流趋势明确**：课堂对话与建课代理终将统一在 pi 服务端 agent 循环上；
- 经典 LangGraph 路径保持独立（AI SDK 适配桥），但 v1.0.x 对它零功能投入——处于维护态。

---

## 6. 核心业务流程

### 6.1 经典生成流（首页 → 课堂）

```text
用户在首页填表：素材文档(多文件,排序冻结) + 主题要求文本 + 联网搜索开关
  + 交互模式开关 + 职业测评开关
    ↓ POST /api/generate-classroom → 202 + jobId（前端跳 /generation-preview）
（可选 web 搜索 + agent 人设生成）
    ↓ ① 大纲生成（单次 LLM，流式 SSE 增量解析）
    ↓ ② 用户可编辑大纲（OutlinesEditor 中途修改/重试）
    ↓ ③ 逐场景生成（内容 + 动作脚本，按场景类型路由模型；
        媒体以占位符异步回填，TTS 串行保跨页衔接）
    ↓ ④ 媒体趟次 + TTS + 持久化（进度 0-100，8 步状态链）
    ↓ 完成后 router.push('/classroom/${stage.id}')
```

### 6.2 播放流（课堂页）

```text
PlaybackEngine 按 (sceneIndex, actionIndex) 游标逐动作执行
  ↓ speech 动作等 TTS/预生成音频播完再走下一个（音画同步锚点）
  ↓ 遇 discussion 动作延时 3s 弹"加入讨论"卡（5s 无人理自动跳过）
  ↓ 游标持久化（localStorage）+ 关闭后窄路径自动续播
```

### 6.3 讨论流（打断进 live）

```text
用户插话/加入讨论 → 保存断点(actionIndex-1) → 进 live 态
  ↓ 客户端循环 POST /api/chat（无状态，directorState 随请求旅行）
  ↓ 服务端 LangGraph 跑"导演决策 → 单 agent 发言"一拍
  ↓ SSE 事件流（agent_start/text_delta/action/cue_user/done）
  ↓ 客户端 StreamBuffer 以打字节奏放文本 + ActionEngine 实时执行白板动作
  ↓ 退出条件：cue_user（交还话筒）/ end / aborted / 连续 2 次空响应熔断
讨论结束 → 恢复讲课游标（重播被打断那句）
```

### 6.4 Pro 建课流（workspace 三栏）

```text
首页 Pro 卡片（ONE composer，提交即建会话）→ /workspace?session=&course=
  ├ 左栏 WorkspaceRail：chat/courses 两 tab 导航树（文件夹容器、拖拽归档/重排）
  ├ 中栏 WorkbenchChat：乐观发送 → agent 流式执行
  │    （时间线折叠工具调用组；ask_user 到达时 composer 变答题表单；双 Esc 停止）
  │    素材回形针上传（durable，会话中途可附加）/ "/" 技能菜单 / "@" 提及课程
  │    v1.0.1：画布套索选元素 → 引用 pills 进消息
  └ 右栏 WorkspaceClassroomPane：内嵌真课堂（与 /classroom/[id] 同组件），
       支持 Pro 内编辑模式、多课程 tab
后台：runner 认领会话 → 工具循环（写工具串行）→ durable 事件日志
       （崩溃恢复/断线 SSE 重放/取消/追问 steering 均基于日志）
```

### 6.5 导出流

讲稿收集 SpeechAction 文本 → Markdown/DOCX；PPTX 纯浏览器端转换；交互 HTML 资产内联；ZIP 打包（资产清单与媒体行同 id）；MP4 走 IR 编译 → render-service（或降级 ZIP 本地渲染）。

---

## 7. 用户功能入口与操作方式

| 入口 | 路由 | 用户能做什么 |
|---|---|---|
| **首页** | `/` | 填生成表单（素材/主题/搜索/交互/职业测评开关）发起经典生成；文件夹分组浏览最近课程（缩略图/搜索/删除确认）；Pro 模式入口卡片（ONE composer）；workspace 恢复链接 |
| **生成预览页** | `/generation-preview` | 观看流水线进度（pdf-analysis → web-search → outline → agent-generation → slide-content → actions + TTS/媒体）；**中途编辑大纲**；前台重试失败步骤；AgentRevealModal 揭示本课人设；完成后自动跳课堂 |
| **课堂页** | `/classroom/[id]` | 播放/暂停/倍速/讲稿逐行跳转（安全前缀内）；打断进入讨论（打字与 AI 角色 multi-agent 对话）；测验作答与判分；交互 widget 探索；白板查看；软关闭倒计时自动续播；导出五格式；进入编辑器 |
| **Pro 工作台** | `/workspace`（`/workbench/new` 为兼容桥） | 聊天式建课全流程（§6.4）：素材上传、技能 `/` 菜单、课程 `@` 提及、元素引用、ask_user 答题、右侧内嵌课堂实时预览编辑、导航树管理 |
| **设置面板** | 全局 Settings（11 区） | 配置五类 provider 与模型路由；人设管理；TTS/ASR/PDF/图片/视频/搜索配置；**技能管理（列表/下载/删除/上传）**；用量仪表盘；通用（语言/主题） |
| **评测页** | `/eval` | 白板布局评测可视化 |
| **OpenClaw** | IM 内（ClawHub 技能） | 对话中完成部署/配置/生成课堂的 6 阶段 SOP |

---

## 8. 值得借鉴的功能设计与产品思路

### 8.1 产品设计

1. **"生成前可编辑大纲"**——人工确认插在大纲与全量生成之间，成本最低的控制点（与 KnowRealm"AI 总结（人工确认）"闭环互为印证）；
2. **教学产品的克制**：PBL 的 hint 只引导不解答（"学员能否直接复制进编辑器通过？能就重写"）+ Instructor 无推进工具防 AI 代做；简答题标准答案不下发前端；
3. **AI 判分的体验兜底**——解析失败兜底给 50% 分 + 提示参考标准答案，而非报错中断；
4. **讨论卡节奏控制**——延时 3s 弹卡、5s 无人理自动跳过，互动不打断不想互动的人；被打断重播一句；
5. **"人味"不是装饰**——学生角色 50 字符短发言防抢戏、导演"规则 13"把"学生提问必须被回应"写成一票否决级规则；
6. **durable 会话的交互语义**——刷新/断线/重启后会话照常（SSE 重放），composer 即答题表单，双 Esc 停止。

### 8.2 技术实现

1. **AICallFn 模型接缝 + 提示词模板资产化**——生成逻辑纯包化，模板是带条件块/片段引用的 markdown 资产，可评审、可 diff、可被 eval 复用；
2. **无状态编排（拓扑即上限）**——LangGraph 图内不循环，状态随请求旅行，服务端零会话状态；轮长由 LLM 语义控制；
3. **JSON 数组输出协议 + 容错解析 + 残渣抑制**——比 function calling 更适合"动作与语音交错"的流式场景；残渣抑制锚定缓冲区开头防误杀；
4. **动作 DSL 单一契约贯穿五条路径**（流式/live、离线回放、视频导出、编辑器、导入器）+ 编译期穷尽性守卫 + choreography 纯度层（eslint 边界强制）防双实现漂移；
5. **durable agent runtime 三原则**——日志即真相（SSE 是尾巴，Last-Event-ID 重放）；客户端连接不属于执行生命周期（后台 runner + 租约）；工具 at-least-once 因此全幂等（确定性 id 派生）；
6. **校验式 AI 编辑**——路径白名单 + 唯一锚点 + schema 校验 + 整批原子 + 旧音频自动作废 + 占位符终检；
7. **技能三件套**——模型可见/机器校验分离；激活即 transcript read（零平行状态机）；诊断不代改；
8. **分阶段模型路由**——一个环境变量、最长前缀回退、路由压倒客户端（连 key 都隔离）、惰性解析（配置错误不拖垮主流程）；
9. **确定性判官的提示词回归评测**进 CI 门槛（无 LLM-as-judge）；
10. **降级链设计哲学**贯穿全仓——媒体生成失败不阻塞、render-service 缺失降 ZIP、Postgres 配错降直出、PBL 规划失败降循环、浏览器 TTS→阅读计时器："配置错误绝不能拖垮主链路"；
11. **安全纵深工程化**——SSRF 含云元数据清单与隧道内嵌 IPv4 展开；重定向逐跳校验 + 跨域剥凭证；guard 全环境化后配**仓库扫描元测试**防回退；渲染容器 iptables fail-closed。

---

## 9. 对 KnowRealm-AI 的可复用与扩展建议

> 按 KnowRealm 当前进度（2026-09-11：F1 Segment+Anchor 已完结，下一步 A3 Evidence Builder + A1/A2 chat 工具层）重新校准。旧报告的 P0 三项中，**判分契约已随 plan 15 交付、用量归账已随 plan 19 交付**，不再列为待办。

### 9.1 可直接采纳（低成本、对现路线有增量）

| # | 借鉴项 | KnowRealm 现状 | 落地建议 |
|---|---|---|---|
| 1 | **防御性 JSON 解析管道**（jsonrepair → stripNulls → fail-loud normalize → 局部降级） | **未引入**（backend 无 json-repair 依赖）——所有 LLM 结构化输出（总结/KP/习题/判分/复习资料）仍暴露在坏输出风险下 | Python 侧引入 `json-repair` 库，在后端 LLM 输出解析层统一封装一次；"丢一个元素降级一页，留着炸整个场景"的哲学写进解析层注释 |
| 2 | **提示词模板资产化**（markdown 模板 + snippet + 条件块） | 场景包机制已计划 prompt 模板资产化（扩展文档 §39.3/§39.6），但后端提示词仍散在 Python 代码里 | OpenMAIC 的 loader 设计（snippets → conditionals → variables 固定顺序、PromptId 联合与目录双向约束）可直接作场景包 prompt 资产的实现范式；B3 Tutor 场景包落地时顺手建 `prompts/` 目录 |
| 3 | **durable 事件日志模式**（日志即真相、SSE 是尾巴、Last-Event-ID 重放、修剪中间 token 帧） | chat SSE 已在产，但断线重放/刷新恢复未做；JobRunner 已有崩溃恢复（不同层面） | 对 A2 工具调用前端呈现顺手可做：SSE 事件带递增 seq，前端持 Last-Event-ID 重连重放——长时 agent 回复刷新不丢 |
| 4 | **元素引用 pills 交互**（套索选元素 → 引用进对话消息，hover 联动） | chat 已有 citations 角标点击跳转（F1 后升级为时间戳/页码定位） | 引用方向已有等价物；可借鉴的是**反向引用**——用户在转写/文档页选中段落作为问题上下文（"就这段问我"），与 B2 跨记录问答天然契合 |

### 9.2 方向性参考（占位不排期，触发条件到了再立项）

| # | 借鉴项 | 与 KnowRealm 的契合点 | 触发条件 |
|---|---|---|---|
| 5 | **校验式 AI 编辑**（patch_stage 范式：路径白名单 + 唯一锚点 + 原子批 + 诊断） | "可编辑可追溯"是核心卖点；AI 优化总结/KP 时局部 Patch 而非整体重写，保留用户未触碰部分 | 复习资料版本链（F 系确认+编辑）之后，若要做"AI 建议差异预览 + 逐项接受"的强版本 |
| 6 | **分阶段模型路由**（供应商内任务槽：总结强模型/判分快模型） | 与 plan 14"单 active 供应商"不冲突（供应商内分槽）；BYO-key 用户的成本/质量平衡 | 用户抱怨总结质量或 token 成本时 |
| 7 | **技能三件套的"机器可查约束 + 诊断不改写"** | 场景包机制（§39.3）已定；OpenMAIC 证明约束文件与 prompt 分离 + 校验出诊断（不代改）是可扩展范式 | 场景包出现第二个以上可配置风格时（与旧报告 P2 #10 一致） |
| 8 | **词法检索地基的 chunk/lineage 设计**（1200 字素簇分块、sha256 确定性 id、四级血缘指纹、CJK 逐字 tokenizer + 覆盖率打分） | F1 document_segments 已做文档分片；未来 B5 sqlite-vec / 全局 RAG 时，lineage 指纹（"同一资源重摄取可判定替换"）与确定性 id 是防索引漂移的关键设计 | B5 触发条件成立时（BM25 真实吃力） |
| 9 | **确定性判官提示词回归**（改 prompt 前后跑 N 采样比较行为指标，无 LLM-as-judge，进 CI） | 工单 20 已建习题 Groundedness 评测与回归触发纪律（prompt_version/模型变更）；OpenMAIC 证明"行为指标差值"可以更便宜 | 核心 prompt（总结/出题）频繁调优且出过回归时 |
| 10 | **双角色学习对话**（长度预算分档 + "学生提问必须被回应"规则） | B3 Tutor 场景包已排队（prompt 模板 + 模式开关先行）；注意 OpenMAIC 双 agent 形态被 KnowRealm 红线 #2 否决，**借鉴的是 prompt 规则层**（角色纪律、回应性硬规则），不是运行时多 agent | B3 实施时作为 prompt 工程素材 |

### 9.3 明确不借鉴（维持既有裁定）

| 能力 | 理由 |
|---|---|
| 回放引擎/动作系统/白板/聚光灯/MP4 导出 | 服务于"AI 授课演绎"形态；重基建（估 5 人月级）与本地优先学习资产路线正交 |
| TTS 音色克隆/多 TTS 矩阵 | 无语音播报需求；闪念速记是录音输入（ASR 已有） |
| 多 provider 接入矩阵（LLM 19 家等） | plan 14 已定"单 active 供应商"；仅将来接新供应商时参考其兼容网关 thinking 注入细节 |
| 三套 Agent 体系并存 / pi 迁移 | 单栈纪律（LangGraph Python）；DeepAgents/multi-agent 已否决（红线 #2） |
| OpenClaw IM 集成、访问码、SSRF 全家桶 | 桌面单机应用无此威胁模型与分发场景 |
| Postgres 持久化栈 | SQLite 唯一事实源已定（#55） |

---

## 10. 附录：OpenMAIC 关键文件索引

| 主题 | 路径 |
|---|---|
| 幻灯/动作/PBL/交互 DSL（单一真相源） | `packages/@openmaic/dsl/src/{slides,action,pbl,interactive,stage}.ts` |
| 两阶段生成流水线 | `packages/@openmaic/generation/src/{outline-generator,scene-generator,scene-builder}.ts` |
| 提示词模板资产 | `packages/@openmaic/generation/templates/`（13 组 26 文件 + 7 snippet）；`prompts-pbl/`（3 个规划器） |
| 导演图（LangGraph） | `lib/orchestration/director-graph.ts`、`lib/prompts/templates/director/system.md`（规则 13） |
| 客户端讨论循环 | `lib/chat/agent-loop.ts`、`lib/chat/summarizers/` |
| Agent 输出协议/残渣抑制 | `lib/orchestration/stateless-generate.ts` |
| Pro 建课 Agent 运行时 | `lib/server/agent-runtime/{runner,resume,skills,dsl-tools,material-tools,generation-tools}.ts` |
| durable 会话存储 | `packages/@openmaic/storage/src/agent-session/pg.ts`（claim fence / 租约） |
| Pro 工作台 UI | `app/workspace/page.tsx`、`components/workbench/workspace/{WorkspaceShell,WorkspaceRail,WorkbenchChat,WorkspaceClassroomPane}.tsx` |
| 校验式编辑 | `lib/server/agent-runtime/dsl-tools.ts`（read/patch/grep_stage）、`course-edit/tools.ts`（edit_deck） |
| 回放引擎/动作引擎/时序 | `lib/playback/{engine,action-navigation,cursor,auto-resume}.ts`、`lib/action/engine.ts`、`lib/choreography/{timing,timeline,cursor}.ts` |
| 编辑器内核 | `packages/@openmaic/editor/src/`（core 纯几何 + react 手势层）、`lib/store/snapshot.ts` |
| LLM 统一入口/路由/thinking | `lib/ai/{llm,providers,thinking-config,reasoning-sse}.ts`、`lib/server/{model-routes,resolve-model}.ts` |
| SSRF/重定向防护 | `lib/server/{ssrf-guard,fetch-with-redirect-validation}.ts` |
| 异步生成 job | `lib/server/{classroom-generation,classroom-job-store}.ts` |
| quiz 判分 | `app/api/quiz-grade/route.ts` |
| 交互 widget 协议 | `packages/@openmaic/generation/templates/*-content/`、`lib/interactive/` |
| RAG 词法检索地基 | `lib/rag/{types,chunking,ingest,providers/in-memory-lexical-index}.ts` |
| 用量归账 | `lib/server/usage-storage.ts`、`lib/usage/normalize.ts`、`app/api/usage/route.ts` |
| 持久化双模式 | `lib/persistence/{server-provider,owner-bound-document-store}.ts`、`packages/@openmaic/storage/src/document/pg.ts` |
| 视频渲染服务 | `render-service/src/{render-coordinator,render-executor,resource-profile,preview-renderer}.ts`、`docker-entrypoint.sh`（出口封锁） |
| 教学法技能 | `skills/agent-runtime/*/`（23 个，9 个带 outline-constraints.json） |
| OpenClaw SOP skill | `skills/openmaic/SKILL.md` + `references/`（8 篇） |
| 评测 harness | `eval/{orchestration,outline-language,whiteboard-layout,pbl-v2-planner}/` |
