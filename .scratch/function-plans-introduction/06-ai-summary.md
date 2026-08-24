# 06 - AI 总结与 HITL

> Wave: A ｜ PRD: §4.4.1 / §6.1 / §6.2 ｜ 决策引用: #27 #36 #43 #46

## 功能描述 / 目标

产品唯一自动触发点的 AI 产出：转写完成后自动生成结构化总结，经人工确认（HITL）落定并解锁全部后续 AI 能力。Wave A 出口线的核心环节。

## 功能范围

**做**：
- 存在 Transcript、Record=SUMMARY_PENDING、课程存在且 ACTIVE → 创建 Summary Job 并自动触发（含 11 的升级触发，走同一管线）；05 只提供输入契约，不生成 Summary
- 结构化输出：课程主题（一句话）+ 摘要（500~1000 字）+ `{sections:[{heading,points:string[]}]}` 分点结构（Pydantic Schema 校验入库）
- HITL 循环：生成 → 展示 → 【确认】（解锁后续按钮）/【调整】（输入反馈重新生成，次数不限）
- 跨重启 / 隔天恢复：LangGraph interrupt + checkpointer（应用重启后未确认总结可继续处理）
- 版本链：每次生成记录 model / prompt_version / latency / token / version_no，可回溯
- 长转写分级：≤3 万字单次生成；超过按语义段落分块 map-reduce，禁止静默截断（#36）
- 每个 Summary 绑定生成时的 `transcript_source_version`；写回前再次校验仍为当前版本
- 用户编辑 Transcript 后旧 Summary 标记 SUPERSEDED、Record 回 SUMMARY_PENDING；仅在用户明确触发后基于新版本重新生成（编辑入口在 04）
- SUMMARY_CONFIRMED 事件落 learning_events（幂等键，#43）
- llm_call_logs 埋点接入（本 plan 首个消费者，工厂层统一埋点）
- 最小单一 LLM Provider 配置与连接测试；首次真实总结前按供应商身份取得外部处理同意，缺配置/同意不建 Job、不批量扫描待总结 Record
- 总结质量黄金样本 20 条 + 人工评审 checklist 建立（含长转写回归样本，#46）

**不做**：
- 知识点 / 习题 / Todo 等后续产物（各自 plan）、联网工具（红线 #11 禁止）

## 核心业务流程

Transcript 已存在 + Record=SUMMARY_PENDING + 课程 ACTIVE → SUMMARY_PROCESSING（生成，提交 2s 内返回 job_id）→ SUMMARY_READY（HITL 待确认，进今日页待办）→ 确认 → COMPLETED + 事件落表 + 解锁后续；调整 → 反馈重生成（不限次）

## 关键业务规则

- 确认结果与版本链落业务表（ai_summaries），Checkpoint 只存运行态
- 单次 LLM 请求 90s 超时；长文 Job 可包含多次请求。初次失败 → FAILED，调整失败保留上一版 SUMMARY_READY；不自动付费重试，手动重试复用失败 Job。提交 2s 内返回 job_id 且 processing_jobs 可查询（#27）
- AI 上下文必含课程 learning_context / education_stage / depth（升级强制先归类的根因）
- Summary Job 创建前再次校验课程仍为 ACTIVE；05/04 内容处理期间课程被归档时保留 Transcript，但不触发 AI
- Summary 写回前比较 `transcript_source_version`；版本已变化则丢弃迟到结果，不覆盖当前 Transcript 对应的总结状态
- prompt 版本化；prompt 与输出全文不进日志
- 每次 LLM 生成对应一条 Summary Job；Graph thread 使用 `summary-{record_id}-source-{source_version}`，避免新 Transcript 恢复旧 interrupt

## 前置依赖

- 05（提供首个真实 Transcript + SUMMARY_PENDING 文档来源）或 04（后续音频来源）；开工时至少一条真实 Transcript 来源已接通，不要求两条来源同时完成

## 验收标准（出口线）

- [ ] 至少一条真实来源走通：Transcript + SUMMARY_PENDING → 校验 ACTIVE → Summary Job → 调整一次（如"更简洁"）→ 确认 → 状态 COMPLETED、后续按钮解锁；仅文档通过时不冒充录音链路完成
- [ ] 重启应用后，未确认的总结可继续确认（跨重启恢复）
- [ ] 3 万字以上长转写无截断（黄金样本回归通过）
- [ ] SUMMARY_CONFIRMED 事件落表且幂等键唯一
- [ ] 生成期间 Transcript 版本变化时迟到 Summary 不写回；显式重生成的新 Summary 正确绑定新 source_version
