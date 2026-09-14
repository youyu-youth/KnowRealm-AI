# 03 — 消费循环与证据映射

**What to build:** 独立后台消费循环把学习事件按确定性映射规则转换为学习证据落库——Event→Evidence 管道全线贯通。零 LLM、零前端、零新 API。

**Blocked by:** 01 — learning-evidence 地基 + 逐题作答事件首通；02 — 其余四挂点事件写入。

**Status:** ready-for-agent

- [ ] 独立 asyncio 后台任务随应用 lifespan 启停（先例：JobRunner、RecordInvalidationNotifier 同类并存）；约 30s 周期扫描 + 启动即扫；不做写入时推送唤醒
- [ ] 单调 id 水位扫描：`id > 水位` 逐条取、逐条转换、幂等 upsert（event_id 唯一约束兜底）；崩溃重启全量补扫天然去重；全程禁止 NOT EXISTS 相关子查询（O(N×M) 前科，ADR-0021）
- [ ] 映射规则集中一处声明：QUIZ_ANSWERED（含测验键位）→ QUIZ（weight 0.9 / confidence 0.8，score/difficulty 透传）；SUMMARY_CONFIRMED → USER_CONFIRMATION（0.3/0.7）；KNOWLEDGE_CONFIRMED → USER_CONFIRMATION（0.4/0.7）；QUIZ_TEST_COMPLETED 不产证据（双计规避）；concept_id 与 source_anchor_id 本期恒 NULL
- [ ] 失败语义：单条转换重试 3 次后跳过 + error 日志 + 内存计数告警；不建死信表、不阻塞水位
- [ ] 「单轮执行」服务级测试接缝（唯一新接缝，不 monkeypatch 时钟）：映射表逐条、幂等重跑、全量重放重建（清空后重建一致）、失败 3 次跳过、水位推进、逐题/测验键位事件共存不串
- [ ] 门禁：pytest（--basetemp=.pytest-tmp）、ruff、pyright strict 全绿；openapi 逐字零 diff
