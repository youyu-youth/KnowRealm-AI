# 资料库以 LibraryItem 统一来源资产，RAG 经单一检索边界提供可回查证据

---
Status: accepted（2026-09-18，资料库 / RAG Agent grill Q1~Q42 定稿）
---

现有 `/library` 主要是搜索壳，Record、来源文件、AI 学习资产和课程级检索各自暴露，无法作为 Agent 的统一知识入口。早期 `course_materials` 草案把资料限定在 Course 下，又把来源、学习记录和生成资产混成一个实体；早期 Qdrant / 默认 sqlite-vec 方案还会引入第二套生命周期与数据隔离逻辑。本 ADR 固化资料库 V1 的领域边界、检索契约和升级安全要求。

**决定**：

- **资料库是联邦工作台，不是文件夹树**：`LibraryItem` 只表示用户拥有的原始来源；Record 是学习处理单元，Summary / KnowledgePoint / Quiz / ReviewMaterial / Todo 是派生学习资产。Course 仍是唯一知识容器；Smart View、标签、收藏只做元数据视图，不建第二套目录树。
- **来源与 Record 多对多**：以 `library_items` + `library_item_records(role, sequence_no)` 连接来源与 Record。一个长来源可拆多个 Record，一个 MULTI_SOURCE Record 可组合多个来源；移动来源 Course 不静默移动 Record。存量数据由幂等后台任务回填，原文件优先复用 `record_files`，不复制字节。
- **本地快照是可迁移事实**：文件、文本和网页都保存数据目录内的规范化快照；`origin_uri` 只表示出处，不是离线依赖。网页剪藏仅允许受限 HTTP(S)：`httpx` 获取原始字节，`trafilatura 2.2.x` 抽取正文与元数据；不执行 JS、不抓子资源、不绕过登录或反爬、不爬站。抽取失败降级为手动粘贴。
- **生命周期彼此独立**：LibraryItem 只有 ACTIVE / ARCHIVED / 软删除，处理状态从 Job / Segment / Index 派生。归档、软删或移动来源不级联 Record / 学习资产；有未删除 Record 引用时禁止物理删除。资料条目回收站只恢复 LibraryItem，保留 30 天。
- **检索只有一个领域边界**：`LibraryRetrievalService` 统一执行运行时范围过滤、Segment FTS、CONFIRMED Concept 扩展、Source Anchor 回链与可选向量召回；模型只见 `search_library(query)`。结果分 `evidence_hits`、`asset_matches`、`concept_hints`，只有逐字命中 Segment 且锚点有效的 `evidence_hits` 可作为引用。
- **五档 Chat Scope**：FREE / RECORD / LIBRARY_ITEM / COURSE / ALL。LIBRARY_ITEM 仅从资料详情创建并由运行时强制 `library_item_id`；COURSE 不包含未归类全局资料，ALL 可包含。挂载范围内无证据时必须回答“当前资料中未找到”，不得用模型常识伪装为资料结论；FREE 才允许一般知识回答，Web 引用保持独立来源类型。
- **FTS + Concept 是基线，sqlite-vec 是条件能力**：先冻结真实查询黄金集并记录 Recall@K、MRR、无答案准确率和引用正确率。只有出现真实词汇错配失败且混合召回相对基线有可测净增益时，才在同一检索服务内加入 sqlite-vec；不引入独立向量服务。
- **确定性业务不进 Agent**：入库、解析、分片、索引、生命周期、导出恢复由 Feature Service + JobRunner 完成。LangChain 承载工具与结构化输出，LangGraph 只编排需要分支、循环或 interrupt 的流程，DeepAgents 只用于查询改写、多轮检索与回答；V1 不启用 SubAgents、通用 Skills 或虚拟文件系统。
- **Agent 写入必须先提案**：整理、研究入库等写动作先持久化为 `agent_proposals`，用户确认后由领域 Service 应用；Agent、Tool、Skill、MCP、SubAgent 均不得直接写业务表。跨重启待审提案不依赖暂停中的 Graph。
- **升级先保护数据**：schema migration 前独立快照 `knowrealm.db`；migration 只变 schema，存量 LibraryItem 关系由启动后的幂等后台任务回填。schema 失败停止启动；回填失败不阻塞原 Record 流程、可重试，且不得删除或移动旧文件与关系。

## Considered Options

| 方案 | 结论 |
|------|------|
| **A. LibraryItem 来源资产 + Record M:N + 单一检索服务** | **采纳**——来源治理、学习处理和 Agent 检索职责清晰，未来网页、书籍、仓库等入口复用同一契约 |
| B. 把 Record / AI 资产都建成 LibraryItem | 否决——生命周期、删除语义和可引用性混乱，产生多套事实源 |
| C. Course 文件夹树 + 物理目录 | 否决——Course 已是知识容器，树会制造第二组织体系与移动级联问题 |
| D. 每种来源公开一套 Adapter SDK | 延后——V1 只有网页等少量真实适配器；达到至少三种新来源且重复模式稳定后再抽取 |
| E. Agent 直接写表或长期挂起 Graph 等审核 | 否决——绕过领域校验，且跨重启状态与业务事实混淆 |
| F. 默认上 sqlite-vec / Qdrant | 否决——现有 FTS+Concept 基线尚未证明不足；先评测再承担依赖、Embedding 成本与隐私税 |

## Consequences

- `/library` 顶层固定为「全部 / 资料来源 / 学习记录 / 学习资产」，次级筛选只展示真实支持的类型；右侧 Inspector 按来源、Record、资产动态展示详情、相关内容和 AI 解读，不增加讨论域或重复编辑器。
- 统一检索能力可被课程、知识空间、项目、研究和后续 Agent 复用，但这些消费者不能绕过范围、生命周期和引用校验。
- 导出 / 备份必须包含 LibraryItem 事实、关系与本地快照；FTS / 向量索引可重建，不作为不可替代备份内容。
- 发布零容忍门禁包括：范围泄漏、无锚点引用、归档/删除内容被召回、数据丢失、未经确认写入、未经同意向外部模型发送来源片段。
