# 04 — 让删除、归档、重启与算法升级保持 Mastery 正确

**What to build:** 当学习者删除 Record、归档 Concept、重启应用或升级 Mastery 算法时，系统从仍有效的 Evidence 确定性恢复正确快照；上游 Event/Evidence 始终优先保存，派生计算故障不会造成学习事实丢失。

**Blocked by:** 02 — 让 Concept 作答形成可见的真实 Mastery.

**Status:** ready-for-agent

- [ ] Record 软删除后，其历史 Event/Evidence 保留审计价值但立即退出有效 Mastery 集合，所有受影响 Concept 从剩余 Evidence 全量重算。
- [ ] Archived Concept 保留历史 Mastery 与 Evidence，但退出活跃课程聚合且不接收新证据；重命名不改变快照归属。
- [ ] Course 删除沿用现有 Record 删除纪律，Concept 被物理删除时派生快照清理，追加事实不被业务服务改写。
- [ ] Mastery 重算失败不回滚已成功持久化的 Event/Evidence，并有结构化错误日志与有限重试。
- [ ] 应用启动时识别缺失或算法版本过期的快照，并按 Concept 从有效 Evidence 重建；不增加新任务队列、死信表或增量加减账本。
- [ ] 算法版本升级通过版本号与全量重建完成，不静默修改旧口径或混用不同算法结果。
- [ ] 重复重建、应用重启和 Consumer 重扫保持幂等，同一 Evidence 不被重复计数。
- [ ] 生命周期测试覆盖 Record 删除、Concept 归档、重命名、Course 删除、计算失败、缺失快照、版本过期与重复恢复。
- [ ] 课程与 Concept Mastery API 在上述状态变化后返回正确覆盖率、列表和详情，不需要前端维护补丁状态。

