# 04 — RAG Agent 闭环：LibraryRetrievalService 与五档会话

**What to build:** 挂载会话（RECORD / LIBRARY_ITEM / COURSE / ALL）统一经 LibraryRetrievalService 单一 `search_library` 工具多轮检索问答；从资料详情「AI 解读」创建 LIBRARY_ITEM 会话，对该资料及其关联 Record 提问；每条本地引用带逐字摘录并可跳转原文位置；范围内无可引用证据时明确回答「当前资料中未找到」；联网引用与本地引用类型分开；SSE 呈现检索过程；工具预算生效。

**Blocked by:** 02 — Schema、存量回填与基础工作台.

**Status:** done（2026-09-19 实施完毕，剩用户真机验收：资料详情「AI 解读」创建会话提问、引用跳转、失效只读态）

- [x] `LibraryRetrievalService.search(scope, query, filters, limit)`：作用域与软删过滤 → 查询规范化 → Segment FTS 与 CONFIRMED Concept 扩展并行召回 → 去重与确定性排序 → 回业务表取逐字原文与相邻小窗口 → Source Anchor 组装；返回 `evidence_hits` / `asset_matches` / `concept_hints` 三类（仅前者可引用；分数只用于排序）— 落地 `library/retrieval.py`；相邻窗口 = 同宿主 sequence_no±1 分片拼接 ≤400 字符；Source Anchor 不在检索读路径落锚点行（V1 定位走 locator：time/page，citations 的 anchor_id 字段预留）
- [x] 现有 `search_library` 工具改为消费该服务，不再自行拼接 Concept 与分片召回；`search_transcript` 退出模型可见工具面（单记录实现可作迁移期内部复用代码）— 工具文件删除，记录级子串兜底（无分片粘贴/速记）由服务在 RECORD/LIBRARY_ITEM 范围继承；COURSE/ALL 不做兜底（contract §4 冻结）
- [x] LIBRARY_ITEM 第五档会话：仅由资料详情「AI 解读」创建、不进全局范围切换按钮、运行时强制绑定 library_item_id、检索授权=该资料 + 其关联 Record（资料条目关联多个 Record 时仍以 library_item_id 为边界）
- [x] COURSE 作用域含本课程资料与记录（不含未归类全局资料）；ALL 含未归类；chat prompt version bump — v7 `chat-library-scope-v7`
- [x] citations 新增 library 条目；最终引用逐字校验（未删除 Segment/Source Anchor）+ 跳转（Record 引用→转写定位，LibraryItem 引用→来源预览）；禁止引用 FTS token、Embedding、Concept 描述或 AI 摘要 — `{index, source:"library", library_item_id, title, quote}`，前端 library 引用跳转 `/library?sel=<id>&selType=item`
- [x] 挂载范围内无可引用证据时回答「当前资料中未找到」，不得用模型常识补成资料事实；通用知识走 FREE；web 引用独立 citation 类型互不冒充 — 范围指令 + 工具 docstring 双注入；RECORD 单记录解析新增来源标记容错剥离
- [x] 工具预算生效（01 冻结的每轮调用次数/每次命中数/总上下文字符上限）；检索工具体异常 ok=false 不炸整轮流（既有先例）— 每轮 6 次 / 单载荷 4k / 累计 12k 截断并附 truncated 说明
- [x] 每档 scope 至少一个「不越界」失败即红自动化用例（LIBRARY_ITEM/RECORD/COURSE/ALL 四档隔离 + 归档/软删来源不被以资料身份召回）；SSE tool_call/tool_result 过程呈现 — `test_library_retrieval.py` 11 项（四档隔离/归档软删零召回/预算/引用条目/会话守卫）+ test_chat_streaming 既有 SSE 呈现用例随新工具名更新
- [x] 前端：资料详情「AI 解读」入口创建会话、会话范围标识、引用跳转；zh/en 文案同步

## 备注

- 本票与 03 可在 02 后并行（03 提供新语料、04 消费存量与新语料同构的分片索引）。
- 实施要点：`chat_sessions.library_item_id` ORM 补列（0026 已建 DB 列）；`ChatSessionCreate` 校验矩阵扩 LIBRARY_ITEM（其它范围拒绝 library_item_id）；创建守卫 404 `LIBRARY_ITEM_NOT_FOUND` / 409 `LIBRARY_ITEM_ARCHIVED`·`LIBRARY_ITEM_DELETED`，运行时失效 409 `CHAT_LIBRARY_ITEM_UNAVAILABLE`（zh/en 已登记）；`_resolve_agent_config` 收敛为 retrieval×web_search 两轴（MOUNTED 变体删除）；asset_matches V1=LIBRARY_ITEM+RECORD 标题导航命中（type 开放枚举，KNOWLEDGE_POINT 等后续按需）；evidence 的 library_item_id 经 library_item_records 解析代表条目（确定性：sequence_no/创建序首个）。
- 双轴 review（Standards+Spec）修复已落地：① ALL/LIBRARY_ITEM 档文档分片对软删记录泄漏（record 路径 LEFT JOIN 缺 r.id 防线 / 关联子查询缺 records.deleted_at 过滤），SQL 已修并补失败即红（软删记录文档分片在 ALL/COURSE/LIBRARY_ITEM 三档零召回）；② ChatScope 枚举下沉 library/schemas（agent re-export，消模块环 agent↔library，fastapi.md §1）；③ 概念扩展词单次命中上限显式生效（EXPANSION_PER_TERM_LIMIT）；④ AI 解读按钮对 ARCHIVED 条目前端禁用；顺带修 03 已提交 service.py 一处冗余 cast（pyright 门禁阻塞）。langchain-langgraph.md §7「search_transcript 挂载互斥」现状描述已过时（rules 正本不可改，待用户裁定镜像同步）。
- 已知行为变化（冻结契约使然）：COURSE/ALL 不再做 B2 迁移期 transcript LIKE 兜底——无分片粘贴/速记记录在这两档不可检索（`test_search_library_degrades_without_concepts` 断言如实返回未找到）；occurrences（「讲过几次」去重计数）随旧载荷移除，指令改为按 evidence_hits 不同来源计数。
