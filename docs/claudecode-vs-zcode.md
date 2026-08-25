## claude code
第一轮：7 个决策点

❓ Q1 - 数量档位的语义（总数 vs 每题型）
计划写「题型多选（选择题/判断题/简答题）→ AI 建议数量 3/5/10 道 → 生成」。存在歧义：3/5/10 是所选题型合计总数，还是每种题型各 N 道？若勾了两种题型、选 5 道，是共 5 题（如 3 选择 + 2 简答），还是每种各 5 共 10 题？「AI 建议」是指默认推荐其中一档、用户可在三档间改选吗？

➡️ 建议采用总数制：勾选 ≥1 种题型 + 从 3/5/10 选一个总数（默认推荐 5）；LLM 在所选题型内自行分配题数（Schema 只校验总数与题型合法，不强制均分）。验收标准「选 2 种题型、5 道」与此读法吻合，UI 也最简。

❓ Q2 - 首次生成是否需要「采用确认」步骤
计划只在「重新生成」处写了 候选批次 → 确认 → 旧批次 SUPERSEDED。首次生成（没有旧批次）是否也要经过一步「预览并采用」，还是生成完直接成为当前可用批次？

➡️ 建议首次生成直接成为当前批次、立即可作答，不设确认步骤——「确认」的价值只在保护既有批次不被更差的重生成覆盖；核心业务流程「生成 → 逐题作答」也隐含此意。

❓ Q3 - 重新生成的限制（三小问捆绑）
(a) 旧批次还没答完时，允许发起重新生成吗？
(b) 已有一个候选批次待确认时，再次点「重新生成」怎么处理？
(c) 候选批次可以被「放弃」吗（保留旧批次继续用）？

➡️ 建议：(a) 允许，无作答进度前置；(b) 同时最多一个候选，再次重新生成直接覆盖当前候选（前端提示）；(c) 可放弃，候选作废（软删），旧批次不动。

❓ Q4 - SUPERSEDED 批次的命运（未答题目 + 可见性）
确认新批次的瞬间，旧批次里尚未作答的题目是否就此封存、不可再答？另外，MVP 是否提供历史 SUPERSEDED 批次及其已答内容的UI 查看入口？（数据上「答案与作答事件保留」是明确的，这里只问 UI 入口。）

➡️ 建议：SUPERSEDED = 整批只读归档，未答题目不可再答；MVP 不提供历史批次查看入口，UI 只展示当前批次——历史作答记录页属于复习/错题域（15，Wave B），不在 08 提前做。

❓ Q5 - 作答不可变性与「完成」定义
(a) 一道题提交判分/自评后，还能修改答案重做吗？
(b) 允许中途弃答离开、之后回来继续吗？
(c) 批次「完成状态」如何定义？

➡️ 建议：(a) 不可重做，一题一答——这是 QUIZ_ANSWERED 幂等语义最干净的支撑，「想再练」就走重新生成；(b) 允许，逐题即时落库，回来续答；(c) 完成 = 批次内全部题目已作答（客观题已判分、简答题已自评），完成后 tab 给出完成态展示。

❓ Q6 - 新 Summary 确认后的旧批次联动
计划说「Transcript/Summary 换代不自动删除旧题、答案或作答事件」，但没说旧批次会不会被自动 SUPERSEDED。用户确认了一版新 Summary 后，绑定旧 Summary 的习题批次：(a) 保持 ACTIVE 照常可作答；还是 (b) 自动 SUPERSEDED？

➡️ 建议 (a)：不自动换代，旧批次保持可用；SUPERSEDED 只由「重新生成并确认新批次」这一用户动作触发；新的生成请求始终绑定最新确认的 Summary。（07 的 KP 换代联动若做了不同选择，那是 KP 域的裁决，不必传染习题——最终以文档 + 你第二轮的定夺为准。）

❓ Q7 - 简答题的作答前置
简答题是否必须先提交自己的文字作答，才允许查看参考答案并自评？还是允许直接翻看参考答案？

➡️ 建议必须先提交非空作答才能看参考答案——保住练习价值，也让 QUIZ_ANSWERED 事件里简答题有真实答案载荷。

术语冲突（CONTEXT.md 挑战）→ Q2 修订

CONTEXT.md「候选批次」定义：一次 AI 生成产出的候选集合（知识点/习题共用），经用户确认整体生效；新批次确认后旧 AI 批次才置过时。这与我原先「首次生成免确认」的推荐冲突——术语表明每一批（含首批）都经确认生效，且与 07 已落地的 KP 确认闭环同构（generation_status：DRAFT=候选 → ACTIVE → SUPERSEDED 单列承载）。

❓ Q2（修订） - 首批也走「采用确认」？
➡️ 改推荐：是——生成 → DRAFT 候选（预览）→ 点「采用」→ ACTIVE 可作答；重新生成同样产出 DRAFT 候选、旧 ACTIVE 并行可用，采用候选后旧批 SUPERSEDED。与术语表及 KP 模式一致，两个 tab 可复用同一套组件语义。

❓ Q10 - 「采用」的粒度（新题）
预览候选批次时，只能整批采用/放弃，还是能先剔除个别差题再采用？（编辑题干/选项不在 08 范围，这里只问剔除。）
➡️ 建议 MVP 整批采用/放弃——08 保持最小闭环；差题容忍成本很低（不做错题本，判分/自评不受影响），逐题剔除留给 Wave B 再议。

文档张力解锁的新题

❓ Q8 - Wave A 作答明细落在哪张表（本 plan 最大的上游张力）
数据模型把 quiz_tests / quiz_test_items 划在「P1 补（Wave B）」，但 Wave A 验收线要求「习题作答 + QUIZ_ANSWERED 落地」，且 learning_events.source_type 的示例就是 quiz_test_item、计划还要求 SUPERSEDED 后「既有答案保留」——Wave A 必须有作答载体。选项：
- A（推荐）：quiz_tests + quiz_test_items 提前至 Wave A 建表（数据模型 §3/§11 波次行同步：Wave A 基线 15→17 张）。逐题模式 = quiz_tests.mode 新增枚举 PRACTICE；一个批次对应一条 quiz_tests（开始作答时创建），每题一条 quiz_test_items（sequence_no=批次内题序）；08 不用 score / ai_grade_json（Wave B 域）。
- B：自建轻量 quiz_answers 表（直接绑 quiz_id）——违背「作答存于 quiz_test_items」既有设计，Wave B 还得迁移合并。
- C：不落明细、只落事件——违反「答案保留」验收，不可行。

➡️ 建议 A。它需要一次小的数据模型文档同步（波次挪动 + mode 枚举注记，按治理惯例升版处理）——你点头我就列入收尾清单。

❓ Q9 - quizzes 的软删列（文档内部不一致）
表定义无 deleted_at / updated_at、未标〔软删〕，但 §9 删除链把 quizzes 列入 record 的软删子资产。08 要建迁移，必须现在定。
➡️ 建议对齐 knowledge_points：加 updated_at + 可空 deleted_at，软删——符合数据层规范「可编辑实体统一软删」与 §9 删除链；数据模型 quizzes 行同步补标注。

---
等待你的答案：Q1（总数制？）、Q2 修订版、Q3(b)(c)、Q4、Q5、Q7 + 新增 Q8 / Q9 / Q10。

代码 agent 返回后进第二轮：生成异步模式（processing_jobs / 轮询，随 07 现状）、QUIZ_ANSWERED 幂等键格式与 payload、选项/答案 JSON 细节（选择题是否单选）、习题 tab 的 UI 形态。
❓ Q11 - 生成输入源
KP 有 input_mode（FULL_TRANSCRIPT / SUMMARY_ONLY）双模式可选。习题生成吃什么？
➡️ 建议 MVP 仅用确认 Summary 文本（generated_from_summary_id 绑定它，prompt 只喂总结）：总结是人工确认过的事实源，题干/解析天然 grounded；喂全转写会放大 prompt 体积与成本，且习题没有 KP 那种「筛细节」的审阅场景。想要转写级细节题，Wave B 再加 input_mode。

❓ Q12 - 选择题形态：单选还是多选
数据模型只给了 options_json / correct_answer_json，没定选择题是否含多选题（多选判分要面对「部分对」问题）。
➡️ 建议 MVP 仅单选：options_json=选项数组，correct_answer_json=单个选项标识；判断题 options 固定空/对错二值；多选题（一题多答案、部分给分）不进 08——PARTIAL 枚举值留给 Wave B。

---
当前待你拍板的：Q1（数量=总数制？）、Q2（首批也走采用确认）、Q4（SUPERSEDED 无历史入口）、Q5（一题一答/可续答/完成=全答完）、Q7（简答必先作答）、Q8（作答落表，推荐 A 提前建 quiz_tests/items）、Q9（quizzes 加软删列）、Q10（整批采用不剔除）、Q11（仅 Summary 输入）、Q12（仅单选）。

答完这批，前沿就空了——我会汇总全部裁决、列出文档同步清单（数据模型两处、pla迁移号），等你确认后再动 plan 文件。






## zcode

 Q1 - 作答状态存哪里：数据模型缺口。逐题作答后，「这题已作答、答了什么、对错如何」的当前状态由谁承载？三个方案：

A. quizzes 行上加作答列(如 user_answer_json / answer_result / answered_at),事件照落(行=当前态，事件=行为日志，同事务写)；
B. 事件即真相：不加列，读端按 record 查 QUIZ_ANSWERED 事件、按 source_id 组装每题作答态，作答内容塞 metadata_json;
C. 新建 quiz_answers 表(与 15 的 quiz_test_items 职责重叠)。
➡️ 推荐 A。与全库「业务态在行上、事件是追加型行为日志」模式一致(KP 的 ACTIVE/SUPERSEDED、summary 的 CONFIRMED 都在行上)；读端最简，「完成状态展示」直接可查；数据模型文档回写 3 列。B 把追加型事件表当读模型，长期别扭；C 多一张职责重叠的表。

❓ Q2 - 重做语义：同一题允许多次作答吗？这直接决定幂等键格式。

A. 一题一答定终身：提交即定，幂等键 quiz-answered:{quiz_id},重复提交后端幂等返回现状(仿 KP 确认)；
B. 允许重做：每次作答都落事件，幂等键须带序号(quiz-answered:{quiz_id}:{attempt_no}),「幂等」退化为防并发重复。
➡️ 推荐 A。MVP 最简，且与 #43「一行为一事件」语义干净；「再做一遍」的需求由 15 组卷测验承接(同一题可在不同 test 里反复出现)。若选 A,Q1 的行上状态就永远等于唯一一次作答，无覆盖问题。

❓ Q3 - 简答自评粒度：plan 说「自评对错」，但 15 的 quiz_test_items.result 定义了 CORRECT / WRONG / PARTIAL 三态。08 的自评与事件 result 字段用几态？

➡️ 推荐二态(CORRECT / WRONG)。PRD 原文就是「自评对错」;PARTIAL 语义模糊、给用户增加决策负担，留给 15 的 AI 语义评分场景。事件与行上状态(若 Q1 选 A)统一二态。

❓ Q4 - 「AI 建议数量 3/5/10 道」的语义：是总题数档位(用户从 3/5/10 选一个总数，多题型时构成由 AI 自由分配)，还是每题型 3/5/10 道(选三种题型最多 30 道)？

➡️ 推荐总题数档位。PRD 行文「题型多选 → AI 建议 3/5/10 道」更自然读作总数；每题型 3/5/10 会让“选 3 题型 × 10 道”生成 30 题，成本失控。Schema 只约束 items 总数 = 所选档位,题型构成由 AI 定(仅选一个题型时全部为该题型)；UI 默认档 5。

❓ Q5 - 候选题目的编辑能力:07 的 KP 有批内删/改 + 手工补充(PRD 明说)。08 的 PRD 行没有 HITL 编辑要求，plan 也没写。候选(DRAFT)审阅时用户能做什么？

A. 纯只读审阅：只能「确认批次」或「丢弃候选」，不能删题/改题，也没有手工出题；
B. 仿 07:批内删题、行内编辑题干/选项/答案，确认后 ACTIVE 仍可编辑。
➡️ 推荐 A。PRD 未要求，且「题目不好」已有解法——丢弃后重新生成(PRD:249 明确重新生成不限次)；A 砍掉整套编辑表单与校验工作量。代价是「错别字级别的瑕疵」只能整批重来——MVP 可接受。若你实际使用中很在意改题，选 B。

❓ Q6 - 作答前提与「确认」术语：(a) 只有 ACTIVE(已确认)批次的题可作答，DRAFT 只读审阅——对吗？(b) 习题的「确认批次」不落任何 learning_event(四事件无 QUIZ_CONFIRMED),只是批次状态迁移——确认吗？

➡️ 推荐 (a)(b) 均是。(a) 是术语表「候选批次经用户确认整体生效」的直接推论，也保证作答事件永远指向稳定题目;(b) 与 07 不同但正确——KP 确认是学习行为(我学会了这些点)，题目批次采纳不是。我会在定稿后把「作答」与「批次采纳」的术语区分写进 CONTEXT.md。

❓ Q7 - quizzes 建表与 07 的对齐：数据模型 v2.2 给 quizzes 定义了 model / prompt_version / quality_score / cognitive_level / concept_id / source_anchor_id 列，但 07 定稿时 KP 实际建表砍掉了溯源列(记 processing_jobs.result_json,0009 无 model/prompt_version 列)。quizzes 照哪个来？

A. 仿 07:砍 model/prompt_version(溯源记 job),quality_score/cognitive_level/concept_id 等 P3+/P5 列也不建(YAGNI,后续迁移加列便宜)；
B. 照文档全建：可空列先占位。
➡️ 推荐 A,与 07 的既定裁决保持一致，迁移最瘦；数据模型文档回写同步。

❓ Q8 - QUIZ_ANSWERED 事件契约：参照 KP 事件(source_type=KNOWLEDGE_BATCH、source_id=batch_id、metadata 记批次上下文)，逐题作答事件我建议:

source_type = QUIZ_QUESTION、source_id = quiz_id(逐题落，题即来源)；
幂等键 quiz-answered:{quiz_id};
metadata_json = {batch_id, question_type, generated_from_summary_id}——用户所选答案不进事件(行上有,事件保持行为日志定位，与 KP 事件不放知识内容一致)；
result = CORRECT / WRONG(Q3 二态);score 恒空(result 已表达，避免双表达);duration_ms 恒空(逐题不计时);difficulty 从题目行带出(EASY/MEDIUM/HARD,事件表本就有此列);concept_id 恒空。
有什么要调整的吗？

➡️ 推荐全按上述。唯一可议的是「用户所选答案不进事件」——若你预期 17 学习统计要做错题归因(知道具体选了哪个错项)，就要把 user_answer 塞进 metadata。我判断统计吃 result/difficulty 足够，不加。

❓ Q9 - 生成 Schema 约束:QuizBatch pydantic Schema(extra=forbid, strict, 仿 KP)我建议:

一次调用混合生成:多题型在同一次 LLM 调用里产出,items 每条带 question_type;
items 总数 = 所选档位(3/5/10,上限 10);
选择题：单选,选项 3~5 个、每项 1200 字,correct_answer = 正确选项的下标;判断题：选项固定「对/错」(存储上 options_json 存两项,correct_answer 为其中下标，与选择题同构、判分逻辑统一);简答题:options 为空数组,correct_answer = 参考答案文本(11000 字);
stem 1500 字;explanation 11000 字;difficulty 由 AI 输出(EASY/MEDIUM/HARD);
题型构成由 AI 定，但所选题型必须至少各 1 道(选了却不生成等于白选)。
➡️ 推荐全按上述。可议点:(a) 选择题要不要支持多选——我判断 MVP 单选够用且判分/UI 都简单;(b) 「所选题型至少各 1 道」在极少总量时(如 3 道选 3 题型)会挤占比——如果你觉得过度约束，可降为「所选题型尽量覆盖，不保证」。

❓ Q10 - 作答交互流:

客观题：选中选项后需点「提交」按钮才判分(防误触)，提交后锁定、显示对错 + 解析；
简答题:textarea 输入 → 提交 → 才显示参考答案 + 「对/错」自评按钮 → 自评提交后锁定、落事件(事件在自评完成时落，因为那时 result 才确定);不允许不作答直接看答案(否则自评无意义、事件缺失);
生成入口 UI:题型多选(默认全选三种)+ 数量档位单选(默认 5)→ 生成按钮；
已作答题不可重做不可改自评(Q2 定终身的 UI 落实)。
➡️ 推荐全按上述。

❓ Q11 - 完成状态展示:plan 流程最后一环「完成状态展示」的形态——顶部轻量计数(「已答 x/y,答对 z」)+ 每题状态徽标(未答/已答对/已答错)，不做测验报告、正确率曲线等(那是 15/17 的域)。

➡️ 推荐如上。轻量计数属逐题模式的自然反馈，不算越界做测验。

❓ Q12 - 换代联动与阻塞态(全仿 07 KP,逐项确认):

生成输入仅送已确认 Summary,无 3 万字 input_mode 分叉(KP 有是因为它可送转写，习题天然只送总结);
job_type = QUIZ_GENERATION + 部分唯一索引(每 Record 至多一个活跃 job);
worker 领取/发布两阶段复核 summary 仍 CONFIRMED(转写换代会先把 summary 置 SUPERSEDED,故无需另绑 transcript 版本),不符则 CANCELLED;
在途 DRAFT 批次时再点生成 → 409;「丢弃候选」可用；
DRAFT 批次绑定的 summary 已换代 → 确认 409 + read 端 blocked_reason=SUMMARY_SUPERSEDED;
ACTIVE 批次在 summary 换代后仍可继续作答(已采纳资产不失效——与 KP 的 ACTIVE 行为一致);
blocked_reason 枚举仿 KP:SUMMARY_NOT_CONFIRMED / PROVIDER_NOT_CONFIGURED / CONSENT_REQUIRED / SUMMARY_SUPERSEDED;
quiz tab 解锁条件 = record COMPLETED(总结已确认)。
➡️ 推荐全按上述。

❓ Q13 - SUPERSEDED 历史展示:确认新批次后，旧批次(含其作答状态)默认隐藏,API ?include=superseded 可查但不做 UI(完全照 07 的定稿裁决)；作答事件本就永久保留在 learning_events。

➡️ 推荐照 07。代价是用户在 UI 上看不到「我旧批次答过什么」——但事件在、行在，17 统计不受影响。

答完这轮，剩下就只有收尾：我把全部裁决回写 08-quiz.md(含验收线补齐：重复提交幂等、在途 DRAFT 409、换代场景)和数据模型 v2.2 的 quizzes 表(作答 3 列、砍溯源列)，那就是 shared understanding 的终点。
