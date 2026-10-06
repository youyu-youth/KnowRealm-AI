# 复习资料

Status: ready-for-agent

## Problem Statement

KnowRealm 的学习闭环到「练完」为止：转写 → 总结确认 → 知识点 / 习题 / Todo。但考前真正需要的是一份**能在十分钟内刷完的浓缩材料**——总结太长、知识点太散，没有一个面向「考前速过」的形态。记录详情的「复习」页签目前是禁用占位。

复习资料（PRD §4.4.2，Wave B）填补这个位置：Record 级三段式资产——考前速记 + Top 重点清单 + Markdown 大纲树。2026-09-06 plan grill 定稿了三处与此前的差异：**生成上下文用转写/文档原文而非总结+知识点**（用户裁决：原文才「最适合」，总结作辅助）、**确认必选且支持手动编辑与版本链**、**引入 LangGraph 成为第二个 graph 域**。完整决策见 `.scratch/function-plans-introduction/16-review-materials.md` 与数据模型 v2.3 变更记录。

## Solution

总结确认后（Record=COMPLETED），用户在「复习」页签一键生成三段式复习资料：后端以**转写/文档解析全文为主 + 当前 CONFIRMED 总结辅助**（KP 不进上下文）组装输入，走 LangGraph（generate → review[interrupt] → 条件回 generate，与总结同构）产出结构化三段——考前速记（Markdown，可含代码块）、Top 重点清单（条数由模型按内容密度决定）、Markdown 大纲（纯标题层级树）。

生成完成弹出 **HITL 工作台弹窗**：预览三段，可【确认】定版、【反馈调整】（自然语言反馈，不限次，重生成产生新版本、旧版 SUPERSEDED）、【手动编辑】（速记/大纲改 Markdown 源码、重点清单条目增删改，就地生效不换代）。关闭弹窗后页签常驻阅读态展示当前内容，操作重开弹窗。确认后的版本可经 10 的导出通道单 Tab 导出 `.md` 或进入聚合导出。

## User Stories

1. As an 学习者, I want to 总结确认后在复习页签一键生成三段式复习资料, so that 考前十分钟刷完一堂课的要点。
2. As an 学习者, I want to 生成基于完整转写/文档原文而非仅总结, so that 总结没覆盖的细节不会漏进复习盲区。
3. As an 学习者, I want to 已确认总结作为辅助上下文参与生成, so that 我人工校验过的重点信号不浪费。
4. As an 学习者, I want to 生成结果在弹窗中预览三段, so that 定版前我能审阅 AI 产出。
5. As an 学习者, I want to 用自然语言反馈调整（如"更简洁""侧重某主题"）并不限次重生成, so that 资料逼近我想要的形态。
6. As an 学习者, I want to 手动编辑考前速记与大纲的 Markdown 源码, so that AI 措辞不合我意时能就地改。
7. As an 学习者, I want to 增删改重点清单条目, so that 清单留下真正要考的点。
8. As an 学习者, I want to 确认定版一份复习资料, so that 它成为可导出的正式版本。
9. As an 学习者, I want to 编辑已确认版本后无需重新确认, so that 微调不增加仪式负担。
10. As an 学习者, I want to 重开弹窗继续调整或编辑已定版资料, so that 复习资料可随时迭代。
11. As an 学习者, I want to 查看历史版本列表并回看任意旧版, so that 对比调整前后差异。
12. As an 学习者, I want to 反馈重生成后旧版本退场但数据保留, so that 「过时」不等于「丢失」。
13. As an 学习者, I want to 大纲按标题层级渲染成可折叠树, so that 像思维导图一样纵览课程结构。
14. As an 学习者, I want to 大纲树默认全部展开、按需折叠, so that 打开即见全貌。
15. As an 学习者（程序员）, I want to 速记段默认含关键代码速查块, so that 考前过一遍核心代码。
16. As an 学习者, I want to 代码块语法高亮且亮暗主题都正确, so that 夜间复习不刺眼。
17. As an 学习者, I want to 重点清单条数按内容密度浮动而非固定, so that 三小时的课和十分钟的速记各自得到合适的清单。
18. As an 学习者, I want to 单 Tab 导出复习资料为 .md 且与界面一致, so that 打印或发同学不用重排。
19. As an 学习者, I want to 聚合导出包含复习资料章节, so that 一份文件带走全部资产。
20. As an 学习者, I want to 只有已确认（CONFIRMED）版本进入导出, so that 未定版的草稿不会流出。
21. As an 学习者, I want to 转写更新后旧资料得到「已过期，可重新生成」提示而非被悄悄覆盖, so that 我决定是否基于新转写重做。
22. As an 学习者, I want to 超长课程录音生成覆盖全文不静默丢段, so that 我信任速记没有漏考点。
23. As an 学习者, I want to 生成异步进行并展示进行中状态, so that 界面不被模型调用阻塞。
24. As an 学习者, I want to 生成失败时看到可重试的失败状态, so that 一次网络问题不让功能报废。
25. As an 学习者, I want to 前置不满足（未确认总结/缺 Provider/未同意外发/课程归档）时得到下一步指引, so that 我知道去哪补齐条件。
26. As an 学习者, I want to 总结未确认时复习页签禁用并说明原因, so that 解锁条件一目了然。
27. As an 学习者, I want to 归档课程无法生成复习资料, so that 归档语义与其他资产一致。
28. As an 本地用户, I want to prompt 与输出全文不进入日志, so that 学习内容不出现在日志文件里。
29. As an 本地用户, I want to 每次写操作同事务落库, so that 崩溃不留半截版本。
30. As an 本地用户, I want to 复习资料的确认与导出不产生学习事件, so that 事件流里只有真实学习行为。

## Implementation Decisions

### 数据与迁移

- 新建 `review_materials` 表（下一号迁移 0017），按数据模型 v2.3 全列：`status`（GENERATED / CONFIRMED / SUPERSEDED）、`version_no`（(record_id, version_no) 唯一）、`transcript_source_version`（≥1）、`generated_from_summary_id`（可空 FK，ON DELETE SET NULL）、`quick_review`、`key_list_json`、`mind_map_markdown`、`model` / `prompt_version`、`user_feedback`（可空）、`token_usage_json` / `latency_ms`、`confirmed_at`（可空）、`updated_at` + 软删列。行上留痕（区别于 KP/Quiz 的 result_json 方案）——复习资料是版本链资产，对齐 ai_summaries。
- `processing_jobs.job_type` 新增 `REVIEW_MATERIAL_GENERATION`（迁移重建表扩 CHECK，照 0016 模板）+ one-active 部分唯一索引：每 Record 至多一个 PENDING/RUNNING 的复习资料任务。同步顶 6 处 user_version 断言。
- 后端 schema 落定后重跑 api-types 类型生成。

### 生成管线（LangGraph 与上下文）

- **上下文组装**：转写/文档解析全文为主 + 当前 CONFIRMED 总结（abstract + 结构化分点）辅助 + 课程 learning_context / education_stage / depth（照总结规则）；**KP 不进上下文**；输出中文。
- **LangGraph 第二域**（红线 #2 不建超级 Graph 的前提下，新增独立 ReviewMaterial Graph）：generate → review[interrupt] → 条件回 generate，与总结同构；AsyncSqliteSaver 复用 langgraph.db，thread_id 按域前缀隔离；调整重生成经 `Command(resume="ADJUST")` 携带反馈恢复；确认对 graph 线程的处置照总结既有机制。KP/习题/Todo 维持直接 LLM 不动——边界：只有「多版本 HITL 循环」型资产上 graph。
- **超长窗口自适应**：估 token 用保守启发式（中文字数折算），模型窗口 MVP 不进 providers.json——模块常量保守默认（按 128k 窗口折算、给输出留余量）；装得下全文单次调用，装不下按语义段落分块 map-reduce 分级（照总结 #36 模式），任何情况禁止静默截断/丢段。**「单次 or 分块」决策抽为纯函数**（唯一新后端测试缝）。总结域 3 万字硬阈值不动。
- 结构化输出走既有 LLM 客户端链路（Pydantic strict + json_mode 降级 + llm_call_logs 埋点）；prompt 版本化自 review_v1 / review_adjust_v1 起；**prompt 与输出全文不进日志**。
- 输出校验：quick_review / mind_map_markdown 非空且带长度上限、mind_map 仅允许标题与列表行（禁代码块/表格）、key_list 条目非空——违规令 Job FAILED（LLM_OUTPUT_INVALID），不自动修正不自动重试。
- 前置校验（任一不满足 409，不建 Job）：存在当前 CONFIRMED Summary、课程 ACTIVE、Provider 已配置、外部处理同意有效；input_json 记 transcript_source_version + provider_fingerprint + generated_from_summary_id。单次 LLM 请求沿用 90 秒超时。
- worker 领取/发布两阶段复核：绑定 Summary 仍 CONFIRMED、transcript_source_version 未变、课程仍 ACTIVE，失效则 CANCELLED（ARCHIVED 第三道闸门照抄）。
- Record 软删同事务级联复习资料，迟到结果不得写回。

### 版本链与 HITL 语义

- 状态机：`GENERATED → CONFIRMED`（确认必选，confirmed_at 落行，确认不锁编辑）；反馈调整/重新生成 → 新行 version_no+1 置 GENERATED、旧行置 SUPERSEDED；**手动编辑就地更新当前版本，不换代、不迁移状态**。
- 调整端点绑当前 GENERATED 版本（feedback 1~1000 字，照 SummaryAdjustRequest 形状）；对 CONFIRMED 版本的再调整 = 走同一 adjustments 流程产生新 GENERATED 版本。
- 版本列表只读回看 + 切换查看（照总结版本列表先例），无一键回滚。
- 过时判定：行上 transcript_source_version < 当前 source_version → 前端非阻塞提示「转写已更新，可重新生成」；旧内容不删不覆盖；`generated_from_summary_id` 仅溯源，总结换代不阻塞。
- 不新增 learning_event（#43 事件集不扩；确认与导出均不发）。

### API 契约

- `GET /api/records/{id}/review-material`：当前版（最新未软删行）+ action_required / blocked_reason / active_job_id（镜像总结读端点模式）。
- `GET /api/records/{id}/review-materials`：版本列表（只读）。
- `POST /api/records/{id}/review-material-jobs`：首生，202 返回 job_id。
- `POST /api/records/{id}/review-material-adjustments`：反馈调整，202。
- `POST /api/records/{id}/review-material-confirmations`：确认（幂等，重复确认返回现状）。
- `PATCH /api/records/{id}/review-material`：手动编辑就地生效（速记/大纲文本、重点清单整体提交）。
- OpenAPI 是前端类型唯一契约：schema 先落 OpenAPI 再生成 api-types。

### 桌面端

- 「复习」页签从 unavailableTabs 占位转真实功能：解锁 = record COMPLETED（同 quiz/todo）；路由 tab 白名单、i18n 文案同步更新；禁用文案改为解释解锁条件。
- **弹窗 HITL 工作台**（Dialog）：生成完成打开，三段预览 +【确认】【反馈调整】【手动编辑】；编辑态 = 速记/大纲 Markdown 源码 textarea + 重点清单条目编辑器（增删改）；关闭后页签常驻阅读态，操作按钮重开弹窗。
- 页签阅读态纵向三卡：考前速记 → 重点清单 → 大纲树；进行中态复用 active_job_id 条件轮询（不加新通道）。
- **Markdown 渲染统一组件**（放共享组件层供复用）：react-markdown + shiki 转正（两者已在依赖清单声明，零新增）；shiki 用 css-variables 主题，经 `.dark` 语义变量实现亮暗双主题。
- **大纲树自建**：解析 mind_map_markdown 标题层级递归渲染折叠节点（chevron 图标），默认全部展开；不引树组件库。
- UI 文案一律「考前速记」全称，与捕获入口「速记」（Quick Note）区分（GLOSSARY.md 术语已定）。
- 文案全走 i18n；交互组件 shadcn/ui + Base UI 原语；纯图标按钮带 aria-label。

### 导出接入（10 通道）

- 仅 CONFIRMED 版本可导出；无 CONFIRMED 版本时「导出当前 Tab」禁用并说明原因。
- 单 Tab 导出默认名 `{Record标题}-复习资料.md`；导出内容 = 速记原样 + 重点清单转 Markdown 列表 + 大纲原样，**不套纯文本转义**（保留 Markdown 与代码块语义，10 既定规则）。
- 聚合导出位次 Summary → 知识点 → 习题 → 复习资料 → Todo（10 既定）；`ExportableAsset` 扩 review；聚合读取失败整次失败语义照 10。
- 导出不产生 learning_events；触发时最新快照语义照 10。

## Testing Decisions

- 好测试只断言外部行为：HTTP 响应、数据库终态（review_materials 行、版本链、软删标记）、UI 可见结果；不断言 graph 内部调用序列与 prompt 措辞。
- **后端主缝（既有）**：create_app 应用工厂注入 Fake ReviewMaterialModel（StructuredModel 协议，镜像 FakeSummaryModel），httpx + ASGITransport + 真实迁移库 + 真实 worker + 真实 checkpointer 全栈驱动——覆盖闸门矩阵、生成落库、interrupt/resume 调整、确认、编辑、版本链、map-reduce 分块路径（Fake 分块输出）。
- **后端唯一新缝**：窗口自适应纯函数单测（恰好装下/恰好装不下/空文本边界）。
- **前端既有缝**：导出序列化纯函数并入 serializers 测试（三段拼装、聚合位次、CONFIRMED-only）；页签/弹窗组件测试沿 RecordDetail 先例（MSW mock 端点、渲染真实路由 `?tab=review`），注意既有坑——mock 含 summary provider 链、错误断言 8s timeout（react-query 重试）、getByRole 非 exact。
- **前端唯一新缝**：Markdown 渲染组件测试断言代码块结构（语言 class、主题变量挂载），不做像素断言。
- 本机 pytest 必须加 `--basetemp=.pytest-tmp`。
- **真机项全部单列「用户真机验收」清单，agent 不验证不代勾**（用户 2026-09-06 重申）：弹窗 HITL 交互体验、大纲树折叠手感、shiki 亮暗双主题视觉效果、导出 .md 中文文件名落盘。
- 必测场景：生成基于原文+总结（KP 断言不在 prompt 上下文）；确认前不可导出；反馈调整产生新版本且旧版 SUPERSEDED、版本列表可回看；手动编辑就地生效不换代；编辑 CONFIRMED 版本不触发重确认；输出校验违规令 Job FAILED；409 矩阵（未确认总结 × 课程归档 × 缺 Provider × 未同意）；两阶段复核 CANCELLED；转写更新后旧资料提示且不删；one-active 防重；Record 软删级联。

## Out of Scope

- RAG 检索式生成（已否决：选择性召回 vs 全覆盖浓缩不匹配、撞静默截断红线、向量基建属 P2/P3 chat 档期）。
- 图形化思维导图导出；P4 遗忘雷达 / 复习排期 / 复习队列。
- 版本一键回滚（用旧版内容 = 复制后手动编辑）。
- learning_events 写入（#43 事件集不扩）。
- providers.json 模型窗口字段（MVP 用模块常量，供应商卡加窗口配置时再接）。
- chat 域 Markdown 渲染（Streamdown 留给其既定触发条件）；总结域 #36 阈值改动态。
- 课件差异分析等 record_analyses 域（P3）。

## Further Notes

- 决策源：2026-09-06 plan grill 定稿（16 项裁决），全文见 `.scratch/function-plans-introduction/16-review-materials.md`；表结构见数据模型 v2.3 §4.3 与其变更记录；术语见 GLOSSARY.md「复习资料」「考前速记」。
- 前置依赖：06（总结——解锁闸门与辅助上下文）、10（导出通道）；07 不再是上下文依赖。
- 拆票建议（供 /to-tickets 起步）：①后端域（迁移 + graph + 六端点 + 测试）→ ②前端页签与弹窗 HITL + 渲染组件 + 版本列表 → ③导出接入；①为 ②③ 的 blocking edge。
- 遗留：docs/rules 两处「数据模型 v2.2」引用漂移（rules 文件禁改，章节号仍有效，待用户处置）。
- 实现注意：工作区存在未提交的 `apps/desktop/src/routeTree.gen.ts` 改动（非本功能），动工前先确认其归属或错峰提交。
