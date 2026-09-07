# 全局搜索与命令面板

Status: ready-for-agent

## Problem Statement

工作台的学习资产已经积累成库——学习记录、转写全文、知识点、课程——但找东西只能靠记住「哪门课的哪条记录」逐层点进去：想找「讲过傅里叶变换的那节课」没有任何跨课程入口；捕获动作（录音/速记/粘贴）也要回到顶栏找按钮。PRD §9.1 规划的两件工作台形态能力一直缺位：Ctrl+K 命令面板，以及左栏资产库视图（侧栏 nav.library 至今是禁用占位）。

引擎方向经 2026-09-07 两轮裁决定稿：上午咨询稿「MVP 维持 LIKE、中间站 jieba+FTS5」被外部交叉方案（ChatGPT）的 grill 推翻，用户终裁采纳 **FTS5 day-one**——决策 #32 随 PRD v2.6 改写，ADR-0016 记录选型与作废理由（trigram 2 字中文词失效、Tantivy 双存储一致性税）。本 spec 固化该轮全部裁决。

## Solution

三个用户可见能力，共用一个后端搜索服务：

1. **命令面板**：Ctrl+K 或顶栏 🔍 按钮唤起；空查询显示命令项（开始录音/新速记/新粘贴），输入关键词后命令项与三类资产检索结果（课程/学习记录/知识点）同屏混排；键盘全流程（↑↓ 移动、Enter 确认、Esc 关闭），Enter 跳转详情或执行命令。
2. **资产库视图**：左栏资产库入口激活为独立页面；搜索优先形态——搜索框 + 类型过滤（全部/记录/知识点/课程）+ 分组结果，空态走 #42 引导卡；复用同一搜索 API 与结果项组件。
3. **结果跳转**：课程 → 课程详情；学习记录 → 记录详情；知识点 → 所属记录详情的知识点页签。

引擎 = SQLite FTS5 + jieba 应用层分词（统一索引表、BM25 排序）。后端新增 search 模块作为唯一搜索入口（HTTP 出口 `GET /api/search`），未来 AI 对话检索工具复用其内部 service 而非 HTTP 自调。

## User Stories

1. As an 学习者, I want to 在应用任意界面按 Ctrl+K 唤起命令面板, so that 不挪鼠标就能直达任何内容与动作。
2. As an 学习者, I want to 点顶栏 🔍 按钮打开同一面板, so that 不知道快捷键也能找到搜索入口。
3. As an 学习者, I want to 面板刚打开（还没输入）时看到可用命令项, so that 打开即有引导而非空白。
4. As an 学习者, I want to 在面板里直接执行开始录音/新速记/新粘贴, so that 捕获动作不必回顶栏找按钮。
5. As an 学习者, I want to 输入中文关键词后看到课程、学习记录、知识点的混合结果, so that 跨课程一步找到「讲过 X 的那节课」。
6. As an 学习者, I want to 用 2 字中文词（如「代数」）也能命中, so that 搜索符合中文直觉。
7. As an 学习者, I want to 命中转写正文时看到上下文摘录（snippet）, so that 不点开就能确认是不是要找的内容。
8. As an 学习者, I want to 结果按相关度（BM25）排序, so that 最相关的排最前。
9. As an 学习者, I want to 用 ↑↓ 移动、Enter 确认、Esc 关闭, so that 单键盘完成整个检索跳转流。
10. As an 学习者, I want to 点学习记录结果直达记录详情, so that 跳转一步到位。
11. As an 学习者, I want to 点知识点结果直达其所属记录的知识点页签, so that 知识点回源一次到位。
12. As an 学习者, I want to 点课程结果直达课程详情, so that 快速进入那门课。
13. As an 学习者, I want to 从左栏进入资产库独立页面, so that 不经命令面板也能做完整检索。
14. As an 学习者, I want to 在资产库按类型（全部/记录/知识点/课程）过滤, so that 缩小范围快速定位。
15. As an 学习者, I want to 凭知识点标签（tags）搜到知识点, so that 我打的元数据也是检索入口。
16. As an 学习者, I want to 凭课程热词（hot_words）搜到课程, so that 用课堂关键词想起那门课。
17. As an 学习者, I want to 编辑转写/标题/知识点后新内容立刻可搜到, so that 索引与内容永不脱节。
18. As an 学习者, I want to 软删除的记录和知识点不出现在结果里、恢复后重新出现, so that 搜索尊重我的删除操作。
19. As an 学习者, I want to 归档课程及其记录不进搜索结果, so that 搜索口径与其他视图一致。
20. As an 学习者, I want to 升级应用后旧数据也能被搜到, so that 历史学习资产不因升级丢失检索。
21. As an 学习者, I want to 打开应用后第一次搜索与后续一样快, so that 不被词典首次加载卡一下。
22. As an 学习者, I want to 输入过程中结果实时刷新（不需回车）, so that 输入即所得。
23. As an 学习者, I want to 无结果时看到明确空态提示, so that 知道搜索已执行而非界面卡死。
24. As an 开发者, I want to 搜索能力沉淀为后端唯一搜索服务, so that 未来 AI 对话检索工具直接复用而不重写引擎接线。

## Implementation Decisions

- **引擎与分词**：SQLite FTS5（sidecar 自带，已实测可用）+ jieba 应用层分词 `cut_for_search`，索引侧与查询侧一致；排序 FTS5 内置 bm25()。选型论证与作废方案（LIKE 阶段/trigram/Tantivy）见 ADR-0016。
- **分层**：前端（命令面板 + 资产库页）→ `GET /api/search` → 后端 search 模块 service（切词、MATCH、聚合/分组、回表过滤、snippet）→ 统一 FTS5 索引表。前端永不直查数据库（#55：SQLite 唯一属主是 sidecar）。
- **统一索引表**（新增 0018 迁移，只建表）：一张普通 FTS5 虚表，可检索列 `title / body / keywords`（jieba 切词后空格拼接文本）+ `entity_type / entity_id`（UNINDEXED）。实体映射：学习记录（title=记录标题、body=转写全文）、知识点（title=名称、body=详情、keywords=tags 切词）、课程（title=课程名、keywords=hot_words 切词）。
- **索引同步**：三实体全部写路径在**同一业务事务**内 upsert 索引行——记录创建/改标题、转写落稿/PATCH 编辑、知识点确认/编辑/重新生成、课程创建/改名。触发器与 external content 表不可用（触发器执行不了 jieba；external content 绑定原文列，索引文本是变换后的派生物）——ADR-0016。
- **软删/归档**：软删不删索引行、恢复零索引操作；查询期 MATCH 得到 entity_id 后回业务真表取显示数据（标题、所属课程名上下文），顺带过滤 `deleted_at` 与 ARCHIVED 课程（含其记录与知识点，与全库归档护栏口径一致）。索引是可再生衍生数据，业务表是唯一事实源。
- **存量回填**：启动时 run_migrations 之后对三类实体做「缺行补索引」幂等回填，并预热 jieba 词典（首次加载约 0.5~1s）。
- **API 契约**：`GET /api/search`，参数 `q`（必填、trim、长度上限）与 `limit`（每类上限，默认 5）；响应按类型分组 `{courses, records, knowledge_points}`，每项含实体 id、标题、snippet（FTS5 snippet 生成的命中摘录）、所属课程名（上下文）、updated_at。后端 openapi 导出后 api-types 重新生成，前端按既有惯例 types re-export + react-query 封装。
- **命令面板 UI**：9ui Command 组件（cmdk-base 内核、Base UI 原语，经 shadcn CLI 安装；**不直接装 cmdk**——默认变体带 Radix，破坏 Base UI 单原语纪律）。Ctrl+K 为 React keydown 监听、硬编码（不进偏好改键体系，不涉 OS 全局注册）。顶栏新增 🔍 按钮（带 Ctrl K 角标）唤起同一面板。空查询=命令列表；输入后前端 250ms 去抖调 API。命令注册表=前端常量，仅 3 项捕获命令；面板分组顺序=命令→课程→学习记录→知识点；键盘行为由 cmdk-base 内核提供。
- **资产库视图**：新路由 `/library`，侧栏 nav.library 占位激活；搜索框 + 类型 Tabs（全部/记录/知识点/课程）+ 分组结果列表，空态 #42 引导卡；与面板共用搜索 API 与结果项组件；资产库传更大的每类 limit，类型过滤在展示层取对应组。
- **i18n**：zh.json 新增 commandPalette 与 library 顶层命名空间（按 feature 分域惯例）。

## Testing Decisions

- 好测试只断言外部行为：后端=HTTP 响应 JSON（命中集合、排序、snippet、过滤、每类上限、422 校验），不测内部切词函数；前端=用户可见行为（键盘流、混排、空态、跳转目标路由），不测去抖实现细节。
- **后端**（pytest + 真实 SQLite，先例=course/record 模块测试）：
  - 中文检索闭环：种子记录/转写/知识点/课程 → 2 字中文词命中、tags 命中、hot_words 命中、BM25 相关度排序（构造标题命中 vs 正文命中的明确用例）。
  - 写路径同步：经既有端点改标题/编辑转写/确认知识点/改课程名后新词可搜到（证明同事务 upsert 生效）。
  - 软删/归档过滤：SQL 直改模拟（先例=归档护栏测试）；恢复后回归结果。
  - 启动回填：SQL 直改种子存量 → 调回填入口 → 可搜（证明迁移外的 Python 回填路径）。
- **前端**（vitest + RTL + MSW，onUnhandledRequest=error 惯例，先例=spaces/inbox 页测试）：mock `/api/search`；面板：Ctrl+K 开、Esc 关、↑↓ 循环、Enter 执行命令/跳转、空查询命令态、去抖后请求；资产库页：空态引导、类型过滤、点击跳转断言路由 search params。
- **真机验收**（用户手动执行，agent 不代勾）：Ctrl+K 全局唤起（含焦点在各输入框场景）、顶栏按钮、真实数据检索体感与首搜速度。

## Out of Scope

- 向量语义检索（P2，sqlite-vec 接管）
- LIKE/子串兜底（FTS5 失配即无结果；召回缺口凭真实反馈再议）
- 搜索历史/收藏/Recent Items
- 题目与 AI 对话会话的检索（后续波次；速记本身是学习记录，天然被覆盖）
- 导航类命令（打开设置/前往资产库/前往 AI 对话——后续小增量）
- Ctrl+K 可配置改键、OS 全局快捷键唤起（Alt+Space 全局搜索窗）
- Tantivy/Meilisearch/Elasticsearch 等外部引擎（重开条件见 ADR-0016）
- 索引重建/维护的管理 UI

## Further Notes

- 决策链：三轮选型咨询（维持 LIKE 稿）→ ChatGPT 交叉方案 grill → 用户终裁 FTS5 day-one；与上午稿的全部差异点及理由已固化于 ADR-0016 与 PRD v2.6 变更记录。
- 「资产库」「命令面板」词条已入 CONTEXT.md（工作台与偏好节）。
- jieba 为后端新依赖：纯 Python、零传递依赖、词典随包分发，通过本地优先两问。
- 前置 02（跳转宿主）与 07（知识点作为搜索对象）均已交付；record-detail-panels/01 为纯重构不构成本功能阻塞。
