# 04 — 让删除、归档、重启与算法升级保持 Mastery 正确

**What to build:** 当学习者删除 Record、归档 Concept、重启应用或升级 Mastery 算法时，系统从仍有效的 Evidence 确定性恢复正确快照；上游 Event/Evidence 始终优先保存，派生计算故障不会造成学习事实丢失。

**Blocked by:** 02 — 让 Concept 作答形成可见的真实 Mastery.

**Status:** done

- [x] Record 软删除后，其历史 Event/Evidence 保留审计价值但立即退出有效 Mastery 集合，所有受影响 Concept 从剩余 Evidence 全量重算。
- [x] Archived Concept 保留历史 Mastery 与 Evidence，但退出活跃课程聚合且不接收新证据；重命名不改变快照归属。
- [x] Course 删除沿用现有 Record 删除纪律，Concept 被物理删除时派生快照清理，追加事实不被业务服务改写。
- [x] Mastery 重算失败不回滚已成功持久化的 Event/Evidence，并有结构化错误日志与有限重试。
- [x] 应用启动时识别缺失或算法版本过期的快照，并按 Concept 从有效 Evidence 重建；不增加新任务队列、死信表或增量加减账本。
- [x] 算法版本升级通过版本号与全量重建完成，不静默修改旧口径或混用不同算法结果。
- [x] 重复重建、应用重启和 Consumer 重扫保持幂等，同一 Evidence 不被重复计数。
- [x] 生命周期测试覆盖 Record 删除、Concept 归档、重命名、Course 删除、计算失败、缺失快照、版本过期与重复恢复。
- [x] 课程与 Concept Mastery API 在上述状态变化后返回正确覆盖率、列表和详情，不需要前端维护补丁状态。

## 实施备注（2026-09-18）

- **删除触发重算**：`RecordService.soft_delete` / `CourseService.soft_delete` 事务内从 `learning_events` 收集受影响 `concept_id`（事实源，含未消费事件），返回 `set[str] | None`（None=不存在）；由删除端点在事务提交后调 `MasteryService.recompute_concepts`（编排放路由层：service 持 session 会撞事务边界，路由组合跨域有 `SegmentService` 先例）。同步 await 是工单「立即重算」的正确实现——删除不产生事件，若交给 30 秒后台轮询则永不触发。
- **归档裁决（review 回改）**：详情端点维持 404（spec「归档保留快照但退出活跃查询」原句优先）；一度尝试放行 200 供审计查看，但 evidences 实时口径与历史快照自相矛盾（列表 4 条 vs 快照 3 条），回改。「保留历史」由 SQL 层证明：归档后新作答证据照常落库、快照数值停在归档时刻。归档不接收新证据由 `_recompute_concept` 的 CONFIRMED 门保证。
- **启动恢复**：`MasteryService.recover_snapshots` 扫描全部 CONFIRMED 概念，快照缺失或 `algorithm_version != ALGORITHM_VERSION` 即重建（幂等：版本一致零写入）；lifespan 在三个 backfill 之后同模式接线（失败记 `MASTERY_RECOVER_FAILED` 不阻断启动）。算法升级 = bump 版本号 + 启动全量重建。归档概念快照停留旧版本属「保留历史」语义，`algorithm_version` 字段自辨口径。
- **物理删除级联**：Concept 物理删除（墓碑清理 `DELETE FROM courses` 走 `concepts` CASCADE）→ `user_concept_mastery` 双 CASCADE 清理快照；`learning_events.course_id` 无 FK 保留事实，`learning_evidence.course_id` CASCADE 删除系 0021 既有设计，非本票改动。
- **既有覆盖**：重算失败不回滚证据 + 有限重试（3 次）+ 结构化日志、Consumer 重扫幂等、跨轮幂等已由票 02 的 `test_learning_consumer.py` / `test_mastery.py` 覆盖，本票未重复补测。
- **零 schema 变化**：无新端点无字段变更，OpenAPI 契约与前端零改动。
