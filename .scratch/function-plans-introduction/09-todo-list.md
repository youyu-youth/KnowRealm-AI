# 09 - Todo 清单

> Wave: A ｜ PRD: §4.4.2（红线 #9）｜ ADR: 0011

## 功能描述 / 目标

Record 级课堂任务清单：AI 从总结中生成待办，用户手动增删改并勾选完成——最轻的后续 AI 资产，独立小闭环。

## 功能范围

**做**：
- 总结确认后按需 AI 生成 Todo 建议（零参数一键生成，prompt 约束 3~8 条）
- 候选态修剪：DRAFT 候选可逐条编辑/删除，整批「采纳」或「丢弃」（KP 式）
- 手动增 / 删 / 改条目（tab 解锁后始终可用，不受总结门控）
- TODO / DONE 状态勾选切换（划线弱化展示，不过滤）
- 清单挂记录详情 tab（挂 02 壳，解锁条件同 Quiz：`record.status === "COMPLETED"`）

**不做**：
- Learning Plan Item（目标级计划项，P6）、Autopilot Action（P6）——三表分立不合并（红线 #9）
- Todo 不产生 learning_events（不在 MVP 四事件内，#43）
- 拖拽排序、DONE 过滤/折叠/统计

## 核心业务流程

总结已确认 → 一键生成（无参数）→ DRAFT 候选展示 → 用户逐条修剪 → 采纳整批 ACTIVE（旧 AI 批次 SUPERSEDED）→ 增删改 / 勾选 → 状态持久

## 关键业务规则

- Todo 是 Record 级实体，只属于一条学习记录
- 编辑保存最后写入生效（sidecar 单写者，无并发冲突——数据模型 v2.2 未为 Todo 设置乐观锁列）
- AI 生成是建议：候选态可逐条修剪——修剪不算接管，项仍属批次随采纳整体生效（HITL 弱于总结的强确认，KP 同构）
- **接管（ADR 0011）**：ACTIVE 的 AI 项被用户编辑内容或勾选 DONE 即脱离批次生命周期（generation_status 置 NULL），永不随批次换代；取消勾选不回退
- AI Todo 批次绑定 `summary_id`；Transcript/Summary 换代不自动删除既有 Todo，确认新批次后仅将旧 AI 批次中仍为 ACTIVE 的行标记 SUPERSEDED，手工项与被接管项不受影响
- 手动 CRUD 与总结确认解耦：仅「AI 生成」按钮走 blocked_reason 门控（SUMMARY_NOT_CONFIRMED / SUMMARY_SUPERSEDED / PROVIDER_NOT_CONFIGURED / CONSENT_REQUIRED，照抄 Quiz 枚举）
- 排序：手工新增与 AI 批次均追加列表尾部（sort_order 取最大值 +1）；DRAFT 候选单独区块，ACTIVE 项与手工项按 sort_order 混排一张清单

## 前置依赖

- 06（总结确认解锁）

## 验收标准（出口线）

- [ ] 确认总结后可生成 Todo 建议（零参数）
- [ ] 候选可逐条修剪，整批采纳 / 丢弃
- [ ] 总结未确认时手动新增 / 删除 / 编辑条目仍可用
- [ ] 勾选完成状态持久，重启后保持
- [ ] 重新生成候选期间旧 Todo 仍生效；确认新批次后旧 AI 批次 SUPERSEDED，手工 Todo 与被接管的 AI Todo 保留
