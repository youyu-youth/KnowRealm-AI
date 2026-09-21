# 03 — 向课程添加文本记录（复用验证）

**What to build:** 学习者说"向 Python 学习课程添加这条记录"并给出文本，Agent 查找消歧课程后出确认卡（明示"保存后将尝试生成 AI 总结"），确认后记录保存并收到回执卡（记录入口 + 总结任务真实状态）。第二动作复用 02 公共机制，作为扩展性验收锚点。

**实施约束：** 不造轮子——优先复用 deepagents / langgraph / langchain 现成 API 与仓库已验证模式（`@tool`、`AgentConfig` 装配、`ProposalService`、领域 Service）；框架用法先经 `langchain-docs` / `langchain-reference` / `context7` 任一 MCP 或 `.agents/skills/` 相关 skills 查证（详见 spec Further Notes）。

**Blocked by:** 02 自然语言创建课程。

**Status:** ready-for-agent

- [ ] TEXT_RECORD_ADD 复用 02 的 operations 注册与提案链：公共流程零改动（仅注册新动作 + 新薄工具）——扩展性硬验收
- [ ] 文本捕获事务内核心抽取：Record(SUMMARY_PENDING) + Transcript + 搜索索引 + 资料库回填同事务；HTTP 与应用器共用，既有捕获路由测试零改动通过
- [ ] 总结 job 维持事务外 best-effort；result_json 回写 {record_id, summary_job_id | 提交失败错误码}
- [ ] 回执卡三态如实呈现：记录已保存 ≠ 总结已生成 ≠ 可检索；总结提交失败展示可重试入口指引
- [ ] 确认卡明示"保存后将尝试生成 AI 总结"；用户要求"只保存不总结"时如实告知当前不支持（不绕过、不谎称）
- [ ] 目标课程归档/不存在 → 提案 FAILED + 稳定错误码，零悬挂记录；执行前重新校验
- [ ] 正文超限（1 MiB）与空正文 → 稳定错误码，模型可转述；标题取首行 100 字对齐领域
- [ ] 幂等：确认重放不重复建记录；总结失败不重复建记录
- [ ] 写目标解析与会话范围解耦：FREE 会话可向消歧出的课程添加记录，资料读取范围不变
- [ ] zh/en 文案同步；新错误码登记；门禁全套过
