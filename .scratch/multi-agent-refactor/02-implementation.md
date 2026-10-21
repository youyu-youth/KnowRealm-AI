# 02：单 Knowledge 委派的持久协作闭环

日期：2026-10-21。代码已实现并提交，双轴评审修正已复查；前端全量 871 通过，后端全量 1464 通过、1 项工具名单旧预期失败，更新后该项定向复测通过。真实模型与原生桌面验收待人工执行。

## 授权、范围与事实源

- 用户明确要求使用 implement 完成 02，含当前分支提交。基点 `43cce46bf31a1e8545f1e15caaa40f72a72d2841`，开工工作区干净；分支 `feat/multi-agent-refactor`，初次实现 `0917e90`。
- 复用原两个 CHAT_TURN 槽、JobRunner、knowledge 配置、模型工厂、六次根工具预算、interrupt/等待及 GET 事件端点。未增加依赖、专业 Agent、后台调度循环、审批/Operation 或隐藏聊天会话。
- 0057 仅新增表/列/索引：delegation、类型化决定、原请求/工具消费的子身份以及 wait 的结果尝试；不修改历史迁移或回填业务数据。
- 单次 `delegate_knowledge(task)`，模型不能指定范围、权限、预算根、claim 或目标 Agent。knowledge 仍只有本地只读工具，不开放嵌套委派。03 的双调用并行验收及 04 的真实分层验收未关闭。

## 实现接线

- 登记在根写锁内原子保存委派、Job、wait、冻结输入与排队事件。相同根/namespace/ToolCall 身份复用原委派，参数冲突拒绝，累计不超过两个。
- 子输入使用独立 knowledge 提示和同范围材料，只包含明确任务、冻结规则及策略/供应商身份；不复制父历史、页面提示、长期记忆或可变 RuntimeContext。子图不选择父固定项、不压缩或写回父摘要。
- 根线程 `chat-turn-{turn_id}`，子线程和逻辑 namespace 分别显式传入稳定 `agent-delegation-{execution_id}`；claim/attempt 不作为逻辑键。
- 根预算归属和实际执行身份分开。工具准入、字符提交、模型请求及结果提交验证子 claim/attempt、父子归属和根取消；父 WAITING_JOB 时合法子执行可提交，缺根子身份拒绝进入内存预算。
- 子请求逐条保留 execution_id/attempt/decision/retry 关系与 usage；未知用量保持 NULL。父再次消费报告经过完整输入准入及引用有效性复核。
- 父 interrupt 停驻后归还槽；持久对账绑定原 interrupt ID 恢复，不写 checkpoint。`next` 为空时仍先处理持久 interrupt，避免误判已完成图。
- STARTED 无可靠结果不自动重发。请求已 COMPLETED 但对应节点输出尚未保存时安全等待；已完成图则直接补提交业务结果，不调用模型。
- 不确定请求的等待快照包含稳定快照 ID、子 ID/尝试及请求 ID。决定按稳定 ID 和参数指纹幂等；旧快照/冲突拒绝。RETRY_DELEGATIONS 原子重排选中子 Job 并清理对应 wait 的旧结果/尝试缓存；ACCEPT_PARTIAL 收口未完成子执行，再唤醒父图汇总。原 RETRY_AFTER_FIX 不授权重发未知请求。
- 取消及根失败持久传播专属子执行；旧 claim、取消后输出/请求/终态事件不能提交。子 Job 成功、失败及定向收尾在改 Job 前也核对当前 claim。
- 成功/明确失败结果先提交，再按精确子线程清理；等待用户时保留。取消/接受部分结果后清理，启动补清；不按父或会话前缀删除兄弟图。
- 子状态沿现有 commentary 持久事件承载类型化 delegation 过程条目，保持根 seq/attempt/revision；未扩充原事件表 CHECK。快照、压缩、SSE、Zod、handler 和过程区贯通；子 token/done 不进入父正文。双语等待卡明确重试可能再次计费。

## 已执行验证

统一入口和日志根为仓库 `.pytest-tmp-runs/`，日志、临时数据库及截图不加入 Git。

| 范围 | 状态 | 证据 |
| --- | --- | --- |
| 相关后端 70 项 | PASS | `20261021T101842Z-36137572/backend`：委派初始 5 项和原 background/recovery/tool_budget/context_budget |
| 前端 51 项 | PASS | `20261021T102320Z-bf8e479d/frontend`：等待卡、SSE 契约、useChatTurns、消息列表 |
| 共享六次限额及新增子身份检查 | PASS | `20261021T102511Z-305d5565/backend`，6 项 |
| 五个持久化窗口及委派/预算/等待联合回归 | PASS | `20261021T110518Z-6d51266a/backend`，39 项；登记未停驻、子图完成未提交、结果提交未唤醒、请求完成未保存消息及供应商变化恢复；含连续两次结果不明与旧决定不能推进新等待 |
| 最终范围 lint/格式/前后端类型/生产构建 | PASS | `pwsh -NoProfile -File scripts/check-changed.ps1 -Base 43cce46bf31a1e8545f1e15caaa40f72a72d2841`，退出码 0；日志 `.tmp/check-changed-02-formatted.log`（前一次检查仅显式外键行的格式不合规，已用 Ruff 修正） |
| OpenAPI/api-types | PASS | `pnpm --filter @knowrealm/api-types check`；最终契约未增加新 HTTP 错误码 |
| 前端全量 | PASS | `20261021T103332Z-3a6e1464/frontend`，871 项；此后前端未再修改 |
| 后端全量复跑 | FAIL | `20261021T111001Z-6b7564e0/backend`，1464 通过、1 失败、7 warnings，2342.16 秒；命令 `uv run --frozen --directory backend python -m scripts.run_tests backend`。唯一失败为工具可见性旧预期遗漏新委派工具，未过滤；本轮第二 sidecar 目录锁测试通过，不表示其历史间歇超时已修复 |
| 工具可见性矩阵修正复测 | PASS | `20261021T114926Z-4dc9049a/backend`，1 项；六个有资料范围预期补入 `delegate_knowledge`，FREE 仍按原精确名单校验；保留顺序、联网开关和全部旧工具断言，Ruff 检查及格式通过 |
| 同项基点对照 | PASS | 独立 detached worktree `43cce46`、`uv sync --frozen --directory backend`、同一统一入口与 node ID；`20261021T115125Z-354edbac/backend`，1 通过、3 warnings，55.14 秒；日志/结果保存 `.tmp/baseline-matrix-02/`。这是新工具引入后的预期同步，不登记为历史失败 |
| 真实模型、真实 Tauri/WebView2、Windows 系统缩放 | NOT_RUN | 未使用模型替身或浏览器模拟代勾 |

模型替身只替换外部 LLM；公开 POST、实际 Middleware、迁移 SQLite、JobRunner 和 knowledge 图均真实执行。故障窗口额外停驻公开 checkpoint I/O，不直接写业务终态或伪造委派完成。

首次统一 `all` 的后端记录 `20261021T103332Z-3a6e1464/backend` 为 FAILED（退出码 4294967295），不是全量通过：旧 t16 约束夹具未显式列名，新增 wait 列后先抛 OperationalError，未释放网络闸门而挂起，已于 10:58:39 UTC 核对 PID 后主动终止本轮 pytest。已改显式列名，保留唯一约束断言；故障停驻点也已改为实际 interrupt 写入前并断言父状态。独立预算回归 `20261021T110329Z-52190da8` 为 24 通过、1 失败：取消观察器迁移到共享 runtime 后，测试仍修改旧常量路径；现已同步所有引用并保留可控轮询常量。修正后上表 39 项通过，最终后端全量另跑，未过滤失败项或扩大超时。

全量唯一失败是新工具引入后的测试预期未同步，不属于历史失败豁免；精确补齐预期后复测通过，生产代码未因此修改。修正后未再重复整套后端，不将 1464+1 与定向通过合写为一次“全量全绿”。全量启动时记录为 `b32c42a`+脏工作区，其后 `c5f7b3e` 固化了同一轮询/夹具及连续不确定测试修正；本轮剩余差异仅外键格式化、工具矩阵预期与文档，未借脏标记冒充不可变源码快照。

一次“子图完成、业务结果未提交”窗口的只读 SQLite 样本（`20261021T103217Z-24fd2077`）：根 `f783c0f8-9baa-45b3-b3dc-022014eb0e43`，子 `c69594a8-28ec-4b66-8ecc-37103cc2dc16`，Job `90d6035e-7633-442a-a6d2-10e7c833af8d`，子请求 `9935b8ab-2345-4203-ae1c-fe0cb27cf584`。子请求在 attempt 1 已 COMPLETED；恢复领取 attempt 2、claim `3b630fe4-ca96-4c85-b637-07feaac4ca47` 后只补业务结果，仍只有一个子模型请求。根/子总请求三条，usage_json 均 NULL；工具准入一条、wait 一条，原 interrupt `bd91220a2d9c2d52315424307948145e` 保留。此为隔离测试样本，不是用户真实模型账单。

## 双轴评审

按 code-review 技能对基点至 `0917e90` 并行只读审查，两轴分别保留结论，不将一种审查当作另一种通过。

### Standards

初审 3 项：父等待误取消子 Job、子取消收尾无界、旧 claim 可改新 Job。`af8d088` 修正后复查均关闭；补充复查发现新测试读取 resume 响应层级错误，已修为 `turn.status`，`c5f7b3e` 联合回归 39 项通过。最终未关闭发现 0 项。

### Spec

初审 3 项：已完成请求重发、旧 claim 收尾及缺根预算退化。`af8d088` 修正后复查均关闭；同样指出上述新测试响应层级错误，已修并验证。`b32c42a` 显式 ORM 外键无导入环，t16 显式列名无额外发现。最终未关闭发现 0 项。

两轴未代跑自动化或人工验收。之后全量发现的工具可见性旧预期只补入新增委派工具，保留 FREE 精确白名单及原顺序断言，不修改生产装配来迎合旧断言。

UI 沿现有语义令牌与 Button 原语。desktop-ui-mastery 小范围 lint 的 focus/hover 告警由共享 Button 的 focus-visible/hover 和过程行既有 Tailwind 焦点样式覆盖，不另复制样式；这不是浏览器或原生视觉验收证据。

## 人工复现与清理

1. 在隔离数据目录配置并同意真实模型外发，创建带少量事务隔离原文的课程，以 general 在课程范围要求先委派检索再汇总；记录根 turn/delegation/Job/request/claim 关联。
2. 观察 knowledge 排队、执行、完成；等待时向另一对话发消息，再返回原对话，核对状态及 seq、最终引用和正文。
3. 分别在等待时停止、真正退出进程后重启，核对取消不回活、已完成子图不再计费调用。
4. 对确实触发的结果不明请求分别重试/接受已有结果；记录等待快照、决定 ID、原/新请求和 usage 是否已知，验证旧决定不推进下一次等待。不确定窗口未触发时记 NOT_TRIGGERED。
5. 真实 Tauri 下分别检查亮暗主题、窄窗、字号和键盘；Windows 125%/150%/200% 作为独立真机验收。

工具矩阵修正提交 `b039cd6`；独立基点原路径为 `E:\workspace\project\my\KnowRealm-AI-baseline-delegation02-20261021`，未借用当前 `.venv` 或源码，未安装与该后端单项无关的前端依赖。对照后先复制测试日志/结果，再核对绝对路径及干净 Git 状态，移除本票 worktree；不清理其他历史 worktree 或用户数据。测试日志与临时资源均不 add/commit。
