# 02 — 首门课程持久化闭环

**What to build:** 让学习者从知识空间的真实空态创建第一门课程，并立即看到真实列表；课程经安全 localhost sidecar 写入本地 SQLite，sidecar 或应用重启后仍可读取。

**Blocked by:** 01 — 工作台骨架与真实空态.

**Status:** resolved

- [x] 从真实空态可打开课程创建交互，填写名称、学习场景、对应教育阶段或学习深度，以及可选课程类型和说明。
- [x] SCHOOL 必须填写教育阶段并清空学习深度；CAREER/INTEREST 必须填写学习深度并清空教育阶段；API 边界和数据库约束行为一致。
- [x] 创建成功后课程立即出现在按最近更新排序的真实列表中；失败时保留输入并显示可理解、可重试的错误。
- [x] sidecar 创建默认数据目录及当前功能实际需要的子目录，SQLite 开启 WAL 和外键，并通过编号迁移与 `PRAGMA user_version` 建立课程 schema。
- [x] 生产和测试均重放同一迁移链；空数据库首次启动、已迁移数据库重复启动均成功，不使用 ORM `create_all` 或 Alembic。
- [x] FastAPI 提供课程创建和列表契约，路由只负责参数与响应，事务边界位于课程服务；前端不直连数据库或数据目录。
- [x] Tauri 壳每次启动分配随机端口并生成单次启动令牌；sidecar 仅绑定 `127.0.0.1`，正确令牌可访问，缺失或错误令牌均返回 403。
- [x] 所有受保护请求统一携带 `X-KnowRealm-Token`；健康探测没有令牌旁路，日志不包含令牌、Authorization、课程说明或热词。
- [x] 生产 WebView 与本地开发 origin 使用最小 CORS 允许列表，不允许通配 origin。
- [x] OpenAPI 是前端课程类型的唯一来源；生成类型能够被桌面端编译使用，漂移检查可以发现手写或过期契约。
- [x] TanStack Query 持有课程列表并使用稳定 query key；课程数据不进入 Zustand 或持久化前端缓存。
- [x] 使用临时数据目录的 API/SQLite 集成测试覆盖迁移、校验、创建、列表、排序和软删过滤基线。
- [x] 真实进程检查证明监听地址、随机端口及 403 边界；ASGI 内存调用不得冒充 socket 绑定证据。
- [x] 真实桌面 Network 证明请求命中随机 localhost API、携带启动令牌且响应来自 FastAPI，不使用 fixture、MSW 或内存课程数据。
- [x] sidecar 或应用重启后课程仍可读取；源码、API 集成、真实 HTTP、桌面 Network 与持久化证据分别记录。

## Comments

- 2026-08-17 源码/静态：FastAPI 路由薄壳、`CourseService` 事务边界、SQLAlchemy async SQLite、`0001_courses.sql` + `PRAGMA user_version`、Tauri 类型化桥接与统一 HTTP 客户端落地；OpenAPI schema/types 的 generate 与 `--check` 均通过。PyInstaller sidecar 与 `.msi` 仍按规格属于 Out of Scope，未据此声称安装包完成。
- API/SQLite 集成：临时数据目录下 4/4 pytest 通过，覆盖首次/重复迁移、WAL、外键、API 与 CHECK 交叉字段约束、创建/列表、最近更新排序、软删过滤和重启持久化；Ruff、Pyright strict 通过。
- 前端组件：Vitest 4/4 通过，覆盖真实空态入口、条件字段、失败保留输入、启动令牌头、单次 POST 与创建后 Query 列表刷新；TypeScript strict、ESLint、Prettier、Vite build、Impeccable detector `[]` 通过。
- 真实 HTTP/socket：实进程测试通过；现场端口 55426 仅监听 `127.0.0.1`，归属 Python sidecar，缺失/错误令牌均为 403；Tauri 退出后旧端口关闭。Rust test、Clippy `-D warnings`、fmt 通过。
- 真实桌面 Network：WebView2 请求命中随机 `http://127.0.0.1:55426/api/courses`，POST/GET 均携带 64 字符 `X-KnowRealm-Token`，响应 201/200；无 fixture、MSW 或内存课程数据。无乱码复验使用端口 57939，创建后列表为 1 行。
- 重启持久化：关闭并重启 Tauri 后端口从 57939 变为 56957、令牌重新生成且长度 64，同一 SQLite 中的“操作系统”仍由真实 GET 读取并渲染为 1 行；测试数据目录随后已删除，避免污染用户环境。
- 渲染：1280×800 亮色/暗色、1099×720（侧栏稳定为 64px）、Dialog/Select、Tab 焦点与整体横向溢出已检查；runtime error、Vite overlay 和横向溢出均为 0。录制位于 browser-harness 的 `course-persistence-clean` 与 `course-persistence-clean-restart`。
