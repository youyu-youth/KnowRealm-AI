# A1+A2 Chat 检索工具（挂载会话段落检索 + 工具调用前端呈现）

Status: ready-for-agent

## Problem Statement

挂载长转写（>30,000 字符）的对话里，AI 只拿到"摘要 + 知识点 + 近三轮引用摘录"的降级材料，被明确告知"缺失细节不可推断"——学习者问"老师讲的那个公式第二步是什么"这类细节问题时，AI 答不出或只能编。AI 是被动的：材料给什么用什么，不会主动去查。同时 AI 的工作过程是黑盒：它有没有查资料、查到了什么，用户完全看不见，回答的可信度无从校验。

## Solution

1. **AI 获得第一个工具（A1）**：挂载会话注入检索工具 `search_transcript`——对挂载记录的句级转写分片 / 文档分片做 FTS5+jieba 检索（BM25 排序），返回逐字原文命中 + 时间戳 / 页码。>30k 降级材料保底不变，模型可主动检索找回细节；命中句逐字可用作引用（现有 citations 契约零改动，角标点击跳句级定位走 F1 已建能力）。
2. **过程透明（A2）**：SSE 流新增 `tool_call` / `tool_result` 事件；消息流内显示"正在检索「关键词」→ 命中 n 条"状态卡，检索过程可见。
3. **索引地基**：分片级 FTS5 索引表（迁移 0020），写路径同事务 upsert、查询期回表过滤软删、启动幂等回填——ADR-0016 全套纪律照搬。

## User Stories

**检索问答（A1）**

1. As an 挂载长转写的对话用户, I want to 问转写深处的细节问题（公式第二步、某个例子的原话）时 AI 主动检索原文作答, so that 超长材料不丢细节、不再收到"缺失细节不可推断"。
2. As an 挂载文档（PDF/DOCX/txt/md）的对话用户, I want to 检索命中落在分片上并带页码, so that 回答能定位到文档的具体位置。
3. As an 挂载粘贴/速记长文本的对话用户（该类记录无分片）, I want to 检索工具退化为全文子串匹配仍能工作, so that 能力不因记录来源而缺失。
4. As an 对话用户, I want to AI 换个关键词就能再次检索, so that 我的问法与转写用词不一致时也有机会命中。
5. As an 对话用户, I want to 检索无命中时 AI 如实说"没查到"而不是编造, so that 回答可信任。
6. As an 挂载短材料（≤30k）的对话用户, I want to 行为与现状一致（全文已在上下文，工具闲置）, so that 本功能对我不产生干扰。

**过程透明（A2）**

7. As an 对话用户, I want to 看到"正在检索「关键词」"的实时状态卡, so that 知道 AI 在查资料而不是卡死。
8. As an 对话用户, I want to 检索完成后状态卡显示"命中 n 条", so that 对回答的证据量有预期。
9. As an 对话用户, I want to 工具失败时状态卡明确显示失败, so that 失败有反馈而不是无声吞掉。
10. As an 对话用户, I want to 多次检索时看到逐条状态卡, so that 多轮检索的过程完整可循。

**引用信任（沿用既有）**

11. As an 对话用户, I want to AI 引用的摘录逐字来自转写原文（≤80 字校验不变）, so that 角标点击总能跳到真实定位。
12. As an 对话用户, I want to 中断/停止后半截回答与工具过程一并不落库, so that 中断语义与现状一致。

**开发者**

13. As an 开发者, I want to 工具直接进 `AgentConfig.tools`（ADR-0018 预留扩展点，空骨架闸门不动）, so that 骨架迁移的投入直接兑现。
14. As an 开发者, I want to 分片索引照 ADR-0016 模式维护（同事务 upsert / 回表过滤 / 幂等回填）, so that 索引一致性纪律一以贯之。
15. As an 开发者, I want to token 用量跨工具循环正确累加, so that 用量统计不因多模型调用而低估。
16. As an 开发者, I want to >30k 提示注入工具指引且 `CHAT_PROMPT_VERSION` bump, so that 行为变更有版本可追。
17. As an 开发者, I want to 新增 UI 文案 zh/en 同步, so that 一致性防线不破。

## Implementation Decisions

**范围根决策（2026-09-13 grill 定稿，九问全收敛）**

1. **仅挂载会话、单工具 `search_transcript`**。全局 `search_library` 不做，留给 B2 连同跨记录引用、范围胶囊接线一起设计。依据两代码事实：SearchService 的 FTS snippet 产自 jieba token 串（非逐字原文），不可能通过引用的逐字校验；全局索引 body 截断在 30,000 字符，覆盖不了 >30k 痛点。扩展文档 §40.2"直接包装 SearchService.search"的设想据此修正为段落级检索（§40.4"Segment 命中"表述一致）。
2. **检索实现 = 分片 FTS5 索引**（用户拍板，检索质量优先）：jieba 分词 body + BM25 排序，FTS 只负责"找到哪个分片"，**引用 quote 从业务表回表取逐字原文**，逐字校验天然成立；无分片记录（粘贴/速记，F1 有意不建分片）在工具内做全文子串匹配兜底（transcript 即事实源），不给文本捕获建分片（不动 F1 语义）。
3. **>30k 降级保底 + 工具指引**：降级材料照给（保底回答质量），挂载 system 提示追加"转写已截断，细节可用检索工具查原文"；不改为"只给摘要全靠工具"。
4. **A2 = `tool_call` / `tool_result` 两事件 + 消息流内 inline 状态卡 + 不持久化**：工具卡与流式文本同生命周期，`done` 后随流式态消失；历史消息仍只有正文 + 引用。右栏四开关假状态本轮不动（B1 web_search 时开关才有真语义）。
5. **验收与顺手修复**：`CHAT_PROMPT_VERSION` v2→v3；token usage 从"最后 chunk 覆盖"改为累加；评测样本集不阻塞本工单。

**数据（迁移 0020，数据模型 v2.4 → v2.5）**

- 新表 `segment_search_index`（FTS5 虚拟表）：`entity_type`（`transcript_segment` / `document_segment` 两值）+ `entity_id` + `body`（jieba tokenize 后的分词串）。照 `search_index` 模式：无 UNIQUE、先删后插同事务幂等、索引是可再生衍生数据（软删不触碰索引行，查询期回表过滤）。分片被物理删除（编辑重切）时同事务清理索引行。
- 与 `search_index` 分表不复用：全局搜索三类资产语义不混入分片命中，`/api/search` 行为零变化。
- 全量 `user_version` 断言测试同步（19→20）；导入归档版本上限走既有动态函数自动生效。

**索引服务（search 模块内扩展）**

- 分片索引表与维护服务归 search 模块（复用 tokenizer 与 upsert 模式；模块定位"唯一搜索入口"延续）；chat 模块的工具调用它（chat→search 单向依赖）。
- 写路径挂点（全部同事务）：finalizer 建转写分片 / 文档分片后；编辑重切（realign）后——同函数已有 `upsert_record_index` 先例；F1 存量回填建分片后。
- 启动幂等回填：main.py 与搜索索引回填、分片回填并列挂载，同容错级（失败记日志不阻断启动）。jieba 切词走线程池（既有 `asyncio.to_thread` 模式），分片粒度切词开销天然小于整篇。

**检索工具（chat 模块）**

- `@tool` 定义 `search_transcript(query: str)`：`match_expression` → FTS 查分片索引（限定挂载 record）→ 回表（限定挂载 record_id、transcript 未软删；文档分片按 record 挂靠路径）→ 返回 top-N（约 8）命中：逐字 content + 时间戳（转写 record_start_ms/record_end_ms，无时间戳则省）/ 页码（文档 page_no）+ sequence_no。
- 分片为空（粘贴/速记）→ transcript 全文内存子串匹配兜底（无时间戳）；无命中如实返回"无命中"。
- 工具描述（中文）引导：用关键词检索转写原文；换关键词重试；引用时逐字使用命中句、≤80 字。
- 形态装配：`AgentConfig` frozen dataclass 增挂载变体常量（含 `tools=(search_transcript,)`），自由聊天维持空配置——遵循 ADR-0018"新变体=新增常量实例"；`DEEPAGENT_TOOL_NAMES` 排除闸门不动。
- 工具获取 DB 会话：经 `session_factory` 短事务只读（与 `_session_context` 同模式），不与流式生成共用会话。

**系统提示与编排**

- >30k 降级分支追加工具指引一行（≤30k 与自由聊天不加）；`CHAT_PROMPT_VERSION` = `chat-mount-cite-v3`。
- `CHAT_RECURSION_LIMIT=25` 维持（每次检索消耗模型+工具两步，上限内多次检索可行）。

**SSE 与流式（A2）**

- `stream_chat_reply` 产出从纯文本串改为结构化流事件（text token / tool_call / tool_result）；`astream` 的 `stream_mode="messages"` 已同时产出 AIMessageChunk（含 tool_call_chunks）与 ToolMessage，按消息类型分发。
- 事件载荷：`tool_call` = `{tool, query}`（工具名 + 检索词）；`tool_result` = `{tool, hits, ok}`（命中数；失败 `ok:false`）。
- SSE 序列：`status → (tool_call → tool_result)* → token… → citation… → done / error`；message_service 转发。
- token usage 累加：多次模型调用的 usage_metadata 求 input/output/total 之和（现有"最后 chunk 覆盖"在工具循环下低估）。
- 中断语义（GeneratorExit 不落库不埋点）、409 在途锁、`ChatStreamRegistry` 全部不变。

**前端**

- SSE 解析（chatSessions）新增 `tool_call` / `tool_result` 分发；`useChatStream` 增工具状态临时态（与 `streamedText` 同生命周期、同清理路径）。
- `ChatMessageList` 消息流内 inline 状态卡：`tool_call` 到达显示"正在检索「query」"（加载态），`tool_result` 替换为"命中 n 条"或失败态；多次检索逐条陈列；`done` / 中断后随流式态消失。右栏上下文面板本轮不动。
- 新 UI 文案 zh.json / en.json 同步新增（key 两侧一致）。
- OpenAPI / api-types 零变化（无新 REST 端点，SSE 事件不进 schema——与 citation 事件同惯例）。

## Testing Decisions

好测试只断言外部行为（事件序列、落库行、检索命中），不断言内部结构。四个 seam 全部复用现有（2026-09-13 用户确认）：

1. **chat streaming seam**（`test_chat_streaming.py` 现有 34 项的 fake model 模式）：驱动完整工具循环——断言工具被调用且结果进模型上下文、SSE 事件序列（status → tool_call → tool_result → token → citation → done）、引用逐字校验通过、>30k 指引注入 / ≤30k 不注入、token usage 累加、中断不落库维持。
2. **search 索引 seam**（`test_search.py` 模式，真 SQLite 内存库）：分片索引同事务 upsert、编辑重切索引同步（命中句保留 / 删除句索引清理）、查询期回表过滤软删、启动幂等回填、粘贴记录兜底路径。
3. **迁移断言**：0020 并入 user_version 顶链与表结构断言。
4. **前端 jsdom seam**（现有 19 项 chat 测试模式）：SSE 解析器对新事件分发、状态卡渲染（正在检索 → 命中 n 条 → done 消失）、zh/en 文案键存在。

## Out of Scope

- 全局 / 跨记录 / 课程级检索与"课程、全部资料"范围胶囊接线（B2）；web_search（B1）；右栏工具开关接真（B1 时一并）。
- 工具轨迹持久化（TOOL 行落库 / assistant 行新列）——升级路径已识别，按需另票。
- 命中邻句窗口合并（可选打磨，检索碎时再议）；sqlite-vec 语义检索（B5 触发条件不变）。
- 检索 groundedness 评测样本集（`docs/evaluation/` 模式另票，不阻塞）。
- 引用契约升级（citations 带时间戳 / 分片 id）——A3 锚点写入者落地时一并。
- 全局搜索（/api/search、命令面板、资产库）任何变化。

## Further Notes

- 扩展设计文档 §40 A 档表 A1 行落地时回写一句：实现形态定为"分片级 FTS 索引 + 挂载内单工具"，与 §40.2 原设想（包装全局 SearchService）的差异及理由（snippet 非逐字 / body 30k 截断两事实）。
- 数据模型文档升 v2.4 → v2.5（新表 `segment_search_index`）。
- A1+A2 同波交付，拆三票：01 索引地基 → 02 工具与流式协议（依赖 01）→ 03 前端呈现与文档收尾（依赖 02）。
