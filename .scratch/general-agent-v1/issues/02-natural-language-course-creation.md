# 02 — 自然语言创建课程（公共执行链随首个写动作落地）

**What to build:** 学习者说"帮我创建课程"，Agent 澄清缺失必填项（名称、学习场景、阶段/深度），齐全后出确认卡，用户确认后课程真实创建并收到可跳转的回执卡。底层落地最小公共执行机制：operations 注册表（动作标识 → 类型化 schema、级别、应用器、结果投影）+ 薄工具，课程创建为首个接入动作。

**实施约束：** 不造轮子——优先复用 deepagents / langgraph / langchain 现成 API 与仓库已验证模式（`@tool`、`AgentConfig` 装配、`ProposalService`、领域 Service）；框架用法先经 `langchain-docs` / `langchain-reference` / `context7` 任一 MCP 或 `.agents/skills/` 相关 skills 查证（详见 spec Further Notes）。

**Blocked by:** 01 页面上下文、统一运行时上下文与课程查询。

**Status:** ready-for-agent

- [ ] operations 子包：声明式注册表 + 公共提案入口；create_course 薄工具（docstring 面向模型、参数 schema 来自注册项）；无领域专属公共分支
- [ ] COURSE_CREATE 判别 payload schema（未知键拒绝）注册进既有提案判别校验表
- [ ] 课程创建事务内核心抽取：HTTP 路由与提案应用器共用，既有课程路由测试零改动通过（零行为漂移）
- [ ] 迁移 0028：agent_proposals 增加 result_json（可空）；全库 user_version 硬编码断言同步（先 grep 后改）
- [ ] 应用器：确认事务内创建课程 + 搜索索引 + APPLIED + result_json（课程 id）原子提交
- [ ] 幂等：APPLIED/REJECTED 终态双确认 409；未确认零创建；超时后查询可查明
- [ ] 缺必填时工具返回结构化缺失项说明（模型可转述追问）；用户要求"只保存不总结"类越界能力时如实告知不支持
- [ ] done 载荷新增 operation_proposals（零新 SSE 事件类型）
- [ ] 前端确认卡（完整参数预览，读提案 payload）+ 回执卡（APPLIED 后跳转课程入口）；断线/重启经既有提案查询恢复
- [ ] 每轮操作类提案上限 5 条，超限拒绝不截断
- [ ] 结果进提案输出契约（AgentProposalOut 扩展）；api-types regenerate；zh/en 文案同步；新错误码登记
- [ ] 门禁全套过（后端 pytest/ruff/pyright、前端 vitest/lint/build、OpenAPI --check）
