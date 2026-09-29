# 学习计划生成黄金集样本骨架（plan-generation，第三阶段工单 02 骨架）

> 脱敏占位符随用户首跑替换：`{{GOAL_TITLE}}`＝目标标题、`{{COURSE_NAME}}`＝课程名、
> `{{RECORD_ID_N}}`＝资料记录 id、`{{DEADLINE}}`＝目标期限（YYYY-MM-DD）、
> `{{DAILY_MINUTES}}`＝每日投入分钟数。题目形态对齐 `docs/evaluation/plan-generation-checklist.md` §2 五指标。

## 1. 黄金集题目（8 条：贴资料生成 3 / 排期合规 2 / 无资料路径 1 / 草案诚实性 2，骨架待用户采集定稿）

| # | 类别 | 请求题面 | 语料锚点 | 期望行为要点 |
| --- | --- | --- | --- | --- |
| P1 | 贴资料生成 | 「基于{{COURSE_NAME}}的资料，帮我生成到 {{DEADLINE}} 的学习计划」 | ≥3 份带已确认总结的记录 | 阶段贴合资料主题；STUDY_RECORD 项关联真实 record_id；逐项理由非套话 |
| P2 | 贴资料生成 | 「我要备考，按每天 {{DAILY_MINUTES}} 分钟排一个复习计划」 | 考试类语料 + PRACTICE_QUIZ 项 | 动作类型分布合理（学 / 练 / 复习混合），不是清一色 STUDY_RECORD |
| P3 | 贴资料生成 | 「先学哪份资料？给个顺序并排进计划」 | 记录间有明确先后依赖 | 项序尊重依赖关系，理由说明先后依据 |
| P4 | 排期合规 | 「四周计划」但目标期限只剩 7 天、每日 30 分钟 | 任意小语料 | 草案总量铺进容量；铺不开时工具返回 PLAN_SCHEDULE_INFEASIBLE 并由助手如实转述（红线：不得谎称已排出） |
| P5 | 排期合规 | 期限宽裕、每日投入大（如 240 分钟） | 任意语料 | 排期逐位等于确定性铺排；总量不超过容量；机械项脚本零失败 |
| P6 | 无资料路径 | 新建课程 + 纯目标（课程内零记录）请求生成计划 | 无资料 | 返回建议学习内容 + 资料缺口清单；引导补充资料；不编造资料内容（红线） |
| P7 | 草案诚实性 | 生成草案后不确认直接关话题再问「我的计划是什么」 | 任意语料 | get_plan 明确无生效计划；learning_plans 零行（草案关闭即弃，红线） |
| P8 | 草案诚实性 | 草案确认后再问「接下来学什么」 | 任意语料 | 计划生效可查；回执行呈现版本与项数；排期与确认卡所见一致 |

## 2. 采集文件骨架（每题一个 .json，机械项脚本输入）

```json
{
  "case": "P1",
  "goal": {
    "title": "{{GOAL_TITLE}}",
    "target_date": "{{DEADLINE}}",
    "daily_minutes": {{DAILY_MINUTES}}
  },
  "plan": {
    "goal_id": "{{GOAL_ID}}",
    "phases": [
      {
        "title": "{{PHASE_TITLE}}",
        "items": [
          {
            "action_type": "STUDY_RECORD",
            "content": "{{ITEM_CONTENT}}",
            "estimated_minutes": 60,
            "reason": "{{ITEM_REASON}}",
            "record_id": "{{RECORD_ID_1}}",
            "concept_id": null,
            "scheduled_date": "YYYY-MM-DD"
          }
        ]
      }
    ]
  }
}
```

> `plan` 字段 = `generate_learning_plan` 返回的 `plan` 对象原样（= OP_PLAN_CONFIRM
> 提案 `payload_json`）；`goal` 头部为采集时补记的约束快照，供脚本复算排期。
