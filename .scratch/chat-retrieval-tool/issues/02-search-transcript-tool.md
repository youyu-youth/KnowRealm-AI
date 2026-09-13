# 02 — 检索工具与工具循环（search_transcript + SSE 工具事件）

**What to build:** chat 挂载会话获得第一个 Agent 工具：`@tool` 定义 `search_transcript(query)` 调用票 01 的分片索引服务（无分片记录全文子串兜底），挂载形态经 `AgentConfig` 常量实例注入（自由聊天维持空配置，ADR-0018 排除闸门不动）；>30k 降级 system 提示追加工具指引；流式链路从纯文本串改为结构化事件并向 SSE 转发 `tool_call` / `tool_result`；token usage 改累加。`CHAT_PROMPT_VERSION` bump v3。

**Spec 参考:** 同目录 `../spec.md`（工具返回形态、事件载荷、中断语义不变项；实施前先读，票与 spec 不一致时以 spec 为准）。

**Blocked by:** 01

**Status:** done

- [x] `search_transcript` 工具：query → match_expression → 分片索引 FTS（限挂载 record）→ 回表 top-N（约 8）逐字命中 + 时间戳/页码 + sequence_no；分片为空（粘贴/速记）走 transcript 全文内存子串兜底；无命中如实返回；工具描述引导换关键词重试与逐字引用；DB 会话经 session_factory 短事务只读
- [x] `AgentConfig` 挂载变体常量（tools 含 search_transcript），自由聊天维持 `CHAT_AGENT_CONFIG` 空配置；>30k 降级分支追加"细节可用检索工具"指引（≤30k 与自由聊天不加）；`CHAT_PROMPT_VERSION` = chat-mount-cite-v3
- [x] `stream_chat_reply` 产出改结构化流事件；按消息类型分发（AIMessageChunk 文本→token、tool_call_chunks→tool_call、ToolMessage→tool_result）；SSE 序列 status → (tool_call → tool_result)* → token… → citation… → done / error
- [x] 事件载荷：`tool_call`={tool, query}、`tool_result`={tool, hits, ok}；token usage 跨模型调用累加（input/output/total 求和）；中断（GeneratorExit 不落库）、409 在途锁、引用解析与校验全部维持现状
- [x] 测试（test_chat_streaming.py fake model seam）：工具循环端到端——工具被调用且结果进上下文、SSE 事件序列、命中句引用逐字校验通过、>30k 指引注入 / ≤30k 不注入、usage 累加、兜底路径；全套门禁绿

**交付注记（2026-09-13）：**
- 落点：`backend/app/modules/chat/search_tool.py`（`SearchTranscriptContext` 经 ContextVar 每轮绑定 + `@tool search_transcript`：FTS top-8 逐字命中带 time/page + sequence_no；无分片记录经 `SegmentSearchService.record_has_segments` 判定后回退 transcript 全文子串（含跨行查询、400 字窗口），有分片记录 FTS 无命中如实返回；tool 输出为 JSON `{hits, message?}`）；`graph.py`（`MOUNTED_CHAT_AGENT_CONFIG`、`ChatTokenEvent/ChatToolCallEvent/ChatToolResultEvent` 结构化流、usage 累加、`MountedMaterial` 成对挂载参数、>30k 指引、v3）；`message_service.py`（SSE 转发两新事件，正文与引用落库不变）。
- 评审修复：① `AIMessageChunk.tool_calls` 对未闭合 args 做部分解析（实测 1.6.3 把 `{"query": "傅里叶` 报成截断 query）——改为 tool_call_chunks 逐片累加 + 严格 `json.loads`，拼装完整才上报；② `record_id`/`transcript` 数据泥团收拢为 `MountedMaterial` 单一可选参（`SessionPromptContext.mounted`）。
- 测试：`test_chat_streaming.py` +5 项（FTS 命中端到端含引用逐字校验与 usage 累加、分片 args 不截断、无分片兜底、有分片 FTS 无命中不兜底、>30k 指引、工具失败 ok:false），全量 435 绿；`ruff check` / `pyright` strict 0 错误；OpenAPI 无漂移（校验命令相对路径应为 `../packages/api-types/openapi.json`，文档中 `../../` 有误）。
- 遗留（建议 docs 收尾处理）：SSE 新增 `tool_call`/`tool_result` 与 `.claude/rules/fastapi.md` §5 固定事件清单不符（spec 已授权，rules 正本禁改，宜落 ADR 或同步规则）；`ruff format --check .` 在 lock 钉的 ruff 0.16.3 下对 8 个历史文件报格式差异（非本次触及文件）。

