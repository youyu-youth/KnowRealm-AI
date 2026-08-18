# 03 — 课程搜索与筛选

**What to build:** 让学习者在真实课程列表中按名称子串、教育阶段和课程类型快速缩小范围，并能刷新、清除条件或从无匹配结果恢复。

**Blocked by:** 02 — 首门课程持久化闭环.

**Status:** resolved

- [x] 课程列表支持名称搜索、教育阶段筛选、课程类型筛选以及三者组合使用。
- [x] 名称搜索去除首尾空白并执行字面量子串匹配；`%`、`_` 和转义字符按普通输入处理，不成为数据库通配符。
- [x] 搜索和筛选参数位于受校验的 URL 状态中，刷新页面后仍可恢复，不进入 Zustand。
- [x] 有课程但无匹配结果时显示“没有匹配结果”，与尚未创建课程的真实空态明确区分。
- [x] 学习者可以一次清除全部条件并恢复默认的最近更新排序列表。
- [x] API 查询参数、OpenAPI 生成类型和前端调用保持单一契约，不新增重复手写类型。
- [x] 所有列表查询恒定过滤已软删课程；组合条件不会使墓碑数据重新出现。
- [x] 查询失败显示可理解的错误与重试动作，不用空数组伪装成功。
- [x] API/SQLite 集成测试覆盖普通中文搜索、组合筛选、空白搜索、字面量 LIKE 转义、无匹配结果和软删过滤。
- [x] 前端行为测试通过可访问角色操作搜索、筛选、清除和错误重试，不断言内部 state 或 CSS 类名。
- [x] 真实桌面 Network 证明筛选请求命中 sidecar 且渲染结果来自真实 SQLite；静态测试或 mock 不作为集成通过依据。

## Comments

- 2026-08-18 API/SQLite：临时数据目录下后端 6/6 pytest 通过；课程集成测试覆盖中文子串、组合筛选、空白查询、`%`/`_`/反斜杠字面量匹配、无匹配与组合条件下软删过滤。Ruff、Pyright strict 与 OpenAPI schema 漂移检查通过。
- 2026-08-18 前端：筛选状态由 `/spaces` 的 `validateSearch` 校验并保存在 URL；查询参数类型直接来自 OpenAPI `operations`，Query key 包含筛选条件。可访问行为测试 7/7、双 tsconfig、ESLint、Prettier、Vite build 与 Impeccable detector `[]` 通过。
- 2026-08-18 真实桌面：Tauri WebView2 1280×800 连接随机 sidecar `127.0.0.1:58857`，真实 SQLite 创建 4 门课程后，Network 依次命中 `q=操作`、`education_stage=UNDERGRADUATE`、`course_type=MAJOR`，最终仅渲染“操作系统”；无匹配、清除恢复 4 行、无 overlay/console 告警通过。1099×720 暗色下 `scrollWidth=1099`，无整体横向溢出。录制目录为 browser-harness `course-discovery-real`。
- 2026-08-18 审查修复：双轴审查发现空库携带筛选 URL 会误判“无匹配结果”，以及 API 在 trim 前执行长度校验。实现已改为零结果时用既有无条件列表确认真实空态，并把清洗与 100 字约束统一到 Pydantic 查询边界；对应后端回归已通过。修复后前端依赖环境因既有 `node_modules` 文件缺失及镜像超时未能重跑，故前端行为与真实桌面两项恢复为待人工复验，不沿用修复前证据宣称最终通过。
- 2026-08-18 复验（ZCode）：后端 6/6 pytest、Ruff 通过；前端 9/9 vitest（含空态区分与错误重试）、ESLint、Prettier、双 tsconfig + Vite build 通过，验收项 10 恢复勾选。复审将筛选列宽魔法间距 token 化（`--spacing-filter-search` / `--spacing-filter-select`，desktop-ui.md §1）。验收项 11 真实桌面 Network 仍待人工复验，Status 保持 ready-for-human。
- 2026-08-18 人工复验：用户在真实桌面确认列表渲染 4 门当日真实创建的课程（截图佐证，数据来自真实 SQLite），并确认验收项 11 通过；10/10 全勾，议题 resolved。
