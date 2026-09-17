# 03 — 从 Mastery 下钻到每条 Quiz Evidence

**What to build:** 学习者打开某个 Concept 的 Mastery 详情时，可以看到当前算法实际采用的普通 Quiz 与模拟测试逐题 Evidence、得分、发生时间和来源，并跳回相应学习资产；无效、已删除或不参与当前窗口的证据不会冒充计算依据。

**Blocked by:** 02 — 让 Concept 作答形成可见的真实 Mastery.

**Status:** done

- [x] Concept Mastery 只读详情返回快照、状态、Confidence 分档以及当前算法版本实际采用的有效 Evidence。
- [x] Evidence 按发生时间倒序，区分普通 Quiz 与模拟测试逐题来源，并提供前端可消费的业务定位信息。
- [x] 关联软删除 Record、课程不匹配、无主概念、非 Quiz 类型或落在最近 12 条窗口之外的 Evidence 不出现在“参与计算”列表。
- [x] Concept 已确认但尚无快照时返回 `NOT_ENOUGH_DATA` 空详情，不伪装成 404 或 0%。
- [x] Knowledge GPS 的 Concept 行可打开详情；详情展示分数、Confidence、Evidence 数量、最近验证时间和 Evidence 列表。
- [x] 学习者可从 Evidence 跳转到对应普通 Quiz 或模拟测试结果；定位能力不足时保留来源说明和时间，不生成假链接。
- [x] 已删除来源有明确降级语义，历史事实不被删除或改写，但不参与当前 Mastery。
- [x] 中文与英文文案、键盘焦点、Dialog/Sheet 滚动边界和空态符合现有桌面组件规范。
- [x] API 测试覆盖来源类型、排序、窗口截断、删除过滤、跨课程防护和空详情；前端测试通过用户点击完成详情与跳转闭环。

## 实施备注

- **修复票 02 遗留缺陷**：有效集合查询原为 inner join `records`，而模拟测试逐题事件无 `record_id`，其证据被整体误排除、永不参与 Mastery。已改 LEFT JOIN + `deleted_at IS NULL`（`service._load_effective_evidence_rows`），重算与详情共用同一过滤；`test_concept_mastery_detail_returns_snapshot_and_evidence_sources` 锁定该行为。
- 详情端点为 `GET /api/courses/{course_id}/mastery/concepts/{concept_id}`，响应 = `snapshot`（与课程列表同口径复用 `_concept_mastery_out`）+ `algorithm_version` + `evidences`；窗口选择复用算法纯函数 `mastery.window_evidence`，列表与快照永远同口径。
- 两类作答事件的 `source_type` 均为 `QUIZ_QUESTION`，来源区分依据 Event 固化的 `metadata_json.test_id`：有 `test_id` 判为模拟测试逐题（携带 `sequence_no`），否则按宿主 Record 定位（`record_id` + 标题 + `quiz_id`）；`source=null` 时前端只展示时间，不生成假链接。
- 跳转：普通 Quiz → `/records/{record_id}?tab=quiz`；模拟测试 → `/spaces/{course_id}/tests/{test_id}`；前端 `ConceptMasteryDetailDialog` 从 GPS 列表行打开，滚动边界 `max-h` 限制。
- 错误码清单：`COURSE_NOT_FOUND` 适用域补登 `learning`（补票 02 遗漏）；`COURSE_BRAIN_CONCEPT_NOT_FOUND` 适用域补登 `learning`（跨模块复用同一「概念不存在」条件）。
- 归档概念详情当前返回 404（活跃聚合口径）；spec US35 只要求归档保留历史快照不要求可查，若票 04 生命周期需要归档详情可见，此端点需回改。
- 真机验收统一收敛在工单 06 的清单，本票不单列。

