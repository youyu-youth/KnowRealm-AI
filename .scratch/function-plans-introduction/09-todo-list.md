# 09 - Todo 清单

> Wave: A ｜ PRD: §4.4.2（红线 #9）

## 功能描述 / 目标

Record 级课堂任务清单：AI 从总结中生成待办，用户手动增删改并勾选完成——最轻的后续 AI 资产，独立小闭环。

## 功能范围

**做**：
- 总结确认后按需 AI 生成 Todo 建议
- 手动增 / 删 / 改条目
- TODO / DONE 状态勾选切换
- 清单挂记录详情 tab（挂 02 壳）

**不做**：
- Learning Plan Item（目标级计划项，P6）、Autopilot Action（P6）——三表分立不合并（红线 #9）
- Todo 不产生 learning_events（不在 MVP 四事件内，#43）

## 核心业务流程

总结已确认 → AI 生成建议 Todo → 用户增删改 → 勾选完成 → 状态持久

## 关键业务规则

- Todo 是 Record 级实体，只属于一条学习记录
- 编辑保存最后写入生效（sidecar 单写者，无并发冲突——数据模型 v2.2 未为 Todo 设置乐观锁列）
- AI 生成是建议：落库前经用户确认编辑（HITL 精神，弱于总结的强确认）
- AI Todo 批次绑定 `summary_id`；Transcript/Summary 换代不自动删除既有 Todo，确认新批次后仅将旧 AI 批次标记 SUPERSEDED，手工项不受影响

## 前置依赖

- 06（总结确认解锁）

## 验收标准（出口线）

- [ ] 确认总结后可生成 Todo 建议
- [ ] 手动新增 / 删除 / 编辑条目生效
- [ ] 勾选完成状态持久，重启后保持
- [ ] 重新生成候选期间旧 Todo 仍生效；确认新批次后旧 AI 批次 SUPERSEDED，手工 Todo 保留
