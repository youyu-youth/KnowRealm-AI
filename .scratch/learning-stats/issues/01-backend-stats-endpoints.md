# 01 — 后端：学习统计聚合端点（七口径 + 趋势序列）

**What to build:** 本地 API 即可取到学习统计全貌——七项累计指标与 7/30 天学习时长趋势，数字与业务表实数一致、删除即回落。纯只读聚合（无新表、无迁移、无 Job），在 today 模块内实现；口径与契约以 `.scratch/learning-stats/spec.md` 实现决策节为准。

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `GET /api/today/stats` 返回七字段单对象：total_learning_ms / record_count / course_count / ai_summary_count / quiz_generated_count / quiz_answered_count / chat_turn_count
- [x] 口径命中（测试证明）：记录数含 FAILED / NOTE / 收件箱未归类；课程数含 ARCHIVED；AI 总结次数含重新生成版本（GENERATED / CONFIRMED / SUPERSEDED 全状态）；习题生成次数含 DRAFT / SUPERSEDED 历史批次；问答轮次 = role=USER 消息数
- [x] 一致性回落（测试证明）：删记录后其名下 AI 总结 / 习题指标同步回落且记录数 −1；删课程后全链回落；删聊天会话后问答轮次回落——record 域指标一律 JOIN records 软删过滤，子表自身 deleted_at 按 data-layer 规则同样过滤（ quizzes 的 discard 软删有真实写入者，双重过滤 = spec「软删过滤 + JOIN records」）
- [x] 重新生成总结后 ai_summary_count +1（#54 口径验收）
- [x] 模拟测试交卷不增加 quiz_answered_count（作答写在 quiz_test_items，不回写 quizzes）
- [x] `GET /api/today/stats/trend?days=7|30`：按捕获日聚合 duration_ms、软删过滤、空白天补 total_ms=0、日期连续无空洞；days 非 7/30 → 422；纯文档 / 粘贴 / 速记记录时长贡献 0
- [x] OpenAPI schema 落定并重生成 api-types（前端类型契约）
- [x] 测试并入 today 测试族既有缝（create_app + httpx ASGITransport + 真实迁移库，经真实端点造数，不断言 SQL 内部）；本机 pytest 带 `--basetemp=.pytest-tmp`；ruff / pyright 全绿

**实现备注（2026-09-07）：**

- 造数缝偏离说明：spec Testing Decisions 写「经真实 HTTP 端点造数」——端点可及处（建课 / 归档 / 软删记录 / 软删课程 / 建聊天会话 / 删聊天会话）全走端点；records / ai_summaries / quizzes / chat_messages / quiz_test_items 的写入因端点依赖 ASR / LLM 全链机器，沿用 today 测试族既有的裸 SQL 直插模式（与 test_quizzes / test_summary 等同族一致），断言仍全部落在 HTTP 响应上。
- days 白名单校验走业务 `HTTPException(422)`（`INVALID_TREND_DAYS`）：pydantic v2 的 `Literal[7, 30]` 对查询串不做 str→int 强转（实测 "7" 也 422），与 capture/text_capture 的业务 422 先例一致。
- 趋势捕获日 = `date(created_at)`（UTC 存储列上直接聚合），与 spec 契约字面一致；未做本地时区偏移（spec 未要求，属后续设计决策）。
- 验证：today 族 10 测试全绿；全量 pytest、ruff、pyright、openapi schema:check 全绿。
