# 01 资料学习与返回计划闭环：实施与验收

基点 `7f745d38b37d9b7ab511dafc2c52a3e69b0eafb8`，分支 `feat/extend-dev-09`，首个实现提交 `96da766`。范围只含工单 01；已有 02 的练习准备能力保留，03～05 不随本票关闭。

## 实现与事实边界

- `GET /api/plan-items/{id}/study` 查询关联、有效来源、最近明确启动及页签；资料候选复用本课程归属或有效共享引用的可见性，最多显示 50 条，可按标题继续搜索。推荐不能按标题静默绑定。
- 关联复用现有计划项 PATCH、`update_plan_item` Operation、快照、审计及确认卡。仅资料项可修改关联，提交重验版本、目标及记录；三档 Agent 授权均要求用户确认具体记录，绕过薄工具的自动执行也拒绝保存。来源名称/版本变化使旧确认失效。
- `POST .../study/start` 显式启动，`PUT .../study/tab` 只接受当前启动身份和同一记录。迁移 0053 为计划项新增四个可恢复访问字段；初次明确启动时可使用记录已有页签，此后普通入口只写原 continue-learning 元数据，不回填本项学习结果。没有计时、阅读百分比、LLM 代读或额外掌握度事件。
- 历史计划、完结目标及跳过项不能启动、保存本次页签、改关联或完成。原有跳过项的文本/日期编辑语义保留；当前生效且目标进行中的 DONE 项可继续打开，完成仍复用首次时间戳及今日完成投影，不重复计数。
- 无关联项可首次选择，来源失效说明原因并提供重新关联，不保留失效记录链接；记录物理删除后保留启动身份用于解释失效。课程软删后所有新增查询同样不可见。
- 页面通过现有 Router/Query 接入。记录 URL 携带计划项和访问身份，返回独立原计划项，再按真实目标/版本定位课程计划行并恢复焦点；写后刷新现有计划及今日缓存。Agent 已装配 `get_plan_study`，只查询与返回站内入口，关联/完成走已有受控链。
- 共享来源保留只读，页签、文字阅读和外部读取刷新可用；内容写控件禁用，复习写工作台不挂载。资料转为共享时重新挂载记录内容以关闭旧写弹窗；生成总结/知识点/习题携带请求课程，复用既有服务端共享只读校验。普通记录入口仍沿用原行为。

## 测试接缝与证据

固定数据沿用 `tests/test_plan_editing.py` 的 COURSE_ID / PLAN_ID / ITEM_ID / RECORD_ID。HTTP 使用生产 `create_app`、完整 lifespan/迁移、启动令牌与真实临时 SQLite；资料学习不调用外部模型。页面使用真实 Router/Query＋MSW，IPC 为替身。

| 层级 | 状态 | 证据及范围 |
| --- | --- | --- |
| 首条 HTTP 用例 RED→GREEN | PASS | `.pytest-tmp-runs/20261017T071934Z-eee64436/backend/` 原本 404；`20261017T072100Z-4e91741f/backend/` 同用例通过 |
| 新增领域/HTTP/已装配 Tool | PASS | `20261017T072543Z-912a73ef/backend/` 12 项通过：关联、三档人工确认、启动、页签、重启、历史/失效、共享、首次完成与零学习证据 |
| 原计划编辑与旧库回拨夹具 | PASS | `20261017T073436Z-a76e8668/backend/` 原编辑与迁移夹具等 36 项通过；新增 stale 用例把旧确认框架 422 错写成 409，该断言已按真实契约修正，`20261017T073603Z-789baae3/backend/` 单项通过 |
| 页面基本闭环 | PASS | `20261017T073335Z-477d5580/frontend/` 4 项通过：关联后焦点、启动/页签/返回/再次打开、完成后计划行焦点与缓存、失效历史、过期访问、共享只读 |
| 评审修复与最终页面 | PASS | `20261017T074422Z-926be29e/frontend/` 页面及四个记录面板共 44 项通过；最终公开 `course_id` 参数版本在 `20261017T075007Z-b4f5dd13/frontend/` 新进程运行 6 项全通过 |
| 真实共享写防线 | PASS | `20261017T074856Z-df41029c/backend/`：有效他课归属＋资料库共享夹具，总结生成真实 HTTP 请求被既有共享只读校验拒绝，没有调用模型；三个生成调用的 `course_id` 传递另经源码与公开契约核对。早期测试的供应商前置条件及错误查询参数已纠正，失败原日志保留 |
| 真实 HTTP/SQLite 浏览器 | PASS | `.pytest-tmp-runs/record-study-20261017/browser-result.json`：24 组四主题×双语×三种视口/字号，无横向溢出、无页面运行错误；真实补关联→阅读→刷新→人工完成→原行焦点 |
| 最终共享状态动态变化 | PASS | `record-study-20261017/transition-browser-result.json`：真实 HTTP 迁移归属、共享、移除共享，浏览器模拟窗口 focus；原写弹窗关闭、只读内容仍可刷新、失效后可重新关联。截图 `04-shared-transition.png`、`05-invalid-source.png` 已目视检查；此补验没有另外的主题矩阵 |
| 真实模型 | NOT_RUN | 本票无模型代读；自然语言意图选择质量及真实模型 Tool 调用由 05 验收 |
| 原生 Tauri/WebView2、系统缩放、屏幕阅读器 | NOT_RUN | 浏览器使用 Tauri IPC 替身，视口/字号不代表 Windows 系统缩放，原生复验归 05 |

双轴评审修复后未解决项均为 0，见 [评审记录](01-review.md)。全量及基点复核已结束；失败原始结果保留，不视为通过。

### 全量原始结果

执行 `uv run --frozen --directory backend python -m scripts.run_tests all`，结果目录 `20261017T073631Z-0dc6c8fd/{frontend,backend}/`。前端 808 通过 / 8 失败，后端 1350 通过 / 26 失败；后端实际耗时 2236.55 秒，未超时或中断。本票新增后端 13 项、原计划编辑 20 项、已交付练习准备 25 项及今日继续学习回归均通过。

前端全量启动后发生评审修复并补入两个边界用例，原始失败中这两项不能用来代表最终源码；最终文件在新进程运行 6 项全部通过，记录见上表。另 6 项失败为 `toolIcons` 唯一性 1、`LearningPlanTab` 历史/终结/多目标断言 3、`RecordDetail` 复习结构断言 1、`CommandPalette` 同名标题关闭断言 1。后端 26 项涉及旧迁移回拨、旧聊天断言、上下文压缩/恢复、文档日志及习题偏好。不将定向通过换算为新的全量通过数。

### 独立基点复核

在 detached worktree `E:/workspace/project/my/KnowRealm-AI-study01-baseline` 固定基点 `7f745d3`，执行 `pnpm install --frozen-lockfile` 和 `uv sync --frozen --directory backend`，使用独立 node_modules/.venv。测试记录的 `dirty_worktree=false`。

- 同一入口 `python -m scripts.run_tests frontend` 加四个原失败文件，结果 **27 通过 / 6 失败**，六个旧节点全部一致。基点原始目录 `20261017T082909Z-837aa967/frontend/`，已复制至本工作区 `record-study-20261017/baseline-frontend/`。
- 同一入口 `python -m scripts.run_tests backend` 加本轮 26 个失败 node ID，结果 **26 失败**，耗时 451.92 秒，全部重现同类错误。原始目录 `20261017T083226Z-40770497/backend/`，已复制至 `record-study-20261017/baseline-backend/`，`comparison.json` 留存逐节点摘要。UUID、时间及预算数值差异不解释为同字节错误。
- 预算夹具失败原本就存在：该断言的基点输入/工具成本为 35629/25461，当前为 36310/26078，预算同为 32723。新增查询 Tool 带来成本增量，未放宽生产预算或等待时间；本票已装配 Tool 的确定性测试通过，真实模型质量仍未验。
- 基点 `LearningPlanTab.tsx` ESLint 同样因 `react-refresh/only-export-components` 警告失败（773 行原导出）；记录 `record-study-20261017/baseline-eslint.log`。没有关闭规则，也未修无关历史断言。

这些证据确认本轮剩余 32 项为基点已有失败；全量保持 FAILED，不声称全库门禁通过。

## 页面与原生复验

1. 使用独立数据目录，准备有效课程/进行中目标/当前计划，一个已有资料关联项及一个缺关联项；准备一条有效共享资料和一条已删除或移出范围的来源。记录课程、计划、计划项、记录及访问身份。
2. 从旧项进入，搜索选择并确认资料；确认前不得有绑定、阅读启动或完成事实。再开始学习，切换 Transcript，返回原项，重开及重启后检查页签恢复。
3. 从普通记录入口切到其他页签，返回原计划项检查其页签与启动时间不变；人工完成两次，核对首次完成时间、今日已完成数量及零新增掌握度事件。
4. 返回学习计划，检查目标、版本、原行位置与焦点。切历史版本、完结目标及跳过项，只可查看结果；DONE 当前项仍能打开学习。
5. 共享入口检查编辑/生成禁用、页签及读取刷新可用；在拥有资料时打开写弹窗，再经其他入口迁移并保留共享，切回窗口后旧写弹窗应关闭，生成请求的课程上下文由服务端拒绝共享写入。
6. 移除共享或删除来源，检查原因和重新关联路径，不得有失效来源链接。恢复课程后复查可见性；退出隔离实例，恢复主题、语言、字号和窗口设置，仅清理本次隔离目录。

逐项记录 PASS / FAIL / NOT_RUN / NOT_TRIGGERED，以及主题、CSS 视口、DPR、真实 Windows 缩放和证据路径。不得以本票浏览器截图代勾原生或屏幕阅读器验收。

## 设计与工具检查说明

沿用 DESIGN.md 的现有语义令牌和公共 Button/Input/RadioGroup，不新增配色或动画系统。主动作、确认对象、最后启动事实与人工完成分开表达；短行换行，宽窄窗自然重排。桌面扫描器对公共组件误报缺局部 focus/hover，控件继承公共组件的焦点/悬停样式，返回链接另有明确 focus-visible；焦点流已由页面测试和浏览器实际验证。

范围脚本被 `LearningPlanTab.tsx` 既有 Fast Refresh 导出警告阻止；没有关闭规则。最终 `pnpm build`（含两份 TS）通过，Vite 打包耗时 43.75 秒，保留既有大块警告，见 `record-study-20261017/build-final.log`。`pnpm --filter @knowrealm/api-types check` 通过，见 `contract-final.log`。触及前端文件 Prettier、其余触及 TS/TSX 的 ESLint 通过，见 `static-final.log`；该日志随后捕获到新增导入排序问题，合并同模块导入后，17 个触及 Python 文件 Ruff check/format 与 Pyright（0 错误）复验通过，见 `backend-static-final.log`。最终只调整导入与测试排版，没有再改变业务行为。临时数据库、截图、脚本与原始日志均留在忽略目录，不提交。

浏览器补验脚本曾因 Vite 入口带时间戳未匹配 IPC 拦截、误写迁移请求字段及对含刷新按钮的提示使用整段精确文本匹配而失败；均为脚本前提/定位修正，没有用这些失败声称产品通过。最终动态变化补验独立执行通过，测试 API 与 Vite 进程已按本次 PID 清理。

基点证据已复制回当前工作区的忽略目录。测试生成路由文件仅有行尾差异；确认后执行 `git worktree remove --force` 已移除本次登记，但目录清理返回 `Directory not empty`。核对绝对路径后使用原生 PowerShell 清理残留，被自动审批以 `blocked by policy` 拒绝；未再换方式删除。残留路径 `E:/workspace/project/my/KnowRealm-AI-study01-baseline` 不属于交付提交，也没有借机清理用户的其他 worktree。

## 补评修复：移除学习计划对 today 的反向依赖

2026-10-17 核实用户指出的包级方向环真实存在：`learning_plan.study` 导入 `today.resume_models`，而 today 聚合又依赖 learning_plan，违反 `fastapi.md` 的下游方向；它不是运行时 ImportError。沿用现有 `learning_plan.audit` 的注册钩子方式，将页签查询归回 `LearningResumeService.record_tab`，由 `main.create_app` 注入读取器。首次明确启动仍在原领域事务内读取已有页签，此后普通访问不反写本项；未装配 today 的隔离领域使用默认 summary。HTTP、数据表及前端契约不变，没有新增模型调用。

验证：AST 检查 learning_plan 下已无 today 导入；复用资料学习 13 项及今日恢复/重启 2 项，**15 项全部通过**，证据 `.pytest-tmp-runs/20261017T091123Z-bc3ca1d1/backend/`。三个触及 Python 文件 Ruff check/format、Pyright（0 错误）及 OpenAPI `--check` 通过。现有测试覆盖此次保留的行为，未新增重复测试，未重跑全量或原生桌面验收；之前的全量失败结论保持。

## 补评修复：统一窗口返回的学习范围重查

核实学习查询的 `refetchOnWindowFocus: true` 覆盖了全局 false，与 `desktop-state.md` 相反，同时记录学习页还监听局部 focus。TanStack Query v5 的默认焦点通知实际来自 visibilitychange，自动刷新还受缓存新鲜度及请求去重影响，因此不宣称每次 focus 必然发两次请求。本次删除该 Query 覆盖项，继承全局禁止自动焦点重查的策略，仅保留记录学习页在窗口返回时主动校验访问身份与共享范围的路径。`refetchOnMount: "always"` 用于进入页面时重验范围，不受“不 refetchOnWindowFocus”条款限制，保留并补充原因注释；没有修改 rules 或全局 QueryClient。

扩充原共享弹窗集成用例，使用生产 QueryClient、真实 Router/Query 与 MSW，验证缓存过期后的 Query 焦点通知不发学习查询，局部 focus 只新增一次查询，共享只读状态到达后旧写弹窗关闭、读取刷新仍可用。定向 RED `20261017T091511Z-dfda9807/frontend/` 复现自动焦点多发一次请求，修复后 `20261017T091553Z-9518722a/frontend/` **6 项全部通过**。早期检查曾要求重挂载复用新鲜缓存，该要求会改变原有入口重验策略，已从最终测试范围移除。此次未改后端或接口，未重跑全量、浏览器矩阵及原生桌面，既有验收边界不变。

`pwsh -NoProfile -File scripts/check-changed.ps1` 本次改动范围检查通过：触及文件 ESLint、Prettier、两份 TS 及生产构建均通过；Vite 保留既有大块警告。日志 `.pytest-tmp-runs/record-study-20261017/focus-check-changed.log`。
