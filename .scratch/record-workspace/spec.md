# Record 工作区：真实列表、详情与软删除

Status: ready-for-agent

## Problem Statement

KnowRealm 已经具备工作台外壳、知识空间列表、课程详情以及课程详情内稳定的 Records 内容宿主，但 Record 仍没有真实数据链路。学习者进入 Records 时只能看到“尚未接入”，无法查看持久化学习记录、理解当前处理状态、打开详情或删除记录。后续文档导入、音频转写、录音、轻捕获和 AI 总结都需要一个稳定的 Record 数据与界面入口；如果各来源管线自行创建列表、详情或删除逻辑，会形成多套状态解释、查询入口和软删边界。

本功能还面临两个真实性风险。第一，当前没有 Record 创建入口，如果为了演示非空列表而加入生产种子接口、示例数据或临时创建 API，会把测试工具变成产品合同。第二，`FAILED` 的技术失败来源、资产存在性、轮询和重试都依赖尚未落地的后台任务与资产表；若在本阶段提前模拟这些能力，就会破坏业务态与技术态分离，并冻结没有真实消费者的接口。

因此需要一个最小但完整的 Record 纵向切片：只建立 Record 本体、真实查询、全局详情入口和当前可验证的删除语义；所有页面经受保护的 localhost API 读取 SQLite，不伪造创建、处理、资产或恢复能力。

## Solution

在现有课程详情 Records 宿主内接入真实 Record 列表。没有记录时展示真实空态；存在持久化记录时按创建时间倒序展示标题、捕获类型、时间和八态业务状态。学习者可以从列表进入全局 Record 详情路由，刷新或直接打开仍能读取同一条本地记录。

Record 详情以 Summary 为默认可进入页面，当前只显示“尚未生成”的诚实状态。Transcript、知识点、习题、复习、Todo 和 Ask AI 保留最终信息架构标签，但在对应资产功能接入前使用明确的禁用语义。FAILED 只表达用户可理解的处理失败，并说明当前没有可用恢复操作；本阶段不展示虚构失败来源或重试按钮。

学习者可以通过确认弹窗软删除 Record。删除成功后，该 Record 立即从课程列表和直接详情查询中消失。课程被删除时，其下 Record 在同一事务内同步软删；Record 自身或父 Course 任一已删除，正常查询都视为不存在。最终物理级联由数据库外键承接，但文件、向量、Chat、Evidence 和 30 天批量物理清理留给出现真实消费者后的删除链扩展。

本功能不提供生产 Record 创建接口。非空态、八态和持久化验收使用测试专用临时 SQLite 植入数据，再通过真实 localhost API 和桌面 UI 读取；证据明确标注为迁移、查询、渲染与重启持久化，不冒充捕获链路端到端完成。

## User Stories

1. As a 学习者, I want to 在课程详情进入 Records, so that 我能在稳定位置查看这门课程的学习记录。
2. As a 学习者, I want to 没有记录时看到真实空态, so that 我不会把未接入提示误认为数据加载失败。
3. As a 学习者, I want to 空态不包含示例记录, so that 虚构内容不会污染我的真实学习数据。
4. As a 学习者, I want to 有记录时按创建时间从新到旧排列, so that 我能优先继续最近的学习活动。
5. As a 学习者, I want to 在列表中看到记录标题, so that 我能识别每次学习会话。
6. As a 学习者, I want to 未填写标题的记录显示统一的未命名文案, so that 可选标题不会造成空白列表项。
7. As a 学习者, I want to 在列表中看到捕获类型, so that 我能区分录音、音频、文档、粘贴、速记和剪藏来源。
8. As a 学习者, I want to 在列表中看到本地时间, so that UTC 存储不会让我误判记录发生时间。
9. As a 学习者, I want to 仅在时长有效时看到时长, so that 文档或未知时长不会显示误导性的零分钟。
10. As a 学习者, I want to NOTE 显示为可理解的仅保存状态, so that 我知道该内容尚未进入处理管线。
11. As a 学习者, I want to DRAFT 显示为草稿状态, so that 我知道记录已经建立但尚未处理。
12. As a 学习者, I want to CONTENT_PROCESSING 显示为内容处理中, so that 我能理解转码、解析或转写尚未完成。
13. As a 学习者, I want to SUMMARY_PENDING 显示为等待生成总结, so that 我知道内容已准备但总结尚未开始。
14. As a 学习者, I want to SUMMARY_PROCESSING 显示为总结生成中, so that 我知道 AI 处理仍在进行。
15. As a 学习者, I want to SUMMARY_READY 显示为总结待确认, so that 我知道后续需要人工处理。
16. As a 学习者, I want to COMPLETED 显示为已完成, so that 我能辨认已走完当前业务流程的记录。
17. As a 学习者, I want to FAILED 显示为处理失败, so that 技术错误不会以内部任务枚举暴露给我。
18. As a 学习者, I want to FAILED 在没有真实任务命令时明确说明暂无恢复操作, so that 我不会点击一个无法成功的假按钮。
19. As a 学习者, I want to 从记录列表进入详情, so that 我能在统一工作区继续处理学习资产。
20. As a 学习者, I want to 刷新 Record 详情后仍能读取同一条记录, so that 页面不是依赖列表内存状态的临时视图。
21. As a 学习者, I want to 直接打开 Record 详情链接, so that 记录拥有独立于课程入口的稳定地址。
22. As a 学习者, I want to Inbox 中未来出现的未归类 Record 复用同一详情地址, so that 系统不会因为 course_id 为空再建第二套详情页。
23. As a 学习者, I want to Record 详情默认进入 Summary, so that 页面结构与最终产品信息架构一致。
24. As a 学习者, I want to 尚未生成 Summary 时看到诚实空态, so that 页面不会展示虚构 AI 内容。
25. As a 学习者, I want to 尚未接入的资产标签清楚显示为禁用, so that 我不会把静态文字误认为可用入口。
26. As a 键盘用户, I want to 禁用标签不能获得误导性的激活行为, so that 键盘导航与视觉状态保持一致。
27. As a 学习者, I want to 删除前看到明确确认与不可从界面恢复的说明, so that 我不会因误触丢失学习记录入口。
28. As a 学习者, I want to 取消删除时保持当前详情和数据不变, so that 关闭确认框不会产生副作用。
29. As a 学习者, I want to 删除失败时留在当前页面并获得可重试错误, so that 短暂的本地数据库错误不会让我丢失上下文。
30. As a 学习者, I want to 删除成功后记录立即从列表消失, so that 软删墓碑不会泄漏回正常视图。
31. As a 学习者, I want to 删除成功后直接访问详情得到未找到状态, so that 已删除对象不能继续被操作。
32. As a 学习者, I want to 删除课程后其下 Record 同时不可见, so that 父知识空间与子学习记录的生命周期一致。
33. As a 学习者, I want to 已删除父 Course 下的 Record 不能通过猜测地址访问, so that 嵌套数据不会绕过父对象可见性。
34. As a 学习者, I want to 未归类且未删除的 Record 仍可通过全局详情读取, so that Inbox 后续能复用 Record 本体能力。
35. As a 学习者, I want to 列表或详情加载失败时看到可理解错误和重试动作, so that API 错误不会被伪装成空数据。
36. As a 学习者, I want to 加载期间看到稳定状态, so that 页面不会短暂闪现错误空态。
37. As a 学习者, I want to 亮色、暗色和现有桌面尺寸下保持连续工作面, so that Record 页面与课程页面属于同一产品。
38. As a 使用辅助技术的学习者, I want to 状态不只依赖颜色表达, so that 我能通过文字和语义理解记录状态。
39. As a 开发者, I want to Record API 类型由 FastAPI OpenAPI 生成, so that 前后端没有第二份手写契约。
40. As a 开发者, I want to Record 状态与捕获类型是受控枚举, so that 非法字符串不能进入持久化数据或 UI 分支。
41. As a 开发者, I want to 所有正常 Record 查询恒定过滤软删边界, so that 新调用方不会偶然暴露墓碑数据。
42. As a 开发者, I want to Course 软删与其 Record 软删共享事务, so that 部分成功不会留下生命周期矛盾。
43. As a 开发者, I want to 从已有 user_version 升级和空库初始化都使用同一迁移链, so that 老用户与新用户得到相同 schema。
44. As a 开发者, I want to 测试直接植入的数据只存在于临时数据目录, so that 验收工具不会进入生产 API 或用户目录。
45. As a 开发者, I want to 真实桌面证据经过随机 localhost 端口和启动令牌, so that 组件 mock 不会被误报为桌面集成完成。
46. As a 维护者, I want to 验收报告区分静态、API/SQLite、真实 HTTP、Network、渲染和重启持久化, so that 每项完成声明都能追溯到正确证据层。

## Implementation Decisions

- 本功能是贯穿 SQLite、FastAPI、OpenAPI 类型和桌面 UI 的最小纵向切片。它复用现有工作台外壳、课程详情 Records 宿主、统一 localhost 客户端、TanStack Query、路由、Dialog、Tabs 与错误边界，不增加依赖或第二套基础设施。
- SQLite 新增 records 表。字段包括文本主键、可空 course_id、capture_type、title、status、duration_ms、可空 summary_confirmed_at、created_at、updated_at 和可空 deleted_at。
- course_id 引用 Course，允许为空以支持 Inbox；最终物理删除使用 `ON DELETE CASCADE`。该外键只承接父 Course 最终物理删除，不替代应用层软删事务。
- capture_type 是受控枚举：RECORDING、AUDIO_IMPORT、DOCUMENT_IMPORT、PASTE、QUICK_NOTE、CLIP。
- status 是受控八态枚举：NOTE、DRAFT、CONTENT_PROCESSING、SUMMARY_PENDING、SUMMARY_PROCESSING、SUMMARY_READY、COMPLETED、FAILED。数据库不提供隐式业务状态默认值，未来每个创建来源必须明确写入正确状态。
- title 为非空文本但允许空字符串，因为录音标题在产品合同中可选。UI 对空白标题使用统一的“未命名学习记录”回退文案，不回写派生标题。
- duration_ms 为非负整数，未知或不适用时存 0；UI 仅在值大于 0 时展示格式化时长。
- 时间统一存 ISO8601 UTC 文本。UI 使用当前系统时区格式化，不在本功能引入可持久化时区设置。
- records 建立创建时间倒序索引、course_id 与创建时间的组合索引、status 索引。列表按 created_at 降序；验收数据使用不同时间值，不依赖未定义的同毫秒排序。
- 迁移继续使用编号 SQL 与 `PRAGMA user_version`，同时支持空库顺序执行和现有课程数据库升级。ORM 不能使用 `create_all` 代替迁移。
- Record 只提供一个输出模型供列表和详情复用，字段为 id、course_id、capture_type、title、status、duration_ms、summary_confirmed_at、created_at 和 updated_at；deleted_at 不进入正常响应。
- API 提供 `GET /api/courses/{course_id}/records`。父 Course 不存在或已删除时返回 404；存在但没有 Record 时返回空数组；结果只包含未删除 Record并按 created_at 降序。
- API 提供 `GET /api/records/{record_id}`。Record 不存在、自身已删除，或其非空 course_id 指向已删除 Course 时统一返回 404。course_id 为空且自身未删除的 Record 可正常返回。
- API 提供 `DELETE /api/records/{record_id}`。可见 Record 删除成功返回 204；不存在或已删除返回 404。接口只执行软删，不同步物理删除文件或业务行。
- 本功能不提供 POST、PATCH、批量删除、恢复或测试种子 API。后续捕获功能通过各自真实入口创建 Record。
- 所有 Record 路由沿用现有 localhost 启动令牌鉴权和统一字符串错误响应；缺失或错误的 `X-KnowRealm-Token` 返回 403。
- Record 查询与删除事务放在普通确定性 Service 中，不引入 Repository 接口、工厂、事件总线或通用 CRUD 基类。
- Record 列表查询恒定包含自身 deleted_at 过滤。Record 详情同时检查自身可见性和父 Course 可见性；对 course_id 为空的记录不强制父 Course 条件。
- Course 软删除服务在同一事务内更新 Course 及其全部未删除 Record 的 deleted_at 与 updated_at。失败时整次回滚，不允许父对象已删而子对象仍为活跃墓碑。
- 现有 Course 30 天物理清理可通过外键级联删除其 Record 行；独立 Record 墓碑的 30 天批量物理清理随首个真实 worker 引入。本功能不能宣称完整完成文件、向量、Chat、Evidence 或 Mastery 删除链。
- 删除 Record 不级联 Chat。当前尚无 Chat 表或会话行为，因此本功能只保留领域合同，不预建 Chat schema、失效标记或查询。
- FastAPI OpenAPI 是 Record 请求与响应类型的唯一来源；桌面端只从生成类型包导入 RecordStatus、CaptureType 和 Record 输出结构，不复制字符串联合类型。
- 生成的 OpenAPI JSON 和 TypeScript 声明文件固定使用 LF。仓库级换行规则必须让生成、检出和 `--check` 在 `core.autocrlf=true` 的 Windows 环境下得到同一字节结果，根治当前无语义变化却报告 stale 的门禁。
- 桌面端增加 Record query key 工厂，至少区分全部 Record、指定 Course 的列表和指定 Record 的详情。删除成功后精确失效所属 Course 列表并移除或失效详情缓存，不把 Record 复制进 Zustand 或持久前端缓存。
- 课程详情 Records 宿主从“尚未接入”切换为真实查询状态：加载、错误、真实空态和非空列表互斥。API 错误保留重试动作，不用空数组代替错误。
- Record 列表项展示标题回退、捕获类型、创建时间和状态文字。状态色仅作辅助，文字是权威表达；无有效时长时不展示时长占位。
- 状态中文映射为：NOTE“仅保存”、DRAFT“草稿”、CONTENT_PROCESSING“内容处理中”、SUMMARY_PENDING“等待生成总结”、SUMMARY_PROCESSING“总结生成中”、SUMMARY_READY“总结待确认”、COMPLETED“已完成”、FAILED“处理失败”。
- 点击列表项进入全局 `/records/{record_id}` 路由。该路由不嵌套 course_id，避免未来 Inbox Record 产生第二套详情页面；course_id 只用于显示归属和返回课程 Records 的上下文。
- Record 详情包含标题、捕获类型、创建时间、可选时长、状态和删除入口。course_id 非空时提供返回对应课程 Records 的路径；course_id 为空时提供返回知识空间的安全路径，Inbox 在后续功能接入时替换为自身来源路径。
- 详情默认激活 Summary。当前 Summary 内容只显示未生成/尚未接入的真实状态，不根据 Record status 推断资产存在，也不请求不存在的 Summary 端点。
- Transcript、知识点、习题、复习、Todo 和 Ask AI 标签使用原生 disabled 或等价的可访问禁用语义。禁用项不导航、不获得激活样式、不伪装 hover/pointer，也不创建空 feature、资产探测或 available_assets 聚合接口。
- FAILED 详情显示通用说明和“暂无可用恢复操作”。本功能不创建 processing_jobs、不展示 error_code/error_message、不轮询、不连接 SSE，也不提供重试按钮。
- 删除确认复用现有 Dialog 原语，明确告知当前无恢复 UI。取消无副作用；失败保留当前上下文和重试能力；成功后清理缓存并返回来源 Course 的 Records，直接路由随后为 404。
- 所有新增用户可见文案进入中文 i18n 资源。页面继续遵循既定 Continuous Work Surface、主题、焦点、响应式和无整体横向溢出合同，不修改应用外壳或全局视觉身份。
- 生产构建不包含示例 Record、静态列表、种子按钮、开发者菜单或隐藏创建入口。测试植入只能操作测试专用临时数据目录。

## Testing Decisions

- 测试断言外部行为和跨边界合同，不断言组件内部 state、CSS 类名、SQLAlchemy 私有调用、具体 query key 数组形状或迁移实现细节。
- 最高层主接缝是“真实桌面 Records/详情渲染 → 携带启动令牌的随机 localhost API → 临时数据目录中的真实 SQLite”。这条接缝验证非空列表、八态、详情直达、软删除和重启持久化；它不验证任何捕获来源。
- 非空态使用测试专用植入：在 sidecar 未运行时，对已执行正式迁移的临时 SQLite 写入 Course 与 Record；随后启动真实 sidecar 和桌面读取。生产 API、用户数据目录和前端代码中不存在种子能力。
- 迁移/API 集成测试覆盖从现有 user_version 升级与空库初始化，确认 records 表、外键、索引、八态 CHECK、捕获类型 CHECK、非负时长约束和 user_version 推进。
- 数据库约束测试至少拒绝非法 status、非法 capture_type、负 duration_ms 和不存在的非空 course_id；允许合法 course_id 与 NULL course_id。
- API 集成测试覆盖：有效 Course 空列表、created_at 倒序、八态序列化、course_id 为空详情、父 Course 不存在或已删返回 404、Record 自身已删返回 404、删除成功 204、重复删除 404。
- Course 生命周期集成测试覆盖同一事务软删其下多个 Record，并验证父删除后课程列表、Record 列表和直接 Record 详情均不可见。通过故障注入或事务失败检查证明不会部分提交。
- 最终物理外键测试覆盖删除 Course 物理行后 Record 行级联消失；该证据只证明数据库行级联，不冒充文件、向量或完整 30 天清理链。
- 启动令牌边界沿用现有最高接缝：正确令牌可访问三个 Record API，缺失和错误令牌均为 403。日志不得包含令牌或学习内容。
- OpenAPI 测试执行 schema 导出、TypeScript 类型生成和无漂移检查；额外在 Windows `core.autocrlf=true` 条件下证明连续生成两次仍为 clean，避免只做语义比较掩盖换行假失败。
- 前端组件行为测试使用现有 MSW 与可访问角色查询，覆盖加载、API 错误重试、真实空态、倒序列表、标题回退、八态文字、详情直达、未来标签禁用、FAILED 无重试、删除取消、删除失败和删除成功后的导航/缓存表现。
- 组件测试中的 MSW 只证明前端行为，不作为 localhost、SQLite、Network 或桌面端到端证据。
- 真实 HTTP 进程测试使用随机端口和临时数据目录，证明请求穿过实际 socket、令牌中间件、FastAPI 与 SQLite；ASGI 内存调用不替代该证据。
- 真实桌面 Network 验证列表、详情和删除请求命中随机 `127.0.0.1` 端口并携带 `X-KnowRealm-Token`，响应数据来自植入的临时 SQLite，而非 MSW、fixture 或前端内存。
- 重启持久化验证在同一临时数据目录重启 sidecar 后，未删除 Record 仍可读取，已删除 Record 仍保持不可见；随机端口和启动令牌应随重启变化。
- 视觉与可访问性检查覆盖 1440×900、1280×800、1099×720，至少包含亮色/暗色、键盘焦点、禁用标签语义、删除 Dialog 和整体横向溢出。
- 静态门禁覆盖后端格式、Lint、严格类型检查、迁移/API 测试，桌面 TypeScript、组件测试、Lint、格式和构建，以及 OpenAPI 生成物检查；本功能不使用 Docker。
- 完成报告分开列出：源码/静态、数据库迁移、API/SQLite 集成、真实 HTTP/socket、桌面组件、真实 Network/渲染、重启持久化。任一低层通过不能升级表述为更高层通过。
- 实现结束后以开始该功能前的固定点运行 Standards + Spec 双轴审查；两轴均通过后才把后续 ticket 标记完成。

## Out of Scope

- 任何生产 Record 创建、编辑、批量删除、恢复或种子接口。
- 录音、音频导入、文档导入、速记、粘贴、剪藏和 Inbox 视图。
- Transcript 正文、Summary 正文、知识点、习题、复习资料、Todo 和 Ask AI 的真实资产查询或交互。
- processing_jobs、asyncio worker、轮询、SSE、技术失败来源、任务进度、重试命令和自动状态推进。
- available_assets 聚合字段、资产存在性预探测或根据 Record status 推断资产存在。
- 文件、向量、Chat、Evidence、Mastery 的软删扩展，以及独立 Record 墓碑的 30 天批量物理清理。
- 挂载 Record 的 Chat 失效态 UI；本功能只保持“不级联删除 Chat”的领域合同。
- 收件箱归类/升级、课程间移动 Record、全局 Record 搜索、筛选、分页和虚拟滚动。
- 空态引导卡完整 Wave B 交互、示例数据、产品向导或教学演示记录。
- Provider、LLM、ASR、ffmpeg、LangGraph、Learning Event 和任何 AI 调用。
- 应用外壳、左栏、顶部捕获栏、主题系统、全局设置或新的视觉方向。
- `.msi`、PyInstaller sidecar 打包、新机安装、CI 发布或自动更新。

## Further Notes

- 当前代码已经真实具备 Course 详情、Records 稳定宿主、SQLite/WAL/迁移器、受启动令牌保护的随机 localhost sidecar、OpenAPI 类型链和 TanStack Query；Record 表、模型、API、生成类型、查询和页面均尚不存在。实现应扩展现有路径，不重建基础设施。
- 当前 Course 软删除只处理 Course 本身。records 成为首个真实后代实体后，Course → Record 同事务软删是本功能的 P0 完整性要求，不属于额外功能扩张。
- `FAILED` 的来源只能来自未来 processing_jobs；本功能选择通用失败说明，是为了守住业务态与技术态边界，而不是遗漏错误处理。
- Summary 默认可进入、其余资产标签禁用，是当前信息架构与真实能力之间的阶段合同。后续资产功能应在拥有真实表和查询时启用对应标签，不应回头增加统一 available_assets 占位协议。
- Record 创建不属于本功能，因此测试植入是验收手段，不是用户功能。任何完成报告必须明确说明“持久化读取已验证，捕获链路未验证”。
- 当前 TypeScript OpenAPI 无漂移检查会因 Windows CRLF/LF 字节差异产生假失败。本功能首次修改生成契约，必须同时修复仓库级 EOL 规则；忽略、手工重写生成文件或绕过 `--check` 都不是可接受方案。
- 本规格不产生新领域术语，也没有满足 ADR 的不可逆、反直觉且存在真实权衡三条件；因此不修改领域词汇表，不新增 ADR。
