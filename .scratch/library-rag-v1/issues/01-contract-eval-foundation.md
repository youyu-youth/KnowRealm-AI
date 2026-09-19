# 01 — 契约与评测地基：冻结实施契约与真实黄金集

**What to build:** 实现开始前，把 spec 留白的全部实施级数值冻结成可执行契约：迁移编号与最终 Schema、OpenAPI 资源契约草案、真实语料黄金集与检索质量阈值、sqlite-vec 触发判据、Agent 工具预算。本票产出文档与可运行的评测资产，不改业务代码；后续工单不再重新讨论已定边界（ADR-0024/0025 与 spec 为准）。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] 冻结迁移编号（自 0026 起）与四张新表 DDL 终稿，逐列核对与数据模型 v3.0 一致；盘点全库 `supported_user_version` 断言同步点
- [ ] 冻结 OpenAPI 契约草案：统一 ingest 请求/响应（URL/文件/文本判别）、library 列表/详情/生命周期端点、提案确认/拒绝端点、RetrievalResult 三类结构、citations library 条目、LIBRARY_ITEM 会话创建
- [ ] 构建并冻结真实语料黄金集（含中文、英文、同义改写、跨 Course 同名概念、网页/文档/音频、归档/删除来源；合成+真实样料混合，标注期望来源与允许命中范围），落 `docs/evaluation/`
- [ ] 用黄金集测量 FTS + Concept 基线，记录 Recall@K、MRR、无答案准确率、引用正确率；据此冻结各项阈值与 sqlite-vec 触发判据（何种词汇错配失败 + 何种可测净增益才启用）
- [ ] 黄金集含英文内容对现有 jieba 分词链路的召回验证结论（是否需在实施票补英文分词处理）
- [ ] 冻结 Agent 工具预算数值（每轮工具调用次数、每次命中数、总上下文字符上限）

## 备注

- 本票是纯契约票：黄金集与阈值是 07 发布门禁的判据，也是 sqlite-vec 是否进入本波次的唯一依据。
