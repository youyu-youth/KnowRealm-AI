# CB-01 — 检索基线评测：FTS + Concept 扩展召回（合成样例口径）

**What to build:** 用合成覆盖样例评测「FTS BM25 + Concept 扩展」的课程级查询召回，形成 sqlite-vec 是否进入本 Epic 的门禁结论。四类样例：同义词（可见性→MVCC）、简称/展开（TCP→传输控制协议）、跨记录统计（讲过几次 X 的去重计数）、原文定位（逐字 quote 回表）。

**Blocked by:** None（评测脚本依赖 CB-03 的 search 雏形则推后到 CB-03 完成时执行，结论文件不阻塞 CB-02 开工）。

**Status:** done

**执行口径（grill Q8 裁决）**

- [x] 评测样本 = 人工构造的合成课程语料（转写/文档分片各若干条，含同义词对/简称对/多记录重复概念），落 `backend/tests/` 或 `docs/evaluation/` fixture，不依赖用户真机数据
- [x] 评测维度：概念命中（Concept FTS top-k 是否含目标概念）、检索词扩展有效性（canonical_name 并跑对 BM25 召回的增益）、occurrences 按 record 去重正确性、逐字 quote 回表成功率
- [x] 结论文件 `docs/evaluation/course-brain-retrieval-baseline.md`：样例清单、通过率、失败归因；sqlite-vec 结论默认「延后」，若主要失败来自词汇不重合则升级 CB-VEC 工单（concepts.terms 列优先于引库）
- [x] 明确记录口径：合成样例达标 ≠ 真实语料达标；真实语料评测并入 CB-12 用户真机验收清单

**门禁**

- [x] 评测脚本可重复执行（pytest 内嵌或 scripts/），临时产物测试后删除
