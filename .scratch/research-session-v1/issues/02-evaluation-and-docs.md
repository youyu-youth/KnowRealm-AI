# 02 — 评测黄金集与文档收口

**What to build:** 研究会话 V1 的评测资产与权威文档收口：研究问题黄金集 + 四指标可复跑脚本（触发式回归：prompt 版本 / 模型变更时执行）、CONTEXT.md 术语修订、PROJECT_PROGRESS 回写、全量门禁复跑。本票不改运行时行为。

**Blocked by:** 01 — 研究会话全栈闭环

**Status:** ready-for-agent

- [ ] `docs/evaluation/` 新增研究会话黄金集（约 10 条研究问题，覆盖四类：跨来源比较 / 冲突识别 / 无证据拒答 / 范围隔离），含期望断言与语料依赖说明
- [ ] 四指标可复跑脚本：引用正确率、无证据拒答、范围隔离（不越 scope）、固定结构完整率；观测项不设门禁（工具调用次数、来源提案接受率）；沿用 `docs/evaluation/` 既有样本集与回归触发纪律
- [ ] CONTEXT.md：「会话范围」词条中「mode（交互形态轴，恒 ASK）」表述修订；新增「研究会话（Research Session）」词条（mode=RESEARCH 的证据综合型会话，五节结构，出口=入库提案+B6；不写实现细节）
- [ ] PROJECT_PROGRESS.md 回写：研究会话 V1 完结、§3/§5 同步、剩真机验收
- [ ] 本票真机验收清单单列（不代勾）
- [ ] 全量门禁复跑：后端 pytest + ruff + pyright、前端 vitest + lint + build、OpenAPI `--check`、zh/en 一致性防线
- [ ] `.scratch/research-session-v1/` 两张工单状态回写 done + 全勾，随 docs 提交
