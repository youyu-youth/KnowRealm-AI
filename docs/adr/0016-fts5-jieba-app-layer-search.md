# 全局搜索引擎：SQLite FTS5 + jieba 应用层分词

---
Status: accepted（2026-09-07，plan 18 grill 终裁，PRD 决策 #32 随 v2.6 改写）
---

全局搜索（命令面板 + 资产库，PRD §9.1）需要跨课程检索学习记录（标题+转写全文）、知识点（名称+详情+tags）与课程（名称+hot_words）。决策 #32 原文为「LIKE 子串匹配（SQLite）；不引入中文分词」。2026-09-07 同日经历两轮裁决：上午三轮选型咨询定稿「MVP 维持 LIKE，中间站 jieba+FTS5」；晚间外部交叉方案（ChatGPT）提议 day-one 直接 FTS5 + 服务层抽象，用户终裁采纳，跳过 LIKE 阶段。此前已实测/论证的事实继续有效：SQLite 3.50.4 的 FTS5 可用，但 trigram tokenizer 对 2 字中文词（"代数"）MATCH 返回空（3 字符滑窗硬伤）——trigram 否决；Tantivy 为嵌入式库非独立服务，但双存储一致性税 + 新原生依赖 + 中文零增益（tantivy-py 同样无内置中文分词）——否决；Meilisearch/Elasticsearch 违反零部署红线——不可选。

**决定**：

- **引擎 = SQLite FTS5 + jieba 应用层分词**，索引侧与查询侧一致使用 `cut_for_search`（检索模式，粒度细、召回高），排序用 FTS5 内置 bm25()。中文分词落在 Python 应用层：jieba 纯 Python、零传递依赖、词典随包分发，满足本地优先两问（不要求用户多装任何东西）。
- **统一索引表**：一张普通 FTS5 虚表，可检索列 `title / body / keywords`（存切词后空格拼接文本），`entity_type / entity_id` 为 UNINDEXED 列。实体映射：学习记录（title=记录标题、body=转写全文）、知识点（title=名称、body=详情、keywords=tags）、课程（title=课程名、keywords=hot_words）。
- **应用层同事务维护**：三实体全部写路径（记录创建/改标题、转写落稿/编辑、知识点确认/编辑/重新生成、课程创建/改名）在业务事务内 upsert 索引行。**触发器与 external content 表双双作废**：SQLite 触发器只能执行 SQL、调用不了 jieba；external content 表绑定的必须是原始列文本，而索引文本是切词变换后的派生物。
- **软删/归档不触碰索引**：软删不删索引行、恢复零索引操作；查询期 MATCH 得到 entity_id 后回业务真表取显示数据，顺带过滤 `deleted_at` 与 ARCHIVED 课程（含其记录与知识点，与全库归档护栏口径一致）。索引始终是可再生衍生数据，业务表是唯一事实源（#55）。
- **启动幂等回填**：迁移 SQL 同样跑不了 jieba，故迁移只建空表，启动时在 run_migrations 之后对三类实体做"缺行补索引"回填，顺带预热 jieba 词典（首次加载约 0.5~1s，避免首搜卡顿）。
- **服务层抽象前置**：后端新增 search 模块作为唯一搜索入口（HTTP 出口 GET /api/search，聚合/分组/排序/回表过滤），未来 AI 对话检索工具复用其内部 service；引擎再演进（sqlite-vec 语义检索）不动 API 契约。

## Considered Options

| 方案 | 结论 |
|------|------|
| **A. FTS5 + jieba 应用层分词（day-one）** | **采纳**——BM25 排序与检索质量一步到位；jieba 零传递依赖不破坏本地优先；服务层抽象保住后续演进路径 |
| B. LIKE 子串 MVP，jieba+FTS5 作中间站（09-07 上午咨询稿） | 否决——用户终裁跳过：LIKE 阶段的实现（含各视图接线）在中间站落地时即作废，属一次性代码；统一索引表与同步钩子反正要建 |
| C. FTS5 trigram（零新依赖） | 否决——2 字中文词命中失效（实测），中文高频词恰以 2 字为主 |
| D. Tantivy / tantivy-py | 否决——双存储一致性税（索引在库外，崩溃对账自写、拷数据目录需额外处理）、新原生依赖、中文能力与 FTS5+jieba 等价；重开条件=多用户服务端 / 千万级文档 |
| E. Meilisearch / Elasticsearch | 否决——违反零部署红线（#55） |

## Consequences

- 丢失部分子串召回：非词典子串（如只输入"量代"找"线性代数"）不再命中。MVP 不做 LIKE 兜底（两种语义混进一个排序，复杂度不成比例）；召回缺口凭真实使用反馈再议。
- jieba 进入后端依赖（停更 5~6 年但仍为事实标准；HanLP 重、pkuseg 慢约 3 倍、LAC 拖 Paddle）。切词大文本（长转写编辑保存）约百毫秒级，同事务内可接受；若成为写入瓶颈，再评估词典预载/增量切词优化，而非推翻本 ADR。
- 语义检索（同义词/概念匹配）分词解决不了，演进终点是 sqlite-vec（P2），届时向量列与本索引并存或由其接管——由当时的 spec 裁决。
- PRD 决策 #32 已随 v2.6 改写；18 号功能计划与 .scratch/search-command/spec.md 为实施依据。
