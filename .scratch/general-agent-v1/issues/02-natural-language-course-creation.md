# 02 — 自然语言创建课程（公共执行链随首个写动作落地）

**What to build:** 学习者说"帮我创建课程"，Agent 澄清缺失必填项（名称、学习场景、阶段/深度），齐全后出确认卡，用户确认后课程真实创建并收到可跳转的回执卡。底层落地最小公共执行机制：operations 注册表（动作标识 → 类型化 schema、级别、应用器、结果投影）+ 薄工具，课程创建为首个接入动作。

**实施约束：** 不造轮子——优先复用 deepagents / langgraph / langchain 现成 API 与仓库已验证模式（`@tool`、`AgentConfig` 装配、`ProposalService`、领域 Service）；框架用法先经 `langchain-docs` / `langchain-reference` / `context7` 任一 MCP 或 `.agents/skills/` 相关 skills 查证（详见 spec Further Notes）。

**Blocked by:** 01 页面上下文、统一运行时上下文与课程查询。

**Status:** done

- [x] operations 子包：声明式注册表 + 公共提案入口；create_course 薄工具（docstring 面向模型、参数 schema 来自注册项）；无领域专属公共分支
- [x] COURSE_CREATE 判别 payload schema（未知键拒绝）注册进既有提案判别校验表
- [x] 课程创建事务内核心抽取：HTTP 路由与提案应用器共用，既有课程路由测试零改动通过（零行为漂移）
- [x] 迁移 0028：agent_proposals 增加 result_json（可空）；全库 user_version 硬编码断言同步（先 grep 后改）
- [x] 应用器：确认事务内创建课程 + 搜索索引 + APPLIED + result_json（课程 id）原子提交
- [x] 幂等：APPLIED/REJECTED 终态双确认 409；未确认零创建；超时后查询可查明
- [x] 缺必填时工具返回结构化缺失项说明（模型可转述追问）；用户要求"只保存不总结"类越界能力时如实告知不支持
- [x] done 载荷新增 operation_proposals（零新 SSE 事件类型）
- [x] 前端确认卡（完整参数预览，读提案 payload）+ 回执卡（APPLIED 后跳转课程入口）；断线/重启经既有提案查询恢复
- [x] 每轮操作类提案上限 5 条，超限拒绝不截断
- [x] 结果进提案输出契约（AgentProposalOut 扩展）；api-types regenerate；zh/en 文案同步；新错误码登记
- [x] 门禁全套过（后端 pytest/ruff/pyright、前端 vitest/lint/build、OpenAPI --check）

## 实施备注

- **operations 子包**：`agent/operations/registry.py`（`OperationSpec`：action → proposal_type/level/payload_schema/result_schema/applier——级别 `OperationLevel`（L0~L3，设计-4 §6，第一阶段仅声明不接线）与类型化结果投影经 PEP 695 类型参数静态绑定应用器返回，`register_operation` 同步注册 payload schema 与投影适配器（按 result_schema 校验后转 dict）进提案框架 + 公共入口 `submit_operation_proposal`：schema 校验 → 每轮上限 → ProposalService.create）+ `operations/course_create.py`（`CourseCreatePayload` 继承 HTTP 创建契约 `CourseCreate` 仅收紧 extra=forbid 同源零漂移；`CourseCreateResult` 结果投影 `{course_id}`（spec 决策 8）；应用器经 `CourseService.create_core` 建课；导入即注册）。公共流程零领域专属分支，03 文本记录 = 新注册项 + 新薄工具。（02 review 修复：补全级别与类型化结果投影契约）
- **参数面同源**：薄工具参数 schema 由注册项 payload schema 经 `lenient_tool_args_schema` 派生（spec 决策 3「参数 schema 直接来自注册项」）：同组字段与类型、全部可选默认 None、保留字段描述、未知键拒绝；缺失项在**提案创建时**由注册项 schema 执法并结构化返回 `{ok:false, missing:[...], detail}`，模型转述追问，langchain schema 层不硬拦截（宽松派生对缺必填恒放行，决策 9 链路保留）。防线测试 `test_create_course_signature_matches_registered_payload_schema` 逐字段钉住字段集/类型/宽松可选性不变量。（02 review 修复：六参数手写签名改派生，测试从仅比字段名强化为逐字段断言）
- **迁移 0028**：agent_proposals 整表重建（CHECK 放开 `COURSE_CREATE` + 新增 `result_json` 可空列 + json_valid CHECK，0027 先例）；全库 user_version 断言已收敛 `supported_user_version()`（工单 C2），仅 test_library 两处字面量同步（28 + 快照名 f-string 化）。
- **提案框架扩展**（library 域最小改动）：`register_payload_schema`（library 不依赖 agent，操作类型反向注册，先例 register_applier）+ confirm 中应用器返回值（结果投影）同事务写 `result_json` + `AgentProposalOut.result` 输出。幂等沿用既有终态 409（APPLIED/REJECTED）。
- **事务核心**：`CourseService.create_core`（不开事务、调用方拥有）+ `create` 包 begin；既有课程路由 14 测试零改动通过（零漂移证明）。
- **挂载与事件**：create_course 进恒挂载段（spec 决策 12：FREE 可建课，范围只约束资料读取）；`ChatOperationProposalEvent`（`_operation_proposal_event` 收窄 {proposal_id, action, payload}）→ done 载荷 `operation_proposals`（零新 SSE 类型）；prompt bump `chat-library-scope-v10` / `chat-research-scope-v11`。
- **前端**：`ChatOperationProposalCard`（字段行预览复用 spaces.form/spaces.* 枚举翻译；APPLIED 回执态 `/spaces/$courseId` 跳转）；提案数据源收敛查询缓存（服务端唯一事实源，不复制进 Zustand；done 失效提案查询走 REST 重取）；zh/en 同步。
- **恢复链闭环（02 review 修复 P1，4bee33f + b28bb8d）**：列表端点加 `session_id` 过滤；确认卡查询改本会话全状态提案（`libraryKeys.sessionProposals` + `staleTime: 0` + 会话维度 key），APPLIED 回执课程入口（读 `result_json`）、FAILED 失败原因（`errors.{error_code}` 文案 + 原码兜底）与重试（后端 FAILED 可再确认）、REJECTED 终态文案均由服务端状态还原，不依赖组件内存；`useChatStream` 全部流结束路径（done / SSE error / 停止 / 断开）统一失效提案查询；确认失败 catch 后回查真相（超时已应用可见回执、落 FAILED 可重试）；新增 useChatStream 失效断言测试与卡片 APPLIED/FAILED/REJECTED 恢复用例。
- **错误码**：零新增 HTTP 错误码（复用 PROPOSAL_PAYLOAD_INVALID / PROPOSAL_ALREADY_DECIDED / PROPOSAL_APPLY_FAILED 等）；工具载荷内标识（OPERATION_PROPOSAL_LIMIT / AGENT_CONTEXT_UNBOUND）为模型转述用，对齐 RESEARCH_SOURCES_EMPTY 先例不入错误码清单。
- **门禁**：后端 pytest 全量 744 passed + ruff/format + pyright 0 错 + OpenAPI `--check` 零 diff；前端 vitest 全量 523+（1 失败为 CourseBrainMastery 全量并发既有抖动，单跑 8/8 绿）+ lint + build（内嵌 tsc）+ i18n 一致性防线 + 触及文件 Prettier；api-types regenerate。
- **双轴 code-review**：Standards 采纳 3（queryKey 收敛 `libraryKeys` 工厂+前缀失效〔连带修复 OrganizeDialog 等既有提案查询缓存失真〕、删 clear/restore_payload_schemas 死代码、`as` 断言补注释）+ Spec 采纳 1（同源防线测试）；备案不采纳 3：工具载荷标识入错误码清单（≠HTTP 错误码，先例一致）、快照断言回退字面量（f-string 与实现同源免每次迁移改测试）、两卡提取公共 hook（数据源不同：operation 卡=当轮+恢复查询合并）。
