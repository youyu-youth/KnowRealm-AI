# 06 - AI 总结与 HITL

> Wave: A ｜ PRD: §4.4.1 / §6.1 / §6.2 ｜ 决策引用: #27 #36 #43 #46

## 功能描述 / 目标

产品唯一自动触发点的 AI 产出：转写完成后自动生成结构化总结，经人工确认（HITL）落定并解锁全部后续 AI 能力。Wave A 出口线的核心环节。

## 功能范围

**做**：
- CONTENT_PROCESSING 完成且已选课 → 自动触发（含 11 的升级触发，走同一管线）
- 结构化输出：课程主题（一句话）+ 摘要（500~1000 字）+ 分点结构（Pydantic Schema 校验入库）
- HITL 循环：生成 → 展示 → 【确认】（解锁后续按钮）/【调整】（输入反馈重新生成，次数不限）
- 跨重启 / 隔天恢复：LangGraph interrupt + checkpointer（应用重启后未确认总结可继续处理）
- 版本链：每次生成记录 model / prompt_version / latency / token / version_no，可回溯
- 长转写分级：≤3 万字单次生成；超过按语义段落分块 map-reduce，禁止静默截断（#36）
- 用户编辑转写文本后可基于新文本重新触发（编辑入口在 04）
- SUMMARY_CONFIRMED 事件落 learning_events（幂等键，#43）
- llm_call_logs 埋点接入（P0-07 骨架首个消费者，工厂层统一埋点）
- 总结质量黄金样本 20 条 + 人工评审 checklist 建立（含长转写回归样本，#46）

**不做**：
- 知识点 / 习题 / Todo 等后续产物（各自 plan）、联网工具（红线 #11 禁止）

## 核心业务流程

转写完成 → SUMMARY_PROCESSING（生成，提交 2s 内返回 job_id）→ SUMMARY_READY（HITL 待确认，进今日页待办）→ 确认 → COMPLETED + 事件落表 + 解锁后续；调整 → 反馈重生成（不限次）

## 关键业务规则

- 确认结果与版本链落业务表（ai_summaries），Checkpoint 只存运行态
- 生成 90s 超时 → FAILED 可重试；提交 2s 内返回 job_id 且 processing_jobs 可查询（#27）
- AI 上下文必含课程 learning_context / education_stage / depth（升级强制先归类的根因）
- prompt 版本化；prompt 与输出全文不进日志

## 前置依赖

- 04、05（音频与文档两条内容来源就绪）

## 验收标准（出口线）

- [ ] 真实课堂录音当日走通：转写完成 → 总结自动出 → 调整一次（如"更简洁"）→ 确认 → 状态 COMPLETED、后续按钮解锁
- [ ] 重启应用后，未确认的总结可继续确认（跨重启恢复）
- [ ] 3 万字以上长转写无截断（黄金样本回归通过）
- [ ] SUMMARY_CONFIRMED 事件落表且幂等键唯一
