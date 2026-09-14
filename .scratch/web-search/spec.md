# B1 Web Search 工具（chat 联网搜索：Tavily + 开关接真 + 网络引用）

Status: ready-for-agent

## Problem Statement

AI 对话完全离线：自由聊天里问时效性问题（最新版本、行业动态、教材外背景）时，模型只有参数知识，会过时甚至编造；挂载会话里用户也常想追问材料之外的补充信息，AI 只能说"不知道"。同时右栏「联网搜索」等工具开关是图 1 对齐的本地示意假状态，拨了也不生效。用户没有任何方式给对话接上外部信息源。

## Solution

1. **chat agent 获得第二个工具 `web_search`**：Tavily 搜索（用户自备免费档 key），薄 SearchProvider 抽象仅落 Tavily 一家实现，预留博查/智谱。
2. **右栏「联网搜索」开关接真**：按轮次生效（发消息带 `web_search` 标志），自由聊天默认开、挂载会话默认关（红线 #11）；开关状态前端本地记忆，不落库。
3. **网络来源进引用**：`citations_json` 条目扩展 `web` 类型（标题 + URL），前端渲染为外链点击打开；转写引用的逐字校验契约不变。
4. **无 key 功能级降级（#38）**：开关置灰提示未配置，聊天照常；后端无视标志强制不挂工具（双保险）。
5. **设置页「服务与用量」新增搜索供应商卡**：key 配置 + 手动连通性测试（真实搜索消耗 1 credit）。

## User Stories

**联网问答**

1. As an 自由聊天用户, I want to 问时效性问题（"X 库最新版本是多少"）时 AI 联网搜索后作答, so that 回答不过时、不编造。
2. As an 挂载会话用户, I want to 打开联网开关后追问材料外的背景（作者生平、术语的业界定义）, so that 材料外的补充也有据可依。
3. As an 挂载会话用户, I want to 默认不联网、AI 优先基于我的材料作答, so that 挂载语义（扎根用户资料）不被稀释。
4. As an 对话用户, I want to AI 在需要时自行决定搜索时机与关键词、可多次搜索, so that 不用我手动替它查。
5. As an 对话用户, I want to 搜索失败时状态卡明确显示失败、回答不中断, so that 网络抖动不毁掉整轮对话。

**开关与降级**

6. As an 对话用户, I want to 右栏「联网搜索」开关真实生效（开=本轮可联网）, so that 我能控制哪轮对话外发查询词。
7. As an 未配置搜索 key 的用户, I want to 开关置灰并提示去设置页配置, so that 我知道为什么用不了而不是以为坏了。
8. As an 未配置搜索 key 的用户, I want to 聊天一切照常, so that 缺 key 只降级搜索、不降级对话（#38）。
9. As an 对话用户, I want to 关闭开关后本轮绝不发起任何外部搜索请求, so that 外发完全受我控制。

**引用与过程透明**

10. As an 对话用户, I want to 网络来源出现在回答引用列表里（标题+外链，点击系统浏览器打开）, so that 网络结论可溯源。
11. As an 对话用户, I want to 消息流内看到「正在搜索网络」状态卡（含搜索词、命中 n 条）, so that 联网过程可见（沿用 A2 检索状态卡形态）。
12. As an 挂载会话用户, I want to 同一回答里转写引用与网络引用并存且各自可点击, so that 本地材料与外部来源一目了然。
13. As an 对话用户, I want to 历史回答的引用列表重开对话依然在, so that 来源记忆不随会话结束丢失。

**设置与隐私**

14. As an 用户, I want to 设置页「服务与用量」配置 Tavily key（保存/清除，模式同 LLM 卡）, so that 与其余供应商管理体验一致。
15. As an 用户, I want to 手动测试搜索连通性（一次极简真实搜索）, so that 配完 key 立刻知道通不通。
16. As an 注重隐私的用户, I want to 设置卡写明「搜索词将发送至 Tavily」, so that 我知情后自愿开启。
17. As an 用户, I want to 界面文案中英同步, so that 语言切换不破功。

**开发者**

18. As an 开发者, I want to 工具进 `AgentConfig.tools`、装配按"自由/挂载 × 开关/无 key"组合, so that ADR-0018 变体机制直接兑现。
19. As an 开发者, I want to SSE `tool_call`/`tool_result` 事件零改动复用（tool 名已通用）, so that A2 协议不破。
20. As an 开发者, I want to 零新依赖（httpx 直连）、零迁移（citations_json 本就是自由 JSON）, so that 变更面最小。
21. As an 开发者, I want to web search 提示注入仅在开关开启时发生且 `CHAT_PROMPT_VERSION` bump, so that 关闭开关时模型可见面与现状严格一致、变更有版本可追。
22. As an 开发者, I want to summary/review 两图零改动, so that 红线 #11（工具仅聊天域）不破。

## Implementation Decisions

**根决策（2026-09-14 grill 十问定稿，用户全按推荐拍板）**

1. **编号 B1**（扩展文档 §40.3；B2=跨记录问答不碰）。范围：只接真 webSearch 一个开关，右栏其余三工具（knowledgeBase/codeRun/documentParse）维持示意态；不做 `search_library`。
2. **SearchProvider = 薄抽象 + 单实现**：统一结果类型的 Protocol 级抽象，仅 Tavily 实现；`providers.json` 新键 `web_search = {provider: "tavily", api_key}`（provider 字段预留，本期只认 tavily）。不做注册表/工厂，博查/智谱真接入时再抽独立模块。
3. **httpx 直连客户端，零新依赖**：Tavily 单端点 REST（POST /search，Bearer key）；**尊重系统代理**（trust_env=True，与 LLM 端点 trust_env=False 的动机不同：Tavily 需外网，国内用户常挂代理）。
4. **开关 = 每请求参数**：发消息 body 加 `web_search: bool`（默认 false 向后兼容）；前端开关状态 Zustand 本地按会话记忆（重启重置），不落库、零新列、零迁移。
5. **默认值矩阵**：自由聊天默认**开**、挂载会话默认**关**（红线 #11 状态语义：自由聊天开放问答联网是本分，挂载先扎根用户材料）。隐私顾虑由「配 key 即显式 opt-in」兜底。
6. **引用契约扩展（零迁移）**：`citations_json` 条目判别化——`record` 条目照旧 `{index, record_id, quote≤80}`（逐字校验不变）；`web` 条目 `{index, source:"web", url, title}`（无 quote，不做逐字校验，仅非空检查）。模型提示约定网络引用行格式 `[n] 标题 — URL`，解析器按行内是否含 URL 分流；`ChatCitationOut` 的 `record_id` 变可空并新增 `source`/`url`/`title`，api-types 重生成。上下文回喂的摘录取用（`_cited_excerpts` 同源逻辑）天然只认 record 条目，web 条目自动排除。
7. **设置端点三件套**（对齐 llm/tencent-asr 卡模式）：GET/PUT `/api/settings/providers/web-search` + POST `/api/settings/providers/web-search/tests`；连通性测试 = 一次真实极简搜索（max_results=1，消耗 1 credit，文案注明）。
8. **不建外部处理同意门**：Tavily 用用户自己的 key，配 key 即显式 opt-in；设置卡描述写明搜索词外发即可（区别于 llm/asr 同意门的"无凭据也外发"场景）。
9. **搜索结果不做快照持久化**：工具结果只活在当轮循环；跨轮/跨会话的"来源记忆"由已落库的回答正文 + 引用条目天然承载。外部正文留存走 P2 网页剪藏、学习痕迹记忆走 §40.2 Memory（偏好沉淀），不在 B1 造快照表。

**工具与装配（agent 模块）**

- `@tool` 定义 `web_search(query: str)`：调 Tavily，返回 top-5 结果（title + url + content 摘要截断约 400 字/条）；请求超时约 10s，失败返回错误 JSON 载荷（模型可据此向用户说明），不炸流。
- 运行期配置（key）经与 `search_transcript` 相同的 ContextVar 绑定模式注入（每轮生成前绑定，无 key 不绑定不挂工具）；`AgentConfig` 工具元组按「挂载 × web_search」组合构造（frozen dataclass 实例化，常量语义维持）。
- 后端读 providers.json：无 key 时**无视请求标志**强制不挂工具（前端置灰之外的双保险）。
- system 提示：仅当本轮 web_search 生效时注入联网指引（何时搜、挂载会话"材料优先、网络补充"语义、网络引用行格式 `[n] 标题 — URL`）；关闭时提示零变化。`CHAT_PROMPT_VERSION` bump v4。
- SSE 事件零改动复用：`tool_call {tool:"web_search", query}` / `tool_result {tool, hits, ok}`（A2 协议 tool 名已通用）。

**前端**

- 开关接真：右栏 webSearch Switch 从示意态改为控制消息请求参数；按会话 id 在 Zustand 记忆，默认值按会话类型（自由 ON / 挂载 OFF）；无 key 时 disabled + tooltip 引导去设置页（可用性经设置端点 GET 获知）。
- 工具状态卡按 tool 名分流文案：`web_search` →「正在搜索网络「query」」/「找到 n 条结果」/ 失败态（沿用 A2 卡形态）。
- 引用列表分流：web 条目渲染外链（Globe 图标 + 标题 + 域名，点击经 opener 插件开系统浏览器）；record 条目照旧跳转写页。
- 设置页「服务与用量」新增搜索供应商卡（模式抄 LLM 卡：key 掩码显示/保存/清除/手动测试 + 状态徽章）。
- zh.json / en.json 同步新增；api-types 重新生成（消息 body 参数 + 引用条目 schema）。

## Testing Decisions

好测试只断言外部行为（SSE 事件序列、落库行、装配面、HTTP 语义），不断言内部结构。全部复用现有 seam，无新 seam：

1. **chat streaming seam**（`test_chat_streaming.py` fake model 工具循环模式）：装配矩阵（自由/挂载 × 开关开/关 × 有/无 key 四维组合的工具可见面）、`web_search` 工具调用进模型上下文、SSE 事件序列不变式维持、混合引用块解析（URL 行 → web 条目不校验、转写行照旧逐字校验、分流后正文剥离正确）、开关关闭时提示与现状逐字一致、prompt_version 断言。
2. **Tavily 客户端 seam**（httpx MockTransport）：正常响应解析、超时、非 200、坏 JSON——四态对外行为（结果载荷/错误载荷）。
3. **settings 端点 seam**（现有 providers 路由测试模式）：GET/PUT 往返与坏值容错、tests 端点成功/失败（mock transport）。
4. **前端 jsdom seam**（现有 chat 19 项模式）：开关状态→请求参数传递、无 key 置灰、web 引用外链渲染与 record 引用分流、工具卡文案、zh/en key 一致。

## Out of Scope

- B2 跨记录/课程级问答、`search_library`、「课程/全部资料」范围胶囊。
- 右栏其余三工具开关接真；工具轨迹持久化。
- 搜索结果快照/记忆持久化（Q10 定稿 A 不做）；网页剪藏；外部处理同意门。
- 博查/智谱实现代码（仅抽象预留）；sqlite-vec（B5）。
- llm_call_logs/用量面板新增搜索维度（Tavily 用量是用户自己的额度，不做本地记账）。

## Further Notes

- 文档收尾随票 02：扩展文档 §40.3 B1 行回写 + §40.4 第 3 步标记完成；数据模型文档就地补 `citations_json` web 条目说明（零表变更不升版，变更记录加行）；CONTEXT.md 视需要补「网络引用」词条；PROJECT_PROGRESS 同步。
- 粒度从简拆两票：01 后端全链（含测试）→ 02 前端接线 + 文档收尾（依赖 01）。
