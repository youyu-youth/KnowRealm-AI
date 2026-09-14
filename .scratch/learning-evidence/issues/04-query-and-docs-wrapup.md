# 04 — 只读查询 + 文档收尾

**What to build:** learning 域薄只读查询能力（未来学习上下文中间件与统计的共同底座），以及 A3 全部文档收尾——数据模型升版、交叉引用同步、进度回写。

**Blocked by:** 03 — 消费循环与证据映射。

**Status:** ready-for-agent

- [ ] 薄只读查询：按记录/课程取证据（服务级测试覆盖）；不建独立服务层抽象、不暴露 API 端点
- [ ] 数据模型升 v2.6 重命名：event_id 唯一约束的字段级收紧标注、§4.5 A3 已实施标注；全部交叉引用同步（PRD / 技术栈 / CONTEXT.md / 扩展文档头部，历史「变更记录」行是史实不改动）
- [ ] 扩展文档 §40.3 / §40.4 的 A3 行回写「已实施」
- [ ] PROJECT_PROGRESS.md 更新（§2 当前阶段、§5 待开发、最后更新行）
- [ ] 门禁：pytest（--basetemp=.pytest-tmp）、ruff、pyright strict 全绿；openapi 逐字零 diff
