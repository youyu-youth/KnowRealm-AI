# 04 — 单步可靠性综合验收与收口

**What to build:** 对 02/03 已交付的恢复、停止、错误与回执机制补齐故障场景测试与产品回归，确认"失败不谎报成功、停止后不新增动作、重启后可查明"；完成文档回写与真机验收清单（不代勾）。

**实施约束：** 不造轮子——优先复用 deepagents / langgraph / langchain 现成 API 与仓库已验证模式（`@tool`、`AgentConfig` 装配、`ProposalService`、领域 Service）；框架用法先经 `langchain-docs` / `langchain-reference` / `context7` 任一 MCP 或 `.agents/skills/` 相关 skills 查证（详见 spec Further Notes）。

**Blocked by:** 02 自然语言创建课程、03 向课程添加文本记录。

**Status:** ready-for-agent

- [ ] 故障场景：确认请求超时后重查/重试不重复创建业务对象
- [ ] 故障场景：用户停止生成后不再产生新提案；SSE 断开不影响已产生提案（保留待决）
- [ ] 故障场景：后端异常时提案落 FAILED + 稳定错误码，回执不谎报成功（APPLIED / FAILED / Job 状态三态区分）
- [ ] 重启恢复：PENDING 提案与 APPLIED+result 经持久化查询恢复视图，与界面展示一致
- [ ] 产品回归：普通问答、研究提案、记忆提案、RAG 引用、总结审核保持原有约束零回归
- [ ] 扩展性复核：公共执行流程无领域专属分支（静态检查 + 用例佐证）
- [ ] 文档回写：PROJECT_PROGRESS（≤200 行）、开发计划状态、CONTEXT.md 补词条（动作/操作（Operation）/操作回执/对象查询工具族）
- [ ] 真机验收清单单列（Tauri/WebView2 + 真实模型），不代勾
- [ ] 门禁全套过（后端全量 pytest/ruff/pyright、前端 vitest/lint/build、OpenAPI --check 零 diff、api-types 同步）
