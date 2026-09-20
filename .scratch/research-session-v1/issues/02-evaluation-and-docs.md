# 02 — 评测黄金集与文档收口

**What to build:** 研究会话 V1 的评测资产与权威文档收口：研究问题黄金集 + 四指标可复跑脚本（触发式回归：prompt 版本 / 模型变更时执行）、CONTEXT.md 术语修订、PROJECT_PROGRESS 回写、全量门禁复跑。本票不改运行时行为。

**Blocked by:** 01 — 研究会话全栈闭环（已完结）

**Status:** done

- [x] `docs/evaluation/` 新增研究会话黄金集（`research-session-golden-set.md`：10 条研究问题覆盖四类：跨来源比较 3 / 冲突识别 3 / 无证据拒答 2 / 范围隔离 2，含期望断言与语料依赖说明〔锚定 library-rag 检索评测语料或用户真机语料〕）
- [x] 四指标口径与门禁：引用正确率 ≥90%、无证据拒答 100%（红线）、范围隔离 100%（红线）、固定结构完整率 ≥90%；观测项不设门禁（工具调用次数、来源提案接受率）；回归触发=prompt 版本 / 模型变更
- [x] 可复跑脚本：`backend/scripts/score_research_structure.py`（固定结构完整率机械判定：五节标题逐字+顺序+无增删，输入=采集的回答文件，退出码随门禁阈值）；其余三指标需真实 LLM 回答，按黄金集 §3 rubric 人工评（沿用 quiz-groundedness「用户采集、不代标」纪律，非离线可自动化的部分不做假脚本）
- [x] CONTEXT.md：「会话范围」词条「mode（交互形态轴，恒 ASK）」修订为「现值 ASK 问答 / RESEARCH 研究」；新增「研究会话（Research Session）」词条（不写实现细节）
- [x] PROJECT_PROGRESS.md 回写：研究会话 V1 完结、§3 新行 / §5 序列同步、剩真机验收
- [x] 全量门禁复跑：后端 721 passed + ruff + pyright 全绿、前端批跑 89/89 稳定绿 + lint + build、OpenAPI `--check` 零 diff、zh/en 一致性防线过
- [x] `.scratch/research-session-v1/` 两张工单状态回写 done + 全勾，随 docs 提交

## 用户真机验收清单（不代勾）

- [ ] 按 `docs/evaluation/research-session-golden-set.md` §4 配置 provider（联网题需 Tavily key），10 题逐题建会话采集回答
- [ ] 运行 `uv run python -m scripts.score_research_structure <回答目录>`，固定结构完整率达门禁（≥90%）
- [ ] 按黄金集 §3 rubric 人工评引用正确率 / 无证据拒答 / 范围隔离三项，结果回写黄金集「复跑记录」表
- [ ] 首跑后复核四指标阈值是否合理（library 01 先例：实测后冻结）

## 实施备注

- 本票与工单 01 同窗口交付：01 的双轴 code-review 发现评测资产缺失（spec「随票前置」项），补齐过程中确认存在本票，遂按本票票面收尾。
- PROJECT_PROGRESS §3「研究会话 V1」行以工单 01/02 合并口径表述。
- 2026-09-20 用户发起双轴复审：8 项对照 HEAD 实物核验全落地，门禁复跑一致（后端 721 passed、ruff/pyright 绿、OpenAPI 契约逐字节零漂移）。修复：评分脚本 `startswith("##")` 误杀三级小节（改精确 `## ` 前缀）；CONTEXT「研究会话」词条收敛实现细节（去工具名/表名）；黄金集归属标注更正为本票。附带勘误 backend/AGENTS.md OpenAPI 命令相对路径（`../../`→`../`，原路径自 backend/ 执行指向仓库外）。
