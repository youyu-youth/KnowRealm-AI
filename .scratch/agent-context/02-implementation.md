# 02 自动摘要、额度与持久恢复实施记录

日期：2026-10-13。比较基点：`6b6f25d80e1cdb564e542f12bd9fa0e0ee209c02`。先查看 01 的 `a5f84b5`、`ccd7e87` 两提交；本票沿用其最终请求计量、供应商能力、轮次绑定输入及独立页面。按项目 `implement` skill 实施和双轴评审。本票不实施 03～05 的取回、固定、排除、重置，也不修改权威规则/ADR。

当前状态：02 因后续复审缺陷重新打开。恢复后重复主模型超限兜底、摘要供应商结构化输出兼容、两类用量投影及并发继续重复追加额度已修复；小窗口分块及超限错误码识别仍待修复，不能据单项修复宣称整票完成。

## 实现

- 生产组装不再裁十轮或按六万字符静默删除历史；原始消息保留。近期往返和当前提问/工具闭环以预算选取，完整请求达到 80% 时压缩，目标 60%；目标不可达时允许安全输入继续。
- 最终模型 Middleware 使用公开 `request.override(messages=...)` 接缝，旧有效摘要加增量原文分块。程序记录消息身份及逐字片段，结构化输出固定六栏，来源不得超出已处理输入；约束/决定须摘录用户原文。摘要作为派生 AI 消息，无执行权限，不包含独立系统提示、Learner Context 或整份材料。
- 0047 仅 DDL：原输入绑定段/摘要及四次额度；压缩表保存完整计划、结果、覆盖来源和计数；请求表独立区分 ANSWER/SUMMARY，保留实际回答输入与超限重试来源。数据仍在原 knowrealm.db，由后端唯一写入。
- 摘要复用原模型工厂（SDK `max_retries=0`）、当前供应商和原外发同意；每次实际请求出网前同事务检查 claim/取消/输入身份并扣额度。恢复复用已提交结果，真正重新出网另计一次；瞬时错误同块最多重试一次，持久记录跨恢复保持。
- 单轮四次耗尽进入原 `WAITING_USER`，`CONTEXT_COMPACTION_LIMIT` 释放执行槽；公开 resume 追加四次，不由工具或模型审批；并发重复继续的额度幂等仍有复审缺陷。部分摘要不激活，整批有效后原子激活，并重新检查完整回答预算；旧轮次不能覆盖新版本设置。
- 主模型超限兜底用压缩前原始请求指纹绑定 `retry_of`；每次模型出网准入在原 claim/取消事务中检查已消费兜底。已准入的兜底中断后不再出网；旧版记录通过已登记重试的实际输入指纹识别，不清零或迁移计数。工具后新模型请求仍独立计量，不重放已提交业务工具、不重置工具预算；供应商超限错误码识别范围仍待修复。
- 聊天与独立上下文页通过 REST 的压缩事实轮询恢复进度、额度、六栏来源和取消/失败状态；沿用既有 SSE 轮次等待/取消投影。摘要与回答的请求及 usage 分开显示，缺失 usage 显示未知；继续按钮明确追加四次请求且不批准业务操作。

## 证据

新增测试 `test_conversation_compaction.py` 使用生产 API、迁移 SQLite、双槽 JobRunner、LangGraph 公共执行链和受控结构化模型替身，覆盖：十轮以上原文；逐字分块覆盖；原子激活与下一轮；四次额度及显式继续；准入后/分块后/激活后重启；瞬时重试；无效来源的安全降级/不安全停止；小窗口计划失败降级；供应商有效输出上限；取消迟到结果；claim 接管和输入身份变化；实际超限时业务写唯一、工具预算不重置。

- 新增核心 13 项全过（`02-acceptance.log`）；新增输入身份 1 项过（`02-identities.log`），claim 接管修正测试夹具后 1 项过（`02-takeover.log`）。最终组合回归结果见下文。
- 前端六栏/来源展开、请求消耗和继续按钮 4 项过；聊天原相关 45 项过。后续导航超时独立复跑和全量结果见下文。
- `scripts/check-changed.ps1` 全部通过：本次前端 ESLint、格式、构建、后端 Ruff/格式及 Pyright 0 错误（`02-check-changed-final.log`）。OpenAPI 已生成并检查。
- 浏览器模拟：隔离页面以测试 SQLite 结果作 fixture，四主题、中文/英文、682px 窄窗检查六栏可达、用量分离及横向溢出。截图在工具返回中检查；保存截图被浏览器工具路径权限拒绝，未换方式绕过。此证据不等同真实 Tauri 或 Windows 系统缩放。

## 双轴评审

- Standards：规划同步持有写锁已移到事务外 `asyncio.to_thread`，短写事务重新 guard；后续复审新增缺陷及当前修复范围见本文“当前状态”，不能沿用无残余发现的结论。
- Spec：指出规划失败绕过安全降级以及预留使用未收紧摘要输出；已修复并加入相应小窗口/有效输出回归。完整分块覆盖不是语义无损保证。

## 未验证项

- [ ] 真实供应商摘要语义、遗漏与成本校准，包含无损程度评估；归 06 汇总。
- [ ] 真实 Tauri/WebView2 中持续生成、等待继续、取消与页面往返；Windows 125%/150%/200% 系统缩放；不代勾真机验收。
- 本次基点工作树为仓库外 `E:/workspace/project/my/KnowRealm-AI-context02-baseline`，独立安装依赖用于同用例基点比较。用户原 `.scratch/agent-context/baseline/` 未修改或清理。

## 本次恢复兜底修复验证

- 修复前新增恢复用例 3 项均失败；修复后公开 API、迁移 SQLite、持久 checkpoint 与真实 Worker 的生命周期重启验证通过，模型为受控替身。覆盖直接强制压缩、先自动再强制压缩及旧版已准入记录：重启后主模型调用仍为 2 次，摘要/分块及请求消费不追加，以 `MODEL_INPUT_BUDGET_EXCEEDED` 收口。
- 扩展既有业务工具用例验证同轮两个不同模型请求均可各自获得一次兜底；已提交课程只创建一次，工具预算不重置。没有新增数据库迁移、HTTP 契约或状态机。
- 首轮组合为 65 passed / 3 failed：新增场景的工具消费阶段断言已修正，另外两项报 SQLite 写锁冲突；claim 接管隔离复跑通过，最终相同四文件组合 68 passed。未将写锁失败归因为已确认的历史债务，也未扩大超时或排除用例。最终日志见 `02-overflow-retry-regression.log`。
- 触及两 Python 文件 Ruff、格式及 Pyright 零错误；未验证真实供应商、进程强杀或 Tauri。其余复审缺陷仍待修复。
- 两份本地工单/实施文档 Prettier 通过；`PROJECT_PROGRESS.md` 整份格式检查仍有既有失败，父提交原文经同一 Prettier 格式化也产生相同区域差异，仅保留本次三行内容更新和原表格列宽；交接文档行数仍为 199，没有顺带整理无关内容。

## 本次摘要供应商兼容修复验证

- 抽出并复用 LLM Service 的 JSON Schema 提示构造及格式拒绝识别；只在结构化格式被拒绝时切换 JSON 模式，鉴权及无关配置错误不降级。不调用 Service 内部直接出网的生成方法，避免隐藏请求次数。
- 格式拒绝、JSON 降级及瞬时重试均各自先重新计量、检查外发同意，并在 claim/取消/输入身份校验事务中扣额度、登记请求。JSON 提示中的 Schema 计入输入，输出上限通过公开 `with_structured_output` 参数绑定到实际 HTTP 请求。格式选择持久化在原分块计划中，后续分块和重启不重复探测已拒绝的格式；未完成摘要仍不激活。
- 修复前真实模型工厂＋LangChain/OpenAI SDK＋HTTP 替身的降级用例失败，原因为供应商拒绝 json_schema（`02-json-mode-red.log`）。修复后 7 场景通过（`02-json-mode-sdk.log`），未替换 `with_structured_output`：原生格式、JSON 降级、503 重试、无效 JSON、401、无关 400、四次耗尽后生命周期重启并显式继续。网络替身在收到请求时核对 SQLite 准入与扣次已提交；断言实际格式、输出上限、账本次数及降级提示重新预算。
- 真实 SDK 的 usage 含嵌套明细，摘要现复用回答请求的整数计数过滤逻辑，避免上下文 REST 快照违反 `dict[str, int]` 契约。没有数据库迁移、HTTP 契约或依赖变化。
- 四个上下文/恢复/工具预算文件及既有 LLM 格式降级、鉴权两项组合结果为 **76 passed / 1 failed**（`02-json-mode-regression.log`）；唯一失败为既有无效摘要安全降级用例的 SQLite 写锁导致轮次超时。该用例两参数隔离复跑 **2 passed**（`02-json-mode-invalid-isolated.log`），未修改测试超时或排除组合用例；写锁未归因为已确认历史债务，不能将原组合称为全部通过。本次新增真实 SDK 7 场景在组合内也全部通过。
- `scripts/check-changed.ps1` 通过（`02-json-mode-check-changed.log`），触及五 Python 文件 Ruff、格式及 Pyright 零错误；两份本地工单/实施文档 Prettier 通过，交接文档保持 199 行，仅更新三行并保留原表格列宽。真实供应商、进程强杀和 Tauri 未验证；其余复审缺陷仍待修复，整票维持 in-progress。

## 本次旧有效摘要额度修复验证

- 上下文 REST 的 `active_summary` 按摘要自身 `turn_id` 读取 `ChatContextInput.summary_allowance`，最新轮次的请求和压缩列表仍沿用最新轮次快照。没有改动执行额度、模型调用、HTTP 契约或前端文案。
- 扩展既有“四次耗尽后显式继续”用例，不新增测试或夹具：A 轮真实 Worker 用 6 次摘要请求完成、额度为 8；随后扩大 B 轮窗口以确保短问不触发新压缩，验证旧摘要完整投影保持一致，两轮持久额度分别仍为 8 和 4。修复前 REST 的旧摘要额度从 8 错变为 4，测试失败（`02-summary-owner-red.log`）。模型使用受控替身，API/迁移 SQLite/Worker 为真实执行链。
- 修复后该用例通过；`test_context_budget.py` 全文件加继续压缩、摘要激活两项组合为 **10 passed / 1 failed**（`02-summary-owner-regression.log`）。唯一失败为既有摘要激活用例的 SQLite 写锁导致轮次超时，隔离复跑 **1 passed**（`02-summary-owner-activation-isolated.log`）；未改超时或排除用例，原失败记录保留，写锁未归因为已确认历史债务，不能称组合全部通过。
- `scripts/check-changed.ps1` 通过（`02-summary-owner-check-changed.log`）：包含此前未提交修复在内的六 Python 文件 Ruff、格式及 Pyright 零错误；两份本地文档 Prettier 通过，`PROJECT_PROGRESS.md` 保持 199 行。该次修复未修改前端；真实模型及 Tauri 未验证，整票保持 in-progress。

## 本次轮次/批次用量投影修复验证

- 修复前调用生产 `compaction_out`，同轮两批各扣 2 次仍分别投影为 2/4；生产组件浏览器模拟也显示“等待追加摘要额度 · 摘要请求 2/4”。问题确为 P2 展示缺陷，执行端总扣减未改变。
- 保留 `requests_used` 的单批口径，新增 `turn_requests_used` 表达所属轮次全部批次的实际累计次数；分子与 `allowance` 均来自同一轮次。当前批次列表按已查询的完整账本累计，旧有效摘要按自身 `turn_id` 汇总所有批次并读取原轮次额度，包含失败/重试/取消前已消费请求。没有改动执行额度、数据库结构或 Middleware。
- 前端沿用原组件、语义样式和换行规则，zh/en 同步明确“本批请求”与“所属轮次摘要请求/额度”，避免把重复展示的轮次累计值当成单批次数。OpenAPI 与 TS 类型同步生成，字段说明明确两种计数口径。
- 新增真实迁移 SQLite＋REST 的持久事实夹具投影测试 3 场景（等待/失败/取消，含下一轮默认 4、旧所属轮次 8），修复前 3 项失败（`02-turn-usage-red.log`），修复后与既有继续压缩、工具后超限兜底合计 **6 passed**（`02-turn-usage-regression.log`）；另上下文预算全文件 **9 passed**（`02-turn-usage-context.log`）。合成批次用于投影验收，不代表该批次由模型/Worker 真实执行；既有 Worker 用例的模型仍为受控替身。
- 前端六栏展开、两语言多批计数及双语一致性 **6 passed**（`02-turn-usage-ui.log`）；修复前对应组件测试 3 项失败（`02-turn-usage-ui-red.log`）。生产组件＋合成显示数据的浏览器模拟覆盖四主题、zh/en、620px CSS 窗口、14px/28px 字号，共 16 条件无横向溢出，截图已检查；DPR 1.25 和 200% 字号调整不等同 Windows 系统缩放或真实 Tauri 验收。
- `scripts/check-changed.ps1` 通过（`02-turn-usage-check-changed.log`）：触及前端 ESLint/格式/TypeScript/构建和七 Python 文件 Ruff/格式/Pyright 均通过。先前组合回归的写锁失败记录继续保留，不以本次绿灯替代全量或真机验收；原用户基点目录及此前未提交修改保留。
- `pnpm --filter @knowrealm/api-types check` 通过；两份本地文档 Prettier 通过，交接文档保持 199 行。本次临时 Vite 5189 已停止，隔离浏览器页已关闭，没有修改 DESIGN/rules 或刷新设计 sidecar。

## 本次并发继续额度修复验证

- 比较基点 `ddc2a7e409c89f9415cc9be5916ea4fc6d435cac`。生产 `resume_turn` 与真实迁移、文件 SQLite 确定性复现：在 SQLAlchemy 数据库接缝让两个请求都读取 WAITING_USER，第一个提交后再释放第二个，修复前持久额度为 12，预期 8，测试失败（`02-resume-allowance-red.log`）。没有替换恢复校验、额度逻辑或调度服务。
- 在原事务中按原状态、更新时间及未取消标记条件领取为 QUEUED；仅领取成功者追加 4 次并确保原任务可领取，未领取者在事务结束后返回最新快照。更新时间阻止迟到请求消费后续新等待的额度；不增加进程锁、数据库字段、HTTP 决定参数或新状态机。
- 同一新增用例覆盖 3 种交错：并发重复继续后额度保持 8、单任务；模拟执行方进入新等待并调用真实 `finalize_waiting` 后，旧继续不追加，而新用户继续只追加一次至 12；真实取消先提交后，迟到继续不复活轮次，新的继续请求仍明确拒绝。生产服务与 SQLite 为真实执行，数据库接缝控制交错，不代表新测试运行了模型/Worker。与既有正文/游标恢复两参数合计 **5 passed**（`02-resume-allowance-boundaries.log`）。
- 最终相关回归 **11 passed**（`02-resume-allowance-regression.log`）：并发/迟到/取消、正文游标、图完成补写、供应商身份和密钥/同意重验，以及公开 API＋真实 Worker 的额度继续与 JSON 模式重启继续。模型为受控替身；SDK 场景使用真实 SDK＋HTTP 替身。未扩大超时、排除失败或运行无关全量套件，先前写锁记录仍保留待定位。
- `scripts/check-changed.ps1` 通过（`02-resume-allowance-check-changed.log`），触及两 Python 文件 Ruff/格式/Pyright 零错误；本地工单/实施文档 Prettier 通过，交接文档保持 199 行。没有新增 HTTP 契约、迁移或前端改动；真实供应商、进程强杀及 Tauri 未验证，整票仍保持 in-progress。

## 最终门禁与基点比较

- 后端分次回归及失败复跑分别见恢复兜底、供应商兼容、旧摘要额度及轮次/批次投影验证；此前恢复兜底修复的四文件组合为 **68 passed**（`02-overflow-retry-regression.log`）。错误码防线原实施记录 **2 passed**，本次未变更错误码。0047 升级夹具已同步移除本票新增表，避免复跑迁移误报表已存在。
- 前端新增两组件 **4 passed**；原聊天相关首轮 **45 passed**。后续组合 **45 passed / 1 timeout**，唯一上下文导航超时独立复跑 **1 passed**（`02-chat-navigation-isolated.log`），没有扩大测试超时。
- 后端全量 Pyright 比较：本次触及文件零错误，基点全量仍有 **6** 项既有测试类型错误（`02-baseline-pyright.log`：chat_turns 未使用变量及 error_code_guard 的未知 dict keys），未修改无关测试。
- 前端全量 **682 passed / 48 failed**（`02-frontend-full.log`）。失败文件单 worker 隔离复跑 **265 passed / 10 failed**（`02-frontend-failed-isolated.log`），最终剩余八文件的同用例基点比较见下条。不能把原全量红灯称为全部通过。

- 前端基点同八文件：84 passed / 7 failed（`02-baseline-frontend.log`）。当前隔离失败中的历史只读、概念徽章、复习页结构及命令面板断言共六项在当前基点复现；另外四项定向复跑三项通过，唯一剩余设置页“即改即存”15 秒超时（`02-remaining-isolated.log`），当前基点同文件组合曾通过，因此该超时未归因；基点另有一个完成点击超时，不能宣称全量无历史债务。
- 后端全量运行超过半小时，在 82% 后多分钟无进展，主动中止并保留 `02-backend-full.log`；此前已出现失败，该次运行没有最终摘要，状态为未完成而非通过。基点额外核心复跑同样长时间无输出后停止，不能据此确认所有后端全量失败均属历史问题；最终 64 项相关回归是本票有效自动化证据。
- 本次构建、规范、契约与相关回归已收口；没有扩大超时、过滤全量失败或改动无关业务以获得绿灯。

临时 Vite 已停止。隔离 worktree 登记已移除；git 删除目录因非空失败，后续已核验绝对路径的原生 PowerShell 删除被自动审批策略拒绝（blocked by policy，无细分原因），未换方式绕过。残留 `E:/workspace/project/my/KnowRealm-AI-context02-baseline` 保留；用户原有基点目录不处理。测试临时目录与日志保留在忽略范围以便复核。
