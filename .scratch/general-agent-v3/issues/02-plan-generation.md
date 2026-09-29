# 02 — 计划数据与生成确认链路

**What to build:** AI 生成学习计划并经用户确认落库。用户说"基于这门课的资料生成四周学习计划"，Agent 产出结构化草案（阶段划分、逐项内容、时长、理由）并以只读确认卡呈现（确认 / 放弃 / 重新生成）；确认后计划落库生效。以纯目标为起点（无资料）时返回建议学习内容与资料缺口清单。草案不持久化，关闭即弃。

**Blocked by:** 01 — 学习目标领域与对话制定

**Status:** ready-for-agent

- [ ] 迁移 0035 落地 `learning_plans`（(goal_id, plan_version) 唯一、status ACTIVE / SUPERSEDED / COMPLETED、effective_from / effective_to）与 `learning_plan_items`（plan_id、action_type 四类：STUDY_RECORD / PRACTICE_QUIZ / REVIEW_CONCEPT / CUSTOM、concept_id 可空、STUDY_RECORD 目标对象关联、priority、estimated_minutes、scheduled_date 按日、status、user_locked 默认 false、reason_json）
- [ ] 生成 Service：LLM 结构化草案（阶段 / 计划项 / 时长估算 / 逐项理由）；日期铺排与预算一致性由确定性校验与修正承担（不超期限、每日总量与 daily_minutes 相容）——脚本优先、LLM 次之
- [ ] 草案确认卡（**只读**版）：确认 / 放弃 / 重新生成；确认落库为 ACTIVE 版本（同一目标同时至多一个 ACTIVE 计划）；草案不持久化、learning_plans 仅确认时写入
- [ ] 目标起点无资料路径：返回建议学习内容＋资料缺口清单（对话卡呈现，引导补充资料）
- [ ] 基于库内资料生成时，复用现有检索把资料内容纳入生成上下文
- [ ] Agent 工具：get_plan（只读）、generate_learning_plan（草案，只读不落库）、confirm_plan（草案卡即确认闸门）
- [ ] prompt_version bump；计划生成黄金集骨架：评测文档两份 md＋评分脚本＋脱敏占位符＋用户采集流程说明（沿用研究会话模式；回归触发＝prompt 版本或模型变更）
- [ ] 测试：Service 生成与落库语义（草案零落库断言、ACTIVE 唯一）、排期确定性修正的黄金样本手算、路由集成测、Agent 工具确认行为；user_version 断言同步
- [ ] 门禁全绿：pytest（独立 basetemp）+ ruff + pyright + OpenAPI --check + 前端测试（确认卡组件）

参考：[spec.md](../spec.md) 计划生成与确认（User Stories 7~11）、生成确认与版本语义段。
