# 08 - 习题生成与作答

> Wave: A ｜ PRD: §4.4.2 ｜ 决策引用: #33、#43 ｜ 2026-08-25 grill 定稿回写（总题数档位 / 一题一答 / 作答三列在行 / 事件契约 / 换代联动 / 砍列）。作答形态（逐题 + 简答自评）系本 plan 定稿——PRD 无"逐题"字样，原引"Q10 定稿"实为决策 #20（属 15 的 AI 评分域），引用已修正

## 功能描述 / 目标

总结确认后按需生成习题，并以逐题模式作答：客观题（选择题 / 判断题）提交即自动判分；简答题先提交自己的作答，再对照参考答案自评对错。组卷测验与 AI 语义评分留给 15（Wave B）。

## 功能范围

**做**：
- 题型多选（选择题 / 判断题 / 简答题）→ 总题数档位 3 / 5 / 10（默认 5；记忆于 settings.quiz_last_count，键与 13 设置页共享）→ 异步生成
- 必含字段：题干 / 选项 / 答案 / 解析（简答题为参考答案）；Pydantic 严格校验，违规重试后仍失败则 job FAILED
- 逐题作答：客观题提交即自动判分；简答题必须先提交非空作答才显示参考答案，自评二态（对 / 错）；可中途离开续答
- QUIZ_ANSWERED 事件逐题落 learning_events（两种题型都落，对错已知时才发，幂等键，#43）
- 重新生成：基于当前已确认 Summary 生成候选批次；候选期间旧题仍可作答；确认新批次后旧 AI 题目批次才置 SUPERSEDED，既有作答与事件永不删除
- 习题 tab 落地（解锁 = record COMPLETED）；批次完成态展示 + 轻量计数（答对 X / Y）

**不做**：
- 组卷 / 测验模式 / AI 语义评分 / 低置信复核标记（15，Wave B）、错题本
- 候选题剔除与编辑（题目不佳的唯一解法 = 丢弃候选 / 重新生成）、确认后单题删除与编辑、手工出题
- 多选题与 PARTIAL 结果（留 15）

## 核心业务流程

总结已确认（record=COMPLETED）→ 选题型与总档位 → 异步生成（DRAFT 候选落库）→ 整批采用（DRAFT→ACTIVE、旧 AI 批次→SUPERSEDED，不发事件）→ 逐题作答（客观判分 / 简答自评）→ QUIZ_ANSWERED 逐题落表 → 完成态展示；丢弃候选 → 回初始态可再生成

## 关键业务规则

- 触发前提 = 存在当前 CONFIRMED Summary（查询前置，同 06/07，非事件驱动）；生成与确认均校验课程 ACTIVE、Provider 与外部处理同意（沿用 06/07，缺则 409 不建 job）
- 生成输入 = 仅当前已确认 Summary 文本（无 input_mode 分叉；转写级细节题留 Wave B）；AI 上下文含课程 learning_context / education_stage / depth（沿用 06）；prompt 版本化，prompt 与输出全文（含题目正文）不进日志
- Schema：一次 LLM 调用混合产出；items 总数严格 = 所选档位（上限 10）；题型构成由 AI 定，所选题型至少各 1 道；选择题单选（选项 3~5 个，correct_answer = 正确项下标）；判断题 options 固定「对 / 错」两项（与选择题同构、判分统一）；简答题 options 空、correct_answer = 参考答案；difficulty 由 AI 输出（EASY / MEDIUM / HARD）；字数上限由 Schema 就地约束
- 异步全仿 KP：job_type=QUIZ_GENERATION（新迁移扩 processing_jobs.job_type CHECK），每 Record 至多一个活跃 job（部分唯一索引仿 0009）；worker 领取 / 发布两阶段复核 summary 仍 CONFIRMED，失效 CANCELLED；在途 DRAFT 再生成 409，提供「丢弃候选」
- 候选纯只读：整批采用 / 放弃；只有 ACTIVE 批次的题可作答
- **批次采纳不发学习事件**（四事件无 QUIZ_CONFIRMED 槽位；采纳是管理动作，不是学习行为——区别于知识点批次确认）
- **一题一答定终身**：提交即锁定不可重做（行上 answered_at 非空即锁）；「再练」由重新生成承接，正式重测归 15
- **作答存储 = quizzes 行上三列**（user_answer_json / answer_result 可空 CORRECT·WRONG·NULL=简答待自评 / answered_at），与事件同事务写；不建 quiz_answers 表，不前移 quiz_tests / quiz_test_items（留 Wave B，届时测验作答另落 items、同题再答键位另立 `quiz-answered:test:{item_id}` 风格）
- 事件契约：source_type=QUIZ_QUESTION、source_id=quiz_id、幂等键 `quiz-answered:{quiz_id}`；metadata={batch_id, question_type, generated_from_summary_id}；用户所选答案不进事件（行上有）；result 二态；score / duration_ms 恒空；difficulty 从题目行带出；concept_id 恒空（P3 起回填）；重复提交返回现状（幂等键唯一约束兜底）
- 事件时机 = 对错已知时：客观题判分后、简答题自评后；未自评 = 待自评、不发事件、不算完成
- 换代联动（全仿 KP）：Transcript 编辑 / Summary 调优使旧 Summary 置 SUPERSEDED 后，**ACTIVE 批次仍可作答**（已采纳资产不失效）；在途 DRAFT 确认 409 并引导丢弃后重生成（blocked_reason=SUMMARY_SUPERSEDED）；SUPERSEDED 只由「确认新批次」触发；SUPERSEDED 批次默认隐藏，`?include=superseded` API 可回溯、无 UI 入口
- blocked_reason 枚举仿 KP：SUMMARY_NOT_CONFIRMED / SUMMARY_SUPERSEDED / COURSE_ARCHIVED / PROVIDER_NOT_CONFIGURED / CONSENT_REQUIRED
- 建表（数据模型 v2.2 已同步修订）：quizzes 含软删列（updated_at / deleted_at）+ 作答三列；不建 model / prompt_version / quality_score / cognitive_level / concept_id / source_anchor_id 列（溯源记 processing_jobs.result_json——07 先例；P3 / P5 / 评测域列后续迁移加）
- 确认新批次弹窗附「旧批次剩 N 题未作答」提示，不阻塞
- 生成进度复用 processing_jobs 轮询（active_job_id 2s 条件轮询）+ SSE 失效链，不加新通道

## 前置依赖

- 06（总结确认解锁；Provider / 同意 / llm_call_logs / jobs 轮询均已就绪）
- 07（候选批次、blocked_reason 与前端 Panel 形态先例，实现镜像）

## 验收标准（出口线）

- [ ] 选 2 种题型、5 道 → 恰好 5 题且字段完整（题干 / 选项 / 答案 / 解析），所选题型各 ≥1，构成由 AI 分配
- [ ] 选择题 / 判断题提交即自动判分正确；简答题须先提交非空作答才见参考答案，自评二态生效
- [ ] QUIZ_ANSWERED 逐题落表且幂等（重复提交不重复落、返回现状）
- [ ] 一题一答：已作答题只读锁定；中途离开可续答；全部作答（简答含自评）后完成态与轻量计数展示
- [ ] 重新生成候选期间旧题仍可作答；在途 DRAFT 再生成 409；「丢弃候选」后可重新生成
- [ ] 确认新批次后旧 AI 批次 SUPERSEDED、默认隐藏但 `?include=superseded` 可回溯；既有作答与事件保留
- [ ] Summary 换代后：ACTIVE 批次照常可作答；在途 DRAFT 确认被 409 阻止并引导重生成
- [ ] 档位选择记忆于 settings.quiz_last_count（初始默认 5）
