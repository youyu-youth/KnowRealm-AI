# 03：双子任务并行、部分成功与聚合实施记录

日期：2026-10-21。实现提交 `4ec5d55`、评审补充 `d5e7d8a`、版本断言同步 `bd4cbe2`；开工基点 `b743a0f`，当前分支 `feat/multi-agent-refactor`。实现及双轴评审已完成；完整全量已运行，失败与修正复测分别记录，真实模型、原生桌面和 Windows 缩放未验。

## 实现与复用

- 复用 02 的逐 ToolCall Send、独立 delegation/Job/wait/interrupt、两个原 CHAT_TURN 槽、根六次工具预算、请求准入及类型化决定。没有新增调度循环、聚合 Job、批量委派入口、迁移或依赖。
- 补齐模型入口的报告校验：Pydantic 契约、原会话/子任务/ToolCall 绑定和原持久结果一致性；非 JSON、错误版本、串用兄弟 ToolCall、改写 summary、给报告伪装 `ok=false` 均拒绝进入模型投影。合法工具错误通道保留。来源继续在提交和模型请求前按当前范围/排除规则重验，删除来源不会被旧缓存带回。
- 空报告返回 FAILED/EMPTY_REPLY，并提供该分支的真实 gaps。委派工具指引要求最终回答区分证据与缺口，部分/全部失败如实结束，不重复委派已成功分支。
- 两个不确定分支在原等待卡各有重试入口；恢复请求只带所选执行，稳定决定 ID 包含选择。接受已有结果仍确认全部当前不确定分支；旧决定、并发输家由原服务裁决。成功兄弟的输入、结果和消费保留。
- 等待卡在 WAITING_USER 继续展示关联任务。复用 Button 与语义令牌、双语同 key；长执行 ID 可换行，键盘入口无需新增页面或状态仓库。依据 Desktop UI Mastery 的 Raskin 模式显式原则，以完整执行 ID 标出重试目标。
- 模型可见委派指引变化后，普通/研究 prompt 升至 v35/v36，图版本 v13。旧版本在途任务沿原不兼容等待/停止后新问机制处理，不静默加载新图。

## 生产链与替身边界

公开提交 general 根轮次 → 实际 Harness 双 ToolCall → Middleware/原子预算 → 稳定委派和原 JobRunner → 两个 knowledge 图 → 迁移 SQLite 的结果/事件/请求 → 原 interrupt ID 恢复 → 父模型输入 → API 快照/前端。

`backend/tests/test_parallel_delegations.py` 共 16 项新增行为验收，只有外部模型输出与阻塞点使用替身。故障窗口通过公开 checkpoint I/O 或真实 JobRunner 写回接缝停驻/抛错；不直接写业务终态，不解除双槽限制。

| 场景 | 验证内容 |
| --- | --- |
| 两根四分支 | 两根同时 WAITING_JOB、每根独立两个 interrupt；原槽峰值 2，同会话忙碌拒绝，8 次模型替身调用对应 8 条请求，子 token 不进入父正文 |
| 逆序及明确失败 | B 先完成不提前唤醒；一失败/全失败分别给真实报告和 gaps；父汇总结束，成功分支不重跑 |
| 不确定请求 | 安全兄弟先收口；只重试 B 或接受部分结果；两分支不明时仅重试一支，余下分支生成新等待快照；并发决定只有一方获准，旧等待决定拒绝 |
| 共享预算 | 两次委派 + 三次已准入检索后，两分支竞争第 6/7 次，仅一个成功；持久总数 6，子检索总数 4，不按子重置 |
| 能力/来源 | 第三任务跨调用拒绝，knowledge 嵌套委派被能力守卫拒绝；契约/身份/正文改写拒绝；A 成功后来源删除，父输入只保留失效错误和有效 B 报告 |
| 取消与重启 | 两子均在途停止、成功 A/在途 B 停止或重启；取消后无迟到报告，成功 A 不重发，不明 B 不自动重发 |
| 父未唤醒重放 | 登记后未停驻、结果已提交但父未唤醒的双分支窗口分别重启，原 delegation/Job/input/result/预算复用，两个 interrupt 恢复，子请求仍只有两次 |
| 单槽故障与线程 | 真实 JobRunner 写回异常走定向收口，B 已完成事实保留、A claim/线程与父图保留，后续新对话仍推进；子线程清理不清父或兄弟，根输入不被子输入覆盖 |
| 事件/快照 | 根 seq 唯一、子状态分别按 execution_id/attempt 投影；终态压缩后 process 与压缩前一致 |

原 `test_tool_budget.py` 的原子字符裁剪、输出记账和恢复测试，以及 02 的取消/重试旧 claim/连续不确定请求回归继续保留；最终全量包含它们。

## 已执行检查

日志均在仓库根 `.pytest-tmp-runs/<运行 ID>/<suite>/`，仅引用，不 add/commit。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 空报告缺口红灯 | FAIL（预期） | `20261021T123540Z-5da96b98/backend`：2 失败、4 通过；两个空报告场景缺少 gaps，修正后后续定向通过 |
| 报告身份/契约红灯 | FAIL（预期） | `20261021T124050Z-a18eb587/backend`：错误版本/串用/改写仍可投喂；修正后该场景通过 |
| 非 JSON 报告红转绿 | PASS | 红灯 `20261021T130042Z-bfdb4aa3`；绿灯 `20261021T130114Z-2bde113a/backend`，1 通过 |
| 双分支原始批跑 | FAIL，夹具已修正 | `20261021T124720Z-03b96ba9/backend`：12 通过、1 失败；压缩后事件已清除，测试错误地访问空事件数组；改为先查 seq 再压缩，`20261021T124923Z-75944de9/backend` 单项通过，不拼作一次批跑全绿 |
| 评审补充窗口 | PASS | `20261021T125926Z-5cc661eb/backend`：3 通过，覆盖两种重启窗口和单槽异常 |
| 前端相关回归 | PASS | `20261021T124633Z-5fc678af/frontend`：22 通过，包含单分支选择与稳定决定身份 |
| 等待卡混合结果收尾检查 | PASS | `20261021T141211Z-8bfae2ba/frontend`：5 通过；扩展原用例确认 WAITING_USER 仍展示成功兄弟和不确定分支，未新增生产逻辑 |
| 范围检查 | PASS | `scripts/check-changed.ps1`：ESLint、Prettier、前端 tsc/build、Ruff/格式和 Pyright 均通过；补充测试另经 Pyright 零错误、Ruff 检查 |
| 最终范围检查 | PASS | `pwsh -NoProfile -File scripts/check-changed.ps1 -Base b743a0fd1b3eca7a914be2856081e4884c61baae`，触及前端文件 ESLint/Prettier、双 tsc 与构建，后端 8 文件 Ruff/格式/Pyright 均通过；日志 `.tmp/03-final-check.log` |
| OpenAPI | PASS | `uv run --frozen --directory backend python -m scripts.export_openapi ../packages/api-types/openapi.json --check`；没有 schema/生成类型变化 |
| 最终统一全量 | FAIL | `20261021T130146Z-6697943f`，从干净提交 `d5e7d8a` 执行 `uv run --frozen --directory backend python -m scripts.run_tests all`；前端 871 通过/2 失败，后端 1481 通过/2 失败。后端启动时因本记录未跟踪而 dirty=true，生产源码仍为该提交 |
| 全量中的本票后端场景 | PASS | 同轮 backend：`test_parallel_delegations.py` 全部 16 项通过，未过滤用例或放宽超时 |
| 全量前端阶段 | FAIL，定向未稳定复现 | 同轮 frontend：871 通过、2 失败，1005.31 秒；设置页档案草稿 5 秒超时，学习画像未及时出现概念工作区；两文件与基点相同，当前及独立基点的同入口文件复跑均 44 通过，不能归为已确认的稳定历史问题或宣称全量通过。本票新增前端用例通过 |
| 全量后端阶段 | FAIL，断言已同步并定向通过 | 同轮 backend：1481 通过、2 失败，运行器 2359.00 秒（pytest 2348.44 秒）；唯一两项为 `test_chat_streaming.py` 硬编码 v34 和 `test_research_session.py` 硬编码 v35，实际日志已按本票升级为 v35/v36。`bd4cbe2` 仅同步两条版本断言，`20261021T135839Z-e82c7a90/backend` 定向 2 通过（17.32 秒）；不是历史失败豁免，也不拼成一次全量全绿 |
| 全量前端失败文件定向复测 | PASS | `20261021T135934Z-d94b5485/frontend`：44 通过，104.18 秒；未改设置页/学习画像源码或断言，未延长超时，尚不能将原全量失败归为稳定历史问题 |
| 独立基点前端对照 | PASS | detached `b743a0f`、独立 `uv sync --frozen --directory backend` / `pnpm install --frozen-lockfile` 后，使用相同统一入口和两个文件；`20261021T140633Z-61b9a8ea/frontend`，44 通过，运行器 92.20 秒（Vitest 87.50 秒）；未手工修改源码或共享当前 node_modules/.venv |
| 独立基点版本断言对照 | PASS | 相同基点/独立依赖，`20261021T140938Z-a599acd7/backend`：相同两个 node ID 均通过，运行器 74.49 秒（pytest 61.63 秒）；基点使用原 v34/v35，当前指引升级后使用 v35/v36，确认为本票需要同步的测试预期。该阶段 dirty=true 仅来自前端运行留下的 routeTree 标记，内容 diff 为空，后端源码未改 |
| 真实模型 / Tauri / Windows 缩放 | NOT_RUN | 不以模型替身、IPC mock 或浏览器字号/视口模拟代勾 |

补充测试首次 `result_committed` 闸门误拦子图初始化，修正为只拦已完成子结果；再次因闸门重复拦截 finally 清理而停滞，核对 PID 后终止该轮 pytest，`20261021T125716Z-02bf29ae` 保留为 FAILED/缺少完成证据。改为每个子线程只停驻一次后，上表三项通过。这是测试闸门问题，不登记为生产缺陷或全量通过。前端首次新 hook 夹具漏配事件订阅 Promise，22 项断言通过但有未处理错误；修正后使用上表干净定向结果。

## 持久样本

取自 `20261021T124720Z-03b96ba9` 的已通过场景；以下为隔离库/模型替身记录，不是真实供应商账单。时间为北京时间，数据库原值为 UTC。

| 根 | 子 A / Job | 子 B / Job |
| --- | --- | --- |
| `dce0e0f0-f6e8-4afd-ba01-8ca913b06ae5` | `235908b0-a2ba-4313-8aa0-8e2acd74dc7e` / `b272617e-9a87-4546-8673-ba4d100e2d6e` | `98e4abfa-7415-4089-ae9a-e495e3712c2e` / `427bff23-325a-4024-9790-c2a9516eee14` |
| `f2a8f077-a9dc-4e8d-842a-1888c5ca6163` | `7cfcb1de-b062-4f74-b927-7d762d82bfb0` / `461d2bb8-14d7-422f-b1ba-128b29067713` | `9b7adb50-281b-4063-98db-f64c8b5e691d` / `39be8e9d-4ee8-4d65-98e8-b5b29425d932` |

- 20:47:31.578/31.609 两根受理；32.699/32.891 两个 A 领取，33.112/33.172 完成；33.136/33.269 两个 B 领取，33.479/33.544 完成；34.151/34.277 两根完成。原槽峰值 2，两根最后 seq 均 13、根 attempt 均 2，四子 attempt 均 1。
- 根 1 的 A/B interrupt 为 `af3fa1df8d5c9921d80e4a3ffa2d7c1d` / `70c9be83cee2a62896cddae3c5fb6b48`；根 2 为 `c21f9e56a37d26e577aaaf537553997b` / `e069005ef97533a01a8a008da2d2bba3`。四个绑定独立，结果 task_id 与原 ToolCall 对应。
- 根 1 请求例：根首次 `04ff6ecb-c49c-48c3-a72e-003c798ce510`、子 A `cd436657-63f9-4e5f-b49d-39aa1c995283`、子 B `68e9b186-e838-491d-9091-b4fd0c32fbd0`、根汇总 `96f74deb-3782-4848-aaf1-92f8fbf75012`。两根共 8 条 COMPLETED 请求/8 次模型替身调用，usage_json 全 NULL；没有真实 HTTP 模型请求。
- 每根预算原表 count 均为 2。最后额度竞争的另一个根 `a947789b-e4be-484f-b994-75fa9ac13740` 在第五次消费后释放闸门，最终预算 count=6，其中子工具 count=4；共 8 条模型请求，工具次数与模型请求次数分开计量。

## 浏览器检查与人工步骤

Browser Use doctor 报 daemon/连接不可用，改用本机已安装的独立无头 Chromium/Playwright；隔离 API + 迁移库 + Worker/Graph 真实运行，外部模型与 Tauri IPC 为替身。

- 原只读预检 PASS：`.tmp/03-ui-preflight/result.json`。
- 六主题（默认亮/暗、Sage/Ink、Retro Warm/Tokyo Night）× 1440/16px、900/18px 共 12 组 PASS；按钮可见、焦点可达、无页面或按钮文本横向溢出。六张窄窗截图在 `.tmp/03-ui-evidence/`，已目检亮色与 Tokyo Night。
- 键盘 Enter 仅提交选中 B 的决定；新等待刷新恢复后接受已有结果，父汇总完成，页面错误列表为空。结果 `.tmp/03-ui-evidence/result.json`。原 SSE 无通知时依赖 15 秒补拉，本次按该已存在的生产上界等待，没有缩短轮询或改写业务状态。
- UI 样本根 `96eab202-dc0e-4fc6-a2a8-a9c385650546`；子 `d4752e5a-bcf0-42f7-abbb-a9ca798bd315`、`db97d382-4179-4b8a-8697-911d25206d03`。浏览器视口和字号不是 Windows 系统缩放。
- Desktop UI Mastery 静态检查提示组件本身没有 focus/hover；本组件全部交互使用共享 Button，焦点环及 hover 在原语中，未重复样式。

真实验收：使用独立 data-dir 和已同意外发的真实供应商，准备两个资料主题；两个不同 general 对话各明确要求同时委派两项任务。记录模型是否实际输出同轮双 ToolCall、四个子/Job/request ID、峰值及 usage。刻意制造一支失败/不明，验证成功分支不重跑、逐分支重试/接受已有结果；等待时切会话、刷新、停止、真正重启。真实 Tauri/WebView2 再验键盘/窄窗/六主题，并分别记录 Windows 125%/150%/200%。未发出双调用记 NOT_TRIGGERED。

## 长报告预算投影修复

原报告投影为 `output:` 指针后，父输入重验证仍按 `KnowledgeResult` 解析，导致合法长报告变为错误结果。现在复用输出投影格式与会话来源过滤，核对指针、工具与调用身份后，对快照中的完整报告继续执行原报告和引用校验。

验证使用真实公开提交 API、迁移 SQLite、Worker 和 Graph，只有外部模型为替身：两分支返回超过内联阈值的合法报告 → 保存输出快照 → 生产预算投影 → 父模型收到可读指针 → 公开 `read_context` 分页读取。跨分支/跨会话指针、篡改预览与版本、来源删除后拒绝读取均通过。

- 新增回归先复现失败（`20261021T234135Z-d53f6662/backend`），修复后单项通过（`20261021T234219Z-fd2b2379/backend`）。
- 统一入口运行 `tests/test_parallel_delegations.py tests/test_context_retrieval.py`：26 项通过，证据 `.pytest-tmp-runs/20261021T234249Z-fc68649e/backend/`；改动范围 Ruff、格式、Pyright 检查通过。
- 本次未运行全量、真实模型或 Tauri/WebView2 验收，不扩大原验收结论。

## 双轴评审

按 code-review 技能，以 `b743a0f` 为基点独立并行审查。

### Standards

初审、`d5e7d8a` 增量复查及 `bd4cbe2` 版本断言复查均 0 项。报告校验复用原 Service，前端复用原恢复 API 和 Button；测试没有伪造业务完成。

### Spec

初审 1 项 P2：缺少双分支单槽故障、父未唤醒重放和线程隔离的直接证据。补充上述三项生产链验证后复查关闭，`bd4cbe2` 两条版本断言符合本票升级，最终未关闭发现 0 项。评审不代跑全量或人工验收。

## 清理

自建 API 与预览进程已停止，1437/43137 无监听；未触碰既有 `.tmp` 资源和用户数据。

独立基点为 `E:\workspace\project\my\KnowRealm-AI-baseline-parallel03-20261021`，未借用当前源码或依赖；对照原日志/结果已保存到本仓库 `.scratch/multi-agent-refactor/.tmp/03-baseline/`。Vitest 触发的路由生成文件仅有工作区标记、内容 diff 为空，已还原后确认基点干净才执行移除。`git worktree remove` 返回 `Directory not empty`：注册已移除，目录仍有 node_modules、packages、scripts 等残留；未换删除方式绕过，未宣称清理完成。

删除本票隔离目录 `03-ui-data`、`03-ui-data-final` 和临时脚本 `03-ui-server.py`、`03-ui-check.py` 的 PowerShell 操作被自动审批拒绝（`blocked by policy`），未换方式绕过。上述资源仍在 `.scratch/multi-agent-refactor/.tmp/`，与浏览器截图/结果、测试运行日志一起保持未跟踪/忽略；均不 add/commit。

## 2026-10-22：重启测试闸门退出边界

基点 `e6158c950a8c63aeb85cba1416180a0ec4a9f2e6`。代码只修改 `test_restart_before_parent_wake_reuses_both_branches_and_preserves_parent_thread`，原有业务断言经 AST 对照全部保留；生产 Worker、共享 `turns_app`、API、图装配及依赖未改，本项不新增产品或 Agent 能力入口。

实测发现：原正常场景可通过，但新增退出断言检出了 `registered` 窗口在 lifespan 结束后仍停驻的 checkpoint 写入任务。此外，同一父线程的两个并行 interrupt 有不同 checkpoint task ID；仅按父线程去重会造成只拦一支，重启后原“两条 interrupt”断言变为一条。因此父闸门以 `(thread_id, task_id)` 一次性拦截，子清理闸门按子线程身份一次性拦截，原拦截位置保持。

具名等待事件保持未释放；记录停驻任务、窗口、根轮次、调用身份和最后观测的子状态。退出先停止新增拦截，lifespan 负责停止 Worker，再取消并回收测试注入后仍停驻的 checkpoint 任务，避免释放闸门让父业务继续。前台等待命中保留 10 秒上限，lifespan 收尾设 10 秒上限，取消后的闸门回收另设 10 秒上限；后台阻塞点不主动抛超时。恢复启动前断言停驻任务清空、Worker 已结束，且超时取消未被吞掉。进程完全卡死仍由原统一运行器兜底，不宣称协作式取消是进程硬时限。

所有运行均使用统一入口 `uv run --frozen --directory backend python -m scripts.run_tests backend <文件或 node ID>`；日志位于仓库 `.pytest-tmp-runs/<运行 ID>/backend/`，包含 `tests.log` 和 `result.json`。

| 验证 | 结果与证据 |
| --- | --- |
| 原测试两窗口 | `20261021T235426Z-50ac3020`：2 通过 |
| 新增退出断言 | `20261021T235647Z-33eaae01`：1 失败/1 通过，检出父 checkpoint 闸门任务仍停驻 |
| 初版仅按父线程去重 | `20261021T235805Z-2def5bc0`：1 失败/1 通过，原 interrupt 数量断言为 1 而非 2；据此改为按 checkpoint 调用身份拦截 |
| 调整中的语法错误 | `20261021T235925Z-f34fa088`：缩进错误导致收集失败，已修正，未计入通过结果 |
| 修正后的两窗口 | `20261021T235938Z-e898d8c4`：2 通过 |
| 命中信号缺失注入 | `20261022T000016Z-5819a51b`：预期失败，输出 `phase='gate'`、根/调用/阻塞身份，调用阶段 11.76 秒后退出；已恢复信号 |
| 收尾停滞注入 | `20261022T000051Z-79a9a879`：预期失败，输出 `phase='shutdown'` 与两个 COMPLETED 子状态，调用阶段 12.67 秒后退出；已移除额外等待 |
| 首轮相关文件回归 | `20261022T000123Z-c6653858`：16 通过/1 失败；目标两个窗口通过，未改动的单槽写回故障用例在 A 仍 QUEUED 时断言 RUNNING 失败；不改写为全绿 |
| 单槽失败项定向复跑 | `20261022T000256Z-794aecac`：1 通过；未修改该用例或放宽断言，不据此认定原时序失败根因已修复 |
| 二轮相关文件回归 | `20261022T000325Z-4277c1b1`：16 通过/1 失败；目标两个窗口及单槽故障用例通过，未改动的 `test_reverse_completion_rejects_third_child_and_nested_delegation` 在目标测试执行前观测到 COMPLETED/QUEUED，而非 COMPLETED/RUNNING；保留失败，不扩大本次修复或归为已确认稳定历史问题 |
| 最终范围检查 | `pwsh -NoProfile -File scripts/check-changed.ps1`：Ruff、格式、Pyright 通过，类型检查 0 errors；`git diff --check` 通过 |

两次故障注入仅为本轮诊断修改，均已撤销；不保留新夹具选项、额外测试文件或新依赖。测试继续运行真实迁移 SQLite、API、Worker 和图，外部模型为替身；本次不重跑全仓前后端全量或真实模型/原生桌面验收，不覆盖前文原始全量失败记录。
