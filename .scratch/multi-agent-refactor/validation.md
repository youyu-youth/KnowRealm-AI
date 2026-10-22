# 04：可行性实验、验收与交接

日期：2026-10-22。执行基点：`16e809603c2fd88f7783076180d13ab056c56996`；当前分支 `feat/multi-agent-refactor`，开工工作区干净。

本票复用既有能力与回归，不扩展 Agent、预算、工具或页面。完整验收未取得前保持未完成项。

## 验证路径与边界

1. 生产迁移执行器重放旧库 → 启动真实 API/SQLite/Worker → 旧会话默认 general，历史消息及独立 Run/Operation 保留；初始化不调用外网。
2. 公开创建/提交 API → 原双槽 JobRunner → general/knowledge 真实装配 → 两个独立 ToolCall/interrupt → 持久子结果 → 原父图恢复 → 消息/事件/快照查询。先复用 `test_independent_agents.py`、`test_agent_delegations.py`、`test_parallel_delegations.py` 及预算/上下文/恢复回归。外部模型替身与真实供应商分别记录。
3. 固定合成课程两份资料，以同一问题比较 general 直接处理、明确双委派、独立 knowledge；记录请求、实际 usage/未知用量、墙钟、引用及缺口。仅在已有供应商配置和有效外发同意下调用，不复制用户学习资料或修改用户配置。
4. 桌面入口 → 会话固定身份 → 双任务进度/等待决定/停止 → 切换刷新/引用定位/重启。真实 Tauri/WebView2 与独立浏览器分层记录；Windows 系统缩放必须真实设置，视口/DPR/字号模拟不代勾。

测试日志、临时脚本与数据库均留在忽略目录，不 add/commit。以下时间字段的原始值为 UTC，用户操作日期按北京时间 2026-10-22。

## 执行环境与改动

- Node `24.9.0`、pnpm `11.2.2`、uv `0.9.22`、Python `3.13.12`；LangChain `1.3.18`、LangGraph `1.2.11`、DeepAgents `0.7.13`、checkpoint-sqlite `3.1.1`、FastAPI `0.141.1`、SQLAlchemy `2.0.52`。当前工作区没有依赖变更；基点按 frozen lockfile 独立安装，锁文件 SHA256 保存在真实模型 `result.json`。
- 本票仅增强已有迁移回归并补交接文档：生产代码、API、schema、双语 key、rules 和用户数据配置均未修改。迁移回归新增 v55 前提检查和既有 Run/Operation 保留检查；没有扩展历史模块覆盖率。
- 真实供应商为 `api.deepseek.com / deepseek-v4-flash`。只读核实既有配置及其有效外发同意，再在专用目录保存临时供应商配置、发送下面两份合成材料。原配置未修改，记录不包含密钥。真实供应商配置在各轮 finally 中移除。
- 隔离资源位于本目录 `.tmp/04-*` 和仓库 `.pytest-tmp-runs/`；pytest 数据各用运行器生成的独立 basetemp。原始证据是本机文件，不随提交发布。

## 自动化与门禁

统一入口均从仓库根执行 `uv run --frozen --directory backend python -m scripts.run_tests <suite> <筛选>`。运行 ID 对应 `.pytest-tmp-runs/<ID>/<suite>/result.json` 和 `tests.log`，结果中的命令、PID、提交与时限可追溯。

| 检查 | 状态 | 本轮证据 |
| --- | --- | --- |
| 单/双委派现有文件回归 | FAIL | `20261022T021257Z-a2d340fa/backend`：31 通过、2 失败，150.29 秒；供应商变更后子状态 FAILED≠QUEUED，双根槽峰值 1≠2 |
| 上述两项原样定向复测 | FAIL | `20261022T021619Z-595802a6/backend`：1 通过、1 失败，26.63 秒；双根并行通过，供应商变更失败复现，不拼成首轮全绿 |
| 增强旧库迁移回归 | PASS | `20261022T021750Z-d42f15d9/backend`：1 通过、21.73 秒；真实 v55 迁移、默认 general、历史消息/Run/Operation 逐行相同、模型请求表为 0 |
| 分支范围检查 | 最终 PASS，保留首轮失败 | `pwsh -NoProfile -File scripts/check-changed.ps1 -Base 202a4c8`；首轮 `.tmp/04-check-changed.log` 的迁移夹具一行 101 字符触发 E501，已拆字符串修正；最终 `.tmp/04-final-check-changed.log`：前端 ESLint/Prettier/双 tsc/build、后端 Ruff/格式/Pyright 全通过，0 errors / 0 warnings |
| 当前触及 Python 静态检查 | PASS | `ruff check`、`ruff format --check`、`pyright tests/test_independent_agents.py`；格式通过，0 errors / 0 warnings |
| API 与生成 TS 契约 | PASS | `pnpm --filter @knowrealm/api-types check`，日志 `.tmp/04-contract.log`；没有 schema 或生成类型漂移 |
| 最终统一全量 | FAIL | `uv run --frozen --directory backend python -m scripts.run_tests all`，`20261022T021909Z-b6881cce`，总退出 1；frontend：91 文件、873 项通过，856.66 秒；backend：1480 通过、6 失败，pytest 2329.52 秒 / 运行器 2338.06 秒。双语一致性包含在前端全量中；不把后续定向通过拼成整套全绿 |
| 独立基点对照 | FAIL | detached 开工 HEAD `16e8096`，独立 `uv sync --frozen --directory backend` / `pnpm install --frozen-lockfile`、工作区干净且无依赖 junction；相同统一入口筛选六节点，`20261022T031527Z-046290ff/backend`：3 失败 / 3 通过，77.10 秒。结果已复制 `.tmp/04-baseline-results/backend/`；不是基点全量 |

迁移夹具通过生产执行器重放到 55；升级前断言 user_version=55、无 agent_id 列和 agent_delegations 表。插入旧会话、原消息及 COMPLETED Run / SUCCEEDED Operation，再经真实 lifespan 升到当前迁移。未从新库删列冒充旧库；没有声称覆盖所有旧 Run 非终态恢复形态。

全量从开工提交 `16e8096` 启动，dirty=true 来自本票迁移夹具/文档；运行期间没有生产源代码改动。六项原始失败如下：

| 节点（均在 backend/tests） | 全量失败形态 |
| --- | --- |
| `test_agent_delegations.py::test_restart_reconciles_persistence_windows_without_repeating_child[provider_wait]` | 子 FAILED≠QUEUED |
| `test_agent_time.py::test_time_tools_share_call_budget` | 实际 ok=false，断言要求 true |
| `test_chat_streaming.py::test_prompt_byte_identical_when_web_search_off` | captured[0][0] 仅一行，按三行解包 ValueError |
| `test_chat_turns.py::test_active_turn_list_carries_partial_output_projection` | 观测到“部分”，断言要求“部分输出” |
| `test_context_retrieval.py::test_source_scope_shared_ref_version_archive_and_material_budget` | 根 FAILED≠COMPLETED |
| `test_independent_agents.py::test_knowledge_keeps_local_url_quotes[COURSE-record]` | 提交轮次前更新夹具遇到 SQLite database is locked |

基点同形重现时间工具 ok=false、提示消息三行解包和共享资料检索 FAILED 三项（后者日志为 chat_compaction_failed / CHAT_STREAM_FAILED）；供应商变化、部分输出与 URL 夹具三项基点定向通过，不能据此消除当前全量红灯或称为稳定历史问题。当前同组六节点复测 `20261022T031710Z-7c6a0916/backend` 为相同 3 失败 / 3 通过，34.25 秒；供应商变化此前多次失败、此轮通过，仍是未收口的间歇场景。基点生产代码与当前相同，基点范围是 04 开工状态，不代表整个 Multi-Agent 分支对比改造前无回归。安装与复测日志留在 `.tmp/04-baseline-{uv,pnpm}.log`、`.tmp/04-baseline-results/`。

## 真实 API / SQLite / Worker 与进程重启

现有回归使用生产 ASGI API、迁移 SQLite、真实双槽 JobRunner 和 Graph，仅替换外部模型；覆盖独立身份/作用域/只读工具、双 ToolCall/interrupt、部分/全失败、取消/迟到、选择性重试/接受部分结果、等待缓存失效、过期决定、线程/输入/清理隔离和事件快照。该批次的失败仍以上表为准，不将通过场景汇总成整批通过。

另用本机 TCP HTTP + 独立 Uvicorn 子进程强杀重启，外部模型使用明确阻塞的替身；生产恢复、数据库与 checkpoint 未替换。证据 `.tmp/04-process-77102632/result.json`，每项保存完整根/子/Job/request ID、决定响应、调用时间、SQLite 查询结果和事件 seq。

| 场景 | 状态 | 根 / 进程 / 结果 |
| --- | --- | --- |
| A 成功、B 请求已 STARTED 时强杀；仅重试 B | PASS | 根 `50157e38-b8a4-4cfd-a574-a4381fbb667d`，PID 26936 → 4264，02:27:12～02:27:39 UTC；根重启后 WAITING_USER/DELEGATION_UNCERTAIN，无恢复阶段模型自动重发；决定后 A 调用总数 1、B 为 2，最后 seq=17 |
| 同一阻塞条件强杀；接受已有结果 | PASS | 根 `1345be11-a67b-49c5-a148-87dd2b5a49bb`，PID 33020 → 30932，02:27:39～02:28:07 UTC；A 保留 COMPLETED，B 按决定 CANCELLED，不重发 B，父汇总完成，最后 seq=15 |
| 过期决定、消费与记账 | PASS | 两根终态后新决定 ID 复用旧快照均 409；两根原工具准入各为 2，原请求/未知 usage=NULL 保留。仅重试场景的新请求 retry_of 指向 B 原 STARTED 请求，并绑定决定；事件 seq 唯一、末值等于根 last_seq |

阻塞点是 B 外部模型流已进入、请求 STARTED 已提交而尚无完成回执；同时 SQLite 已见 A COMPLETED / B RUNNING。驱动器记录这些事实后强制结束进程树并 wait，重新以另一 PID 打开同一隔离目录，不是关闭到托盘或仅重建 lifespan。B 的领取 attempt 随安全重领/显式重试增长，逻辑执行及 Job ID 不变，不把 attempt 当作新任务身份。

原始请求示例：仅重试根的 B 未决请求 `e74ff485-8d8f-4645-9af4-821b9af5a1a3` 保持 STARTED；新请求 `848c6715-e3ca-4c7e-ac2d-7bb097b5ec34` 完成。此层所有 usage 均未知，是模型替身的范围，不代表真实供应商账单。

本轮两次临时进程驱动器首次采证分别误用了事件列名、向 ACCEPT_PARTIAL 发送空分支列表；保留 `.tmp/04-process.log`、`04-process-final.log` 原始失败，修正驱动器后得到上表结果，未改生产恢复逻辑。首轮 finally 的临时配置清理曾遇到 WinError 32，不把该轮宣称为完整采证通过。

## 真实模型固定任务对照

固定问题：比较同课程两份资料的共同点与证据差异，分别说明样本、测试时间、结果和局限，关键判断引用原文。A：40 名学生、次日 82/70 分、未评估长期保持；B：60 名学生、一周后 76/61 分、没有随机分组。共同原句为“主动回忆要求学习者先闭卷作答，再核对答案。”两份完整合成原文、提示、请求和答案均保存在各轮 `result.json`。

先执行未指定检索词的原问题，目录 `.tmp/04-real-comparison-05d5ba5b/`：

| 路径 | 状态 | 根 ID | 请求数 | 已知 input/output tokens | 未知用量请求 | 墙钟 |
| --- | --- | --- | --- | --- | --- | --- |
| general 直接 | FAIL：无有效引用 | `9c40cc2a-2419-4989-be87-3551a5bf2372` | 5 | 86114 / 1668 | 0 | 22.604 秒 |
| general 双委派 | FAIL：双调用触发，子/父均无引用 | `740e5732-4986-458a-933b-47cadca2b940` | 6 | 37293 / 2837 | 0 | 18.903 秒 |
| knowledge 独立 | FAIL：无有效引用 | `a1fb2b96-5afb-463a-b386-5c339c3f5fcd` | 4 | 8012 / 1375 | 0 | 11.449 秒 |

无模型检索预检（同目录 `retrieval-preflight.json`）确认：`主动回忆` 命中两份原文；模型实际生成的 `主动回忆 课堂实验 样本 学生 人数` 无命中。模型使用未出现在原文的复合条件时，标题导航不能替代 evidence_hits。未把该失败归为语料未准备、未把真实无命中改写为额度拦截。

随后给三条路径统一追加“先使用单一短关键词‘主动回忆’，不要把多个条件拼入一次查询；委派时也传递此提示”，固定该受提示条件进行一次对照，目录 `.tmp/04-real-comparison-b70c1c10/`：

| 路径 | 状态 | 根 ID | 请求数 | 已知 input/output tokens | 未知用量请求 | 墙钟 |
| --- | --- | --- | --- | --- | --- | --- |
| general 直接 | PASS：两来源引用有效 | `68d8bd6c-162a-4527-a7d7-0bfc28d76011` | 4 | 72873 / 1953 | 0 | 17.397 秒 |
| general 双委派 | PASS：实际独立双调用、两子完成、两来源有效 | `ad04c495-5b00-44bb-a864-d93f7d01297f` | 7 | 47904 / 6074 | 0 | 27.469 秒 |
| knowledge 独立 | PASS：两来源引用有效 | `65e8ac98-fe53-4171-860c-6e07652af7c3` | 2 | 3039 / 1464 | 0 | 10.094 秒 |

双委派子 A/B 为 `bdef1b7e-5a17-4b4e-a089-bd45694d1ba4` / `72748144-a871-4ec4-a4d0-dbc374e98599`；Job 为 `09a04057-a110-454c-88e6-24dcdab14a67` / `9bcb93ae-25b8-4c68-9c48-a8b5d2d4d055`，分别有 3 / 4 条结构化引用。最终 7 条引用均逐字属于本课程合法记录，回答未将两实验的样本/时间/分数串用。请求列表保留每个 request ID、execution_id、真实 usage 和创建时间；工具次数与模型请求数分别记录。

这些是单次、受提示条件的可行性证据：双委派比直接路径请求更多、墙钟更长；本样本已知 token 较少，不据此推断普遍更省。真实供应商本轮均返回 usage，未知用量与供应商故障恢复记 NOT_TRIGGERED；故障替身的 NULL 不代替此项真实验证。真实模型取消/崩溃重试未运行，不能用上节替身代勾。

采证脚本最初使用了不存在的请求/轮次字段；第一份额外 direct 根 `fa72444a-6b02-4356-b2d9-e69945dbed89` 已完成 3 次真实请求，但脚本 finally 的锁文件路径错误导致没有 JSON 汇总，原始 SQLite 留在 `.tmp/04-real-comparison-16de8cb5/data/`。第二份采证修正从已有终态直接读取，未再次运行其 direct 根；后续才执行其委派与独立路径。上述额外请求未从成本事实中删除。没有通过反复重跑同一未改条件筛选绿灯；受提示轮与原问题失败分开报告。

## 浏览器与原生边界

本机没有可用 browser-use 命令/浏览器工具入口；使用已有 Python Playwright 启动独立 Chromium，不接管用户浏览器。先通过 `scripts/desktop_browser_smoke.py` 只读预检：API 令牌、目录、前端 Origin CORS 和官方 IPC mock，证据 `.tmp/04-browser-preflight/result.json`。

`.tmp/04-browser-evidence/result.json`：真实 TCP API/SQLite/Worker，外部模型替身与官方 Tauri IPC mock。两种语言 × 六主题 × 1440/16px、900/20px、720/24px 共 36 组；主题为 LIGHT_DEFAULT、DARK_DEFAULT、LIGHT_SAGE、DARK_INK、LIGHT_RETRO_WARM、DARK_TOKYO_NIGHT。

- PASS：30 组的等待卡动作完整位于视口；A 完成/B 不明显示、程序直接聚焦动作、Enter 显式重试、再次不明后刷新恢复、Enter 接受部分结果完成均通过。此浏览器脚本没有发送 Tab/方向键/Escape；实际键盘另由下述原生路径验证，不混为此脚本的覆盖。
- FAIL：英文 720×1000 CSS viewport / 24px 下六主题的重试/接受按钮超出右侧视口。截图和 button bounding box 可复现；document.scrollWidth 无溢出及 Playwright to_be_visible 都没有捕捉该裁切，因此初版“36 PASS”已撤销。中文同尺寸按钮几何通过，但主对话列过窄，不将其表述为完整视觉验收通过。
- `.tmp/04-real-comparison-b70c1c10/browser-citations.json`：读取真实模型落库结果，general/knowledge 切换会话与刷新固定身份、引用跳转真实记录的 transcript/highlight 通过。真实供应商配置移除后 UI 会显示未配置引导；该只读预览临时使用不可联网的本地假配置恢复历史显示，没有新增模型调用，结束时清理。
- 浏览器视口、字体及 IPC mock 不代替下述原生层；本轮没有更改系统缩放。

## 真实 Tauri / WebView2 与 Windows 125%

通过 Tauri 官方临时配置覆盖建立独立标识 `ai.knowrealm.acceptance04.20261022`，只为该新标识创建 desktop.json，指向 `.tmp/04-native-data`；该目录是上述合成资料的独立副本。原 `ai.knowrealm.desktop/desktop.json` 与原供应商配置不修改。前端采用当前源码 Vite，Rust 壳从当前代码构建；实际 sidecar/Python/SDK/HTTP/SQLite/Worker/Graph 均为生产链。仅外部模型端改为本地 OpenAI SSE 协议替身 `127.0.0.1:43140 / acceptance04-local-stub`，用明确在途请求控制阻塞，不调用真实供应商。

使用真实 WebView2 CDP 连接，没有注入 IPC mock 或使用 Emulation.setDeviceMetricsOverride。系统 `shcore.GetScaleFactorForDevice(DEVICE_PRIMARY)=125`，原生窗口 `GetDpiForWindow=120`、WebView2 DPR=1.25，运行时为 Edge/WebView2 155.0.0.0。窗口由 Win32 MoveWindow 实际调整：目标外窗逻辑宽 1440/900/720，实际 WebView 内容宽为 1426/886/706，字体手动设为 16/20/24 CSS px；字体覆盖不冒充另一种 Windows 系统缩放。

证据 `.tmp/04-native-evidence/result.json`、`post-validation.json`、`model-boundary.jsonl`、截图及 `.tmp/04-system-scale.json`。以下是**功能路径**的 PASS，不表示窄窗视觉验收全绿；所有原始根/子/Job/request/决定 ID、起止时间、SQLite 状态和请求 usage 均在上述 JSON。

| 原生场景 | 状态 | 本轮事实 |
| --- | --- | --- |
| 新建选择、固定身份与刷新 | PASS | PID 9288，实际菜单 Home/ArrowDown/Space 选择 knowledge、Escape 返回焦点，新建全部资料知识会话并刷新，身份仍 knowledge |
| 双进度、实际退出/重启、仅重试 B | PASS | 根 `319c7636-7b11-4818-9a22-672d1253eb3d`，PID 9288 → 34660；A 已完成、B 请求在途时调用实际 exit_application，核实 Tauri 与 sidecar 均退出，再以新 PID 打开同一独立目录；WAITING_USER 后通过界面 Enter 重试、完成汇总并跳转原文，过期决定 409 |
| 退出/重启后接受部分结果 | PASS | 根 `19a67053-1870-4ef0-b955-d20ea3ed4eed`，PID 34660 → 34772；同一阻塞条件，重启后 B 不自动重发，通过界面接受 A 结果，B CANCELLED，根完成并可定位引用 |
| 停止、迟到防线与消费 | PASS | 根 `97b3dd9b-01de-45b9-ae4d-82b218fe28a8`，实际点击停止后根 CANCELLED，SQLite 恰有 A COMPLETED / B CANCELLED；三个场景根 seq 唯一且与 last_seq 相同，准入数分别 4/3/3。日志核对 A 始终只发一次检索和一次报告请求，重启/决定没有重跑 A |
| 实际键盘 | PASS（该路径） | Home/ArrowDown/Space/Escape 菜单、等待卡真实 Tab → 接受按钮 / Shift+Tab → 重试按钮、Enter 决定与可见焦点；未宣称遍历全部应用快捷键 |
| 六主题 × 中英 × 三种真实窗口/字号 | 部分 PASS，视觉 FAIL | 36 组保存实际内窗尺寸和按钮几何；按钮位于视口的测量通过，但 706px 内容宽/24px 英文截图显示按钮突出等待卡边界，输入列过窄。视口内可见不等于容器无溢出，不能将 36 组写成完整视觉通过 |
| Windows 150% / 200% | NOT_RUN | 本轮只使用机器原有 125%，没有修改系统设置；其余两档留给真实系统切换后的复验 |

本地协议替身中的 token usage 是合成数值，不能作为真实供应商用量。真实供应商账单/语义证据仅在前一节固定任务对照中；本轮未完成“原生 UI + 真实供应商故障”的组合验收。原生启动采证曾在页面目标尚未建立时连接过早，两个原始驱动器错误保留在 `04-native-decide-*.log`；改为先等待 /json/list 中实际前端 target 就绪再连接，未改生产启动流程。最后停止场景后实际退出应用，核实进程消失再清理。

## 人工桌面复现与收口

1. 先完成下述阻塞项修复，并保留本记录中的红灯；建立独立桌面配置标识和独立 data-dir，不覆盖用户 `desktop.json` 或原目录。记录实际 HEAD/diff、模型/同意、目录、屏幕分辨率与 Windows 系统缩放。输入上述同课程两份合成资料，核对原文检索命中后再开始。
2. 用真实 Tauri 新建菜单选择 general/knowledge，键盘方向键/Space 选择、Escape 返回；新建后持续显示固定 Agent，切会话/刷新不变化。knowledge 的写入和联网入口不可用；默认入口仍 general。
3. 在 general 按上述提示请求双委派，记录两个不同执行 ID；等待时观察双进度，切会话/刷新后根 seq 与 SQLite 一致。终态引用点击应定位对应记录和原文，不串用 A/B 来源。
4. 使用可控供应商故障环境制造 A 成功、B 请求结果不明；记录具体阻塞点、请求和消费。分别新建任务验证“仅重试 B”“接受已有结果”“停止”；不能仅关闭到托盘。强杀后确认进程确实退出，再重启。重试可能重复计费；不自动重发，不重跑 A，不重置旧消费，不清父或兄弟线程。过期决定须拒绝。
5. 在 Windows 设置中实际依次应用 125%、150%、200% 缩放，按系统要求完成切换，再检查六主题、中英、大字号、窄窗入口/双任务/等待动作/焦点与裁切。每格记录 PASS/FAIL/NOT_TRIGGERED/NOT_RUN、截图、实际系统比例；不要把 CSS viewport/DPR 填入系统缩放栏。
6. 导出根/子/Job/request/decision IDs、起止时间和 SQLite 对账；停止自建进程，核实专用绝对路径后清理临时供应商配置，不删除用户原有资料。只有真实项完成且失败收口后再勾对应项。

## 已发现的阻塞项

1. **供应商变化恢复竞态，FAIL**：`test_restart_reconciles_persistence_windows_without_repeating_child[provider_wait]` 连续两次观测失败。持久根为 WAITING_USER/PROVIDER_CHANGED，但子为 FAILED/CHAT_TURN_RESUME_CONDITION_UNMET，预期应保留 QUEUED/PENDING 等待恢复原配置。复现根 `eceadaec-212e-4353-b1a9-8f36ad27f1db`、子 `9ef2c9d8-35c7-485e-b917-92b3eace9735`，见对应 basetemp 和日志。`delegations/worker.py` 的供应商条件拒绝进入 failure，父尚未进入等待时会提交子失败；不是请求已发出的未知恢复问题。尚未修改生产行为，须修复并保留原断言验收。
2. **窄窗大字号布局，FAIL**：浏览器英文六主题按钮超出视口；真实原生 125% 英文截图中按钮突出卡片边界、输入列过窄。分别按各层实测记录，不以 DOM 可见或按钮视口内通过掩盖容器溢出。
3. **原问题真实模型证据获取失败，FAIL**：复合检索词无原文命中；只在显式短关键词提示下完成固定对照。需要评估检索词指引或检索策略，受提示样本不证明任意问题都可靠。
4. **双根槽峰值首次失败，定向通过**：原断言未改，尚未证实首次失败根因，不能登记成已解决的历史偶发问题。

## 当前交付判断

清理证据 `.tmp/04-cleanup.json`：原桌面 desktop.json 与原供应商 providers.json 的 SHA256 均与原生验收前一致；自建 Tauri、隔离 sidecar、本地模型服务、Vite 均已停止，1420/1437/9224/43137/43138/43140 无监听。临时原生 AppData 配置、供应商配置与 WebView 缓存已移除；默认应用标识的 debug 二进制已重新构建恢复，日志 `.tmp/04-default-build-restore.log`。截图、结果 JSON、日志和隔离业务库保留用于核对，均不 add/commit。

本轮独立基点已执行 `git worktree remove --force`，Git 登记已移除，但绝对目录 `E:/workspace/project/my/KnowRealm-AI-baseline-multi-agent04-16e8096` 仍残留 node_modules、packages、scripts 和锁文件；未取得完整删除成功证据，不宣称清理完成，也未换删除方式继续。原基点运行记录已先复制到本票 `.tmp/04-baseline-results/`。其他原有 worktree 未动。

04 不具备完整通过/关票条件：真实模型受提示对照、真正进程重启和原生 125% 主要操作路径已取得证据，但全量六项红灯、无提示检索和窄窗视觉缺陷未收口，Windows 150%/200% 及真实供应商故障组合仍未验。不得据此宣称完整桌面交付或合并门禁通过。
