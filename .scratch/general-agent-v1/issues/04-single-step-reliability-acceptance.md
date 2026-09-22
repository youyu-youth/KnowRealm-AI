# 04 — 单步可靠性综合验收与收口

**What to build:** 对 02/03 已交付的恢复、停止、错误与回执机制补齐故障场景测试与产品回归，确认"失败不谎报成功、停止后不新增动作、重启后可查明"；完成文档回写与真机验收清单（不代勾）。

**实施约束：** 不造轮子——优先复用 deepagents / langgraph / langchain 现成 API 与仓库已验证模式（`@tool`、`AgentConfig` 装配、`ProposalService`、领域 Service）；框架用法先经 `langchain-docs` / `langchain-reference` / `context7` 任一 MCP 或 `.agents/skills/` 相关 skills 查证（详见 spec Further Notes）。

**Blocked by:** 02 自然语言创建课程、03 向课程添加文本记录。

**Status:** done

- [x] 故障场景：确认请求超时后重查/重试不重复创建业务对象
- [x] 故障场景：用户停止生成后不再产生新提案；SSE 断开不影响已产生提案（保留待决）
- [x] 故障场景：后端异常时提案落 FAILED + 稳定错误码，回执不谎报成功（APPLIED / FAILED / Job 状态三态区分）
- [x] 重启恢复：PENDING 提案与 APPLIED+result 经持久化查询恢复视图，与界面展示一致
- [x] 产品回归：普通问答、研究提案、记忆提案、RAG 引用、总结审核保持原有约束零回归
- [x] 扩展性复核：公共执行流程无领域专属分支（静态检查 + 用例佐证）
- [x] 文档回写：PROJECT_PROGRESS（≤200 行）、开发计划状态、CONTEXT.md 补词条（动作/操作（Operation）/操作回执/对象查询工具族）
- [x] 真机验收清单单列（Tauri/WebView2 + 真实模型），不代勾
- [x] 门禁全套过（后端全量 pytest/ruff/pyright、前端 vitest/lint/build、OpenAPI --check 零 diff、api-types 同步）

## 实施备注

- **验收方式**：04 为验收收口票，先盘点 01~03 既有测试对各验收项的覆盖（幂等 409 / 并发双确认恰好一次 / 列表 session_id 过滤恢复 APPLIED+result / TEXT_RECORD_ADD 归档与不存在 FAILED / 前端 APPLIED-FAILED-REJECTED 恢复与总结三态 / useChatStream 三路径失效提案查询均已就位），只对真实缺口新增 4 个后端测试，其余以既有测试 + 全量回归佐证；零生产代码改动。
- **新增测试 1（超时重试，`test_agent_operations.py`）**：`test_text_record_add_failed_confirm_retry_applies_exactly_once`——确认落 FAILED（目标归档→422）→ 恢复目标 → 重试确认 APPLIED → 恰好一条记录（零重复创建）→ 终态再确认 409。「已 APPLIED 分支」由既有幂等 409 + 并发双确认测试覆盖，两分支合起来钉死「重查/重试不重复创建」。
- **新增测试 2（停止/断开，`test_chat_streaming.py`）**：`test_interrupted_stream_keeps_pending_operation_proposal`——create_course 工具执行后（收到 tool_result SSE 事件、提案已独立事务提交）`aclose()` 模拟断开/停止；断言 PENDING 提案保留、提案恒一条（无新提案）、确认前零课程、无 assistant 消息落库，且保留提案仍可经确认端点执行（APPLIED + 课程入口回执）。实证：提案写入与 SSE 流生命周期解耦（用户故事 13）。注意写操作工具不发 tool_call SSE 事件（提案经 done 载荷透传），事件序列为 status → tool_result。
- **新增测试 3（失败不谎报，`test_agent_operations.py`）**：`test_course_create_applier_failure_marks_failed_without_receipt`——monkeypatch `CourseService.create_core` 抛带码异常（注入码 TEST_COURSE_CREATE_FAILURE，仅测机制不入码表）：确认 422 + `params.errorCode`、提案 FAILED + error_code 持久化、**result_json 恒 NULL**（回执只在 APPLIED 时写入）、零课程。补齐操作注册表侧（scoped_applier 包装层）异常传播防线；自然失败路径（COURSE_NOT_FOUND/COURSE_ARCHIVED）03 已测。
- **新增测试 4（扩展性静态防线，`test_agent_operations.py`）**：`test_operations_common_flow_imports_no_domain_modules`——AST 解析公共执行流程三文件（`operations/registry.py`、`operations/__init__.py`、`library/proposals.py`），断言 import 的 `app.modules.*` 仅属 {agent, library}（领域接入只发生在动作模块应用器与提案枚举值）；用例佐证 = 03 接入时 registry/proposals 零改动 + 02/03 共用 `submit_operation_proposal` 的既有测试。
- **产品回归**：后端全量 pytest 764 passed + 1 环境抖动（test_server_process 真实进程 ASR 重启测试在全量并发下超时，单跑 14/14 全绿——本票零生产代码改动，判定与本票无关）；普通问答/研究提案/记忆提案/RAG 引用/总结审核既有测试全数通过=零回归。前端 vitest 全量两轮 532/534、531/534，失败文件轮换（第一轮 TodoPanel 等 2 个、第二轮 CourseBrain 三件套+KnowledgePointPanel 3 个）且失败文件批跑单跑 26/26 全绿——与 02/03 收官及 §7 记录的既有并发抖动口径一致（本票前端零改动）；「门禁全套过」按该既有口径认定。
- **文档回写**：CONTEXT.md 补四词条（动作〔Action〕/操作〔Operation〕/操作回执〔Operation Receipt〕/对象查询工具族〔Object Query Tools〕，插在「Agent 提案」之后并同步该词条枚举加操作提案）；开发计划文档头部状态行升「第一阶段（01~04）已完结」；PROJECT_PROGRESS 头部/§3/§5 同步（165 行 ≤200）。
- **门禁**：后端 pytest 全量 **764 passed**（+1 环境抖动单跑全绿，见产品回归行）+ ruff/format + pyright 0 错 + OpenAPI `--check` 零 diff；前端 vitest 全量（既有并发抖动口径见产品回归行）+ lint + build（内嵌 tsc）；api-types regenerate 零 diff（本票零 schema 变更）。
- **双轴 code-review**：Standards 零硬违规，采纳 1（AST 防线补相对导入盲区封堵——领域名集合改从 app/modules 目录动态枚举、首段判领域）；Spec 判定忠实（既有覆盖声明逐条核实属实），采纳 1（应用器失败测试补 422 断言对齐备注措辞）+ 前端门禁口径按实际两轮数字如实披露。备案：注入码 TEST_COURSE_CREATE_FAILURE（仅测机制不入码表）、f-string SQL 断言（文件既有风格三处先例）、开发计划文档 untracked 状态随本票入库（spec 定稿依据文档，f643366 仅入 .scratch 属遗漏）。

## 用户真机验收（Tauri/WebView2 + 真实模型，不代勾）

> 对照开发计划第七节门禁表（授权/目标/幂等/一致性/取消/产品回归/扩展性/兼容性）；在真机 `pnpm --filter @knowrealm/desktop tauri dev` 下执行。

- [ ] FREE 会话说「帮我创建一个 Python 入门课程」：Agent 只追问缺失必填（不重复问已有项）→ 确认卡完整参数预览 → 确认 → 回执卡可跳转课程页，课程列表真实出现
- [ ] 确认前刷新/重启应用：确认卡恢复待确认（不依赖 SSE）；未确认前任何路径都不产生课程
- [ ] 双击/快速重复点击确认：只创建一门课程，第二次确认前端不谎报（409 回查见 APPLIED 回执）
- [ ] 「向 Python 学习课程添加这条笔记：…」：同名课程列候选可选、找不到时明确告知不擅自新建；确认卡明示「保存后将尝试生成 AI 总结」；确认后记录出现在课程记录列表，回执按真实配置三态呈现（已提交生成中 / 未触发 / 失败可重试）
- [ ] 对已归档课程添加记录：确认失败、失败原因可读、无悬挂记录；恢复课程后重试按钮可成功
- [ ] 生成回答中途点「停止」：已产生的待确认操作卡保留可决定，Agent 不再产生新操作
- [ ] 确认请求发出后立即断网/杀进程再重启：提案状态（PENDING/APPLIED/FAILED/REJECTED）与界面一致，回执入口可跳转，不重复创建
- [ ] 界面语言切换 zh/en：确认卡、回执卡、失败原因文案跟随
- [ ] 产品回归抽查：普通问答、研究会话（五节结构+入库提案）、记忆提案、挂载会话 RAG 引用跳转正常
