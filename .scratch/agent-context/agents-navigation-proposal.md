# 复盘后的 AGENTS 导航增补

2026-10-12：用户已批准建议方向及以下精确 diff，根和后端 AGENTS 已按此写入。仓库 `agents-md-maintainer` 的两个批准阶段均完成。前端 AGENTS、用户级文件及 `.claude/rules/` 均不在本次增补范围。

## 来源与去重

- NEW（证据 A/B）：用户要求落实复盘建议；实际 `scripts/check-changed.ps1`、`docs/agents/validation.md` 和 CI 提供统一入口。新增根目录条件导航，避免前后端重复命令及基点细则。
- NEW（证据 A/B）：`backend/app/modules/agent/graph.py` 真实装配会影响默认输入变换；既有 `test_context_budget.py` 的 90k JSON 用例验证最终模型输入。后端增加指向该验证入口的条件导航。
- DUPLICATE：根 AGENTS 的“异步功能与恢复验收”已区分自动化、替身、真实 API/SQLite/Worker、真实模型和 Tauri。保持原条目，具体填写方式落在验证文档及工单。
- NOISE：本次耗时、临时目录清理拒绝及单个测试失败，不写为 AGENTS 的长期规则；已在原实施记录或验证文档中按适用范围说明。
- 本次没有新增架构冲突；不处理既有 rules/子目录指导中的其他漂移。

## 精确 diff

根 `AGENTS.md`，“仓库布局与命令总览”现有并行会话条目之后：

```diff
 - 同仓多会话并行时：pytest 各自独立 basetemp（互踩会产生伪失败）、提交点名 add、git mv 后用 `--follow` 核对
+- 按改动检查或复现基点失败时，先读 `docs/agents/validation.md`；范围检查入口为 `scripts/check-changed.ps1`，CI 接线见 `.github/workflows/check.yml`。
```

后端 `backend/AGENTS.md`，编码规范正本说明之后、“常用命令”之前：

```diff
 > 编码规范正本是根目录 `.claude/rules/fastapi.md` 与 `data-layer.md`（自动加载，本文不重复）。本文件记录本目录的**命令、结构与已验证现状**；rules 中 LangGraph、sqlite-vec、pydantic-settings 等内容是目标态，按 function plan 推进，勿擅自补实现。

+- 改动 Agent 装配、模型 Middleware 顺序、默认摘要或文件卸载时，按 `../docs/agents/validation.md` 的“Agent 装配变更”验证真实装配后的输入及恢复边界，复用现有预算与恢复回归。
+
 ## 常用命令（backend/ 下执行，uv 管理）
```
