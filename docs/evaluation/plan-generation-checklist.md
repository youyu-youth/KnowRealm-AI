# 学习计划生成黄金集口径与采集流程（plan-generation，第三阶段工单 02 骨架）

> 工单 02 ｜ 计划数据与生成确认链路 ｜ 2026-09-29 ｜ 沿用研究会话评测模式（评测资产随票前置）
> 回归触发：计划生成 prompt 版本 bump（现值 `learning-plan-v1`，`backend/app/modules/learning_plan/generation.py`）或模型变更。
> 执行前提：需配置真实 LLM provider；草案采集由用户真机执行（沿用「真机验收由用户执行」纪律，agent 不代跑、不代标）。

## 1. 用途与口径

- 目的：冻结学习计划生成的黄金题目集与门禁，作为 prompt / 模型回归时排期合规性、
  资料贴合度与草案诚实性没有劣化的判据。
- 被测链路 = `generate_learning_plan` 只读生成全链路：资料聚合（记录标题 + 已确认总结 +
  COURSE 范围检索引文）→ LLM 结构化草案（阶段 / 项序 / 时长 / 理由）→ 确定性排期铺排。
- 日期不进 LLM 契约：排期由 `learning_plan/scheduling.pack_schedule` 确定性分配，
  机械可判部分由评分脚本逐位复算（见 §4），这是「脚本优先、LLM 次之」的评测锚点。

## 2. 指标门禁

| 指标 | 定义 | 门禁 | 评分口径 |
| --- | --- | --- | --- |
| 排期合规率 | 草案排期逐位等于确定性铺排、不超期限、每日总量与每日投入相容（单项时长不得超过每日预算，超出判不可行） | 100% | 机械可判：`score_plan_generation.py` 逐题复算（红线指标） |
| 结构完整率 | 阶段 2~5 个、每项含 action_type / content / estimated_minutes / reason 且非空 | 100% | 机械可判：同脚本 |
| 资料贴合度 | STUDY_RECORD 项关联的 record_id 属于本课程资料清单，内容与资料主题相关 | ≥ 90% | 人工 rubric：逐项核对 record 归属与相关性 |
| 理由可解释性 | 逐项理由能说明安排依据（为什么现在学 / 为什么这个时长），无套话 | ≥ 80% | 人工 rubric |
| 草案诚实性 | 草案未确认即关闭零落库、无资料路径如实返回建议与缺口（不编造资料内容） | 100% | 红线指标：出现把模型常识表述为资料事实即整轮判负 |

观测项（不设门禁，记录备查）：单题生成耗时、草案项数、总量与期限容量的占比。

## 3. 用户采集流程

1. 用户真机配置 LLM provider；语料对齐 `plan-generation-samples.md` 各题「语料锚点」
   列（或替换为自有语料，判分口径不变）。
2. 逐题在对话中发起生成请求（题面 = 样本文件的问题行）；拿到草案后
   **不要确认**，先采集草案 JSON：
   - 方式 A（推荐，草案即提案载荷）：`SELECT payload_json FROM agent_proposals
     WHERE proposal_type='OP_PLAN_CONFIRM' AND status='PENDING'
     ORDER BY created_at DESC LIMIT 1;`
   - 方式 B：复制 `generate_learning_plan` 工具返回里的 `plan` 对象。
3. 把每题存为一个 `.json` 采集文件（形态 = 样本文件的「采集文件骨架」，含 goal 约束
   头部与 plan 载荷），脱敏占位符按题替换（`{{...}}`）。
4. 机械项跑分：`uv run python -m scripts.score_plan_generation <采集文件或目录...>`
   （`backend/` 下执行）；人工项按 §2 rubric 逐题评。
5. 任一门禁未达 → 按「回归触发」定位（生成 prompt bump / 模型变更）修复后重跑；
   结果与日期回写本节。

### 复跑记录

| 日期 | 生成 prompt 版本 | 模型 | 机械项结果 | 人工项结果 | 备注 |
| --- | --- | --- | --- | --- | --- |
| （待用户真机首跑） | learning-plan-v1 | — | — | — | 首跑后冻结阈值复核（研究会话先例） |
