# 工单 01 复盘建议实施

2026-10-12，基点 `ccd7e87`；仅仓库级文件。用户级 AGENTS、skills、配置和记忆未修改，`.claude/rules/` 未修改；根/后端 AGENTS 的导航增补已获 [精确 diff](agents-navigation-proposal.md) 批准并写入，前端 AGENTS 无新增。

## 落地

- `.gitignore` 中 `lib/` 改为 `/lib/`；既有 `apps/desktop/src/lib/utils.ts` 纳入 Git 索引，未改变函数行为。
- `.github/workflows/check.yml` 接入 Windows CI：只读权限、固定 Action 提交和工具版本、锁文件安装；快速检查与全量测试独立 job。原有 90k JSON/恢复/工具预算/错误登记回归为固定检查，无重复测试平台。全量失败不豁免、不整组跳过。
- `scripts/check-changed.ps1` 固定仓库根、校验基点、合并提交/暂存/工作区/未跟踪差异，保留中文/空格路径；无适用文件不调用检查器，删除项仍验证消费者类型，配置变更明确切换整个域；检查失败立即传播。`-ListOnly` 可先审查范围。前端 Prettier 兼容 CRLF/LF，不放宽其他格式规则。
- `scripts/test-check-changed.ps1` 使用独立 fixture 仓库和假退出码命令测试脚本，不修改真实源码或用户 Git 配置；自检 fixture 清理失败只报告残留，不覆盖原测试异常。
- `docs/agents/validation.md` 记录隔离基点、依赖/日志/退出码、真实装配验证入口及验收层级；`issue-tracker.md` 引用该入口，工单 01 单列真实模型/Tauri/系统缩放未验收项。
- 新检出复现 `unified` 11.0.0/11.0.5 类型冲突；按现有覆盖机制统一为已安装版本 11.0.5，锁文件只保留相关调整，未升级无关包或用类型断言绕过。

## 验证

- 检查脚本 **9 项自检通过**：空范围、暂存/未跟踪中文空格路径及明确参数、跨目录基点差异、无效基点、仅删除 TS、仅 API 类型变更、配置变更、仅删除 Python、原生命令失败传播。
- YAML 解析断言及官方 `actionlint` 检查通过；PowerShell AST 解析通过。
- 当前工作区按改动检查（修改依赖前）通过；依赖变更后的全量前端 lint 有 **2 个 Fast Refresh 警告**：`PlanDraftEditor.tsx:55`、`LearningPlanTab.tsx:760`。两文件 Git blob 与 HEAD 一致，未在本票修复或屏蔽。新增 utils 的范围检查通过。
- 使用 Git 索引导出全部源码到仓库同级 `KnowRealm-AI-validation-<GUID>`，独立 `pnpm install --frozen-lockfile --offline` 成功；没有复制旧 node_modules 或使用指向原工作区的 junction。统一依赖后 **两份 tsc＋生产 Vite 构建通过**（55.83s），保留既有路由测试文件/大 chunk 提示。
- 仓库内嵌套检出最初复测会向父目录解析旧依赖，结果不作为干净通过证据；最终采用上述同级隔离目录。
- 本机旧依赖布局在增量安装后缺少 pnpm 元数据已声明的 `unified@11.0.5` private hoist 链接，仍向旧平铺的 11.0.0 解析；冻结安装及 force 均未补齐。核对元数据和已安装目标后，仅修复该缺失依赖链接，不改用户级配置，也不把它作为项目源码；**当前工作区两份 tsc＋生产构建通过**（1m 3s）。干净安装验证不依赖这项本机修复。
- 完整 OpenAPI/TS 生成物 `@knowrealm/api-types check` 通过；既有大 JSON 两场景＋错误登记回归 **4 项通过**（真实 API/SQLite/Worker＋模型替身，独立 basetemp）。
- 最终同级隔离安装中的既有 `ChatMessageList.test.tsx` **19 项通过**（15.34s），验证依赖调整后的前端消费者。

远端 GitHub Actions 尚未运行，未推送代码或修改分支保护。本次不重复运行未修改业务的全量测试；CI 的全量 job 保留原始结果。真实模型、Tauri/WebView2 和 Windows 系统缩放未新增验收，继续沿 06 清单。

## AGENTS 已落实

仅两条条件导航：根 AGENTS 指向改动检查/基点验证文档和 CI；后端 AGENTS 指向真实 Agent 装配后的完整输入/恢复回归。用户已确认 Gate 2，按提案逐字写入；diff 与引用路径检查通过。

## 临时资源

本次两个源码导出目录的清理被自动审批策略拒绝，返回 `blocked by policy`，没有细分原因；没有换删除途径继续尝试。残留为仓库内 `.pytest-tmp-retro-checkout-c2282385-0418-47d8-b7da-3b4399ec6429` 和同级 `E:\workspace\project\my\KnowRealm-AI-validation-58d241ef-a846-4aed-b6c0-5764c88a2d75`。各自独立 node_modules；路径 marker 为 `.tmp-retro-checkout-path.txt`、`.tmp-retro-external-checkout-path.txt`，均不纳入提交。工作流校验工具位于 `.pytest-tmp-retro-tools`，自检曾因句柄占用保留 `.pytest-tmp-check-script-*` fixture 并输出具体路径，不把这些目录作为正式证据交付。

上一阶段已被拒绝清理的 `.scratch/agent-context/baseline/`、`evidence/` 原样保留，本次未移动、删除或纳入提交。
