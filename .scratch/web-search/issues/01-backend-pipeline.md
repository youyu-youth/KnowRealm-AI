# 01 — B1 后端全链：Tavily 供应商 + web_search 工具 + 网络引用 + 设置端点

**What to build:** 用户在 providers.json 配好 Tavily key 后，带 `web_search=true` 发消息，chat agent 获得联网搜索工具：模型自行决定搜索时机与关键词，SSE 沿用 `tool_call`/`tool_result` 事件呈现过程；网络来源以 `web` 类型条目落进 `citations_json`（标题+URL，不逐字校验），与转写引用并存分流；无 key 时后端无视标志强制不挂工具（聊天照常）。设置域新增 web-search 供应商读写与手动连通性测试端点。全程零新依赖、零迁移。

**Blocked by:** None — can start immediately.

**Status:** done

- [x] providers.json 新键 `web_search = {provider:"tavily", api_key}` 读写函数（模式对齐 llm/tencent_asr：允许空 key 保存、clear 语义、坏值容错）
- [x] 薄 SearchProvider 抽象（统一结果类型）+ 仅 Tavily 实现：httpx 直连 POST /search、Bearer key、**trust_env=True**（尊重系统代理）、约 10s 超时
- [x] 设置端点三件套：GET/PUT `/api/settings/providers/web-search`、POST `/api/settings/providers/web-search/tests`（测试=一次 max_results=1 真实搜索）
- [x] `web_search(query)` @tool：top-5 结果（title+url+content 摘要截断约 400 字/条）；失败返回错误 JSON 载荷（模型可据此说明），不炸流；key 经 ContextVar 每轮绑定（模式同 search_transcript）
- [x] 装配矩阵：挂载 × `web_search` 标志 × 有/无 key——无 key 时无视标志不挂工具；四种组合的工具可见面有测试断言
- [x] 发消息 body 增 `web_search: bool = false`（向后兼容），标志随受理链路流到装配层
- [x] system 提示仅在本轮 web_search 生效时注入联网指引（何时搜、挂载会话"材料优先网络补充"、网络引用行格式 `[n] 标题 — URL`）；关闭时提示与现状逐字一致；`CHAT_PROMPT_VERSION` bump v4
- [x] 引用解析分流：行内含 URL → web 条目 `{index, source:"web", url, title}`（非空检查，不逐字校验）；无 URL 行照旧转写逐字校验路径；混合引用块剥离正确
- [x] `ChatCitationOut` 扩展：`record_id` 可空 + `source`/`url`/`title` 可选；上下文回喂摘录自动排除 web 条目
- [x] SSE 事件序列不变式维持（status → tool_call → tool_result → token… → citation… → done），中断/在途锁语义不变
- [x] 测试全过（streaming seam 装配矩阵与事件序列、citations 纯函数混合解析、Tavily 客户端 MockTransport 四态、设置端点）
- [x] 门禁：pytest（--basetemp=.pytest-tmp）/ ruff / pyright 全绿；openapi 重新 generate 并随票提交
- [x] 提交 `feat(backend): 实现 chat 联网搜索工具与网络引用契约（B1 票 01）`

**用户真机验收（不代勾）：** 配置真实 Tavily key → 设置页测试按钮通 → 自由聊天问时效性问题命中联网回答与外链引用。

## 完结备注（2026-09-14）

- 落点：`search/web_search.py`（SearchProvider Protocol + WebSearchHit/WebSearchError 抽象）+ `search/integrations/tavily.py`（TavilySearchClient，规则要求供应商集成落 integrations/ 子包）+ `agent/tools/web_search.py`（@tool + ContextVar）+ `settings/config.py` 读写函数 + `settings` 端点三件套 + agent 域标志链路/提示注入/引用分流。
- 失败态契约：web_search 失败返回错误 JSON 载荷（`{hits:[], ok:false, message}`），`_tool_result_event` 增读载荷 `ok` 键（search_transcript 无该键行为不变），SSE 事件 schema 零变更。
- 引用契约：`citations_json` 条目按 `source` 判别；record 条目落库时显式写 `source:"record"`（解析/历史/SSE 三处形状一致；历史无 source 行按默认 record 读取，逐字校验不变）；三个新错误码已登记 `docs/后端错误码清单.md`。
- 审查遗留（有意保留，供后续票参考）：自由聊天联网解析引用块属 spec 隐含扩展（story 10/13 必需）；trust_env=True 与 rules fastapi.md §4 字面冲突为 spec 根决策 3 用户拍板（动机不同：外网直连需代理），未落 ADR。
