# 04 — RAG Agent 闭环：LibraryRetrievalService 与五档会话

**What to build:** 挂载会话（RECORD / LIBRARY_ITEM / COURSE / ALL）统一经 LibraryRetrievalService 单一 `search_library` 工具多轮检索问答；从资料详情「AI 解读」创建 LIBRARY_ITEM 会话，对该资料及其关联 Record 提问；每条本地引用带逐字摘录并可跳转原文位置；范围内无可引用证据时明确回答「当前资料中未找到」；联网引用与本地引用类型分开；SSE 呈现检索过程；工具预算生效。

**Blocked by:** 02 — Schema、存量回填与基础工作台.

**Status:** ready-for-agent

- [ ] `LibraryRetrievalService.search(scope, query, filters, limit)`：作用域与软删过滤 → 查询规范化 → Segment FTS 与 CONFIRMED Concept 扩展并行召回 → 去重与确定性排序 → 回业务表取逐字原文与相邻小窗口 → Source Anchor 组装；返回 `evidence_hits` / `asset_matches` / `concept_hints` 三类（仅前者可引用；分数只用于排序）
- [ ] 现有 `search_library` 工具改为消费该服务，不再自行拼接 Concept 与分片召回；`search_transcript` 退出模型可见工具面（单记录实现可作迁移期内部复用代码）
- [ ] LIBRARY_ITEM 第五档会话：仅由资料详情「AI 解读」创建、不进全局范围切换按钮、运行时强制绑定 library_item_id、检索授权=该资料 + 其关联 Record（资料条目关联多个 Record 时仍以 library_item_id 为边界）
- [ ] COURSE 作用域含本课程资料与记录（不含未归类全局资料）；ALL 含未归类；chat prompt version bump
- [ ] citations 新增 library 条目；最终引用逐字校验（未删除 Segment/Source Anchor）+ 跳转（Record 引用→转写定位，LibraryItem 引用→来源预览）；禁止引用 FTS token、Embedding、Concept 描述或 AI 摘要
- [ ] 挂载范围内无可引用证据时回答「当前资料中未找到」，不得用模型常识补成资料事实；通用知识走 FREE；web 引用独立 citation 类型互不冒充
- [ ] 工具预算生效（01 冻结的每轮调用次数/每次命中数/总上下文字符上限）；检索工具体异常 ok=false 不炸整轮流（既有先例）
- [ ] 每档 scope 至少一个「不越界」失败即红自动化用例（LIBRARY_ITEM/RECORD/COURSE/ALL 四档隔离 + 归档/软删来源不被以资料身份召回）；SSE tool_call/tool_result 过程呈现
- [ ] 前端：资料详情「AI 解读」入口创建会话、会话范围标识、引用跳转；zh/en 文案同步

## 备注

- 本票与 03 可在 02 后并行（03 提供新语料、04 消费存量与新语料同构的分片索引）。
