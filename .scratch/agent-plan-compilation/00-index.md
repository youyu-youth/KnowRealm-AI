# 批量计划编译与延展：当前工单索引

日期：2026-10-12。用户最新决定：优先完成原报告③的架构优化，当前一张内部重构票已实施，源码提交 `1f3f70b`；验收见 [implementation.md](implementation.md)。

当前规格：[spec.md](spec.md)。阶段决策：[grill.md](grill.md)。

| 工单 | 阻塞于 | 交付 | 当前状态 |
| --- | --- | --- | --- |
| [01 收拢批量计划编译与延展的内部编排](issues/01-plan-compiler-refactor.md) | 无 | 两条入口共享解析、快照、步骤分类、序号映射与落库；现有外部格式和行为保真 | done |

无需三票集成分支或后续功能才能验收本票。完成本票只表示内部编排收敛，不表示完整协议/审批升级完成。

后续阶段：新类型化协议、严格版本批准、确定性重新预览等目标仍保留在 [upgrade-spec.md](upgrade-spec.md)，当前不实施。原拆分已停止执行，均为 needs-info，工程策略与依赖需在内部重构后重核：

- [原01 类型化新建批量任务](deferred/01-typed-new-batch-plan.md)
- [原02 固定版本计划延展](deferred/02-fixed-version-plan-extension.md)
- [原03 旧计划重新预览与升级恢复](deferred/03-repreview-and-upgrade-recovery.md)

已核实的 AUTO_APPROVE 自动延展例外及旧卡合并/终态后新建行为仍存在，第一阶段不修正，也不宣称其符合 ADR-0026。修正属于后续独立行为变更。

当前工单验收项已完成，代码与本轮运行证据见实施记录；保留自动化、替身、真实 SQLite/Worker、真实模型/Tauri 和未验证项的区分。
