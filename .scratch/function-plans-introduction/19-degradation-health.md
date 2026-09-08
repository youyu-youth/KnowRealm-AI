# 19 - 无 key 降级与健康面板

> Wave: B ｜ PRD: §4.1 服务与用量行 ｜ 决策引用: #38 #51
> 2026-09-08 收窄：降级机制已随 04/06/12 交付（见现状），本 plan 只剩设置页"服务与用量"分区；原"启动健康检查结果驱动入口可用性"作废（理由见"不做"）
> **Status:** done（代码 2026-09-08 交付，81ea2a3 + db5fd66；剩用户真机验收）

## 功能描述 / 目标

设置页"服务与用量"分区（#51）：健康检查（各外部服务 key 配置状态与连通性汇总）与近 30 天 token 用量展示——供应商 key 可缺省的可用性兜底由已交付的降级机制承担，降级不熔断（#38）。

## 现状（交付前基线，2026-09-08 核实）

- ASR 降级：缺 key / 离线 / 未同意外发时 ASR Job 保持 PENDING 并标 `waiting_reason`（ASR_KEY_REQUIRED / CONSENT_REQUIRED / OFFLINE），不消耗 attempts，条件补齐后无需重建 Record/Job 自动继续（`backend/app/modules/jobs/runner.py` WaitingClaim 分支；测试 `test_waiting_claim_marks_reason_without_consuming_attempts`）
- LLM 缺 key 入口降级（查询式，优于原"置灰"设计）：`has_api_key=false` 时总结 / 知识点 / chat 面板渲染 ProviderSetupGuide 配置引导；首启向导供应商步可跳过（#38）
- 用量埋点：**7 类** LLM 调用（总结 / 知识点 / 习题 / 评分 / Todo / 复习资料 / **chat 对话**）经 `write_llm_call_log` 写入 `llm_call_logs`（token_usage / model / latency / error_code）
- 连接测试端点：`/api/settings/providers/llm/tests`（真实最小结构化生成，计费）与腾讯 ASR 连接测试（GetAsrVocabList 只读列举）均已存在，且供应商卡上已有「测试连接」按钮（配好 key 后显示）

## 决策定稿（2026-09-08 grill）

1. **融合式面板**：不建独立健康分区；现有「供应商」分区改题「服务与用量」，两张卡头部加状态徽章（绿=已配置 / 红=缺 key + 一句补救提示），首启向导复用同卡同步获得提示
2. **连通性仅手动**：原「面板打开时自动调测试端点」作废——LLM 测试是真实计费生成，自动探测=意外扣费；卡上现有按钮即探测入口
3. **端点**：`GET /api/settings/usage/llm`，固定 30 天滚动窗口不做参数化；items 按 model 分组（调用数 / 输入 / 输出 / 总 tokens / 失败数），daily 按天序列服务端补零
4. **用量卡 = 趋势图 + 表格**：token/天单序列全模型合计（折线+面积，复用 BaseChart，tooltip 附当天调用次数），model 明细由表格承载
5. 事实修正：埋点是 7 类非 6 类（chat 也在 `llm_call_logs`），用量面板自然覆盖对话用量

## 功能范围（交付形态）

**做**（已交付）：
- 供应商卡状态徽章 + 缺 key 红色补救提示（LLM / 腾讯 ASR 各一）
- 新增 `GET /api/settings/usage/llm` 只读聚合端点（不新增统计表、无迁移）
- 用量卡：30 天趋势图 + 按 model 分组用量表（失败数标红）+ 空态

**不做**：
- 启动/打开期健康探测与结果缓存（查询式降级新鲜度天然正确；绿灯不保证 key 真实有效）
- token 熔断 / 配额限制（#38 明确不做）、计价金额展示、服务自动重连恢复 UI
- 降级机制本体（已实现，不重验不重构）

## 前置依赖

- 06（llm_call_logs 埋点、Provider 配置）、14（连接测试端点与供应商卡 UI 宿主）——均已交付

## 验收标准（出口线）

- [x] 健康面板显示各服务 key 配置状态，缺 key 标红并给出补救提示（卡头徽章 + 红色提示行）
- [x] 面板内可按需发起连接测试并显示结果（供应商卡既有「测试连接」按钮，复用现有测试端点，本票零改动）
- [x] 用量卡片显示近 30 天 token 用量与调用次数（按 model 分组，附每日趋势图与失败数）

## 实现备注（2026-09-08，agent 交付）

- 后端：`settings/usage.py` 单文件聚合（json_extract 取 token_usage 各口径 + COALESCE 0，失败行 token 计 0 但计入调用数与失败数；`ColumnElement[int]` cast 过 pyright strict）；按天口径与 today 趋势一致（UTC 日界、服务端补零 30 点）；测试 2 用例 + 全量 384 绿
- 前端：`ProvidersSection` 卡头徽章沿用既有状态标签 token（success-soft / danger）；新组件 `LlmUsageCard`（ECharts SVG 复用学习统计的 BaseChart + chartPalette，零新依赖）；MSW 默认 handlers 补空用量防全 App 测试误报
- i18n：分区标题「供应商」→「服务与用量」，补救文案不写死 DashScope（端点自选 OpenAI 兼容）；zh.json Edit 增量改
- 门禁：backend ruff/pyright/pytest 全量绿；desktop tsc/eslint/prettier 绿，相关测试 58（页面+onboarding）+27（settings 目录）全过

## 用户真机验收（用户执行，agent 不代勾）

- [ ] 清空 providers.json 后打开设置页：两张卡红徽章 + 补救提示正确；配好 key 保存后即时变绿
- [ ] 真实数据下用量卡趋势图与表格数值正确（可与 llm_call_logs 对照），失败调用标红
- [ ] 首启向导供应商步同卡显示徽章；「测试连接」两个端点真实可用
