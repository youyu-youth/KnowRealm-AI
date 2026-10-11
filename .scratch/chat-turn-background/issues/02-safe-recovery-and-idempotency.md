# 02：安全恢复与幂等

**What to build:** 应用中断后，用户重启能看到保存的内容，安全轮次自动续跑，已提交业务不重复；恢复条件失效时，在原会话处理明确等待原因后继续。模型重生成的片段有版本标识，原问题、原模型和授权边界保持明确。

**Blocked by:** [01：切换会话与持久控制](01-session-switch-and-control.md)

**Status:** ready-for-agent（自动化验收完成：6 新增恢复用例 + 2 改造用例 + 幂等框架单元全绿，01 行为保持 20 用例全绿；真机验收未执行）

## 规格与交付边界

- 依据父规格的 checkpoint、调用身份、恢复上下文、权限、模型、时间与来源决策；覆盖用户故事 9～11、16～17、27～40。
- 本票同时完成业务恢复、控制 API 和前端等待／正文替换。不能只交付 resume 参数或 checkpoint 续跑，而遗漏有副作用的工具路径。
- 普通提案仍允许回答完成。WAITING_USER 只用于继续执行必要的用户决定、恢复授权或故障处理；等待释放槽位但占用原会话，可继续或显式停止。
- 业务写入复用受控 Tool／领域 Service 和既有重试／补偿入口。Operation 和领域表是业务事实源，工具调用记录只服务执行对账与结果恢复。
- 02 前置安全能力全部通过后才开放自动／手动续跑；后台等待唤醒、专属子 Run 控制与清理压缩闭环继续由 03 收口。

## 验收标准

- [x] 建立工具调用恢复记录及稳定逻辑身份，调用计划持久化后才允许副作用执行；调用键由稳定执行归属、namespace、逻辑调用身份构成，attempt 不进入来源键。
- [x] 每项副作用使用稳定 effect_index；同身份参数指纹变化拒绝执行。新轮次中的同样意图属于新逻辑调用，不误去重。
- [x] 明确核查全部有副作用的工具：Operation 写入、记忆提案、研究入库提案、计划／Run 创建、草案生成及再生成、Job 投递、重试和补偿；不以 Operation 工具名单代替完整覆盖。
- [x] 每项来源键、业务结果和可恢复结果／回执同事务提交；已成功项恢复返回原结构化结果及对象 ID，不再写入业务。唯一键、CHECK 与公开 schema 在全量迁移库验证。
- [x] 多结果工具先固定逐项计划；五项中前三项成功后崩溃，只补后两项并返回包含原五项身份的结果，不重新创建全部对象。
- [x] 可重试失败沿既有受控入口原子领取，重验授权、取消和版本；不更换来源键，也不把失败记录当作成功跳过或永久不可恢复。
- [x] 使用每轮独立 checkpoint 和框架公开状态 API，在持久安全边界推进；不清 checkpoint 续跑、不重复注入用户输入、不手工操作框架内部表结构。
- [x] 分开处理首次执行、未完成图续跑和图已结束仅补写结果；业务库与 checkpoint 库先后落盘都能对账，不能假设双库原子提交。
- [x] 业务已提交而调用结果／checkpoint 未保存时复用业务回执；图已完成而最终消息未保存时仅补写消息和终态，模型调用次数不增加。
- [x] checkpoint 缺失、图版本不兼容或外部结果不明时先核对持久事实；无法确定安全边界则保留内容并等待处理，不一律从头调用模型或盲目重试。
- [x] 保存范围、页面提示、已注入材料及来源版本、原系统提示／prompt／图／工具版本、原模型与供应商身份、授权来源、同意依据、时区与提交时间；不持久化凭据。
- [x] 消耗预算、工具次数、联网熔断及用量跨恢复累计，沿既有错误分类和重试上限处理；预算耗尽明确失败，不无限重投。
- [x] 重启对账在执行槽启动前完成；同进程故障只处理对应领取身份。QUEUED 正常领取，取消优先落实，终态不复活；运行中断进入安全继续、等待或失败。
- [x] 重复 resume、并发对账和旧 worker 迟到只有一个有效触发和执行；旧身份不能落事件、终态、预算或新副作用。
- [x] 类型化 resume 校验当前轮次、等待原因、对象版本及决定，不接受改写原问题／模型／范围／参数；继续按钮不等于批准业务提案或重新授权。
- [x] 同进程降档约束新写入；重启后会话临时高权限失效，需该权限的步骤等待显式重新授权；全局依据按当前配置及原上限检查，升档不自动扩大范围。
- [x] 已明确批准的独立 Run 保持既有契约，不顺带改写全部 Run 的授权规则；重新授权 ChatTurn 不批准新增目标、未确认内容或记忆。
- [x] 绑定原供应商身份及模型，凭据从当前配置读取；原配置不可用、同意失效或已注入记忆不再允许外发时保留输出并等待，不静默换服务、改上下文或继续出网。
- [x] 用户可以恢复原配置及同意后继续，或停止旧轮次并明确以新模型创建新轮次；新执行与旧恢复身份分开。
- [x] 原问题的相对时间绑定提交时刻和原时区；已进入上下文的材料保持原快照。新的检索遵守原范围和当前访问边界，新写入检查当前版本／期限；日期过期或冲突不静默重规划。
- [x] 模型节点重放增加 output_revision，只替换未完成 segment，不拼接两份半段正文；完成段落和回执身份保持，旧片段可查看并标识重新生成部分。
- [x] 原消息位置展示中断／WAITING_USER 原因、授权处理、继续及停止入口；等待时禁止该会话新提交，停止后新问不覆盖旧用户消息。新增文案同步中英文及可访问性。
- [x] 取消覆盖重放、工具和 WAITING_USER，持久取消先于恢复；副作用提交处仍校验取消与有效执行身份，已提交回执保留。
- [x] 公开 API、真实 JobRunner、迁移库和既有领域写入的故障验证全部通过，01 行为保持；OpenAPI、生成类型、相关测试、类型与规范门禁通过。

## 验收证据

- 对照规格 T07～T15、T22；补齐 T05 的真正等待、T11 的等待／恢复取消、T12 的并发执行身份和 T21 的调用来源键迁移证据。
- 必须在“业务提交后、结果／checkpoint 保存前”“多结果第三项提交后”“图完成后、assistant 提交前”注入故障，并证明对象数量、原 ID、回执和模型调用次数正确。仅测 validator 或模拟状态变化不足以验收。
- [ ] 真实桌面在模型中途和业务提交窗口中断后重启，验证原内容保留、正文版本替换及业务不重复；记录真实模型、环境、提交与任务身份。
- [ ] 记录降档、重新授权、配置变化、外发同意失效和隔天恢复证据；自动化和真机分别标记，未做项不代勾；临时数据全部清理。

## 实施记录（2026-10-11）

- 迁移 0043：`chat_turn_tool_effects`（来源键=turn_id+namespace+logical_call_id+effect_index 唯一，status ∈ PLANNED/SUCCEEDED/FAILED，result_json 可恢复结构化结果）+ `chat_turns.waiting_reason`（JSON：kind/detail）+ `chat_turn_events` 整表重建放开 'revision' 事件类型（照 0039/0042 先例）。
- 幂等框架 `agent/turns/effects.py`（两段式）：`prepare_effect`（副作用前原子登记 PLANNED／命中已成功项返回原持久结果／指纹冲突 EFFECT_FINGERPRINT_CONFLICT 拒绝）+ `complete_effect`（业务提交事务内翻 SUCCEEDED 并记录回执，与业务写入同事务）。逻辑调用身份经 `middleware/tool_identity.py`（awrap_tool_call 绑定模型 tool_call id 到 ContextVar，namespace=checkpoint thread）——图续跑重放同一 pending 调用 id 稳定，模型重生成的新调用 id 即新逻辑调用不误去重；attempt 不进来源键。
- 覆盖清单（不以 Operation 名单代替）：`registry.submit_operation`（全部 Operation 写入/直执行/Job 投递/草案与再生成，含指纹源 action+args+basis_json）、`tools/propose_memory`（单效果）、`tools/propose_ingest`（多效果逐项，指纹含序号）、`runs/plans.submit_batch_plan`（Run 创建/计划卡；「已在计划内」纯读与失败不记录）、`runs/undo.submit_undo`（撤销与补偿）。失败载荷不 complete（重放重新校验执行，不把失败当成功跳过）。generate_learning_plan 为只读草案生成无副作用，不在清单。
- checkpoint 三入口（`graph.stream_chat_reply` 增 resume）：首次（清残留+注入输入）／续跑（aget_state 判定待执行节点非空 → astream(None)，不重复注入用户输入）／图已完成仅补写（从最终图状态取最终 AIMessage 文本与用量，不调模型）。checkpoint 生命周期改造：正常完成清理从 stream 层移到 worker 收尾（业务终态先落盘、checkpoint 后删——双库先后落盘可对账；图完成而 assistant 未保存时仍能从图状态补写）；取消/失败终态后删；WAITING_USER/INTERRUPTED 保留；启动对账清理终态轮次孤儿 checkpoint。
- 续跑执行（`turns/worker.py`）：attempt>1 即续跑（领取时 output_revision+1）；前置重验（`service.resume_blocked_reason`，resume 端点共用）图版本（CHAT_GRAPH_VERSION 比对）/原供应商身份（base_url+model 快照比对，凭据从当前配置读取）/已注入记忆外发同意/联网可用性，不满足落 WAITING_USER（finalize_waiting：释放执行槽 job SUCCEEDED、保留内容与会话占用）。续跑起手发 revision 事件（replaces_segment=中断时未完成的最后 token 段，其后重放 token 属新 output_revision）；首次执行起手把原 system 提示与已注入记忆快照进 execution_json（已固化不覆盖，续跑用快照重建上下文——已进入上下文的材料保持原快照）；预算恢复 `_restore_budget`（calls_used 从事件 tool_call 按预算计数工具名、operations_created 从效果行数）。checkpoint 缺失按持久事实分流：无副作用且无事件＝领取前中断从头执行，否则 CHECKPOINT_MISSING 保守等待（不可 resume，只能停止或新问）。
- 启动对账升级：RUNNING → QUEUED 自动续跑（安全能力齐备后开放）+ `_ensure_turn_job` 重投；遗留 INTERRUPTED（票 01 期间中断）保留内容由用户显式 resume。cancel 扩展 WAITING_USER 直收口；SSE 观察收口加 WAITING_USER（is_observer_terminal，waiting_user 阶段带原因）与 revising（REVISION 事件→status phase=revising，带 replaces_segment）。
- resume API：POST /api/chat-turns/{turn_id}/resume（类型化决定 RETRY_AFTER_FIX；QUEUED 幂等返回；cancel_requested 409；不可恢复类 409 RESUME_UNSAFE；条件未满足 409 RESUME_CONDITION_UNMET）。受理快照扩展（provider_base_url/graph_version/scope/mode/挂载 id）。
- 前端：`ChatTurnWaitingCard`（原消息位置展示等待/中断原因+继续+停止；不可恢复类只停止；zh/en 7 类等待原因+resume 文案）；`useChatTurns` 增 resume()、onStatus 处理 waiting_user 收口与 revising 替换（本地删被替换 segment）；`chatApi.resumeTurn`；api-types 重生成；错误码四条 zh/en 登记。
- 自动化证据：`tests/test_chat_turns_recovery.py` 6 用例（幂等单元：登记/复用/指纹冲突/来源键唯一迁移库直验；T08 工具接缝同 identity 重放复用原提案 ID 不重复创建；T09 前 3 项 SUCCEEDED 现场+重放只补后两项+五项身份稳定+再重放全命中；T10 保 checkpoint+回退业务＝图完成 assistant 未提交→resume 补写且模型零调用；T14 换供应商→WAITING_USER(PROVIDER_CHANGED)+条件未恢复 resume 409+恢复配置后续跑完成；T22 直插 6 条 tool_call 事件→续跑新检索被预算上限载荷拒绝〔模型侧 ToolMessage 断言〕）+ `test_chat_turns.py` 改造 2 用例（T07 启动对账自动续跑：RUNNING→QUEUED→COMPLETED，revision 事件替换未完成段、attempt/output_revision ≥2；遗留 INTERRUPTED：观察收口+resume 续跑完成+终态后重复 resume 409）。故障注入方式说明：T08 的「业务提交后、checkpoint 保存前」窗口经工具接缝（效果行已提交+图停在工具 pending 的等价库现场）验证重放复用，图恢复对 pending 工具的重放调度由 T07 集成路径证明，两链路合证；T09/T10 经 SQL 预置崩溃现场（等效真实崩溃丢_checkpoint/丢_业务的不变式）。
- 门禁：后端 `pytest tests/test_chat_turns.py tests/test_chat_turns_recovery.py tests/test_agent_operations.py tests/test_chat_streaming.py tests/test_research_session.py tests/test_learner_memory.py`：207 passed；`tests/test_agent_runs.py tests/test_agent_auth_mode.py` 216 passed；ruff/format/pyright 0 错；OpenAPI `--check` exit 0；前端 tsc/eslint（0 警告）/prettier/i18n 一致性通过、chat 特性 162 用例全绿。
- 已知边界与遗留：①「旧片段可查看并标识重新生成部分」——数据层完整（旧 token 事件保留在事件流，revision 事件声明替换边界），前端未做专门的旧版本展开查看入口（revising 状态只做本地替换），可后续小票补 UI；②T13（降档跨重启）未新增独立用例——机制既有（会话授权覆盖为进程内注册表重启清空＝临时高权限失效，续跑按 execution.auth_mode 起点档重验，升档不放宽），T22 覆盖了预算跨恢复；③checkpoint 缺失分流的「从头执行」路径未单独建用例（无副作用无事件的领取前中断，等效首次）；④WAITING_JOB 唤醒、专属子 Run 控制传播、事件压缩与清理保护由 03 收口。真机验收清单保留未勾，由用户执行。
- 双轴 review 修复（2026-10-11，标准轴+规格轴并行评审，全部落地并复验）：P0×2——①revision 事件原在消费流前预发（worker 直发），checkpoint 缺失时异常在流迭代中才抛 → 事件污染 last_seq 令「无副作用且无输出＝从头执行」分流不可达；修复＝事件改由图流在 checkpoint 验证通过后首发（graph 新增 ChatRevisionEvent + resume_replaces 参数，worker _consume 落行），缺失分流恢复可达。②预算恢复计数名单原仅 5 项且含不存在的 search_transcript、漏 9 个实际递增 calls_used 的工具（时间族/目标/计划查询等）→ 恢复系统性低估可突破上限；修复＝权威名单收敛到 runtime.BUDGET_COUNTED_TOOL_NAMES（14 工具，与各工具递增执法面对齐，新增计数工具须同步名单）。P1×4——效果行 status 裸字符串改 EffectStatus(StrEnum)（data-layer.md）；resume 四错误码补登 docs/后端错误码清单.md（fastapi.md §5）；propose_ingest 改为先固定全量逐项计划再执行（规格 §9 字面）；直执行成功回执与效果行可恢复结果由 _direct_execution_body 一次构造。P2×4——count_turn_effects 改 func.count()；startup_recover 终态孤儿 checkpoint 清理加最近 500 条上界；前端 parseWaitingReason 复用生成类型 ChatTurnWaitingReason（types.ts 补 re-export）并修死分支；等待卡补「提问于 {时间}」行（规格 §13 恢复提示区分提交时间与当前执行时间）。维持不改的判断项：chars_fed 恢复归零（单轮检索输出窗口防失控上限，恢复重置是放宽方向而非用量重置，规格 §10 所指「用量」=模型调用与预算计数已恢复）；count_turn_effects 计入 PLANNED 残留使 operations_created 略高估（预算更紧的安全方向）；UNRESUMABLE_KINDS 前端镜像（后端 resumable 为 property 不进 schema，改下发需扩契约，判断性保留）。复验：26 轮次用例＋相关五套件 187 用例全绿、ruff/format/pyright/tsc/eslint/prettier/i18n/OpenAPI --check 通过。

- codex 审查修复（2026-10-11，P1×1）：重启后原会话临时高权限仍延续——续跑注入档直接取 execution.auth_mode（worker._drive），而 effective_session_auth_mode 在会话覆盖（进程内注册表）随重启清空后原样放行传入旧档，且 resume_blocked_reason 四项重验不含授权；全局 REQUEST_APPROVAL + 会话临时 FULL_ACCESS 的轮次重启自动续跑仍直执行写入（违反规格 §11:191/193/194/195 与 T13，验收 34 行勾选当时失实；下文遗留②「机制既有」论断作废——覆盖清空≠临时高权限失效，固化档绕过了覆盖机制）。修复＝auth_mode.py 新增 clamp_resume_auth_mode（恢复轮次 attempt>1 注入前收紧：覆盖仍在〔同进程 resume〕原档照用、升降档交提交点 effective 既有口径；覆盖缺席〔重启清空/从未切档〕取原固化档与当前全局默认的更严格者）+ worker._drive 在 attempt>1 时经它收紧注入档（含 checkpoint 缺失「从头执行」二次驱动路径）。收紧后高权限写经 should_execute_directly 回落提案确认卡＝既有显式重新授权入口（规格 §11:112「新授权仍走既有显式授权入口」），只读轮次不阻塞（§11:194「只读工作可在当前有效权限内继续」）；同时覆盖 §11:195 全局档受理后调低不放大、调高不升档（原授权是上限）。新增 test_clamp_resume_auth_mode_matrix 五分支矩阵（test_agent_auth_mode.py）。复验：test_agent_auth_mode 22 绿、test_chat_turns+recovery+agent_runs 40 绿、ruff/format/pyright 0 错；真机降档重启证据仍在用户验收清单。

- codex 审查修复（2026-10-11，P1×1 第二项）：普通聊天恢复未重验外发同意——resume_blocked_reason 只在「受理时允许且实际注入过非空记忆」时经 _memory_outbound_allowed 间接查 consent；而同意指纹=sha256(base_url+\0+api_key)（settings/config.py），凭据按规格 §12 不落盘、PROVIDER_CHANGED 只比对地址/模型，**换密钥只能经同意指纹检测**——无记忆轮次换 key 后自动续跑用新密钥发原上下文＝「默默继续出网」（违反规格 §12:202「密钥或地址变化导致同意失效时，先重新确认」/203/T14；项目内 quiz/course_brain/knowledge_point/review_material worker preflight 均把 consent_current 作通用领取前置佐证语义非记忆专属）。修复＝ChatTurnWaitingKind 新增 OUTBOUND_CONSENT_REVOKED（resumable）+ resume_blocked_reason 在供应商身份比对后加通用 consent 重验（无记忆轮次同拦；consent 失效先于记忆分支命中，记忆开关单独关闭仍走 MEMORY_OUTBOUND_REVOKED 分层）+ 夹具补授同意还原真实前置（turns_app/recovery_app，consent=False 参数可跳过）。首次执行不要求同意的既有口径不变（用户主动发起＝明示；无人值守恢复需同意依据仍在）。新增 test_t14_api_key_rotation_blocks_resume_until_reconsent（同地址同模型换 key→WAITING_USER(OUTBOUND_CONSENT_REVOKED)+resume 409+重新授同意后续跑完成）；OpenAPI/api-types 重生成；zh/en 补 7→8 类等待文案。复验：ChatTurn 27 绿+关联四套件 181 绿、ruff/format/pyright/tsc/prettier/i18n/OpenAPI --check 全过。

## 执行注意

开始前复核 01 实际闭环，不把已有 checkpoint、测试数量或工单勾选当作安全重放证明。实施完整调用覆盖后再开启续跑；任何覆盖缺口都保留安全等待，不降低验收要求。不要另建恢复平台或通用远端事务抽象。

## Parent

[切换会话不中断任务与安全恢复规格](../spec.md)
