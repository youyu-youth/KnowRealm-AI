# 工单导航

2026-10-13：用户已明确调用 `/implement` 实施 01～04。01 证据见 [implementation.md](../implementation.md)，02 现状/已知边界见 [02-implementation.md](../02-implementation.md) 与 `PROJECT_PROGRESS.md`；03 实现及后续修复见 [03-implementation.md](../03-implementation.md)；04 固定上下文证据见 [04-implementation.md](../04-implementation.md)。05～06 尚未实施，完整真实模型/桌面验收保留 06。

| 工单 | 交付 | 阻塞 |
| --- | --- | --- |
| [01](01-model-budget-and-context-view.md) | 模型预算与独立页面查看 | 无 |
| [02](02-durable-conversation-compaction.md) | 自动摘要、额度与持久恢复 | 01 |
| [03](03-scoped-context-retrieval.md) | 历史、材料和工具结果受限取回 | 02 |
| [04](04-pinned-context-and-source-validity.md) | 固定内容与来源有效性 | 03 |
| [05](05-exclusion-reset-and-history-inclusion.md) | 排除、重置与旧历史纳入 | 04 |
| [06](06-upgrade-and-real-runtime-acceptance.md) | 升级回归与真实链路验收 | 05 |

依赖顺序：01 → 02 → 03 → 04 → 05 → 06。没有前后端分层票或额外纯基础重构票。每张功能票包含自己的真实 API/SQLite/Worker、相关自动化和 UI 接线验收；06 负责最终组合与真实模型/桌面，不补做前票应完成的恢复/权限逻辑。

## 规格覆盖导航

| 规格验收 | 主要闭环责任 |
| --- | --- |
| C01、C02 | 01；03 增加取回后的预算回归 |
| C03 | 01 建立预算；02 完成压缩阈值；04 验证固定超限 |
| C04、C05、C06、C07、C08 | 02；03 保留大结果及原文取回完整性 |
| C09 | 04 |
| C10、C11 | 05 |
| C12、C13 | 01/02 的快照与执行校验，04/05 的用户设置与竞态闭环 |
| C14 | 04 的固定 L1 链；05 的排除/重置/纳入链 |
| C15 | 03 的读取边界；05 的排除与段纳入过滤 |
| C16 | 02 的过程/等待；05 的设置后恢复 |
| C17 | 01 的页面/草稿；02/04/05 按各自功能延展 |
| C18 | 01～05 各增量兼容；06 的完整升级回归 |
| C19 | 01～05 每条外发及读取路径；06 的组合验收 |
| C20 | 03 的输出生命周期；06 的完整备份/迁移/删除组合 |

依据：[规格](../spec.md)。当前实施授权已覆盖 01～04，不自动实施 05/06或关闭父规格；权威 ADR 和术语变更须另按仓库提案流程批准。
