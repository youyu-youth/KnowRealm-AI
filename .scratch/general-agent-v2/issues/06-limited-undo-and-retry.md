# 06 — 有限 Undo 与重试

**What to build:** 首批动作提供有限撤销（重命名、归类变更、归档 / 恢复、跨课迁移、条目软删——反向走既有回收站恢复链），撤销是新的受控补偿操作（undo_of 链、保留原执行历史），撤销前重验版本与依赖、不覆盖用户后续修改；批次撤销按依赖逆序补偿并保留逐项结果；记录软删、课程删除与课程级联删除不提供 Undo 并明确告知原因。重试分自动（瞬时故障原身份 ≤2 次）与手动（原身份 attempts 递增），失败项重试不重复成功部分。用户可演示：改名后点撤销 → 旧名恢复；期间又手动改过名 → 撤销明确拒绝并说明。

**实施约束:** 实施决策见 [spec](../spec.md) 决策 19~20（取消不冒充撤销；未知结果先对账——operation 行与业务写同事务即对账锚点；UI 显式动作＝用户授权直接建补偿 operation，经 Agent 的 undo 工具走三档）。

**Blocked by:** 03 修改与归档动作、04 删除与跨课迁移、05 批量计划卡与 Run 推进。

**Status:** done

- [x] operation 级 Undo：校验终态 SUCCEEDED、未被撤销、快照版本重验、领域恢复条件完整 → 创建补偿 operation（undo_of 关联）执行；跨课迁移 Undo＝反向迁移过全部校验；条目软删 Undo＝既有回收站恢复链
- [x] Undo 入口：回执卡 / 操作历史按钮（POST operations/{id}/undo，UI 显式动作即授权）＋Agent undo 工具（走三档授权）；撤销后原 operation 标记 undone_by、历史保留
- [x] run 级批次 Undo：按依赖逆序补偿、逐项结果如实呈现；单项补偿失败不谎报整体成功
- [x] 不可撤销动作（记录软删、课程软删、课程级联删除）明确原因呈现（可撤销性在注册项声明，工具结果与回执透出）
- [x] 自动重试：瞬时故障分类（如 SQLITE_BUSY / 临时 IO）原身份自动重试 ≤2 次，每次重验授权 / 版本 / 取消；参数 / 领域 / 版本 / 权限错误不自动重试
- [x] 手动重试：失败项重试端点沿用原 operation 身份（attempts 递增），用户明确要求重复执行才新建 operation；attempts_json 逐次尝试错误历史可查
- [x] 未知结果对账：operation 行与业务写同事务（崩溃＝未发生可安全重试、行在＝已执行）断言测试
- [x] 撤销与取消语义分离断言（取消停止后续、不补偿已完成）
- [x] 前端撤销 / 重试按钮状态（可撤销性、已撤销标记、重试中）＋zh/en 双语同步；新增错误码登记；api-types regenerate
- [x] 门禁全套过（后端 pytest / ruff / pyright、前端 vitest / lint / build、OpenAPI --check）

**实施备注（2026-09-28）：**

- **架构落点**：`OperationSpec` 声明式扩展 `undoer`（补偿器契约）/ `undo_reason`（不可撤销原因）；核心在 `runs/undo.py`（`execute_undo_core`＋`UndoService`＋`submit_undo`＋OP_UNDO 应用器）与 `runs/retry.py`（单步手动重试）。零迁移（undo_of/undone_by/attempts_json 列 0030 已就位，OP_UNDO 走 OP_ 通配）。
- **七动作 undoer**：update/archive/restore × course、library_item 两组（预期态比对 `assert_undo_state`＋恢复走领域核心）＋ move_record_course（反向迁移过全部校验；原课程为收件箱时补「无进行中任务」守卫后轻量恢复）。四不可撤销动作声明 undo_reason（记录软删 / 课程删除 / 创建类两动作）。
- **撤销前重验口径**：目标当前态必须等于原操作执行后的预期态（payload 变换应用到快照的推导，update_course 含 stage/depth 联动推导）；不匹配 → `OPERATION_UNDO_CONFLICT`（用户后续修改不被覆盖）。补偿行固化 undo 前快照（撤销补偿＝恢复到撤销前，天然 redo 语义）。
- **三入口**：POST operations/{id}/undo（单步，trigger=USER_UNDO）、POST runs/{id}/undo（批次，终态守卫＋依赖逆序＋逐项独立小事务＋RunUndoResultOut 如实呈现）、undo_operation 薄工具（按**原操作 level** 分流——默认档落 OP_UNDO 提案确认、自动档直执行回执；进 OPERATION_TOOL_NAMES 复用回执卡）。
- **自动重试**：`is_transient_exception`（registry）认 SQLITE_BUSY/锁竞争（SQLite 单写者下唯一现实瞬时形态；临时 IO 类错误多非瞬时，保守不识别——如需扩分类再补）；worker 每步 OperationalError 分支记账保持 PLANNED 交回循环（重试轮从头重检取消/授权/版本）、直执行 while 循环小睡重试；耗尽落 FAILED＋OPERATION_TRANSIENT_ERROR；非瞬时维持系统性故障上抛口径。
- **手动重试**：run 内沿用 05 票端点；新增 POST operations/{id}/retry 覆盖直执行失败单步行（快照重验＝operation_snapshot_stale 共享口径；失败记账 attempts_json 追加）。**直执行失败小事务补固化快照**（回滚后目标态＝初试前态，手动重试的重验基线；目标不可达时快照缺席由重验保守拒绝）——本票实施中补的产品缺口。
- **attempts_history 透出**：AgentOperationOut 新增 `attempts_history`（attempts_json 投影），操作历史与回执可查逐次尝试错误史。
- **裁决备案——条目软删 Undo 不可达**：spec 决策 19 列「条目软删（回收站恢复链）」，但条目软删未注册为 Agent 操作（工单 03 注册清单与 spec 决策 14 均无此动作，走 HTTP 页面路径），当前不存在可撤销的条目软删 operation 行；回收站恢复链（lifecycle.restore）持续可用。未来若注册 `soft_delete_library_item` 动作，其 undoer 即 `LibraryLifecycleService.restore`。
- **错误码 +6**：AGENT_OPERATION_NOT_FOUND / OPERATION_NOT_UNDOABLE / OPERATION_ALREADY_UNDONE / OPERATION_UNDO_CONFLICT / OPERATION_NOT_RETRYABLE / OPERATION_TRANSIENT_ERROR（zh/en＋清单登记；AGENT_RUN_NOT_FINISHED 描述补撤销语义）。prompt bump v17/v18（chat-library-scope-v17 / chat-research-scope-v18，CHAT_UNDO_GUIDANCE 入 context）。
- **测试**：`test_agent_undo_retry.py` 22 用例（undo 链/冲突/不可撤销原因/重复撤销/批次逆序与单项如实/收件箱守卫/Agent 工具三档/worker 与直执行自动重试/单步手动重试与快照失效守卫/取消不补偿/崩溃对账）；连坐更新 test_chat_streaming（工具面+prompt 断言）、test_research_session（prompt 版本）、ChatExecutedOperationCard.test（+2 前端用例）。
- **真机验收反馈补丁（同日）**：默认档（请求批准）确认路径的消息流回执行无撤销入口（按钮当时只在直执行回执卡与操作历史）——`ChatOperationProposalCard` 的 APPLIED 回执行补 `ProposalUndoEntry`（经会话 operations 查询按 `proposal_id` 关联定位 operation 行，成功且可撤销且未撤销 → 撤销按钮；已撤销 → 标记；与直执行回执卡共用 `agentKeys.sessionOperations` 查询键与撤销端点，零后端改动、零新文案键），测试 +2。
- **双轴 code-review 修复**：i18n 键对齐（undo.applied→accepted）、_undo_reason 类型标注收紧、retry 并发兜底（不 500）、迁移 undo 收件箱分支补 job 守卫、直执行失败 attempts_json 补最终尝试、操作历史单步撤销按钮（工单「操作历史按钮」入口补全）。
- **review P1 修复——失败回执锚点断链（同日）**：直执行失败虽落 FAILED operation 行，但三处叠加使回执卡重试按钮在真实流程恒不可达（原测试用人造锚点未覆盖闭环）——工具载荷 `{ok: False, executed: None}` 不携带 id、`_operation_execution_event` 只认 ok=True、assistant 行锚点仅从成功事件提取；操作历史亦无单步重试入口。修复：registry 三处失败分支载荷带 `operation_id`；graph 失败分支产 `{operation_id, failed, error}` 锚点事件（撤销工具失败不落行、无 id，天然不误锚）；操作历史行补重试按钮（FAILED 且 run_id 空，与后端 OPERATION_NOT_RETRYABLE 守卫同口径；复用 `chat.executedOperation.retry` 文案零新键）。测试：真实失败回执→id 与 FAILED 行一致→事件解析闭环（+1）、失败载荷事件契约（+1）、操作历史重试入口（前端 +1）。
- **review P2 修复×2（次日）——批次撤销失败留痕**：undo_run 单项补偿失败原先只写进 HTTP 响应（前端 onSuccess 仅失效查询丢弃载荷），事务整体回滚零持久化——刷新后原行仍 SUCCEEDED 无失败痕迹，违反「逐项结果如实呈现」。修复：except 分支独立小事务落 FAILED 补偿行（undo_of 挂原行、error_code 记原因、原行保持 SUCCEEDED 无 undone_by 可再撤销）；配套防误用守卫——RunControlService.retry_operation 拒绝 undo_of 非空行（重试会按其 payload 重放正向操作语义；PARTIAL_COMPLETED 任务可重开推进故路径真实）、任务面板补偿行不渲染重试按钮（后端同口径）。测试：如实呈现用例补持久化断言 + 重试守卫用例 + 前端 AgentRunProgress 新测试文件（补偿行无重试按钮/失败原因可见）。
- **review P2 修复——不可撤销原因未呈现（次日）**：后端 AgentOperationOut.undo_reason 零前端消费方，回执卡/操作历史/任务面板对不可撤销成功行只隐藏按钮（回执卡注释「原因在操作历史可见」系虚假声明），不符 spec 故事 28「明确告知原因，而不是默默失败」。修复：三处 UI 对 SUCCEEDED 且 !undoable 且未撤销且 undo_reason 非空的行就地呈现 `不可撤销：{reason}`（新键 chat.executedOperation.notUndoable zh/en）。测试：三个前端测试文件各 +1 用例。
- **review P1 修复——直执行自动重试未重验授权与版本（次日）**：授权在重试循环外固化、快照每轮重采但不与首试比对——锁竞争窗口内会话降档仍按原档执行、目标被手改仍被覆盖，违反 spec 决策 20「每次重验授权/版本/取消」（worker 路径经 _authorized/operation_snapshot_stale 每轮重检，直执行路径漏齐）。修复：重试轮（attempt>0）先重检 `effective_session_auth_mode` 会话覆盖档位（不满足直执行 → FAILED＋OPERATION_APPROVAL_REQUIRED，复用已登记码），快照采集后与首试基线（内存保留，回滚不吞）比对（偏离 → FAILED＋OPERATION_SNAPSHOT_STALE，版本冲突不自动重试）；首试采集前即遇锁（基线 None）不误判；取消属 run 概念，直执行无 run 不适用。原 docstring「每轮重走快照固化＝重验天然成立」系错误论证（重采≠重验），已更正。测试 +2：降档拦截（calls==1 不执行第二轮业务写）、目标漂移拦截（快照偏基线 → STALE）。
- **review P1 修复——交错手动重试重复执行业务（次日）**：retry_standalone_operation 预检（404/run 守卫/FAILED 态）与执行分属两事务，执行事务只重读不重查——两个交错重试都过预检后各执行一次业务（创建类无快照，stale 拦不住，同一 operation 建两门课）。修复：执行事务内条件 UPDATE 原子抢占（confirm 先例 rowcount 判定，仅 FAILED 得手；WAL 写锁串行化，输家条件在赢家提交态上重估）——输家如实返回当前投影（已成功＝既有结果），业务恰好一次。测试：确定性交错用例（A 持锁执行中 B 过预检到来）在未修复代码上实测失败（业务两次），修复后 calls==1、B 返 A 结果、attempts=2 原身份。
- **review P1 修复——Undo 版本重验缺失（次日）**：重验只有字段值比较（assert_undo_state），拦不住「改走又改回」——值复原但 updated_at 已变（用户已重新确认该值），恢复旧值仍是覆盖，违反 spec 决策 19「undo 前重验版本」。修复：执行后版本戳固化进 result（5 个 Result 模型 +after_updated_at，5 个 applier 带执行后 updated_at，覆盖 7 个可撤销动作，直执行/确认/run 三路径同源自动生效）；parse_undo_basis 三元组化（payload+snapshot+result）；新增 assert_undo_version 第二道重验（result 带戳且 ≠ 目标当前 updated_at → OPERATION_UNDO_CONFLICT；旧行无戳降级仅字段比较，产品未发布不回退既有可撤销性）。**tz 坑**：ISODateTime 存储往返读回 naive、内存值/JSON 解析值 tz-aware，直接 == 恒 False——比对前 UTC 归一化（实施中 9 个既有用例暴露）；另 result 序列化三处补 mode="json"（datetime 进 JSON 安全投影）。测试 +4：条目/课程/迁移三类「改走再改回」拒绝且不覆盖 + 降级路径放行。
- **review P2 修复——失败记账快照分叉（次日）**：四个失败记账分支仅 CodedHTTPException 带 _failure_snapshot——瞬时耗尽（OPERATION_TRANSIENT_ERROR）、INTERNAL、授权降档拦截三分支落 FAILED 时快照缺席，而 operation_snapshot_stale 对空快照保守失效（service.py:78 None→True）→ 锁故障耗尽后即使故障解除，修改类操作手动重试恒 OPERATION_SNAPSHOT_STALE 死循环、无法恢复。修复：四分支统一 snapshot_json=_failure_snapshot（重试轮版本重验通过＝目标未变，回滚后当前态＝初试前态＝正确执行基线）。测试 +1：锁耗尽→快照在场→故障解除→手动重试 SUCCEEDED（stash 反证未修复即失败）。
- **真机验收反馈补丁 2（次日）——提案确认回执行漏不可撤销原因**：用户在默认档确认「保存文本记录」提案后回执行上无撤销按钮也无原因。无按钮是设计行为（add_text_record_to_course＝创建类动作，注册项 undo_reason 明确不在首批撤销范围，spec 决策 19）；但「什么都不显示」违反 spec 故事 28——前轮 undo_reason 呈现修复漏了第四处 UI（提案确认路径 ProposalUndoEntry，!undoable 直接返回 null）。修复：该分支改为就地呈现 `不可撤销：{reason}`（复用 chat.executedOperation.notUndoable，与直执行回执卡/操作历史/任务面板同口径；undo_reason 缺省防御行仍不渲染）。测试 +1（创建类回执行：原因可见、无撤销按钮）。

**用户真机验收（单列，不代勾）：**

- 真实改名 → 撤销恢复旧名；撤销前再次手动改名 → 撤销被拒并说明版本冲突。
- 批量归类后整批撤销：按逆序恢复、操作历史逐项呈现补偿结果。
- 构造失败项（如目标课程被归档）→ 手动重试沿用原操作、成功后无重复副作用。
