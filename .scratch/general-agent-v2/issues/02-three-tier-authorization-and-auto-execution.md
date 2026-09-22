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
- 「历史已清理」占位边界：仅当轮会话内可判定（done 载荷内存态 vs 查询缺席）；跨重启后无消息级持久锚点、已清理回执不显示占位（卡片整体消失）。spec 用户故事 33 的完整跨重启占位需消息流持久化锚点，属后续票范围。
- 「完全访问下 L3 直执行」真机演示暂不可行（本票无 L3 注册动作，03/04 票注册后自动继承分流矩阵）。
- 工作区中 OperationHistorySection.tsx / settings keys.ts / AGENTS.md 的未提交改动来自并行会话（01 遗留前端缓存修复），未纳入本票提交。
- 回执卡与提案卡的 fieldString / 跳转 Link JSX 同形（review 判断性提示）：03/04 新动作接入时随 CARD_BY_TYPE 配置表统一收敛，本票不预提取。

**用户真机验收（单列，不代勾）：**

- 真实模型三档走查：默认档确认卡流程与第一阶段一致；帮我批准建课免确认＋回执含档位与指令原文；完全访问下说「删掉这条记录」仍出确认（L3 在帮我批准）或直接执行（完全访问）。〔注：L3 动作随 03/04 票注册，本票真机走查以 L1 建课/加文本记录为准〕
- 会话内切档即时生效；重启应用后会话回落全局默认档；设置页改全局默认只影响新会话。
- 设置页操作历史可见模式切换审计行。
