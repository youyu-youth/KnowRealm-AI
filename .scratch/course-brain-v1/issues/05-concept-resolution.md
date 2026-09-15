# CB-05 — Concept Resolution：归一化匹配 / 合并建议 / 审核操作 / 正式概念保护

**What to build:** 审核闭环后端：`apply-review` 批量端点（confirm/重命名确认/merge/dismiss）+ 构建期相似度合并建议（语义相似只产生建议，不自动合并）。

**Blocked by:** CB-04。

**Status:** todo

**后端**

- [ ] 相似度建议：候选与既有 CONFIRMED 概念的确定性相似度量（编辑距离/token 重叠阈值），超阈值在候选上标注 merge 建议（suggested_target_id），不自动合并
- [ ] `apply-review(course_id, decisions[])`：`confirm`（CANDIDATE→CONFIRMED，可选重命名——重命名走归一化撞名检查）/ `merge`（候选并入目标：record_concepts 迁移（UNIQUE 冲突时计数合并）、锚点链接迁移到目标概念、候选置 ARCHIVED）/ `dismiss`（候选→ARCHIVED）；跨课程目标 404；目标概念必须 CONFIRMED
- [ ] 正式概念保护：任何审核/重建路径不可修改 CONFIRMED 的 canonical_name/description（编辑概念端点 V1 不提供，手动删除/归档走 `archive_concept`——CONFIRMED→ARCHIVED，需二次确认语义）
- [ ] 待归档派生：CONFIRMED 且 record_concepts 全失效（记录软删/删除）→ 快照标 stale_archivable 徽章，不自动改状态
- [ ] 测试：重命名撞名 409、合并后 record/anchor 映射完整且候选退役、跨课程合并 404、重建不覆盖确认结果（重跑 worker 断言 canonical_name 不变）、dismiss 后重建同候选重建为 CANDIDATE（可再审）

**门禁**

- [ ] 后端四门禁全绿；提交：`feat(backend): 实现 Concept 审核闭环与正式概念保护（F4 CB-05）`
