# 06 升级回归与真实链路验收

实施基点：`04d2d2c8347da5d478edd60da460204823cf9497`，当前分支 `feat/extend-dev-09`。用户已有未跟踪 `.scratch/agent-context/baseline/` 不修改、不纳入提交。工单未完成完整真实验收。

## 本轮范围和实现

本票复用 01～05 的 Service、公开提交/等待/继续/取消、受控操作与持久事件；不增加 Agent 工具、不改变授权或 API 契约。对 02 尚未关闭的两个发布缺陷进行对应边界修复：

- 小窗口规划预留不足时不再把合法历史片段判为不可压缩。保留正常窗口的原预留策略；当前实际累计摘要导致下一块超限时，通过线程重新规划尚未处理的片段，保留完成前缀、来源和原消费。新计划写入前复用原 `_guard`，每次模型请求仍独立完整计量及持久准入。
- 主模型超限识别增加百炼明确输入长度文案和兼容端点的最大上下文/Token 文案，保持同逻辑请求一次兜底。普通 max_tokens 参数错误不归类为超限，不重放已经提交的业务工具。错误形态依据 [百炼官方错误清单](https://help.aliyun.com/en/model-studio/error-code)；没有新增错误正文日志。
- 真实 DeepSeek 首轮验收发现输出限额被 SDK 改名后忽略：配置摘要 1024，实际输出 5270/6193/6160/2641 Token。新增统一 `chat_output_parameters`，仅已知 DeepSeek 官方端点通过公开 `extra_body.max_tokens` 传实际限额，回答与摘要共用；其余端点维持现有参数。依据 [DeepSeek Chat API](https://api-docs.deepseek.com/api/create-chat-completion/) 与 [LangChain extra_body](https://reference.langchain.com/python/langchain-openai/chat_models/base/BaseChatOpenAI/extra_body)。Context7 文档检索额度已耗尽，改用官方文档和当前安装源码核对。
- 在既有测试 seam 补升级与生命周期：0045 旧库经真实迁移链升级后无批量模型调用、原消息逐列不变、首次上下文读取才初始化；原大输出经导出恢复保留游标/正文，删除后拒绝访问但保留必要数据；派生摘要经滚动备份及导出恢复保留正文、身份和实际次数，删除后上下文查询拒绝。
- 恢复不含供应商配置的归档后，删除会话再查上下文曾返回 200；生命周期测试确认泄露边界后，`view_context` 改为复用 `ChatSessionService.get`，在读取派生摘要/实际输入前执行软删除校验。GET 与 POST 预估复用同一入口。
- 摘要结构/来源校验失败及 SDK 长度截断时，若供应商已经返回 usage，仍持久保存真实计数；请求保留 FAILED。格式拒绝/网络失败缺少 usage 时保持未知，不填零。没有摘要激活或隐藏重试。
- 提交具体 ADR/四类术语审阅稿及真实验收步骤；2026-10-14 用户批准后，已按提案新增 ADR-0028、在 ADR-0018 添加阶段性关联，并增补 GLOSSARY 四项。编码规范未改。

## 一条完整证据链

公开 ChatTurn POST 受理 → 原 JobRunner/Worker → 最终模型 Middleware → 摘要请求持久准入 → 分块结果/激活提交 → REST 实际输入及来源读取 → 既有导出/滚动备份 → 空目录恢复与新 lifespan → 来源读取或删除后拒绝。

数据全部是测试临时库和固定公开测试文本。模型边界为 StubChatModel/结构化替身；供应商兼容回归为真实 ChatOpenAI/HTTP 替身。ASGI API、SQLite 迁移、Worker、归属/权限及导出恢复使用生产实现；它们不是独立 TCP sidecar、真实供应商或原生桌面证据。

## C01～C20 对照

下列为自动化实现覆盖定位，最终执行结果见后文。每项真实模型/桌面层级均另列待验；定位到测试不等于该层级通过，也不等于覆盖所有可能交错。

| 项 | 对应票 | 本轮复用的公开行为证据 | 真实边界 |
| --- | --- | --- | --- |
| C01 | 01 | context_budget：端点能力、覆盖、原轮策略保持；恢复中端点/密钥变化 | 同一 DeepSeek 真实调用已验；切换端点真实场景待验 |
| C02 | 01/03 | complete_input、same_turn_tool_output、large_json_receipt；实际请求投影 | 真实 usage 分层记录；近似计量不等于精确 tokenizer |
| C03 | 01/02/04 | blocked_input、pin_overflow、压缩触发/目标及有效输出限额 | 真实超限场景待触发 |
| C04 | 02/03 | more_than_ten_turns、complete_chunks、工具后超限不重复业务 | 真实 32 轮完成，素材空切片限制另列 |
| C05 | 02/04/05 | 全覆盖片段拼接、结构/来源校验、固定不进摘要、排除后的重建 | 语义遗漏待真实模型评价 |
| C06 | 02 | small_window 实际重分/完整拼接、四次等待、重启后块/消费保持 | 真实五块/77 来源及等待继续通过 |
| C07 | 02 | transient_retry、json_mode SDK 请求、有限兜底、并发继续 | 真实 SDK 边界耗时与 usage 已记录，未知不填零 |
| C08 | 02 | invalid_summary 安全/不安全降级、取消迟到结果与等待状态 | 原生错误反馈待验 |
| C09 | 04 | 固定/解除、超限拦截、来源版本/归档/删除/范围失效 | 原生主要动作待验 |
| C10 | 05 | material_exclusion、cached_asset/cited_answer、三档规则修改 | 真实排除/重置/纳入/恢复指定来源通过 |
| C11 | 05 | exclusion_reset_explicit_history、旧段读取拒绝、legacy 与独立 Run 保留 | 原生组合待验 |
| C12 | 01/04/05 | 原轮策略/固定/规则恢复、旧摘要不能激活新设置 | 真实后台生成往返待验 |
| C13 | 02/04/05 | claim takeover、input_identity、迟到摘要/取消与提交 guard | 自动化确定性交错；非原生证明 |
| C14 | 04/05 | 三档 L1、过期确认及并发设置写、现有执行身份校验 | 真模型选 Tool/确认待验 |
| C15 | 03/05 | history_scope/cursor、共享范围/版本、工具次数/字符预算 | 新鲜 Tool 回执与下一模型输入核对通过 |
| C16 | 01/02 | 受理消息、REST 实际用量、事件并发落库、恢复游标 | 原生断线恢复待验 |
| C17 | 01/04/05 | chat 页面及 useChatTurns/chatUiStore：独立路由/切换/草稿/恢复 | 浏览器/组件不等于 Tauri |
| C18 | 01/06 | 新增0045升级按需初始化；tool_budget旧轮四状态兼容等待/停止，原输出/消费保留 | 真实旧构建升级待验 |
| C19 | 01/04/05 | 既有恢复同意/密钥变更与 Learner Memory 防线，改动日志无新增正文 | 沿已有有效同意真实外发测试语料；原配置未改 |
| C20 | 03/04/05/06 | 输出/游标导出恢复；摘要滚动备份/恢复；来源失效及删除后访问拒绝 | 原生数据目录迁移/在途组合待验 |

## 自动化记录

- 修改前复现：`.pytest-tmp-runs/20261014T033521Z-4b69da0b/backend/`，5 项中 3 失败/2 通过。失败为小窗口规划及两种已提交工具交错的百炼超限文案。测试边界明确，不涉及真实模型。
- 第一轮压缩回归：`.pytest-tmp-runs/20261014T033636Z-d6f0cf77/backend/`，31 项通过。此后增加普通参数错误不重试、实际重分及摘要备份恢复断言，最终证据由组合/全量补充。
- `.pytest-tmp-runs/20261014T034248Z-feb69b3d/backend/` 为一次命令路径拼写错误：收集 0 项，未执行测试；已修正文件名，不能计入通过。
- 组合回归：`.pytest-tmp-runs/20261014T034319Z-83ba725a/backend/`，147 项全部通过，649.40 秒。含预算、取回、固定、规则、压缩、恢复/事件、工具预算、归档及错误码。运行开始后补充的实际重分/摘要备份断言及之后的 DeepSeek 参数修复由最终检查补证，不能将此结果作为最终源码全量通过。
- `pwsh -NoProfile -File scripts/check-changed.ps1` 退出 0：触及 Ruff/格式、Pyright 0 错误，记录 `06-check-changed.log`。`pnpm --filter @knowrealm/api-types check` 退出 0，无契约变更。
- 最终全量：`uv run --frozen --directory backend python -m scripts.run_tests all`，记录 `.pytest-tmp-runs/20261014T042617Z-86f5ae17/`。前端 FAILED：741 通过/5 失败，1064.96 秒；后端 FAILED：1295 通过/6 失败，2544.82 秒，整体退出 1。上下文预算/取回/压缩/固定/规则五文件共 94 项通过；含本轮最后补充的 length/已知 usage 与最终 SDK HTTP 参数断言。完整结果保持红灯；以下独立基点复测已完成归因。
- 最终触及检查：`06-check-changed-final.log`，退出 0，Ruff/格式及 Pyright 0 错误；API 类型 `pnpm --filter @knowrealm/api-types check` 退出 0。之后仅批准文档落盘，没有生产代码或 API 契约变化。
- 文档落盘经 Spec 只读复核：与批准范围一致，无新增实现冲突；相对链接存在、JSON 证据可解析且无密钥字段，PROJECT_PROGRESS 保持 199 行。

## 全量失败的基点比较

独立 detached worktree：`E:/workspace/project/my/KnowRealm-AI-context06-baseline-04d2d2c`，HEAD 为本轮开工基点。先后执行 `pnpm install --frozen-lockfile`、`uv sync --frozen --directory backend`，均退出 0；各自 node_modules/.venv，不借当前环境。全量、安装和两套复测串行。

基点命令与记录（每份 result.json 保留完整命令/退出码/时限）：

- `uv run --frozen --directory backend python -m scripts.run_tests frontend src/features/learningPlan/components/LearningPlanTab.test.tsx src/features/search/components/CommandPalette.test.tsx src/features/records/components/RecordDetail.test.tsx`：FAILED，26 通过/5 失败；Vitest 197.30 秒、runner 221.45 秒，退出 1。记录基点 `.pytest-tmp-runs/20261014T053049Z-e7a14c4f/frontend/`。
- `uv run --frozen --directory backend python -m scripts.run_tests backend` 后接下表六个 node ID：FAILED，6 失败；pytest 128.95 秒、runner 145.74 秒，退出 1。记录基点 `.pytest-tmp-runs/20261014T053504Z-998529c7/backend/`。元数据 dirty=true 是前端生成 `routeTree.gen.ts` 换行造成；无内容 diff，`git diff --exit-code -- backend` 为 0，基点后端源码未改。已恢复自己生成的路由文件，基点现为干净状态。

| 当前全量失败 | 基点同项复现 | 错误形态 |
| --- | --- | --- |
| LearningPlanTab 三项历史版本/目标只读查看 | 3/3 | 同一旧页面元素/交互断言失败 |
| CommandPalette 空查询捕获命令 | 1/1 | 触发后目标 heading 未消失 |
| RecordDetail review 大纲树 | 1/1 | group 未全部带 open 属性 |
| test_agent_run_waiting.py::test_upgrade_migration_backfills_legacy_recovery_budget | 1/1 | chat_compactions 已存在，旧迁移夹具重复建表 |
| test_chat_streaming.py::test_context_contains_system_snapshot_and_last_ten_turns | 1/1 | 旧断言要求排除问题1，持久历史实际仍保留 |
| test_chat_streaming.py::test_response_process_separates_commentary_and_all_parallel_tools | 1/1 | 旧断言要求下一轮所有输入不含先前 commentary，实际持久历史包含 |
| test_document_import.py::test_unexpected_io_and_parser_errors_are_not_retryable_or_logged | 1/1 | 非预期异常堆栈含测试 private-source-path |
| test_quizzes.py::test_quiz_last_count_preference_round_trip | 1/1 | 旧响应期望缺 light_theme_id/dark_theme_id |
| test_server_process.py::test_second_sidecar_cannot_open_locked_data_directory | 1/1 | 第二进程 10 秒 TimeoutExpired |

前端失败身份集合、后端失败节点集合均与当前全量一致，逐项形态复现。它们已存在于当前开工基点，不是本轮改动新增；保留失败，不修改无关模块、旧断言或检查配置获取绿灯。该比较只覆盖失败节点，不能称为基点全量通过，也不消除仓库发布红灯。

为便于复核保留本次专用基点和测试日志、隔离真实 DB；自建测试脚本/runner 已结束，未修改用户已有 worktree。临时供应商密钥配置已删除；模型明细不含完整输入/输出或密钥。

## Standards

发现同步重新规划会阻塞异步事件循环，已改 `asyncio.to_thread`；DeepSeek 参数、软删除入口及失败 usage 分支复核后无其余明确发现。

## Spec

未发现实现错误或扩范围；实际重分、摘要备份恢复、旧升级及回答最终参数断言已补齐。真实第一次失败与扩大隔离额度后的复验必须分别保留；高额度成功不证明默认额度可靠。两轴最终均无未关闭代码发现；审查未独立跑重测试，不替代执行结果。

## 真实范围与交付状态

真实模型指定场景通过，完整真实验收仍未完成。只读核对现有 sidecar 后确认 `https://api.deepseek.com` / `deepseek-v4-flash` 的凭据及已有外发同意有效；隔离目录只复制同一 LLM 配置与既有同意，不复制用户会话/资料，不重新授予同意。两个验收目录的临时 `config/providers.json` 已删除，原配置未改。所有外发均为测试语料。初轮真实 4 轮完成，第 5 轮反复归并达到额度等待；实际非空块 1、归并块 3，不算原文多块通过。初轮记录 `backend/.tmp/06-real-model/live-20261014/evidence.json` 为 STOPPED；输出上限失效证据保留。

修复后 `backend/.tmp/06-real-model/live-capped-20261014/` 会话 `6fd12c6b-3354-4363-afcd-0f1f67efb6f4`：32 个真实往返完成，32/32 回答末行有 KR06。切片测试中第 12～25 轮素材为空（字符长度与预设切片范围不一致），仍是真实问答但不计作长素材覆盖；后续完整旧历史重新纳入单独触发真实分块。第 32 轮有真实 search_context/read_context 事件；进一步明确来源读取的 Tool 回执与下一次模型输入匹配，首轮目标“离线学习工作台”和期限“三周”确实进入模型，来源 `message:d203d146-c408-4783-a64d-94ecd4c52147`，版本和调用身份见 `06-real-model-evidence.json`。

显式测试预算分阶段记录：32 轮为窗口/输入 60000、回答 4096、摘要 8192；规则重建第一次因 SDK 输出截断失败，未激活摘要，不删除原消息；扩大隔离预算到 100000/16384 后，排除→重置→纳入→恢复均通过。来源返回 409/409/200，固定项 EXCLUDED/EXCLUDED/VALID，设置版本 7→9→10、段 1→2→2。扩额是在新的测试轮次中生效，没有改变失败轮的原输入或历史用量。

真实分块使用窗口/输入 70000、回答 4096、摘要 12000：轮次 `74df34a0-33c4-4cde-8d92-573fe7f53a71`、摘要 `931b5cab-debe-48d8-a658-b4cb529ced6d`，5 个非空块、77 个来源身份，已覆盖片段按原 wire 完整拼接。四次后 WAITING_USER、显式测试步骤继续一次使额度 4→8，原分块复用，6 次实际摘要请求后完成/激活。估算输入 67588→45290，可用预算 52723；未达到 60% 目标但重新计量安全后继续回答。不能把覆盖完整 wire 解释为语义无损。

最终同一会话 38 个轮次身份，37 完成/1 个截断失败。SDK 实际调用与 SQLite 请求数一致：回答 49 次，已知 input/output/total=954952/12775/967727；摘要 40 次，21 次有已知 usage，已知小计 89353/120941/210294，19 次未知（包括格式拒绝及历史观察未保留的截断用量）。未知不当作零，也不宣称小计就是全部实际费用。回答/摘要 SDK 边界耗时累计 142127ms/550961ms，中位数 2445ms/6640ms，含网络与客户端处理；金额/供应商服务器内部耗时未知。明细见 [真实模型证据](06-real-model-evidence.json)，只保留身份、计量、耗时及布尔内容核对，不存完整 Prompt/输出。

1024 输出额度 SDK 探针见 `06-real-output-cap.json`：input=519、output=358（含 reasoning=212）、total=877，4991ms，JSON 有效、finish_reason=stop。它不证明默认 1024 或 8192 足以完成所有长历史/推理模型摘要。历史搜索多次空结果、参数/工具预算拒绝也保留在真实记录中；直接来源取回成功，不宣称检索语义质量全面通过。仅评价了固定标记、首轮目标/期限和来源取回；全部素材的语义遗漏没有逐项人工审计。

Tauri/WebView2、Windows 125%/150%/200%：NOT_RUN。Browser Use 无活动连接，备用 Chrome CDP 仅空白页；本机桌面进程存在，但未取得可用原生控制连接。真实供应商输入超限：NOT_TRIGGERED，有限兜底仍由真实 SDK/HTTP 替身回归验证。原生取消/断线/系统缩放及旧构建真机升级待验；未改变用户数据、外发同意、原配置或系统缩放。ASGI+真实 SQLite/Worker+真实供应商不冒充独立 TCP sidecar 或原生桌面。

步骤与逐项记录见 [06-real-runtime-acceptance.md](06-real-runtime-acceptance.md)。用户已批准并落盘的范围见 [06-documentation-proposal.md](06-documentation-proposal.md)。未完成真实项及全量非绿边界均保留；本票不能标完整真实验收完成。

01～03 的部分旧实施文档在当前基点已不存在，票内历史链接不能当作可访问证据。未恢复用户已删除文件；本记录用当前源码、固定测试节点与新执行记录重建验收索引。
