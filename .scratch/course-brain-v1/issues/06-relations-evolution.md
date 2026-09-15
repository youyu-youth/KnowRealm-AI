# CB-06 — Relation 候选与过期检测 / 失效清理

**What to build:** relation 审核操作（confirm/dismiss）+ 来源变化后的过期与失效清理。关系不过确认不进正式图谱；旧来源不参与检索；正式概念不因一次抽取缺失被删。

**Blocked by:** CB-05。

**Status:** todo

**后端**

- [ ] relation 审核：apply-review 增 `confirm_relation`（CANDIDATE→CONFIRMED）/ `dismiss_relation`（→DISMISSED）；端点或快照暴露 relation 候选列表（含 confidence/evidence_count）
- [ ] 过期检测：重建时既有 CONFIRMED relation 若两端概念仍 CONFIRMED 但本次构建零证据支撑→标记过期徽章（快照派生 stale 提示），不自动降级
- [ ] 失效清理：记录删除/软删→record_concepts 由 FK CASCADE/查询过滤失效；概念删除→relations CASCADE（FK 已保证）；课程删除→全 CASCADE
- [ ] 图谱视图数据：GET 快照含 CONFIRMED 概念邻接（节点+边一次取齐，供前端 ECharts）
- [ ] 测试：未确认 relation 不出现在正式邻接、记录软删后来源与计数即时失效、概念 ARCHIVED 后其 relation 不再参与检索/图谱、重建零证据不删 CONFIRMED relation

**门禁**

- [ ] 后端四门禁全绿；提交：`feat(backend): 实现概念关系候选审核与过期检测（F4 CB-06）`
