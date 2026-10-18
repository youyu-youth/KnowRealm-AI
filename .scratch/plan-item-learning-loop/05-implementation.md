# 05 分层交付验收

日期：2026-10-18。固定基点 `68a96c63bd8eb275ab86a8e404f410561a51535f`；分支 `feat/extend-dev-09`；开始时工作区干净。01～04 均已进入 ready-for-human，具体实现仍以各票及当前代码为准。

**交付结论：可执行验收已完成，05 进入 ready-for-human，尚不能宣布全部验收通过。** 真实模型质量、Windows 150% 和原生未覆盖分支保持未验。前端全量 833 PASS / 6 FAIL、后端 1390 PASS / 28 FAIL；34 个失败在本票固定基点独立复现，全量仍为 FAILED，不改写成全绿。

## 范围与复用

- 50 条故事、Q1～Q23、生产入口到 HTTP / Tool / 页面、固定数据及测试归属见 [05-coverage.md](./05-coverage.md)。表内映射不是运行结果。
- 复跑前四票，未新建业务 Service、Agent Tool、队列、迁移或评分引擎。使用生产路由、完整迁移、SQLite、JobRunner 与 lifespan；ASGITransport 不冒称真实 TCP 进程。
- 新增 `backend/tests/test_plan_practice_delivery.py` 四项交付验收：功能前 0051 旧计划项经生产启动升级并首次关联；五题型 6/15 导出/恢复/搬移后继续和评分；实际资料移动与清理；实际课程清理。此前的物理删除测试直接 SQL DELETE，不能替代本票生产清理 Service。
- 原生验收发现 `LLM_OUTPUT_INVALID` 在简答评分失败时误称 Summary，已同步 zh/en 改为通用结构化内容错误，并纠正既有错误码条目说明；未新增错误码、规范或改变评分行为。
- 不更新未获批的架构/需求正文，不调整无关历史失败、全量等待阈值或规则文件。临时脚本、日志、数据库和截图均在忽略目录，不加入提交。

## 固定路径与数据

1. 旧资料项无关联 → HTTP 确认关联 → 明确启动 → 保存页签 → 退出并重启 → 返回原项 / 原计划；普通入口访问不冒认本项学习，人工完成不写验证性学习事件。
2. 两份归属资料 8+7 道 Redis 简答，混入无关、完全重复、未采纳、已删、共享与跨课题。先确认 8 道来源 → 显示不足并建议补源 → 显式确认第二份来源 → 准备恰好 15 题。替身只判候选相关性，身份、范围、去重、数量及提交校验仍由生产程序完成。
3. 固定卷面 → 6/15 → 新 lifespan 同轮恢复；部分评分 14/15 或 0/15 → 缺口重试；成功题与答案不变，事件按轮/题去重。失败重练、取消、要求/来源/进度变化均保留旧轮；新轮成功后最多一轮可答，晚到旧轮评分不改变默认轮和首次计划完成。
4. 新交付组合：15 题包含五题型各 3，先答 6 题，经真实导出 HTTP 取得 ZIP（排除 providers.json）；独立目标恢复、目录重命名后启动，保持卷面副本逐字相同和同轮 6/15，再完成剩余作答及生产评分。12 道客观题各 1 分、3 道简答替身各 0.5，整轮 0.9，15 个 ANSWERED + 1 个 TEST_COMPLETED，幂等键唯一。
5. 对有真实 RecordFile 的来源先通过 HTTP 建目标课程并移动，核对旧轮固定题面、来源失效与原文件保留，再执行 DELETE，用未来 31 天时点调用生产 `DocumentCleanupService.purge_expired`：记录、原题、文件登记和物理目录清除；固定练习 15 题保留、quiz_id 置空、source_valid=false，仍能完成评分。另删除课程：查询先隐藏，再运行同一清理，课程/记录/原题/轮次题位均实际消失。真实移动为最终定向补验增量，不回算此前全量收集版本。
6. 从功能前 0051 的真实数据库创建旧课程/记录/目标/计划项，关闭旧 engine 后启动生产 lifespan，重放 0052 至当前迁移；旧项学习状态默认 summary、无启动/关联，HTTP 首次关联并启动成功。核对当前版本使用 `supported_user_version()`，升级前快照仍为 51 且旧项保留。此项为最终新增用例，不能用既有 0053 升级用例或之前全量替代。

备份采用生产 `create_rolling_backup` 和 `VACUUM INTO`；使用独立备份输出目录，避免把启动时生成的当天快照误当成之后答至 6/15 的快照。每日仅备份一次的已有契约未改。备份库 integrity_check=ok，固定副本与 6 个已答题核对通过；恢复后的继续验证来自导出 ZIP，不冒称已验证滚动 DB 的完整目录恢复。

## 自动化与真实 API / SQLite / Worker

| 检查 | 状态与范围 | 原始证据（相对仓库根） |
| --- | --- | --- |
| 前四票及兼容回归 | 272 PASS / 1 FAIL。13 文件包含资料学习、准备、轮次、恢复、普通习题/测试、计划、学习事件/消费/掌握度、JobRunner、授权/回执、生产清理。失败为旧 quiz_last_count 偏好响应精确断言，保留红灯 | `.pytest-tmp-runs/20261018T075707Z-4af54091/backend/` |
| 新交付组合首轮 | 3 PASS；五题型恢复/搬移及两类实际清理。后续填空夹具占位符、移动 HTTP 与 0051 升级增量由最终定向四项覆盖，不回算全量 | `.pytest-tmp-runs/20261018T080240Z-381e76fd/backend/` |
| 备份/恢复既有用例 | 15 PASS；与交付组合较早一次同批执行。该批交付夹具 3 FAIL，不能记整批通过 | `.pytest-tmp-runs/20261018T080055Z-98e9db2c/backend/` |
| 最终交付与错误码 | 6 PASS：四项交付用例与两项既有错误码防线，包含真实移动及功能前 0051 升级增量 | `.pytest-tmp-runs/20261018T085717Z-a94c196b/backend/` |
| 恢复答案原值补验 | 1 PASS：恢复后逐题比对前 6 个答案原值，而非只检查已答数量；该用例的最后增量两轴复核通过，Ruff/格式及文件 Pyright 通过，其余用例未改，不重复全量或前端构建 | `.pytest-tmp-runs/20261018T091311Z-57901e0c/backend/`；`.pytest-tmp-runs/plan05/final-pyright.log` |
| 最终页面与双语 | 36 PASS：计划准备、卷面作答/结果及双语一致性；外部 API 为 MSW，非原生证据 | `.pytest-tmp-runs/20261018T085741Z-5e5dc66f/frontend/` |
| 前后端全量 | 前端 833 PASS / 6 FAIL（782.38 秒）；后端 1390 PASS / 28 FAIL（pytest 2437.24 秒），两套均 FAILED。后端保留 7 条 warning。前端失败为工具图标 1、LearningPlanTab 3、RecordDetail 1、CommandPalette 1，未过滤；最终新升级/移动增量由上方定向覆盖 | `.pytest-tmp-runs/20261018T080313Z-4c0c66fb/{frontend,backend}/` |
| 范围与类型检查 | PASS：`pwsh -NoProfile -File scripts/check-changed.ps1`，双语 Prettier、两份 TS、Vite 构建、Ruff lint/format、新增测试 Pyright 0 errors / 0 warnings；保留既有路由测试文件/大包提示及 Pyright 更新提示 | `.pytest-tmp-runs/plan05/check-changed.log` |
| 契约 / 双语 / 错误码 | PASS：`pnpm --filter @knowrealm/api-types check`（OpenAPI 与生成类型一致）；双语 3 项包含在最终 36 项中，错误码 2 项包含在最终后端 6 项中 | 上述定向记录；`.pytest-tmp-runs/plan05/contract.log` |
| 基点比较 | 前端 27 PASS / 6 FAIL；后端 28 FAIL（482.95 秒）。与当前全量失败集合完全相同；两次启动 result.json 均为固定基点、dirty_worktree=false，独立冻结依赖，未共用当前 node_modules/.venv | `.pytest-tmp-runs/plan05/baseline-results/20261018T090236Z-2076ebdb/frontend/`、`20261018T090419Z-2a85756f/backend/` |

命令沿用 `uv run --frozen --directory backend python -m scripts.run_tests backend <上述文件>` 与 `... scripts.run_tests all`。每次 result.json 含完整命令、时限、源码提交、脏标记、进程身份与原生退出码；筛选通过不替代全量。最终变更提交将固定实际 diff。

基点比较按 `docs/agents/validation.md` 执行：新 detached worktree `E:/workspace/project/my/KnowRealm-AI-baseline-plan05`，自行 `uv sync --frozen --directory backend` 与 `pnpm install --frozen-lockfile`，安装、全量和基点复测顺序执行。前端重跑四个失败文件，后端重跑全量 28 个失败 node ID，未过滤全量、扩大等待或改旧夹具。前端生成路由仅行尾变化，经 `git diff --ignore-space-at-eol` 确认后恢复，再以干净源码启动后端。安装日志、node ID 清单、退出码与逐项比较在 `.pytest-tmp-runs/plan05/` 的 `baseline-install-*.log`、`current-backend-failed-nodes.json`、`baseline-exits.json`、`baseline-comparison.json`。

后端同类错误为旧迁移重复表 1、聊天断言 2、context_pins 3、context_rules 2、conversation_compaction 18、document_import 日志泄漏断言 1、quizzes 偏好响应断言 1。逐项核对用例和错误形态一致；随机 UUID、时间、日志中的 worktree/临时路径不同，不作逐字相等声明。前端六个失败用例身份也一致。历史问题未在本票修复，不能以基点复现豁免全量失败。

测试搭建的首次失败分别来自误用题型/文件来源枚举、将 SQLAlchemy Result 直接传 dict、以及复用了当天启动空库备份；均修正测试夹具，未据此声称产品存在缺陷。原始失败分别保留在 `20261018T075940Z-5777ce7d`、`20261018T080055Z-98e9db2c`、`20261018T080154Z-2b6fc1b5` 的 backend 日志中。

## 真实 Tauri / WebView2

**PASS（明确子集）**：真实 Rust 壳、原生 IPC、WebView2、TCP sidecar API、SQLite 与生产 Worker。匹配/简答评分使用 localhost HTTP 供应商替身及合成题；这些结果不证明真实模型质量、用量或真实供应商失败。fixture setup 中初轮准备使用旧外部模型替身；原生操作中的再匹配及评分实际经过 OpenAI-compatible 请求与结构化校验。

- 应用/侧车 0.1.0，Rust 与前端来自固定基点加本票工作区；使用临时覆盖配置标识 `ai.knowrealm.validation-plan05`，隔离数据 `.pytest-tmp-runs/plan05/native/KnowRealm`；未覆盖日常 app 配置或访问用户生产数据。
- 当前 HWND DPI=120（Windows 125%），WebView2 DPR=1.25。Win32 调整实际窗口，测得 CSS 1266×792、886×712、706×712；未调用 CDP viewport/DPR 模拟。四主题 LIGHT_DEFAULT / LIGHT_SAGE / DARK_DEFAULT / DARK_INK × 16/18/20px，12 组合文档无横向溢出，主动作可聚焦及键盘激活，截图已抽看亮色宽窗与深色窄窗。主题与字体通过 DOM 应用现有样式，未验设置面板持久化主题切换。
- 6/15 旧轮通过键盘进入；实际 UI 完成第 7～15 题，交卷前 DOM 无合成参考答案标记。替身返回一次不合规评分，页面显示 14/15、部分成绩与分母 14；点击重试后为 15/15、分母 15。明确重练先取消，再准备并启动第二轮，第一轮结果仍可追溯。
- 旧资料项首次确认关联、键盘启动、返回原项、人工完成、DONE 项继续及返回计划 1/2 均通过；Transcript 页签切换、返回、再继续恢复通过。
- 第二轮答至 6/15，将下一轮要求改为 100 题并确认，实际匹配显示 30/100 不足，旧轮身份与 6 个答案保留。实际结束并重启 Rust + sidecar，核对相同轮次/要求修订/6 个已答题，继续定位第 7 题。
- 脱敏身份、重启进程、指标及脚本：`.pytest-tmp-runs/plan05/native-result.json`、`native-restart.json`、`native-before-restart.json`、`native-facts.json`。后者 user_version=55、integrity_check=ok、foreign_key_check 空；第一轮 15/15、第二轮 6/15，两个轮次各 15 个 frozen_json；15 个 ANSWERED、1 个 TEST_COMPLETED，幂等键均唯一。合成供应商日志的 usage 是替身固定值，不是实际计费。
- 截图：同目录 `native-{主题}-{宽度}-{字号}.png`、`native-partial-14-of-15.png`、`native-complete-15-of-15.png`、`native-round-two.png`、`native-manual-completion.png`、`native-transcript-resumed.png`、`native-repractice-shortage-keeps-six.png`、`native-restarted-6-of-15.png`。

工具边界：优先使用 browser-use。最初驻留默认 daemon 返回其他页面，只作只读探测；命名 daemon 正确连接目标，但初始选中了 about:blank。随后按真实 Target ID 切换并核对原生 IPC、CSS 1280×800、DPR 1.25，证据为 `browser-use-native-proof.json` / `browser-use-native.png`。上述多步流程由现有本机 Playwright 直接 CDP 连接同一真实 WebView2 自动执行，无 IPC mock、无 MSW。定位脚本曾误选空白页、非主 HWND、错误角色或精确文本，已改正并核对真实 CSS 视口，失败脚本不作为验收通过。

## 未验与复验交接

| 范围 | 状态 | 复验与必要输入 |
| --- | --- | --- |
| 真实模型主题相关性、语义近重复与评分质量 | NOT_RUN | 需要人工标注的真实标题及已采纳题、供应商和预算；已在本聊天询问，尚未收到。不得用合成 Redis 前缀判定或本地 HTTP 替身替代 |
| 真实模型失败、真实 usage | NOT_RUN | 匹配/评分分别记录供应商/model、来源范围、题目 ID、请求/Job ID、usage（供应商不返则未知）、失败原因与降级；不展示密钥 |
| Windows 150% | NOT_RUN | 用户在 Windows 显示设置切换到 150%，重开隔离实例，记录 HWND DPI=144、DPR、CSS 视口和主题，重复开始/继续/返回/确认；完成后恢复原缩放 |
| 原生完整四票组合 | 部分 PASS | 上述路径通过；原生 8+7 补源、授权降档/取消/来源漂移提交、晚到旧轮评分等仍只取得自动化层证据，需按 01～04 桌面步骤复验 |
| 屏幕阅读器、用户人工键盘与视觉验收 | NOT_RUN | 已有自动化原生焦点/Enter 与 DOM 交互，不代替用户操作和读屏验收 |
| 真实模型 Agent 自主选 Tool | NOT_TRIGGERED | 已装配 Tool → Operation → 确认/回执和同结果查询在真实 HTTP/SQLite 自动化通过；原生自然语言会话未触发该链 |

人工复验保留独立目录及备份：记录应用/侧车版本与 course/record/item/requirements/preparation/test/job/request 身份，沿前四票路径逐步保存截图和只读数据库核对。真实样本至少涵盖相关/无关、完全重复/近重复、五题型及范围外题；每次要求恰好 N 且无越界，不足不建卷。质量逐题对照人工标签，分别报告相关性、重复、精确数量、范围和简答分数，不只检查数量。

## 评审、资源与提交

双轴 Code Review 及真实移动增量复核已完成，报告见 [05-review.md](./05-review.md)：Standards 0；Spec 无新增实现错误，保留真实模型及完整原生验收两项缺口。

原生进程 6516→36296 的两个实例、供应商替身 31500/31072 与 Vite 25752 已按身份退出，见 `.pytest-tmp-runs/plan05/process-cleanup.json`。未改日常数据目录、供应商配置或 Windows 缩放；用户已明确选择暂不切换 150%。证据和隔离数据保留于忽略目录。

配置清理为 BLOCKED_BY_POLICY：删除 `C:/Users/邹根/AppData/Roaming/ai.knowrealm.validation-plan05` 的 PowerShell 命令含目标绝对路径与链接校验，但在进程创建前被自动审批拒绝，仅返回 `rejected: blocked by policy`；未换方式删除。该配置及 `C:/Users/邹根/AppData/Local/ai.knowrealm.validation-plan05` 的 WebView2 缓存仍存在，不宣称全部资源清理。

基点日志已复制回当前忽略目录；核对绝对目标、非链接、干净源码后运行 `git worktree remove E:/workspace/project/my/KnowRealm-AI-baseline-plan05`，返回 `Directory not empty`；worktree 登记已移除，目录仍残留。未强制递归删除或清理此前票的其他 worktree。冻结安装依赖与临时数据不加入提交。

默认 debug 构建已通过无临时 TAURI_CONFIG 的 `cargo build --locked` 恢复，未启动日常应用，保留既有 linker warning；日志 `.pytest-tmp-runs/plan05/restore-default-native-build.log`。本票只提交点名源码、工单及验收文档，不 add 临时脚本、日志、截图或数据库。最终规范、需求归属、运行结果和待用户验证边界均以本记录及工单为准。
