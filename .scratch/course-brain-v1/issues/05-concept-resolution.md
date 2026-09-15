# CB-05 — Concept Resolution：归一化匹配 / 合并建议 / 审核操作 / 正式概念保护

**What to build:** 审核闭环后端：`apply-review` 批量端点（confirm/重命名确认/merge/dismiss）+ 构建期相似度合并建议（语义相似只产生建议，不自动合并）。

**Blocked by:** CB-04。

**Status:** done

**后端**

- [x] 相似度建议：候选与既有 CONFIRMED 概念的确定性相似度量（编辑距离/token 重叠阈值），超阈值在候选上标注 merge 建议（suggested_target_id），不自动合并（实施拍板：**读取期派生**——spec 数据合同 concepts 表无此列，避免迁移 0024 与建议悬空；编辑距离相似度阈值 0.8 / token 重叠率阈值 0.5，目标取最高分平分按名称定序；列表与详情响应带 suggested_target_id/name）
- [x] `apply-review(course_id, decisions[])`：`confirm`（CANDIDATE→CONFIRMED，可选重命名——重命名走归一化撞名检查）/ `merge`（候选并入目标：record_concepts 迁移（UNIQUE 冲突时计数合并：evidence_count 相加、relevance 取 max、first_start_ms 取最早、KP 桥回填）、锚点链接迁移到目标概念（同锚点同关系去重）、候选置 ARCHIVED）/ `dismiss`（候选→ARCHIVED）；跨课程目标 404；目标概念必须 CONFIRMED；decisions 单事务原子应用，重复 concept_id 在 Pydantic 边界 422；返回刷新后快照
- [x] 正式概念保护：任何审核/重建路径不可修改 CONFIRMED 的 canonical_name/description（编辑概念端点 V1 不提供，手动删除/归档走 `archive_concept`——CONFIRMED→ARCHIVED，需二次确认语义=前端对话框职责，后端普通端点；归档同步清 FTS 索引）
- [x] 待归档派生：CONFIRMED 且 record_concepts 全失效（记录软删/删除）→ 概念列表/详情标 stale_archivable 徽章，不自动改状态（查询时派生；零出现映射如手动创建不算待归档）
- [x] 测试：重命名撞名 409、合并后 record/anchor 映射完整且候选退役、跨课程合并 404、重建不覆盖确认结果（重跑 worker 断言 canonical_name 不变）、dismiss 后重建同候选重建为 CANDIDATE（可再审）；另补 confirm 重命名成功且 FTS 可检索、建议展示与目标归档后消失、stale_archivable 三态、非法决策（非候选确认/自并/空 decisions 422）

**门禁**

- [x] 后端四门禁全绿；提交：`feat(backend): 实现 Concept 审核闭环与正式概念保护（F4 CB-05）`
- 实施备注：确认后 source 保持 AI_EXTRACTED 不变（来源口径=溯源，status 已表达确认态）；新错误码 `COURSE_BRAIN_CONCEPT_STATE_INVALID` 409；零迁移（13 处 user_version 断言未动）
