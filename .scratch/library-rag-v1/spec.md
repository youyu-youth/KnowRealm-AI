# 资料库 / RAG Agent + Learner Memory V1 规格说明

Status: ready-for-agent
定稿依据：扩展设计 §42/§43（2026-09-18 grill Q1~Q42）、ADR-0024、ADR-0025、PRD v2.8 决策 #60/#61、数据模型 v3.0、技术栈 v4.6。本 spec 只做整合与冻结，不重新讨论已定边界；与权威文档冲突时以 ADR 与权威文档为准。

---

## Problem Statement

- 用户的学习来源散落各处：本地文件、网页、粘贴文本、录音各自走不同入口，无法统一回答"我拥有哪些原始资料、它们生成了什么学习内容"。
- 当前 `/library` 只是一个输入关键词才有结果的搜索壳，没有来源目录、生命周期治理（归档/删除/恢复）和 RAG 可用性视图。
- Chat 的 RAG 检索只覆盖 Record 分片（`search_transcript`）与 COURSE/ALL 级 `search_library`，无法对"单个资料"问答，引用也无统一的"来源资产"身份。
- 项目没有跨会话的学习者记忆：换一个会话，AI 就忘记用户的稳定学习偏好与学习状态；而直接引入通用 Agent Memory Store 又会产生用户看不见、无法纠正的黑盒画像。
- Agent 只有读能力时可复用，但直接放开写权限会绕过领域校验；需要一条"提案 → 用户确认 → 领域 Service 执行"的受控写路径。

## Solution

一个外部版本交付两条独立纵向能力：

1. **资料库 V1（决策 #60 / ADR-0024）**：`/library` 升级为统一资产工作台——以 LibraryItem（资料条目）为来源目录，联邦展示其派生的 Record 与学习资产；统一入库入口 `ingest(request)` 接网页剪藏 / 本地文件 / 纯文本，存量捕获幂等回填；`LibraryRetrievalService` 作为唯一检索深模块供 RAG 消费，模型只见一个 `search_library(query)` 工具，五档 Chat Scope（FREE / RECORD / LIBRARY_ITEM / COURSE / ALL）强制隔离，引用必须逐字回查 Source Anchor。
2. **Learner Memory V1（决策 #61 / ADR-0025）**：复用 `learner_preferences` 单例业务表保存显式偏好与经确认的观察偏好；`LearnerProfileService` 按任务聚合偏好、掌握度、误区、近期证据与目标，生成限长可重建的 Learner Context 注入 Agent；写入只有两个入口——用户直接编辑、经 HITL 确认的记忆提案（`agent_proposals(MEMORY)`）。

## User Stories

### 来源导入与入库

1. As a 学习者, I want 把一个网页 URL 保存为资料（剪藏）, so that 离线也能阅读其正文且原文可追溯。
2. As a 学习者, I want 导入本地文件（PDF/DOCX 等）为资料条目, so that 所有学习来源集中在一处管理。
3. As a 学习者, I want 直接粘贴一段文本保存为资料, so that 零散信息不用先创建 Record 才能留存。
4. As a 学习者, I want 导入内容与已有资料哈希相同时被提示"打开已有条目 / 仍然保留", so that 不会无声产生重复来源。
5. As a 学习者, I want 网页剪藏失败（正文为空/质量差/登录墙/网络不可达）时得到明确提示并可降级为手动粘贴正文, so that 不丢失想保存的内容。
6. As a 学习者, I want 导入立即产生可见条目并显示确定性处理状态（解析中/可检索/失败）, so that 不面对无限 spinner、知道下一步能做什么。
7. As a 学习者, I want 资料保存净化后的正文快照而非原始 HTML, so that 本地数据干净、可搬移、安全可渲染。
8. As a 学习者, I want 现有录音/音频/文档/粘贴/速记自动回填进资料库, so that 存量学习来源无需重新导入即可统一浏览。

### 浏览与组织

9. As a 学习者, I want `/library` 默认可浏览（无需先输入关键词）, so that 打开就能看到我的全部资料。
10. As a 学习者, I want 左侧智能视图（全部/最近/收藏/待整理/归档/资料条目回收站）, so that 常用视角一步可达。
11. As a 学习者, I want 左侧领域分类（资料来源/学习记录/学习资产）与 Course 筛选, so that 按对象身份和课程缩小范围。
12. As a 学习者, I want 顶部固定分类"全部/资料来源/学习记录/学习资产"加二级筛选（来源类型/资产类型/Course/处理可用性/归档状态/时间）, so that 界面按领域身份而非文件格式组织。
13. As a 学习者, I want 筛选与视图状态进入 URL, so that 刷新和分享链接后视图可恢复。
14. As a 学习者, I want 收藏任意资料条目, so that 高频来源快速可达。
15. As a 学习者, I want 列表内搜索命中标题、来源与元数据, so that 不依赖 AI 就能定位资料。
16. As a 学习者, I want "待整理"视图汇集未归类、未命名规范的资料, so that 集中处理新导入内容。
17. As a 学习者, I want 给资料重命名、归类/取消归类 Course, so that 资料组织始终由我掌控。

### 详情检查器

18. As a 学习者, I want 选中资料条目看到安全预览、来源元数据（URL/文件路径/MIME/大小/抓取时间）、处理与 RAG 可用性状态, so that 明确区分"已导入"与"已可检索"。
19. As a 学习者, I want 资料详情展示派生 Record 列表并可跳转, so that 从来源追溯到学习内容。
20. As a 学习者, I want Record 详情展示其来源资料与已生成学习资产, so that 双向可追溯。
21. As a 学习者, I want 学习资产详情展示正文摘要、所属 Record 与来源锚点, so that 资产的事实依据可见。
22. As a 学习者, I want 用系统浏览器打开原始 URL、在系统资源管理器中显示本地文件, so that 需要时回到原始环境。
23. As a 学习者, I want 处理失败时看到稳定错误信息与重试入口, so that 自助恢复而不用重启应用。

### AI 整理

24. As a 学习者, I want "AI 整理"先展示确定性检测出的重复项与处理异常, so that 机械问题不消耗 AI 且结果可信。
25. As a 学习者, I want AI 给出标题规范建议与 Course 归类建议并逐项确认后应用, so that 整理结果可控、可拒绝。
26. As a 学习者, I want 拒绝某条建议不影响其他建议, so that 批量审核高效。

### RAG 问答

27. As a 学习者, I want 从资料详情"AI 解读"直接对该资料提问, so that 不必切换到全局问答再描述上下文。
28. As a 学习者, I want COURSE 会话能检索本课程全部未软删资料与记录（不含未归类全局资料）, so that 课程边界可信。
29. As a 学习者, I want ALL 会话能检索包括未归类在内的全部资料, so that 跨课程研究可行。
30. As a 学习者, I want AI 回答的每条本地引用都带逐字摘录并可点击跳转到原文位置（转写定位/来源预览）, so that 结论可验证。
31. As a 学习者, I want 挂载范围内确实没有证据时 AI 明确说"当前资料中未找到", so that 不会把模型常识伪装成资料结论。
32. As a 学习者, I want 需要通用知识时切换到 FREE 会话, so that 范围承诺与自由问答不混淆。
33. As a 学习者, I want 开启联网搜索时网络引用与本地引用类型分开显示, so that 知识来源一目了然。
34. As a 学习者, I want 在 SSE 流中看到检索工具调用过程, so that 理解 AI 如何得出答案。

### 生命周期

35. As a 学习者, I want 归档资料后它退出默认浏览与来源召回、但快照与关联保留, so that 收起不等于销毁。
36. As a 学习者, I want 删除资料前看到其派生 Record 并确认它们不会被级联删除, so that 删除资料不会误删学习成果。
37. As a 学习者, I want 软删资料后 30 天内可从回收站恢复（校验快照并按需重建索引）, so that 误删可挽回。
38. As a 学习者, I want 同 URL 内容变化时"重新抓取"生成新资料条目而非覆盖旧快照, so that 历史版本不丢失。
39. As a 学习者, I want 移动资料到另一 Course 时不静默移动其派生 Record, so that 归属变化由我分别确认。
40. As a 学习者, I want 对失败条目触发失败重试或索引重建, so that 处理问题可恢复。

### Learner Memory

41. As a 学习者, I want 在学习画像的"AI 记忆"区查看、编辑、删除我的显式学习偏好, so that AI 了解我的方式由我决定。
42. As a 学习者, I want 系统从结构化学习证据推断的观察偏好带置信度与证据数展示、且必须经我确认才生效, so that 没有看不见的画像。
43. As a 学习者, I want 对 AI 说"记住我喜欢先看例题"时收到一张就地确认卡片, so that 明确要求才产生记忆。
44. As a 学习者, I want 拒绝记忆提案后事实不被改变, so that 拒绝就是拒绝。
45. As a 学习者, I want 查看本轮对话实际注入了哪些记忆, so that AI 的个性化可解释。
46. As a 学习者, I want 观察偏好永不覆盖我的显式偏好, so that 我的选择永远优先。
47. As a 学习者, I want 在设置中单独关闭"在 AI 中使用长期记忆"，关闭后记忆保留本地但不再外发, so that 隐私可控且不损失本地数据。

### 隐私、离线与数据安全

48. As a 学习者, I want 第一次范围问答前被告知将向外部模型发送相关来源片段与最小必要学习者记忆并明确同意, so that 外发是知情选择。
49. As a 学习者, I want 更换供应商地址或密钥后重新确认外发同意, so that 数据接收方变化时授权不失效。
50. As a 学习者, I want 无网络/LLM 不可用时资料浏览、预览、本地全文检索、来源定位、生命周期与记忆管理全部可用, so that AI 故障不拖垮本地功能。
51. As a 学习者, I want 全量导出与备份包含资料条目、关联关系、本地快照与学习者记忆，而派生索引可重建, so that 我真正拥有不可替代的数据。
52. As a 学习者, I want 首次升级到新数据库结构前自动创建独立升级前快照，失败则停止升级保留旧数据, so that 迁移事故不丢库。

## Implementation Decisions

### 领域与模块边界

- **library 域（新）**：LibraryItem CRUD、统一入库入口、适配器、生命周期动作、整理提案应用；`LibraryRetrievalService` 与 `agent_proposals` 服务也落此域。
- **入库只有一个外部入口** `ingest(request) -> LibraryItem + ProcessingJob`；来源差异由内部适配器消化：ExistingCaptureAdapter（存量幂等映射，不重跑已成功处理链）、WebClipAdapter（V1 新增）、FileAdapter（复用现有导入校验与落盘）；BookAdapter 待 `ai-summary/03` 完成后加入（按 §41.2 拆章，一资料条目多 Record）。V1 不提取公开 Connector/Plugin SDK——第三个真实新适配器出现相同扩展点后才考虑。
- **检索只有一个深模块** `LibraryRetrievalService.search(scope, query, filters, limit) -> RetrievalResult`，内部固定顺序：作用域与软删过滤 → 查询规范化 → Segment FTS 与 CONFIRMED Concept 扩展并行召回 →（条件满足时）sqlite-vec 追加 → 去重与确定性排序 → 回业务表取逐字原文与相邻小窗口 → 组装 Source Anchor。复用现有 `segment_search_index` 与 Source Anchor 体系，不建第二套索引写路径；`search_index`（资产级导航）与 `segment_search_index`（RAG 片段）保持分表。
- **agent 域改造**：`search_library` 工具改为消费 `LibraryRetrievalService`，不再自行拼接 Concept 与分片召回；`search_transcript` 降为迁移期内部复用代码，不再是模型可见工具。挂载会话统一只见 `search_library(query)`，作用域与目标 id 由会话运行时绑定。
- **learner 域（新）**：`learner_preferences` 单例表 + `LearnerProfileService`（按任务与会话范围聚合偏好/掌握度/误区/近期证据/目标，输出限长可重建的 Learner Context）+ MEMORY 提案确认应用。
- **Learner Context 注入**：Agent 运行前由确定性中间层构建并注入，模型不能扩大读取范围；全局显式偏好可跨 Agent，Course 状态只进对应 Course 会话，ALL 按任务取最小集合；受字符预算约束。Learner Context 只影响解释方式与建议，不得改变 Mastery、Evidence、Quiz 判分等确定性数值。
- **职责定案**（ADR-0024/技术栈 v4.6）：入库/抓取/解析/分片/索引/回填/生命周期 = Feature Service + JobRunner（确定性，不进 Agent、不改写为 Graph）；召回/作用域/去重/排序/锚点 = LibraryRetrievalService；查询改写/多轮检索/证据比较/回答 = DeepAgents Chat Agent（沿用 `create_deep_agent` 骨架与既有中间件闸门，V1 不启用 SubAgents、Skills、Filesystem Backend、StoreBackend、MCP server）；跨重启业务建议 = `agent_proposals` + REST + 领域 Service，不依赖 Graph interrupt 悬挂。

### 数据模型（迁移编号由工单 01 冻结；当前已实施 27 张表 / user_version 0025）

- **`library_items`**：id、course_id（FK SET NULL 可空=未归类全局）、source_type（AUDIO/DOCUMENT/WEB/BOOK/TEXT）、title（可编辑 NOT NULL）、origin_uri（只作出处不作离线依赖）、local_path（数据目录内快照相对路径；纯文本可无文件）、mime_type/file_size、content_hash（NOT NULL，重复提示用、不设 UNIQUE）、fetched_at、metadata_json（按 source_type Pydantic 判别校验）+ schema_version、status（ACTIVE/ARCHIVED，技术状态不入此表）、created_at/updated_at/deleted_at（软删 30 天回收站）。
- **`library_item_records`**：联合 PK（library_item_id, record_id，FK 均 CASCADE）、role（PRIMARY/SUPPLEMENTAL）、sequence_no（拆章顺序）、created_at。覆盖"一书拆多 Record"与"多来源 Record"双向。
- **`agent_proposals`**：proposal_type（ORGANIZE/MEMORY/RESEARCH_INGEST）、status（PENDING/APPLIED/REJECTED/FAILED）、session_id/message_id（溯源非授权）、target_type/target_id、payload_json（Pydantic 判别校验，禁止任意 SQL/路径/Shell）、evidence_refs_json、error_code、created_at/decided_at。提案创建不改事实，确认后由领域 Service 原子应用。
- **`learner_preferences`**：单行表（id 固定 `me`）、user_selected_preference（JSON）、observed_learning_preference（JSON）、observed_confidence（0~1）、evidence_count、last_observed_at、updated_at。
- **存量结构改造**：`document_segments`/`source_anchors`/`semantic_embeddings` 预留 `course_material_id` 统一改名为 `library_item_id` 并补 FK；`source_anchors.course_id` 改可空（全局来源拥有真实锚点，不为通过约束伪造 Course）；`chat_sessions.scope` CHECK 扩为五档并新增 `library_item_id` 列（LIBRARY_ITEM 仅由资料详情创建、必填该 id，检索授权始终以 library_item_id 为准）；`processing_jobs` 增 library_item_id 关联与 job_type 扩展（WEB_FETCH/LIBRARY_BACKFILL/INDEX_REBUILD）；`chat_messages.citations_json` 增 library 条目类型 `{index, source:"library", library_item_id, title, quote≤80, anchor_id}`。
- **迁移纪律**：Schema migration 只建表/约束（快速可回滚），存量文件哈希、资料条目创建、关联与索引补建全部走可恢复、幂等、可见进度的 `LIBRARY_BACKFILL` 后台 Job（稳定游标）；回填期间现有功能零中断，新数据直接走新写路径。首次应用新 Schema 前创建独立升级前数据库快照；Schema 失败停止启动保留旧数据，回填失败不阻塞可重试且不删旧文件与关系。

### 检索与 RAG 契约

- `RetrievalResult` 三分类：`evidence_hits`（唯一可引用：逐字 quote + Source Anchor + segment id + 页码/时间戳）、`asset_matches`（LibraryItem/Record/已确认资产的导航命中）、`concept_hints`（CONFIRMED Concept 查询扩展提示）。分数只用于排序，不作用户可见可信度。
- 每个 evidence hit 至少含 library_item_id、可选 record_id、来源标题、逐字 quote、受限上下文窗口、anchor/segment id、定位信息、来源类型与召回通道。
- 最终引用必须来自未删除的业务 Segment/Source Anchor；禁止引用 FTS token、Embedding、Concept 描述或 AI 摘要；禁止把 Summary/Concept/AI 综合文本回灌为来源事实；资料导入不计为 Mastery Evidence。
- 五档 Scope 隔离：LIBRARY_ITEM=该资料+其关联 Record；RECORD 强制 record_id；COURSE=本课程资料与记录（不含未归类）；ALL=全部含未归类。每种范围必须有"不越界"自动化用例。挂载范围无可引用证据必须回答"当前资料中未找到"。
- Agent 工具预算：每轮工具调用次数、每次命中数、总上下文字符设上限（数值工单 01/04 冻结）。
- sqlite-vec 条件门禁：FTS + Concept 为基线；真实黄金集出现词汇错配失败且混合召回有可测净增益才在同一服务内部追加（DashScope text-embedding-v3，1024 维，可重建、可删除、模型/维度可识别），不新增第二个模型工具、不引入独立向量服务。资料库不得以"先上向量库"为开工前置。

### 网页剪藏安全边界

- 仅 HTTP(S)；阻止 loopback/私网/链路本地/云元数据地址，每次重定向后重新解析校验（防 SSRF/DNS rebinding）；限制响应体与解压后大小、重定向次数、连接/读取超时、允许的 Content-Type；不执行 JS、不加载第三方子资源、不绕过登录墙/反爬、不爬站。
- `httpx` 负责受控抓取（以原始 bytes 做编码识别），`trafilatura >=2.2,<3` 只处理已下载 HTML、抽取正文与元数据；保存净化后的 Markdown/纯文本快照；提取为 None 或过短/重复行过多等垃圾正文判定失败，降级手动粘贴。HTML 只作解析输入，不持久化不直接渲染。

### API 与前端

- 后端按用户任务分组暴露：列表/详情（分页+筛选+处理摘要+可执行动作）、ingest（判别请求）、生命周期（重命名/归类/归档恢复/删除/重试/重抓/重建索引）、提案确认与拒绝。RAG 检索接口仅供业务模块内部调用，不开可绕过会话范围的任意查询端点。任务进度沿用 REST 为事实源、SSE 只做失效通知。
- `/library` 前端：左侧三组扁平导航（智能视图/领域分类/最近 Course+查看全部，Course 仅筛选器）；顶部四分类；列表/网格视图；详情检查器按对象类型动态展示；URL search params 承载筛选；整页不纵向滚动、列表与检查器各自滚动。批量动作只在同类语义一致选择开放，跨类型仅收藏/打开等安全动作。V1 不展示视频/图片等未支持类型入口，不做文件夹树，不做讨论页签。
- "AI 解读"：资料条目 → 新建 LIBRARY_ITEM 会话（不进全局范围切换按钮）；Record/学习资产 → 既有 RECORD 会话；不新增第二套聊天界面或持久化"解读文档"。
- 学习画像新增"AI 记忆"区（显式偏好编辑、观察偏好置信度/证据数/确认时间、删除入口、外发开关、最近使用说明）；对话中 MEMORY 提案用就地确认卡片；本轮使用记忆可在 UI 查看。
- 外发同意：第一次范围问答前取得绑定供应商身份的 External Processing Consent（覆盖来源片段与最小必要 Learner Memory）；供应商地址/密钥变化重新确认；长期记忆外发可单独关闭且不影响本地检索。UI 文案 zh/en 同步。

## Testing Decisions

- **好测试只测外部行为**：API 契约（请求/响应/错误码）、检索结果结构与隔离性、引用逐字回查、提案确认前零事实变更、生命周期语义——不断言内部实现细节。
- **测试接缝**（沿用项目既有接缝，新增唯一深模块接缝）：
  - 后端：FastAPI 路由层测试（既有 conftest fixtures、独立 basetemp 纪律）覆盖 library 域端点与提案闭环；`LibraryRetrievalService.search` 作为纯服务层接缝直接测（scope 过滤/三类结果/去重排序/锚点组装）；Agent 侧沿用 SSE 流测试先例（`test_chat_streaming.py` 风格）断言工具挂载、scope 绑定与预算。
  - 网页剪藏：httpx 传输层注入 fake transport 测 SSRF 拦截（私网/loopback/重定向重校验/大小超限/类型白名单）与 trafilatura 提取/垃圾正文降级，不发起真实网络。
  - 回填：`LIBRARY_BACKFILL` 幂等重跑测试（重复执行状态不变、失败可恢复）。
  - 检索质量：真实语料黄金集评测落 `docs/evaluation/`（先例 `course-brain-retrieval-baseline.md`），冻结 Recall@K、MRR、无答案准确率、引用正确率阈值；含中文、英文、同义改写、跨 Course 同名概念、归档/删除来源用例——这是 sqlite-vec 门禁的唯一判据。
  - 前端：vitest + MSW mock 新端点（先例 courseBrain hooks/LibraryPage 测试）；URL 状态恢复、检查器动态展示、提案卡片、外发开关各覆盖。
- **硬门禁零容忍自动化**：scope 泄漏、无锚点引用、归档/删除来源被召回、未确认写入事实/记忆、关闭外发后仍发送——每条至少一个失败即红的用例。
- 迁移测试同步全部既有 `user_version` 断言（动迁移先全库检索断言处数）。

## Out of Scope（资料库 V1 + Learner Memory V1 明确不做）

- 文件夹树/第二套知识空间/Notion 式页面系统/块编辑器；讨论/协作/本地评论模块；视频、图片来源类型入口。
- 通用 Connector/Plugin SDK、MCP server、Multi-Agent 抓取团队、独立爬虫服务、浏览器扩展。
- SubAgents、Skills、DeepAgents Store/Filesystem Memory/通用 `memories` 表（按 ADR-0025 触发条件后置）。
- 版本系统（`library_item_versions`）、后台监控网页/仓库变化、自动订阅、自动覆盖快照、批量静默抓取。
- 强制 sqlite-vec/Qdrant/LanceDB/云向量服务；Agent 直写业务表或任意文件/Shell 操作。
- 从普通聊天静默提取记忆、自动总结全部聊天、人格推断、跨设备云画像、记忆向量库、自由文本情节记忆。
- 标签系统（LibraryItem 标签建议与标签模型后置）；Recycle Bin 扩展到 Record/学习资产（沿用既有删除规则）。
- LangSmith 作为产品依赖（仅开发者可选且默认关闭）；任何未经另行同意的用户内容上传。

## Further Notes

- **七张纵向工单拆分**（对外一个版本，依赖 01→02→{03,04 可并行}→05→07；06 在 01 后可独立推进、07 前集成）：01 契约与评测地基（冻结迁移编号、OpenAPI Schema、黄金集与 sqlite-vec 触发阈值、检索/工具预算数值）→ 02 Schema+存量回填+基础工作台 → 03 网页剪藏闭环 → 04 RAG Agent 闭环（LibraryRetrievalService+五档 scope+LIBRARY_ITEM 会话）→ 05 生命周期与提案闭环（含导出恢复）→ 06 Learner Memory V1 → 07 发布收尾（OpenAPI 类型、i18n、黄金集门禁、Windows/Tauri 真机清单、进度文档同步）。
- 工单 01 不重新讨论已定产品边界；实现与文档冲突时先回 ADR 评审，不得默默偏离。
- 实施已知坑：新增迁移须同步全库 `supported_user_version` 断言；同仓多会话并行 pytest 须独立 basetemp；`chat_sessions.course_id` 自 0014 起零写入者、本波次 COURSE/LIBRARY_ITEM 会话将启用其语义；ExistingCaptureAdapter 回填不得重跑已成功处理链（只建条目与关联）。
- 评测语料需覆盖英文内容（网页剪藏主流语言）验证现有 jieba 分词链路对英文的召回表现，属工单 01 黄金集职责。
