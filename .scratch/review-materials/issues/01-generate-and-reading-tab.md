# 01 — 首次生成与复习页签阅读态

**What to build:** 总结确认后（Record=COMPLETED），用户在「复习」页签一键生成三段式复习资料（考前速记 / Top 重点清单 / Markdown 大纲树），生成完成即在页签读到它；超长转写自动分级、覆盖全文不丢内容。（裁决与契约细节见 `.scratch/review-materials/spec.md`）

**Blocked by:** None — can start immediately

**Status:** done

- [x] 迁移 0017：`review_materials` 全列（数据模型 v2.3 §4.3：status / version_no((record_id, version_no) 唯一) / transcript_source_version / generated_from_summary_id / quick_review / key_list_json / mind_map_markdown / model / prompt_version / user_feedback / token_usage_json / latency_ms / confirmed_at / 软删列）；`processing_jobs` 重建扩 job_type CHECK（REVIEW_MATERIAL_GENERATION）+ one-active 部分唯一索引（照 0016 模板）；顶 6 处 user_version 断言同步
- [x] ReviewMaterial Graph 首生路径：generate → review[interrupt] → 条件回 generate（照总结同构）；AsyncSqliteSaver 复用 langgraph.db、thread_id 域前缀隔离；成功写 GENERATED v1 行（行上留痕 model / prompt_version / token / latency）；prompt 版本化自 review_v1 起；prompt 与输出全文不进日志
- [x] 窗口自适应：估 token 保守启发式（中文字数折算）+ 模块常量窗口默认（不进 providers.json）；「单次 or 语义分块 map-reduce」决策抽为纯函数；任何情况禁止静默截断/丢段；总结域 3 万字阈值不动
- [x] 结构化输出走既有 LLM 客户端链路（Pydantic strict + json_mode 降级）：quick_review / mind_map_markdown 非空带长度上限、mind_map 仅标题与列表行（禁代码块/表格）、key_list 条目非空——违规 Job FAILED（LLM_OUTPUT_INVALID）不自动修正
- [x] 上下文组装：转写/文档解析全文为主 + 当前 CONFIRMED 总结辅助 + 课程 learning_context / education_stage / depth（照总结规则）；KP 不进；输出中文；90 秒超时；llm_call_logs 埋点
- [x] 生成前置校验 409 矩阵（不建 Job）：无 CONFIRMED Summary / 课程非 ACTIVE / Provider 未配置 / 外发未同意 / 已有活跃 Job；input_json 记 transcript_source_version + provider_fingerprint + generated_from_summary_id
- [x] worker 领取/发布两阶段复核：Summary 仍 CONFIRMED、transcript_source_version 未变、课程仍 ACTIVE，失效 CANCELLED（ARCHIVED 第三道闸门）；Record 软删同事务级联复习资料、迟到结果不写回
- [x] 端点：`POST /api/records/{id}/review-material-jobs`（202 job_id）+ `GET /api/records/{id}/review-material`（当前版 + action_required / blocked_reason / active_job_id）；OpenAPI → api-types 重新生成
- [x] 前端：「复习」页签从 unavailableTabs 转正（解锁 = record COMPLETED、路由 tab 白名单、i18n 文案改解锁条件说明）；生成按钮 + blocked 下一步指引（未确认总结指向总结页签、未同意一键授权）；active_job_id 条件轮询进行中态（不加新通道）；失败可重试态
- [x] 渲染组件：Markdown 统一渲染组件（react-markdown + shiki 转正、shiki css-variables 接 `.dark` 双主题、放共享组件层供复用）；大纲自建折叠树（标题层级递归、默认全展开）；重点清单卡片（条数浮动直显）；页签纵向三卡布局（考前速记 → 重点清单 → 大纲树）；UI 文案「考前速记」全称
- [x] 测试：后端 S1 全栈（create_app 注入 Fake 模型：首生落库、409 矩阵、两阶段复核 CANCELLED、输出校验违规 FAILED、map-reduce 分块路径、one-active 防重、软删级联）+ S2 窗口纯函数边界（恰好装下/装不下/空文本）+ S5 渲染组件（代码块结构/语言 class/主题变量挂载，不做像素断言）+ S4 页签基本流（MSW mock 新端点、渲染 `?tab=review`、解锁/禁用/生成中态；mock 含 summary provider 链、错误断言 8s timeout）
