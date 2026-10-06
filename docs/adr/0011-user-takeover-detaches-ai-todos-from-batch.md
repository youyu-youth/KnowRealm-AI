# 用户接管使 AI Todo 项脱离批次生命周期

Todo 候选批次采纳后，用户对某 AI 项的编辑内容或勾选 DONE 视为**接管**：`generation_status` 置 NULL，该行退出批次生命周期；此后新批次采纳只把仍为 ACTIVE 的旧批次行置 SUPERSEDED，被接管项与手工项（`generation_status` 天然为 NULL）一样保留。选它是因为 todo_items 无 is_modified 列（数据模型 v2.2 定稿，零新列），NULL 让 SUPERSEDED 的 UPDATE 谓词天然跳过，且「用户做完的事不随换代消失」。术语见 GLOSSARY.md「接管」。

## Considered Options

- 加 is_modified 列标记用户改写——需改动已定稿的数据模型，且与 NULL 方案信息等价（NULL + source=AI 已可标识被接管项）。
- 编辑时把 source 翻 MANUAL——丢失「来自 AI 建议」的溯源事实，batch_id 仍挂着会与批次查询互相干扰。
- 被接管项照样 SUPERSEDED——违背数据模型 v2.2「手工/用户修改项不自动换代」的注释，且已完成项会从清单隐没。

## Consequences

- 规则难逆转：行一旦置 NULL，数据上无法区分接管时点，反转规则无法回放（其旧批次可能已 SUPERSEDED）。
- 勾选 DONE 即接管意味着：反复勾选/取消不改变已脱离批次的事实（幂等，不可回退）。
- 候选态（DRAFT）的编辑属于修剪，不触发接管——项仍属批次、随采纳整体生效（与知识点批次同构）。
