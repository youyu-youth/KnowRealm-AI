# 工作台骨架与课程管理

Status: ready-for-agent

## Problem Statement

KnowRealm 当前只有已初始化的 Tauri + React 工程和一份视觉合同，没有可使用的工作台导航、页面路由、真实课程数据或本地 API。用户无法从“今日”或“知识空间”进入稳定的桌面工作面，也无法创建、查找、编辑、查看或删除课程。若此阶段只铺静态页面或模拟课程，后续 Record、捕获和 AI 管线会建立在假的数据与交互边界上；若先建设一个独立且过宽的工程 Phase 0，又会延迟首个真实闭环并制造尚无消费者的基础设施。

## Solution

在现有桌面工程内交付一个可复用的 Continuous Work Surface 应用外壳，并把课程管理作为第一个贯穿桌面 UI、localhost sidecar API 与 SQLite 的真实纵向切片。用户能够在“今日”和“知识空间”之间导航，从真实空态创建课程，重启后继续读取；随后完成课程搜索、筛选、编辑、详情、热词维护和软删除。未实现的工作区与捕获动作清楚标记为未接入，不产生死按钮、模拟数据或假成功。

本功能同步引入它实际需要的最小本地基础：数据目录、SQLite WAL、编号迁移、FastAPI sidecar、随机端口、单次启动令牌、OpenAPI 类型生成与统一 HTTP 客户端。它不预建 Record、AI、Provider、worker 或分发阶段才需要的实现。

## User Stories

1. As a 学习者, I want to 启动 KnowRealm 后看到稳定的工作台外壳, so that 我能形成持续使用的空间记忆。
2. As a 学习者, I want to 从左侧导航进入今日页, so that 我能看到当前真实状态而不是示例任务。
3. As a 学习者, I want to 从左侧导航进入知识空间, so that 我能管理唯一的知识容器——课程。
4. As a 学习者, I want to 清楚辨认当前所在导航项, so that 我不会迷失在工作台中。
5. As a 键盘用户, I want to 按 Tab 浏览全部可用操作并看到焦点, so that 我无需鼠标也能操作。
6. As a 学习者, I want to 看到未实现入口的“未接入”状态, so that 我不会误以为收件箱、AI 对话、资产库或学习画像已经可用。
7. As a 学习者, I want to 未实现入口不触发业务行为, so that 我不会遇到死按钮或假成功。
8. As a 学习者, I want to 捕获栏在此阶段保持稳定但明确禁用未接入动作, so that 后续捕获功能有固定挂载位置且当前行为诚实。
9. As a 学习者, I want to 在未知地址看到可恢复的未找到页面, so that 我能返回今日或知识空间。
10. As a 学习者, I want to 在页面加载时看到明确状态, so that 我知道应用正在读取本地数据。
11. As a 学习者, I want to 在 API 失败时看到可理解的错误和重试操作, so that 临时故障不会把我困在空白页。
12. As a 学习者, I want to 在没有课程时看到真实空态, so that 我知道数据确实为空并能开始创建第一门课程。
13. As a 学习者, I want to 创建一门学业课程, so that 我能按教育阶段组织学习记录。
14. As a 学习者, I want to 创建一个职业技能空间, so that 我能按学习深度设置技术或工作内容。
15. As a 学习者, I want to 创建一个兴趣主题空间, so that 非学业内容也能进入同一知识容器模型。
16. As a 学习者, I want to 课程名称在去除首尾空白后仍必须非空, so that 列表中不会出现无意义课程。
17. As a 学习者, I want to 选择 SCHOOL 时必须提供教育阶段, so that 后续 AI 上下文完整。
18. As a 学习者, I want to 选择 CAREER 或 INTEREST 时必须提供学习深度, so that 后续 AI 输出能匹配我的目标。
19. As a 学习者, I want to 可选设置课程类型, so that 我能区分专业、通识与选修课程。
20. As a 学习者, I want to 可选填写课程说明, so that Overview 能承载课程目标与边界。
21. As a 学习者, I want to 创建成功后立即在列表中看到课程, so that 我能确认保存已经生效。
22. As a 学习者, I want to 关闭并重启 sidecar 或应用后仍能看到课程, so that 本地持久化是可信的。
23. As a 学习者, I want to 按最近更新顺序浏览课程, so that 最近使用的知识空间更容易找到。
24. As a 学习者, I want to 用名称子串搜索课程, so that 我无需记住完整名称。
25. As a 学习者, I want to 把搜索中的 `%` 和 `_` 当作普通字符, so that 输入不会意外变成数据库通配符。
26. As a 学习者, I want to 按教育阶段筛选课程, so that 我能聚焦某一学段。
27. As a 学习者, I want to 按课程类型筛选课程, so that 我能聚焦专业、通识或选修内容。
28. As a 学习者, I want to 组合搜索与筛选条件, so that 我能快速缩小结果范围。
29. As a 学习者, I want to 筛选结果为空时看到“没有匹配结果”而不是“尚未创建课程”, so that 我能区分数据为空与条件不匹配。
30. As a 学习者, I want to 清除筛选并恢复完整列表, so that 我能快速回到默认视图。
31. As a 学习者, I want to 打开课程详情的 Overview, so that 我能查看课程场景、阶段或深度、类型、说明和热词摘要。
32. As a 学习者, I want to 在课程详情切换 Overview 与 Records 宿主, so that 后续学习记录能在稳定位置接入。
33. As a 学习者, I want to Records 宿主明确说明功能将在后续计划接入, so that 未实现能力不会伪装成真实空列表。
34. As a 学习者, I want to 编辑课程基础信息, so that 课程方向变化时不必重建。
35. As a 学习者, I want to 从 SCHOOL 改为 CAREER 或 INTEREST 时重新提供有效深度, so that 数据不会保留互相矛盾的场景字段。
36. As a 学习者, I want to 从 CAREER 或 INTEREST 改为 SCHOOL 时重新提供教育阶段, so that 数据始终满足课程上下文约束。
37. As a 学习者, I want to 在课程设置中维护手动热词列表, so that 后续 ASR 能使用课程特有词汇。
38. As a 学习者, I want to 最多保存 100 个热词, so that 热词配置符合供应商与产品约束。
39. As a 学习者, I want to 超过 100 个热词时得到明确错误且旧数据不被覆盖, so that 校验失败不会造成数据丢失。
40. As a 学习者, I want to 保存编辑后列表与详情同步刷新, so that 界面不会显示旧数据。
41. As a 学习者, I want to 删除课程前看到明确确认, so that 我不会因误触丢失学习组织结构。
42. As a 学习者, I want to 删除说明告知当前无恢复 UI, so that 我理解这是不可从界面撤销的操作。
43. As a 学习者, I want to 删除后课程立即从列表、搜索和详情查询中消失, so that 软删数据不会泄漏回正常视图。
44. As a 学习者, I want to 打开已删除或不存在的课程时看到未找到状态, so that 我不会操作失效对象。
45. As a 学习者, I want to 所有课程读写只经过本机 sidecar API, so that SQLite 保持单一写者和单一事实源。
46. As a 学习者, I want to sidecar 只监听本机回环地址, so that 局域网其他设备不能访问我的学习数据。
47. As a 学习者, I want to 每次应用启动使用新的随机端口和启动令牌, so that 其他本机进程不能猜固定接口并误触数据。
48. As a 学习者, I want to 没有正确启动令牌的请求被拒绝, so that localhost 不被误当作天然可信边界。
49. As a 开发者, I want to 前端 API 类型由 OpenAPI 生成, so that UI 与 FastAPI 契约不会形成两份手写事实源。
50. As a 开发者, I want to 迁移链在空数据库和已迁移数据库上都可重复启动, so that 用户升级不会破坏已有课程。
51. As a 开发者, I want to 每个 SQLite 连接启用外键和 WAL, so that 数据完整性与桌面读写体验符合本地优先设计。
52. As a 开发者, I want to 查询层恒定过滤软删课程, so that 任一列表或详情调用都不会因漏写条件暴露墓碑数据。
53. As a 视觉敏感的学习者, I want to 亮色和暗色都保持连续工作面而非卡片墙, so that 应用在长时间学习中安静、稳定。
54. As a 小窗口用户, I want to 在 1099×720 时使用压缩侧栏且页面无整体横向滚动, so that 内容在最低支持尺寸仍可操作。
55. As a 桌面用户, I want to 在 1280×800 与 1440×900 下获得稳定布局, so that 常见窗口尺寸都符合设计合同。
56. As a 使用辅助技术的学习者, I want to 图标按钮有可访问名称且状态不只依赖颜色, so that 我能理解并操作界面。

## Implementation Decisions

- 功能按三个可独立验证的纵向增量交付：工作台骨架；课程真实新建/列表闭环；完整课程管理出口。任何增量结束时应用必须可构建、可启动，且不把未完成增量宣称为整个功能完成。
- 工作台采用既定的 Continuous Work Surface：224px 侧栏、64px 顶部捕获栏、28px 内容边距、Zero Card Chrome、近白纸面与暖中性灰、状态色只表达状态。小于 1100px 时侧栏压缩为 64px。
- 桌面页面属于 Operate 模式。现有产品与设计合同已经定稿，本功能只扩展该视觉世界，不举行新视觉方向选择，也不修改全局视觉身份。
- 导航的真实可用入口只有“今日”和“知识空间”。“收件箱”“AI 对话”“资产库”“学习画像”及捕获动作保留稳定位置，但必须使用原生 disabled 语义或等价的不可用语义，并显示“未接入”；不得导航到假页面。
- “今日”在本计划只呈现真实空态与后续内容宿主，不使用模拟待办、统计或 AI 状态。统计属于后续计划。
- 路由使用文件式类型安全路由。列表筛选与详情 tab 属于可分享、可刷新恢复的 URL 状态，不进入全局 store；页面级业务数据只由 TanStack Query 持有。
- 知识空间列表路由为 `/spaces`；课程详情路由为 `/spaces/{course_id}`；详情 tab 用受校验的 `tab=overview|records` 搜索参数表示。不存在或已软删的课程进入未找到状态。
- 前端所有用户可见文案进入中文 i18n 资源，不在组件中硬编码；API 数据类型只从生成的类型包导入，前端不复制 Course 接口。
- 交互控件优先使用现有 shadcn/ui + Base UI 原语，图标只使用 Lucide。不得混入 Radix 或手写 Dialog、Select、Popover 的焦点与键盘行为。
- 主题在本计划跟随操作系统亮/暗偏好；用户可持久化主题设置属于后续设置功能。两种主题都使用同一连续色面、焦点和 Zero Card Chrome 规则。
- FastAPI sidecar 是 SQLite 的唯一写者；React 和 Tauri 不直连数据库，也不直接写业务数据目录。
- 数据目录默认使用用户目录下的 KnowRealm 目录，并创建数据库、文件、缓存、导出、备份和配置所需子目录。完整首启选择、目录迁移与迁移 UI 不在本计划内。
- sidecar 只绑定 `127.0.0.1`。Tauri 壳每次启动分配随机端口并生成密码学安全的单次启动令牌，通过启动参数传给 sidecar；前端从壳的类型化桥接读取 base URL 与令牌，不使用固定端口或构建时环境变量。
- 所有受保护 API 请求携带 `X-KnowRealm-Token`。缺失或不匹配返回 403；令牌、Authorization、课程正文与热词不得进入日志。健康探测同样要求令牌，避免留下旁路。
- sidecar 对生产 WebView origin 和本地开发 origin 使用最小 CORS 允许列表，不允许 `*`；令牌请求头列入允许头。
- API 资源合同如下：`GET /api/courses` 列表与筛选，`POST /api/courses` 创建，`GET /api/courses/{course_id}` 详情，`PATCH /api/courses/{course_id}` 编辑与热词维护，`DELETE /api/courses/{course_id}` 软删除。删除成功返回 204。
- 课程列表查询参数为 `q`、`education_stage` 和 `course_type`。`q` 去除首尾空白后执行名称字面量子串匹配，转义 `%`、`_` 与转义字符；默认按 `updated_at` 降序。
- 课程创建与编辑使用独立请求模型，响应使用独立输出模型。名称清洗后必须非空；枚举使用受控字面量；错误响应统一为 `{"detail": "..."}`。
- `learning_context` 必填。SCHOOL 必须有 `education_stage` 且清空 `depth`；CAREER/INTEREST 必须有 `depth` 且清空 `education_stage`。该规则在 API 边界和 SQLite CHECK 约束同时成立。
- `course_type` 与 `description` 可空。课程初始状态固定为 ACTIVE；本计划不提供归档操作。
- 热词与课程共用 PATCH 事务，不增加单独资源或额外设置存储。热词按用户顺序保存为 JSON 数组，最多 100 个；每项清洗后必须非空。超限或无效时整次更新失败，不部分覆盖。
- 课程表使用 UUID4 文本主键、ISO8601 UTC 文本时间、`created_at`、`updated_at`、`deleted_at`，并建立更新时间、学习场景和课程类型索引。所有正常查询恒定排除 `deleted_at` 非空行。
- SQLite 使用异步 SQLAlchemy 2.0 与 aiosqlite。每个连接启用 `foreign_keys=ON` 和 WAL；请求级会话由依赖提供，事务边界位于课程服务，不设置 Repository 层或全局会话。
- Schema 只通过编号 SQL 迁移和 `PRAGMA user_version` 推进；生产与测试都重放同一迁移链，不使用 ORM `create_all`，不引入 Alembic。
- 删除在单个事务中写入 `deleted_at` 与 `updated_at`。当前计划不预建 Record 或其他后续业务表；计划 02 引入后代实体时，必须在同一删除事务中扩展课程级联软删，并新增相应集成验收，不能用提前创建空表冒充级联完成。
- sidecar 启动后执行一次非阻塞的过期墓碑清理；当前只清理超过 30 天的课程墓碑。后续计划新增后代实体时必须按数据模型扩展同一清理顺序，先清后代再清课程。
- FastAPI OpenAPI schema 是 API 契约唯一来源。生成流程产出 TypeScript 类型包；代码检查必须能发现 schema 与生成物不一致。不得手改生成类型。
- TanStack Query 使用课程 query key 工厂。创建、编辑、删除成功后精确失效列表与详情缓存；不把课程复制进 Zustand，不持久化 Query 缓存。
- 全局加载、错误、未找到边界属于应用壳；列表空态、筛选无结果、保存失败、删除失败属于课程功能。错误必须提供重试或返回路径，不能只输出控制台日志。
- 不新增与当前需求无关的工厂、事件总线、Repository、通用表单引擎、feature flag 系统或持久缓存。已有平台、框架和原语能完成的行为直接复用。

## Testing Decisions

- 测试只断言用户可观察行为和跨边界契约，不断言组件内部 state、CSS 类名、SQLAlchemy 私有调用或 TanStack Query 实现细节。
- 最高层主接缝是“真实桌面渲染 → 带启动令牌的 localhost API → 临时数据目录中的真实 SQLite”。关键路径在这一条接缝完成：真实空态 → 新建 → 列表出现 → sidecar 重启后仍存在 → 搜索/筛选 → 详情 → 编辑/热词 → 删除后不可见。
- 主接缝同时验证浏览器 Network：请求命中随机 `127.0.0.1` 端口、携带 `X-KnowRealm-Token`、响应来自真实 FastAPI，前端没有 fixture、MSW 或内存课程数据。构建通过不替代此证据。
- sidecar API 使用临时数据目录和迁移链进行集成测试，覆盖：首次迁移、重复启动、WAL、创建/列表/详情/编辑/删除、组合筛选、字面量 LIKE 转义、所有场景交叉字段校验、100/101 个热词边界、软删恒定过滤和 30 天清理。
- 启动令牌在 API 最高可用接缝测试：正确令牌成功，缺失与错误令牌均为 403，日志不包含令牌。监听地址与随机端口通过真实进程启动检查，不用 ASGI 内存调用冒充 socket 绑定证据。
- OpenAPI 类型链执行生成与无漂移检查，并用桌面 TypeScript 编译证明课程 API 没有手写重复类型或 `any` 逃逸。
- 前端行为测试通过可访问角色查询，最少覆盖：未接入导航不可激活、课程表单条件字段切换、保存失败保留输入、热词超限错误、删除确认、筛选无结果与 API 错误重试。
- 视觉验收在 1440×900、1280×800、1099×720 一次批量检查，包含亮色、暗色、键盘焦点、disabled 状态、Dialog/Select 键盘操作与整体横向溢出。仅真实交互行允许 hover 和 pointer。
- 骨架完成后做一次渲染检查；课程完整出口后集中执行桌面构建、后端静态检查、迁移/API 集成测试、关键路径与最终渲染检查。测试期间不使用 Docker。
- 验收报告必须区分：源码/静态检查、单元/组件测试、API/SQLite 集成、真实 HTTP、桌面渲染与重启持久化。低层证据不得升级表述为端到端通过。

## Out of Scope

- Record 列表、详情、处理状态、课程下真实 Records 内容与任何 Record API。
- 录音、音频导入、文档导入、粘贴、速记、收件箱整理和捕获成功流程。
- AI 总结、知识点、习题、Todo、Provider、LLM/ASR、LangGraph、SSE 状态流与 worker 队列。
- Course Brain、Knowledge GPS、Course Chat、资产库搜索、学习画像和今日统计。
- 热词自动同步、课程归档、课程移动、恢复已删除课程和删除回收站 UI。
- 完整首启向导、角色卡、按角色预选课程场景、数据目录选择/迁移 UI、全量导出与备份 UI。
- `.msi`、PyInstaller sidecar 打包、ffmpeg 打包、新机安装、自动更新和 CI 发布流水线。
- 新视觉方向、全局设计系统重写、模拟课程、示例学习记录或后续功能的静态假页面。

## Further Notes

- 当前代码基线是干净的桌面脚手架：应用主体为空，FastAPI 后端尚未实现。此规格因此以首个真实纵向切片为目标，不假定已有 Phase 0 能力。
- 测试接缝已按原计划的出口线收敛为一个最高层主接缝，并辅以迁移与安全边界的最小检查。若后续拆票改变这条主接缝，必须在实现前更新本规格，不能以更多低层测试替代它。
- 课程删除的后代级联在当前 schema 中没有可操作对象；提前创建 Record 空表只为“证明级联”会违反按消费者引入基础设施的既定策略。计划 02 是级联行为真正可验收的首个阶段。
- `X-KnowRealm-Token` 是本规格补齐的传输合同名称；它是 localhost 能力令牌，不代表用户认证、会话或账号体系。
