"""对话式 Agent 域（ADR-0020）：AI 问答会话产品面（会话/消息/路由）与 deepagents
能力面（骨架装配/工具/中间件）同居一个 feature-first 模块。

能力落位规则（接入时才建目录，不留空壳）：
- 工具 → tools/（一工具一文件，按工具名命名）
- 中间件 → middleware/
- MCP / Skills / Memory / SubAgents → mcp/ / skills/ / memory/ / subagents/
- agent 变体多于一个图文件时，graph.py 升格为 graphs/<name>.py（open-swe 模式）。
"""
