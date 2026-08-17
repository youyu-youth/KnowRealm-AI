# 02 — 首门课程持久化闭环

**What to build:** 让学习者从知识空间的真实空态创建第一门课程，并立即看到真实列表；课程经安全 localhost sidecar 写入本地 SQLite，sidecar 或应用重启后仍可读取。

**Blocked by:** 01 — 工作台骨架与真实空态.

**Status:** ready-for-agent

- [ ] 从真实空态可打开课程创建交互，填写名称、学习场景、对应教育阶段或学习深度，以及可选课程类型和说明。
- [ ] SCHOOL 必须填写教育阶段并清空学习深度；CAREER/INTEREST 必须填写学习深度并清空教育阶段；API 边界和数据库约束行为一致。
- [ ] 创建成功后课程立即出现在按最近更新排序的真实列表中；失败时保留输入并显示可理解、可重试的错误。
- [ ] sidecar 创建默认数据目录及当前功能实际需要的子目录，SQLite 开启 WAL 和外键，并通过编号迁移与 `PRAGMA user_version` 建立课程 schema。
- [ ] 生产和测试均重放同一迁移链；空数据库首次启动、已迁移数据库重复启动均成功，不使用 ORM `create_all` 或 Alembic。
- [ ] FastAPI 提供课程创建和列表契约，路由只负责参数与响应，事务边界位于课程服务；前端不直连数据库或数据目录。
- [ ] Tauri 壳每次启动分配随机端口并生成单次启动令牌；sidecar 仅绑定 `127.0.0.1`，正确令牌可访问，缺失或错误令牌均返回 403。
- [ ] 所有受保护请求统一携带 `X-KnowRealm-Token`；健康探测没有令牌旁路，日志不包含令牌、Authorization、课程说明或热词。
- [ ] 生产 WebView 与本地开发 origin 使用最小 CORS 允许列表，不允许通配 origin。
- [ ] OpenAPI 是前端课程类型的唯一来源；生成类型能够被桌面端编译使用，漂移检查可以发现手写或过期契约。
- [ ] TanStack Query 持有课程列表并使用稳定 query key；课程数据不进入 Zustand 或持久化前端缓存。
- [ ] 使用临时数据目录的 API/SQLite 集成测试覆盖迁移、校验、创建、列表、排序和软删过滤基线。
- [ ] 真实进程检查证明监听地址、随机端口及 403 边界；ASGI 内存调用不得冒充 socket 绑定证据。
- [ ] 真实桌面 Network 证明请求命中随机 localhost API、携带启动令牌且响应来自 FastAPI，不使用 fixture、MSW 或内存课程数据。
- [ ] sidecar 或应用重启后课程仍可读取；源码、API 集成、真实 HTTP、桌面 Network 与持久化证据分别记录。
