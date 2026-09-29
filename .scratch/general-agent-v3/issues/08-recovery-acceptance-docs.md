# 08 — 故障恢复验收与文档收口

**What to build:** 第三阶段收口：以故障注入与真实环境验证长任务可靠性，数据库结果、操作历史与界面展示三者一致；权威文档与数据模型同步实际状态，用户真机验收清单单列交付。

**Blocked by:** 07 — 多资料建课编排

**Status:** ready-for-agent

- [ ] 故障注入验收：第三篇资料失败不回滚课程与其余四篇、补偿保留逐项结果；失败步骤单独重试后批次收敛
- [ ] 重启对账验收：Tauri 重启（应用隐藏 sidecar 可继续；完全退出保存进度、下次启动恢复）后未完成 Run 自动续跑，已完成步骤不重做；不承诺退出期间继续执行
- [ ] 取消语义核验：取消后未提交步骤停止、已提交 job 保留回执、已建课程保留由用户处置、取消不冒充撤销
- [ ] 真实模型端到端任务：多资料建课＋计划生成全链一次跑通，数据库结果 / agent_operations 历史 / 界面展示一致
- [ ] 数据模型升版（提案经用户批准后执行）：0030~0035 迁移补登＋本期新表登记＋learning_goals 增 course_id 修正标注＋learning_agent_actions / learning_agent_feedback / teach_back_attempts deferred 登记与启用条件
- [ ] 权威文档回写：扩展文档、PRD、技术栈、CONTEXT.md 学习计划词条（目标 / 计划 / 计划项 / 共享引用术语）、PROJECT_PROGRESS（200 行内）
- [ ] 用户真机验收清单单列（不代勾）：M1 学习计划日常使用、共享引用场景、多资料建课长任务、重启恢复
- [ ] 门禁全绿：后端全量 pytest + ruff + pyright + OpenAPI --check、前端全量 vitest

参考：[spec.md](../spec.md) Testing Decisions 端到端段、Further Notes 搭车项。
