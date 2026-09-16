# CB-13 — P1 遗留修复：来源跳转精确定位 / 课程移动失效 / 零证据闸门

**What to build:** 修复 Course Brain V1 交付后评审发现的三个 P1 缺陷：①来源跳转同一摘录多次出现时只落首次出现；②记录跨课程移动后旧课程概念来源仍泄漏原文且不亮待归档徽章；③零证据 AI Concept 可进入审核并被正式确认。

**Blocked by:** CB-12。

**Status:** done（2026-09-16，5afd33a + c1f8ef4）

**P1-1 来源跳转按分片 id 精确定位**

- [x] 后端 `ConceptAnchorSourceOut` 透出 `segment_id`（`source_anchors.transcript_segment_id/document_segment_id`，SQL 本就 join 只是没 select）；契约再生（openapi.json + schema.d.ts 仅 +segment_id）
- [x] 前端链路：`anchorJumpTarget` 带 `segmentId` → `records.$recordId` validateSearch 白名单接纳 → `RecordDetailPage` 透传 → `SourceTimeline` 先按行 id 精确匹配、未命中回落 quote 文本匹配（`useOpenCitation` 等仅带 quote 的调用方行为不变）；纯文本视图不动
- [x] 测试：TranscriptPanel 新增「segmentId 指向重复摘录第二处分片（05:00）而非首次（04:35）」用例，既有首个命中用例改名为回落语义保留；CourseBrainTab fixture 补 segment_id、href 断言更新（音频+文档锚点均携带）

**P1-2 记录跨课程移动后的读取期防护**

- [x] `_CONCEPT_ANCHORS_SQL` / `_CONCEPT_ANCHOR_COUNT_SQL`：`(a.record_id IS NULL OR r.id IS NOT NULL)` 收紧为 `(a.record_id IS NULL OR (r.id IS NOT NULL AND r.course_id = :course_id))`——软删或移出课程都不泄漏（CHAT 锚点挂 record_id 的同样受约束，与软删行为一致）
- [x] `_STALE_ARCHIVABLE_SQL`：JOIN concepts 比对记录当前归属，dead 条件追加 `OR r.course_id IS NULL OR r.course_id != c.course_id`——移出课程后概念亮待归档徽章
- [x] 快照 STALE 无需改：`_FINGERPRINT_SQL` 已按 `r.course_id` 过滤，移动后指纹自然变化
- [x] 测试：SQL 直改 `records.course_id` 模拟移动（产品入口本版本 409 拒绝重新归类，不放开）→ 断言 anchors/knowledge_points/anchor_count 全空、stale_archivable=true
- [x] 后端 sources 测试补 `segment_id` 断言（音频=seg id、CHAT=null）

**P1-3 零证据 AI 概念三层闸门**

- [x] B1 契约层：`CourseBrainExtractionConcept.evidence` 加 `min_length=1`（json_schema 严格模式把 minItems 传给 provider 约束解码；json_object 降级端点违反时走既有 `INVALID_STRUCTURED_OUTPUT` 构建失败路径，无重试属既有建模）
- [x] B2 构建层：`_build_publish_plan` 记录 `evidenced_concept_ids`，收尾剔除本次新建但零定位证据的概念（含其关系候选与计数）并不写任何 `evidence_count == 0` 的出现映射；复用的既有候选/正式概念不动历史数据，交 B3 兜底
- [x] B3 确认层：`_apply_confirm` 对 `source=AI_EXTRACTED` 候选校验 `sum(record_concepts.evidence_count) > 0`，为零 409 新错误码 `COURSE_BRAIN_CONCEPT_NO_EVIDENCE`（放在改名撞名检查之后，保持既有 CONCEPT_EXISTS 优先级）；merge/dismiss 不设闸；手动概念直接 CONFIRMED 天然豁免
- [x] i18n：zh/en errors 段各加 `COURSE_BRAIN_CONCEPT_NO_EVIDENCE` 文案
- [x] 测试：schema 单测（evidence=[] → ValidationError）；worker 全失配用例（不产生候选/零证据行/关系候选、既有概念保留）；confirm 409 用例（零证据候选被拒且状态不变）；审核日志测试补 evidence 装置适配新闸门

**门禁**

- [x] 后端 pytest 554 全绿（course_brain 47 专项含 4 新用例）+ ruff + pyright 0 错；api-types check exit 0；前端 vitest 461/461（TodoPanel 首轮两用例既有并发抖动、单跑与复跑全绿）+ eslint + tsc 通过
- [x] 提交：`fix(backend): 课程大脑来源校验记录当前归属并封堵零证据候选`（5afd33a，含契约再生）；`fix(desktop): 课程大脑来源跳转按分片id精确定位`（c1f8ef4）

**用户真机验收（不代勾）**

- [ ] 构建→审核工作台点击含重复摘录的来源，确认跳转落在锚点分片而非首次出现
- [ ] 真机观察零证据相关：正常构建仍产出候选；历史零证据候选（若有）确认时提示新错误码文案
