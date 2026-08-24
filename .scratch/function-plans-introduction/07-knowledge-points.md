# 07 - 知识点提取

> Wave: A ｜ PRD: §4.4.2 ｜ 决策引用: #43（红线 #9）｜ 2026-08-24 grill 定稿：16 项裁决回写（候选即落库 DRAFT / 单列状态 / 无 Graph / 批次溯源入 job 等）

## 功能描述 / 目标

总结确认后按需触发的第一项后续 AI 能力：从转写 + 总结中提取知识点（KP），经用户筛选编辑后确认保存为 Record 级学习资产。

## 功能范围

**做**：
- 总结确认后按需触发（记录详情 → 知识点 tab）；生成候选即落库为 DRAFT 行（batch_id 分组），跨重启隔天可继续筛选
- 结构化输出：名称 / 详情 / 标签 / 重要度 / 来源锚点列预留 P1 恒空（Pydantic 严格校验，违规 job FAILED 不自动修正）
- HITL：候选批次内删除 / 编辑；手工补充 = 立即落库的独立行（batch_id 空），确认前后同一套行为；确认后仍可编辑 / 软删 / 补充（不再落事件）
- KNOWLEDGE_CONFIRMED 事件落 learning_events（一次确认动作一事件，幂等键，#43）
- 重新生成：基于当前已确认 Summary 生成新候选批次；在途 DRAFT 至多一批（再生成 409），提供「丢弃候选」；确认新批次后旧 AI 批次才置 SUPERSEDED，已保存行永不因换代删除
- 长转写分级：转写 ≤3 万字全文 + 已确认 Summary 入 prompt；超过仅送 Summary 且 UI 明示「基于总结提取」（非静默截断）
- 知识点 tab 落地；02 壳占位 tab 一次对齐 PRD 命名（知识点 / 习题 / 复习 / Todo / Ask AI，其余保持禁用）
- 生成进度复用 processing_jobs 轮询，不加新通道

**不做**：
- 知识点解释对话入口（归 12，@知识点模式）、Concept 抽取与对齐（P3）、跨记录 KP 汇总视图、SUPERSEDED 批次历史查看 UI（`?include=superseded` API 可查即回溯）

## 核心业务流程

总结已确认（Record=COMPLETED）→ 生成（DRAFT 候选落库）→ 用户筛选（删 / 改 / 补）→ 确认保存（DRAFT→ACTIVE、旧 AI 批次→SUPERSEDED、事件落表）→ 知识点 tab 展示；丢弃候选 → 回初始态可再生成

## 关键业务规则

- **KP 是 Record 级资产，≠ Concept（Course 级）**——不得混同或互并（红线 #9）
- 触发前提 = 存在当前 CONFIRMED Summary；生成与确认均校验课程仍 ACTIVE，归档 409；缺 Provider / 外部处理同意 409 不建 Job（沿用 06）
- 单列状态 `generation_status`（DRAFT / ACTIVE / SUPERSEDED）+ 软删；AI / 手工由 batch_id 与 generated_from_summary_id 区分（数据模型 v2.2 已同步修订，对齐 quizzes 单列）
- AI 批次绑定触发时的 `generated_from_summary_id`；确认时该 Summary 仍须 CONFIRMED，已 SUPERSEDED 则 409 引导丢弃后基于新总结重生成
- Transcript 换代：已保存 KP 保持可见可编辑，重新生成入口等新 Summary 确认后解锁；不自动删除或改状态任何已保存 KP
- 不建 LangGraph Graph（红线 #2）：普通 async worker 单次结构化生成，job_type=KNOWLEDGE_EXTRACTION，每 Record 至多一个活跃 job（部分唯一索引仿 0008 SUMMARY）
- 候选数量由 AI 按内容密度决定（目标 5~15 条，Schema 上限 20 条）；importance 1~5（REAL 列）UI 五星可编辑；tags ≤5 个
- 事件契约：source_type=KNOWLEDGE_BATCH、source_id=batch_id、幂等键 `knowledge-confirmed:{batch_id}`、metadata={batch_id, confirmed_count, generated_from_summary_id}；重复确认返回现状；确认后的手工增删改不落事件
- 批次溯源（model / prompt_version / 候选条数）记入 processing_jobs.result_json，KP 表不加列、不建批次表
- AI 上下文必含课程 learning_context / education_stage / depth（沿用 06）；prompt 版本化；prompt 与输出全文不进日志

## 前置依赖

- 06（总结确认解锁；Provider / 同意 / llm_call_logs / jobs 轮询均已就绪）

## 验收标准（出口线）

- [ ] 确认总结后生成知识点：候选落 DRAFT，确认后列表在详情 tab 可见
- [ ] 删除 2 条、修改 1 条、手动补充 1 条后确认保存生效（手工条目即时落库，批次确认成功）
- [ ] KNOWLEDGE_CONFIRMED 事件落表且幂等（重复确认不重复落）
- [ ] 重新生成候选期间旧结果仍 ACTIVE；确认新批次后旧 AI 批次 SUPERSEDED 且 `?include=superseded` 可回溯
- [ ] 在途 DRAFT 时再生成 409；「丢弃候选」软删整批后可重新生成
- [ ] 转写编辑换代后：已保存 KP 保留可见，在途候选确认被 409 阻止并引导重生成
- [ ] 3 万字以上转写仅基于总结提取且 UI 明示
