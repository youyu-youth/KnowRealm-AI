# 04 — 课程详情与编辑

**What to build:** 让学习者从真实列表进入课程 Overview，查看并编辑课程上下文；详情同时提供稳定的 Records 宿主，但诚实说明学习记录将在后续计划接入。

**Blocked by:** 02 — 首门课程持久化闭环.

**Status:** ready-for-human

- [x] 学习者可从列表进入课程详情，并查看名称、学习场景、教育阶段或学习深度、课程类型、说明和热词摘要。
- [x] 详情路由使用真实课程 ID；不存在或已软删课程显示未找到状态及返回知识空间的路径。
- [x] Overview 与 Records 使用受校验的 URL tab 状态，刷新后保持当前 tab。
- [x] Records 只提供后续计划的稳定内容宿主并明确标示“未接入”，不显示假记录或把未实现功能描述为真实空列表。
- [x] 学习者可以编辑课程名称、场景、阶段或深度、类型和说明；成功后列表与详情缓存同步刷新。
- [x] 从 SCHOOL 切换到 CAREER/INTEREST 时必须填写有效深度并清空阶段；反向切换必须填写阶段并清空深度。
- [x] 无效编辑在 API 边界被拒绝，旧数据保持不变；界面保留输入、聚焦错误字段并提供清楚说明。
- [x] 编辑使用课程 PATCH 契约及 OpenAPI 生成类型，不增加一套专用手写 Course 模型。
- [x] API/SQLite 集成测试覆盖详情、编辑、跨场景切换、清洗空白名称、404 和软删详情不可见。
- [x] 前端行为测试通过可访问角色覆盖 tab、编辑成功、校验失败和保存失败重试。
- [ ] 真实 HTTP 与桌面渲染证明编辑落入 SQLite 并在刷新后保持；Query 缓存更新不能替代持久化证据。

## Comments

- 2026-08-18 源码/契约：GET/PATCH `/api/courses/{course_id}` 落地——`CourseUpdate`（字段级清洗 + exclude_unset 语义：`name`/`learning_context` 显式 null 视为未修改，可空字段 null 为清空）、`CourseDetailOut`（hot_words TEXT JSON 解析，无效 JSON 记事件不带内容）、`CourseService.get/update`（事务边界、跨场景互斥校验 422、updated_at 触碰、空 PATCH 不变更）、路由 404/422/500 响应契约、CORS 允许 PATCH。OpenAPI schema/types 重新生成且 `--check` 无漂移。
- 2026-08-18 API/SQLite 集成：临时数据目录下 11/11 pytest 通过；新增覆盖详情（含直写 DB 的热词 JSON 解析为摘要）、缺失 ID 404、软删课程详情/编辑 404、编辑字段更新 + updated_at 提升与列表重排、空 PATCH 原样返回、空白/超长名称 422 且旧数据不变、SCHOOL↔CAREER 双向切换必填与互斥清空。Ruff、Pyright strict 通过。
- 2026-08-18 前端：`/spaces/$courseId` 路由（tab=overview|records 受校验 URL 状态，非法值回退概览；`spaces.tsx` 改为 Outlet 布局路由、列表移至 `spaces.index.tsx`）、详情加载/错误/未找到（返回知识空间）状态、Overview 字段与热词摘要、内联编辑表单（共享 CourseFormFields/courseFormValues；客户端校验聚焦错误字段，服务端 422/500 保留输入可重试，成功后精确失效 detail 与全部 lists）。Records 为稳定宿主并明确“未接入”，无假记录或伪装空列表。vitest 16/16（新增 7：列表入口渲染、tab URL 恢复与非法回退、404 状态、编辑成功契约与缓存刷新、跨场景校验失败聚焦不发请求、500 保留输入重试、422 服务端说明保留输入）；ESLint、Prettier、双 tsconfig + Vite build、Impeccable detector `[]` 通过。
- 2026-08-18 真实 HTTP/重启持久化：真实 sidecar 进程（随机端口 54162、64 字符令牌，错误令牌 403）经 socket 创建 SCHOOL 课程并 PATCH（清洗名称、切 CAREER 清阶段、设类型）；换端口 59139 与新令牌重启后，编辑值（名称/场景/深度/类型/说明）由真实 SQLite 读回一致。临时数据目录已清理，Query 缓存未参与该证据。
- 2026-08-18 双轴审查修复：抽 `asCourseTab`/`courseLevelLabelKey`/`courseDateFormatter`/`invalidCourseFormField`/`courseFormPayloadFromValues` 消除创建与编辑表单、列表与详情页的重复级联与 payload 拼装；移除 Overview 越界的“最近更新”行；补 API 422 前端行为测试。保留裁决：422 状态码与 CourseCreate 既有校验行为一致；`name` null=未改 vs 可空字段 null=清空符合 fastapi.md §3 模式；互斥字段强制清空为 spec 原文要求（与创建一致）。
- 2026-08-18 验收项 11：真实 HTTP 与重启持久化半项已由上述进程级证据覆盖；桌面渲染半项（WebView 内编辑 → SQLite 落库 → 刷新保持，含 Network 令牌与随机端口）沿用议题 03 先例待人工复验，Status 置 ready-for-human。
