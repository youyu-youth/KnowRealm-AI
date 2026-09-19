# 01 — 契约与评测地基：冻结实施契约与真实黄金集

**What to build:** 实现开始前，把 spec 留白的全部实施级数值冻结成可执行契约：迁移编号与最终 Schema、OpenAPI 资源契约草案、真实语料黄金集与检索质量阈值、sqlite-vec 触发判据、Agent 工具预算。本票产出文档与可运行的评测资产，不改业务代码；后续工单不再重新讨论已定边界（ADR-0024/0025 与 spec 为准）。

**Blocked by:** None — can start immediately.

**Status:** done（2026-09-19）

- [x] 冻结迁移编号（自 0026 起）与四张新表 DDL 终稿，逐列核对与数据模型 v3.0 一致；盘点全库 `supported_user_version` 断言同步点 → `contract.md` §1（DDL 终稿 + 断言盘点：C2 后 16 文件 23 断言全动态，0026 零同步；逐列核对发现并处置实施级调整 #3 = `favorite` 列 + 2 个补充索引，02 负责同步数据模型 v3.0）
- [x] 冻结 OpenAPI 契约草案：统一 ingest 请求/响应（URL/文件/文本判别）、library 列表/详情/生命周期端点、提案确认/拒绝端点、RetrievalResult 三类结构、citations library 条目、LIBRARY_ITEM 会话创建 → `contract.md` §2
- [x] 构建并冻结真实语料黄金集（含中文、英文、同义改写、跨 Course 同名概念、网页/文档/音频、归档/删除来源；合成+真实样料混合，标注期望来源与允许命中范围），落 `docs/evaluation/` → `library-rag-retrieval-baseline.md` §2/§3（20 查询 = 正例 17 + 负例 3；ARCHIVED 来源与真实 WEB 来源无法在 0026 前落地，激活时点在 §3.1 维度激活表，ARCHIVED 零召回为 07 硬门禁）
- [x] 用黄金集测量 FTS + Concept 基线，记录 Recall@K、MRR、无答案准确率、引用正确率；据此冻结各项阈值与 sqlite-vec 触发判据（何种词汇错配失败 + 何种可测净增益才启用） → 同文档 §4/§5（实测 Recall@8=0.941 / MRR=0.941 / 无答案=1.0 / 引用=1.0 / 泄漏=0；阈值 0.90/0.90/1.0/1.0/0；判定=不触发，1/17=5.9% 词汇错配未达 ≥3 条门槛）
- [x] 黄金集含英文内容对现有 jieba 分词链路的召回验证结论（是否需在实施票补英文分词处理） → 同文档 §6（结论=无需补：空白整词透传 + FTS5 unicode61 归一 + 连字符双侧一致；屈折缺口 reduce≠reduces 属词汇错配监测类，不改分词器；可执行归因断言在评测文件 en 维度测试）
- [x] 冻结 Agent 工具预算数值（每轮工具调用次数、每次命中数、总上下文字符上限） → `contract.md` §3（6 次/轮；evidence 8 + hints 4 + asset 8；单次载荷 4k + 每轮累计 12k 字符；quote 80 / 窗口 400）

## 备注

- 本票是纯契约票：黄金集与阈值是 07 发布门禁的判据，也是 sqlite-vec 是否进入本波次的唯一依据。
- **实施交付物**：`contract.md`（契约正本）+ `docs/evaluation/library-rag-retrieval-baseline.md`（黄金集与阈值正本）+ `backend/tests/test_library_retrieval_eval.py`（可复跑评测资产，6 测试全绿）。零业务代码改动。
- 双轴 code review（Standards + Spec）已执行并收敛：修复了评测文件冗余 client/重复序言、契约索引未入调整表、期望命中合计 26 vs 实测 25 口径、触发判据百分比口径；backend/AGENTS.md 过期断言行（"13 文件 == 25"）已随盘点更正。
- 全量门禁：pytest 601 绿 + 1 个 `test_server_process` 真实进程用例全量并发抖动（单跑 14/14 绿，与本次改动无关）；ruff/pyright 0 错。
