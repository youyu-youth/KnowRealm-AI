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
- **双轴 code-review 修复**：i18n 键对齐（undo.applied→accepted）、_undo_reason 类型标注收紧、retry 并发兜底（不 500）、迁移 undo 收件箱分支补 job 守卫、直执行失败 attempts_json 补最终尝试、操作历史单步撤销按钮（工单「操作历史按钮」入口补全）。

**用户真机验收（单列，不代勾）：**

- 真实改名 → 撤销恢复旧名；撤销前再次手动改名 → 撤销被拒并说明版本冲突。
- 批量归类后整批撤销：按逆序恢复、操作历史逐项呈现补偿结果。
- 构造失败项（如目标课程被归档）→ 手动重试沿用原操作、成功后无重复副作用。
