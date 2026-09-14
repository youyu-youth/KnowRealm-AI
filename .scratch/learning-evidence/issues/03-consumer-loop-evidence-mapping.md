# 03 — 消费循环与证据映射

**What to build:** 独立后台消费循环把学习事件按确定性映射规则转换为学习证据落库——Event→Evidence 管道全线贯通。零 LLM、零前端、零新 API。

**Blocked by:** 01 — learning-evidence 地基 + 逐题作答事件首通；02 — 其余四挂点事件写入。

**Status:** done

- [x] 独立 asyncio 后台任务随应用 lifespan 启停（先例：JobRunner、RecordInvalidationNotifier 同类并存）；约 30s 周期扫描 + 启动即扫；不做写入时推送唤醒
- [x] 单调 id 水位扫描：`id > 水位` 逐条取、逐条转换、幂等 upsert（event_id 唯一约束兜底）；崩溃重启全量补扫天然去重；全程禁止 NOT EXISTS 相关子查询（O(N×M) 前科，ADR-0021）
- [x] 映射规则集中一处声明：QUIZ_ANSWERED（含测验键位）→ QUIZ（weight 0.9 / confidence 0.8，score/difficulty 透传）；SUMMARY_CONFIRMED → USER_CONFIRMATION（0.3/0.7）；KNOWLEDGE_CONFIRMED → USER_CONFIRMATION（0.4/0.7）；QUIZ_TEST_COMPLETED 不产证据（双计规避）；concept_id 与 source_anchor_id 本期恒 NULL
- [x] 失败语义：单条转换重试 3 次后跳过 + error 日志 + 内存计数告警；不建死信表、不阻塞水位
- [x] 「单轮执行」服务级测试接缝（唯一新接缝，不 monkeypatch 时钟）：映射表逐条、幂等重跑、全量重放重建（清空后重建一致）、失败 3 次跳过、水位推进、逐题/测验键位事件共存不串
- [x] 门禁：pytest（--basetemp=.pytest-tmp）、ruff、pyright strict 全绿；openapi 逐字零 diff

## 落地备注（2026-09-14，commit 19b76e4）

- **实现**：`backend/app/modules/learning/consumer.py` 新增 `EvidenceConsumer`（`EVIDENCE_MAPPINGS` 集中声明 + `run_once` 测试接缝 + `run` 30s 循环）与 `EvidenceMapping`；`main.py` lifespan 启动/停止接线（`app.state.evidence_consumer`）。透传 result/score/difficulty/metadata_json/occurred_at/course_id；未映射类型（含 QUIZ_TEST_COMPLETED、未来 TEACH_BACK 等）静默跳过、水位照常推进。
- **三处口径定稿**（审查确认，spec 字面的合理技术解释）：
  1. **水位键 = SQLite 隐式 `rowid`**：`learning_events.id` 是 uuid4 非单调，无法作水位；rowid 在追加型表上严格递增、走表 b-tree，即 ADR-0021「单调 id 走索引」的落地形态（consumer.py docstring 已声明）。**ADR-0021 补注转票 04 文档收尾一并落**。
  2. **幂等方式 = event_id 预查点查跳过**（与票 01 统一写入函数同款先例），非字面「撞唯一约束即忽略」；唯一约束仍是兜底（竞态撞上走 3 次重试后跳过自愈）。点查走唯一索引，不触犯禁 NOT EXISTS（该禁令针对 O(N×M) 扫描）。
  3. **「重试 3 次」= 共 3 次尝试**（`MAX_CONVERSION_ATTEMPTS=3`，测试断言 attempts==3）。
- **审查采纳小修**（已 amend 入 19b76e4）：main.py 停止顺序恢复严格逆序（consumer 先停）；lifespan 测试断言移入 with 块内并合并重复查询。
- **审查维持现状项**：EVIDENCE_* 两码为纯日志码，不录 HTTP 错误响应清单（先例 WORKER_INTERRUPTED 同）；run() 循环骨架与 JobRunner 同形系 ADR-0021 显式裁决的独立循环；测试失败注入用子类覆写 `_insert_evidence`（非 patch、不改生产接缝）；event_type 裸字符串与 events.py 现状一致（StrEnum 收敛为遗留小项，见票 02 备注）。
- **门禁**：pytest 444/444（新增 6 例：映射逐条/重扫去重/增量消费/全量重放/失败跳过/lifespan 接线）、ruff 全绿、pyright strict 0 错、openapi 逐字零 diff。
