# 01 — 生成候选批次与档位记忆

**What to build:** 总结已确认（Record=COMPLETED）的学习记录在「习题」页签按需生成候选习题：勾选题型（选择 / 判断 / 简答）与总题数档位（3 / 5 / 10，默认 5、记住上次选择），异步生成**恰好按档位**出题（所选题型各 ≥1、字段完整），成功即整批落库为 DRAFT 候选并只读审阅（跨重启可续看）；不满意可丢弃重来；前置不满足给诚实引导与 409。（裁决与契约细节见 `.scratch/quiz/spec.md`）

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] 迁移新建 `quizzes` 表：`generation_status` 单列（DRAFT / ACTIVE / SUPERSEDED）、软删列、**作答三列**（`user_answer_json` / `answer_result` 可空 / `answered_at`）、question_type 三枚举与 difficulty 三档；**不建** model / prompt_version / quality_score / cognitive_level / concept_id / source_anchor_id 列（溯源记 Job result_json，07 先例）；`processing_jobs.job_type` 新增 QUIZ_GENERATION；每 Record 至多一个 PENDING/RUNNING 习题任务的部分唯一索引生效
- [ ] 生成前置校验：存在当前 CONFIRMED Summary、课程 ACTIVE、Provider 已配置、外发同意有效——任一缺失返回 409 不建 Job，读端给对应 blocked_reason；已有在途 DRAFT 或活跃 Job 再生成 409（并发由部分唯一索引兜底）
- [ ] 应用工厂提供习题生成模型注入缝（镜像 KP 模型缝）；worker 单次结构化生成（无 LangGraph），prompt 仅含课程上下文 + 已确认 Summary；严格 Pydantic 校验（总数严格 = 档位、所选题型各 ≥1、单选 3~5 选项、判断题「对 / 错」两项与选择题同构、简答 options 空且 correct_answer 为参考答案、字数上限就地约束）——违规 Job FAILED（LLM_OUTPUT_INVALID），不自动修正；手动重试复用失败 Job；90 秒超时
- [ ] 成功即在单事务落整批 DRAFT 行（batch_id = 生成 Job id、generated_from_summary_id 绑定）；批次溯源（model / prompt_version / 条数 / 题型构成）写 Job result_json；llm_call_logs 经工厂层埋点；prompt 与题目正文不进日志
- [ ] worker 领取 / 发布两阶段复核 Summary 仍 CONFIRMED，失效则 CANCELLED
- [ ] 丢弃候选：软删整批 DRAFT，回初始态可再生成
- [ ] 「习题」页签从禁用占位转为真实功能：按 record COMPLETED 解锁、未确认总结时空态引导指向总结页签、生成对话框（题型多选 + 档位单选、默认读 `quiz_last_count`、提交后写回）、任务轮询进行中态、失败重试、候选只读列表
- [ ] OpenAPI → api-types 重新生成，前端类型全部来自生成物；后端 ASGI + 真实迁移库 + Fake 模型全栈测试与桌面 MSW 测试通过（含 409 矩阵、Schema 违规 FAILED、恰好按档位出题且题型各 ≥1）
