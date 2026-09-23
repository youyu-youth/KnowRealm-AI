# 02 — 三档授权与自动执行

**What to build:** 上线「帮我批准」「完全访问」两档（默认档=请求批准零行为变更）。设置页新增「Agent 自动化」分区选全局默认档；会话内可临时切换（右栏开关，按会话内存，重启回落全局默认）；提交路径按档位确定性分流——默认档落提案（现状），自动档 L0/L1 校验通过即执行并给含授权依据的回执，L3 删除类在「帮我批准」下仍逐项确认、「完全访问」下自动执行；模式切换全程审计。用户可演示：切「帮我批准」→ 会话说建课 → 免确认直接创建＋回执标注档位与指令原文；切回默认档 → 一切回到确认卡流程。

**实施约束:** 实施决策见 [spec](../spec.md) 决策 9~11、23（Memory / 内容审核 / 外发任何档位不变；禁止项任何档位不暴露；每轮操作预算上限 5 不变、提案与直执行同计）。直执行回执的「历史已清理」降级占位随本票回执卡一并交付（数据源是 01 的 operation 查询）。

**Blocked by:** 01 执行事实地基与操作历史。

**Status:** done

- [x] 全局默认档：settings.json 偏离项（默认=请求批准不写键，learner_memory 外发开关先例）＋设置页「Agent 自动化」分区三选一（sections 新增 automation，RadioGroup 先例=偏好分区）
- [x] 会话档位：前端按会话内存（chatUiStore.authModeBySession，web_search 开关先例）＋聊天右栏授权模式开关（ChatAuthModeSection，先审计后生效）；消息请求携带会话档位覆盖（ChatMessageCreate.auth_mode，不带=全局默认）；重启应用回落全局默认（安全方向）
- [x] 模式切换审计 API（agent/auth_mode.py，落 agent 域根避开 runs 子包 AST 防线的 settings 领域禁令）：全局切换 PUT 自读 from＋先写审计行后改 settings.json（失败方向=档未变）＋写 agent_activity；会话切换 POST 仅写 agent_activity 204（from 由客户端上报会话生效档）；GET 当前档；01 的审计区（OperationHistorySection ActivityBlock）写入者落地自动接真、前端零改动
- [x] 运行时上下文新增授权档位字段（AgentRuntimeContext.auth_mode + instruction_excerpt + message_id；消息流入口 accept 解析：请求覆盖 ?? 全局默认）
- [x] 提交路径分流（执行端执法，提示词与工具描述不随档位改变——docstring 原样保留）：should_execute_directly 纯函数（REQUEST_APPROVAL 恒落提案；AUTO_APPROVE 仅 L1 直执行、L3 恒落提案；FULL_ACCESS 全直执行）；submit_operation_proposal 更名 submit_operation（预算执法前移同计）；档位对已注册的建课/加文本记录（L1）生效，后续票新动作按注册表 level 自动继承
- [x] 直执行（_execute_operation_directly）：单事务写 operation＋业务结果（transient AgentProposal 喂应用器，领域应用器零改动复用；回执经 authorization_json 记录档位、触发指令摘录（≤200 字）、消息引用与时间）；失败独立小事务落 FAILED＋稳定错误码（applier 编码异常透传 / 非编码异常 INTERNAL，_mark_failed 先例）；工具返回结构化回执载荷 {ok, executed}
- [x] L0 读取恒自动（search_courses 在 FULL_ACCESS 下行为不变断言）；Memory 写入在任何档位走原确认规则（propose_memory 落 PENDING 断言）；AI 总结/学习资产采纳/外发同意与档位无共享代码路径（各自独立门禁：外发开关＋llm_consent、总结工作台确认流），正交性由代码结构保证；禁止项任何档位不暴露（不在注册面，工具挂载矩阵不随档位变化）
- [x] done 载荷新增 executed_operations 键（零新 SSE 事件类型；graph 内部事件 ChatOperationExecutionEvent 解析，先例=操作提案事件）；前端直执行回执卡（ChatExecutedOperationCard：授权依据呈现〔档位/指令摘录/时间〕+ 失败原因 + 结果入口跳转 +「历史已清理」降级占位）＋断线/重启经 operation 查询恢复（list_operations 新增 session_id 过滤=json_extract 授权依据列投影）
- [x] 降档后后续动作重新按新档位检查授权（不沿用旧自动授权，跨轮 runtime 重建断言）；升档不自动执行积压提案（PUT 切 FULL_ACCESS 后 PENDING 提案不变断言）
- [x] 错误码登记核实：本票零新增（CHAT_SESSION_NOT_FOUND / OPERATION_PROPOSAL_LIMIT / INTERNAL / 领域错误码均既有且 zh/en 双语齐备，覆盖全部失败路径）；i18n 新键 zh/en 同步（设置分区/右栏开关/回执卡）
- [x] 门禁全套过（后端 pytest 798 绿 / ruff / pyright 0 错、前端 vitest 相关 50 绿+tsc+eslint+build、OpenAPI regenerate+check exit 0；全量 vitest 唯二失败=TodoPanel/KnowledgePointPanel 既有并发抖动，单跑 22/22 绿）

**实施备注（review 修复与边界）：**

- 双轴 review（Standards/Spec）后修复四项：全局切档 from 改后端自读（审计权威口径）；切档顺序改审计先行（失败=档未变，安全侧）；会话切档端点 204（消除 AgentAuthModeOut 语义误用）；回执卡授权档缺失回退默认档显示。
- 真机验收修复（1310a01）：会话切档端点改 204 后前端 `postSessionSwitch` 仍用 `apiFetch`（无条件 `.json()` 解析空 body 报 "Unexpected end of JSON input"），改用 `apiFetchNoContent`（chatSessions.delete 先例）；组件测试 mock 了 API 层故自动化未拦截，属 API 实现层笔误。
- GPT review P1 修复（bf17ac3）：流式生成中途降档不能约束本轮后续工具提交（档位随 runtime 在受理时固化，spec 用户故事 6 缺口）——会话切档端点审计落定后同步写进程内覆盖注册表（`agent/auth_mode.py`，sidecar 单进程先例），`submit_operation` 分流改读生效档＝覆盖档与本轮起点档取更严格者：**降档即时收紧本轮、升档自下一轮生效**（下一轮请求携带新档后两端一致；重启清空注册表＝回落全局默认安全方向）；直执行的 authorization_json 与回执载荷改记执行时实际生效档。断言：流中降档同 runtime 后续提交落提案、流中升档不放宽本轮、端点写注册表。
- GPT review P2 修复（迁移 0031）：「历史已清理」占位原依赖当轮内存态（turnExecuted），重启即消失、spec 用户故事 33 部分交付——改为 assistant 行持久锚点：`chat_messages` 新增 `executed_operations_json`（本轮直执行 operation_id 列表，ADD COLUMN 无重建），`ChatMessageOut.executed_operation_ids` 解析（坏值容忍）；回执卡改锚点驱动（锚点命中查询→回执；锚点在查询空→占位，跨重启成立），删除 turnExecuted 内存态与前端 done 载荷 executedOperations 解析（单一事实源，后端 done 键保留）；版本断言同步（test_library 31 / test_agent_runs 动态化）。门禁=后端 801 绿（唯一失败 library 抖动单跑绿）+ruff+pyright 0+OpenAPI regenerate、前端 tsc/eslint/build+回执卡 6 绿（全量并行失败均抖动单跑绿）。
- GPT review P2 三修（薄路由）：切档编排原在路由函数内（读档→审计事务→写 settings，违反 fastapi.md「路由薄层、事务与领域约束集中在 service」）且 settings 写失败会残留未生效审计——编排下沉为 `switch_global_auth_mode` / `record_session_switch_audit` service 函数（auth_mode.py 模块级，路由只调 service），settings 写失败**补偿删除刚写的审计行**（补偿再失败仅记日志＝残留行语义为一次未完成的切换）后整体抛错；`record_auth_mode_switch` 改返回落库行（补偿按 id 定位）。断言：注入 settings 写失败→500＋activity 空＋偏离键不变，故障消除重试正常。路由 docstring 变化同步 regenerate api-types。
- GPT review P2 续修（回执卡误报/漏显）：①查询加载中或失败原被当空结果→误报「历史已清理」（挂载闪占位、断网永久误报）——改 `!isSuccess` 不渲染（提案卡「失败即无卡」同模式）；②查询原默认 50 条、超出的旧回执漏显且误判清理——limit 按锚点数请求（clamp 50~200=后端契约 le），满页（可能截断）时缺席锚点不计占位（宁缺勿错报）、命中锚点照常渲染；锚点空跳过查询（enabled）。断言：失败不渲染、limit 透传（50/80/51 三档）、满页兜底不计占位。
- 「历史已清理」占位边界（已随 GPT review P2 修复消除，见末条）：占位跨重启成立。
- 「完全访问下 L3 直执行」真机演示暂不可行（本票无 L3 注册动作，03/04 票注册后自动继承分流矩阵）。
- 工作区中 OperationHistorySection.tsx / settings keys.ts / AGENTS.md 的未提交改动来自并行会话（01 遗留前端缓存修复），未纳入本票提交。
- 回执卡与提案卡的 fieldString / 跳转 Link JSX 同形（review 判断性提示）：03/04 新动作接入时随 CARD_BY_TYPE 配置表统一收敛，本票不预提取。

**用户真机验收（单列，不代勾）：**

- 真实模型三档走查：默认档确认卡流程与第一阶段一致；帮我批准建课免确认＋回执含档位与指令原文；完全访问下说「删掉这条记录」仍出确认（L3 在帮我批准）或直接执行（完全访问）。〔注：L3 动作随 03/04 票注册，本票真机走查以 L1 建课/加文本记录为准〕
- 会话内切档即时生效；重启应用后会话回落全局默认档；设置页改全局默认只影响新会话。
- 设置页操作历史可见模式切换审计行。
