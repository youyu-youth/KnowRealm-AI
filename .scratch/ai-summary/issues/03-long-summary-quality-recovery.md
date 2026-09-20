# 03 — 长总结、质量样本与恢复边界

**What to build:** 超过 3 万字的 Transcript 可以完整经过递归 map-reduce 而不截断；单次调用超时、结构错误、课程归档和 Transcript 竞态都有稳定失败或取消语义，用户能手动恢复；项目同时留下可重复运行的 20 条匿名质量评审基线。

**Blocked by:** 02 — 调整、确认与跨重启 HITL

**Status:** deferred（2026-09-20 用户拍板：先不做，标记过期；票面 8 项 checklist 保持未实施原样，重新开工前需按当时依赖与现状复核票面）

- [ ] 3 万 Unicode code point 以内单次生成；超过阈值按段落顺序贪心分块，单个超长段落硬切，reduce 输入过长时递归归并。
- [ ] 自动测试证明每个输入片段都参与 map-reduce，边界 30000/30001、长段落和多层 reduce 均无静默截断。
- [ ] 每次 LLM 请求 90 秒超时；不自动重试或追加修复调用，初次失败与调整失败遵守不同 Record 语义。
- [ ] 手动重试复用失败 Summary Job 并重置该轮状态；确定性结构错误与可重试网络/超时错误提供稳定错误码和诚实操作。
- [ ] 每次外呼前和写回前校验课程 ACTIVE；归档或删除后取消任务，不保留迟到正文。
- [ ] llm_call_logs 记录 request、Graph/节点、模型、Prompt 版本、token、耗时和错误码；埋点失败不影响主流程，任何日志均不含 Prompt、Transcript、总结或密钥。
- [ ] 仓库包含 20 条匿名代表性 Transcript 与人工 checklist，覆盖不同学习场景和长文；显式 qwen-plus 评审命令与默认离线测试分离。
- [ ] 后端全量测试、ruff、pyright、OpenAPI 漂移检查，桌面端 test/lint/format/build，以及真实 sidecar HTTP 与浏览器明暗/响应式/focus/overflow 检查通过。
