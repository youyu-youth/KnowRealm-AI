# CB-06 — Relation 候选与过期检测 / 失效清理

**What to build:** relation 审核操作（confirm/dismiss）+ 来源变化后的过期与失效清理。关系不过确认不进正式图谱；旧来源不参与检索；正式概念不因一次抽取缺失被删。

**Blocked by:** CB-05。

**Status:** done（2026-09-15，后端 542 测试绿 + ruff/format/pyright/openapi check 全绿）

**后端**

- [x] relation 审核：apply-review 增 `confirm_relation`（CANDIDATE→CONFIRMED）/ `dismiss_relation`（→DISMISSED）；端点或快照暴露 relation 候选列表（含 confidence/evidence_count）
  - 实施备注：新增 `GET /{course_id}/brain/relations`（status 筛选默认 CANDIDATE，含两端概念规范名）；`BrainRelationStatus` 枚举对应迁移 0023 既有 CHECK（含 DISMISSED，本票零迁移、13 处 user_version 断言未动）；同 relation_id 重复决策 422（validator 改 `reject_duplicate_targets`，概念/关系分别查重）；跨课程 relation_id 404 `COURSE_BRAIN_RELATION_NOT_FOUND`；非候选状态操作 409 `COURSE_BRAIN_RELATION_STATE_INVALID`（均入错误码清单）
- [x] 过期检测：重建时既有 CONFIRMED relation 若两端概念仍 CONFIRMED 但本次构建零证据支撑→标记过期徽章（快照派生 stale 提示），不自动降级
  - 实施备注：worker writeback 在 result_json 落 `supported_relations`（本次抽取三元组集）；service 查询期派生 `stale`（快照 graph 边 + relations 列表 CONFIRMED 行），无成功构建产物或旧格式不标过期；「零证据」口径=最近一次成功构建的模型输出未覆盖该三元组
- [x] 失效清理：记录删除/软删→record_concepts 由 FK CASCADE/查询过滤失效；概念删除→relations CASCADE（FK 已保证）；课程删除→全 CASCADE
  - 实施备注：全部为迁移 0023 既有 FK 与查询过滤（`_concept_stats`/`_RELATED_*` 已带软删与课程过滤），本票零改动，测试证明覆盖
- [x] 图谱视图数据：GET 快照含 CONFIRMED 概念邻接（节点+边一次取齐，供前端 ECharts）
  - 实施备注：`BrainSnapshotOut.graph`（必填；apply-review 响应同构返回，审核后无需二次请求）；节点=全部 CONFIRMED 概念（含零边孤立节点，附 record_count/occurrence_count 供 spec §109 的节点大小映射）；边=两端均 CONFIRMED 的 CONFIRMED 关系（SQL JOIN 过滤跨课程泄漏）
- [x] 测试：未确认 relation 不出现在正式邻接、记录软删后来源与计数即时失效、概念 ARCHIVED 后其 relation 不再参与检索/图谱、重建零证据不删 CONFIRMED relation
  - 实施备注：新增 4 测试（图谱排除未确认/跨课程边+归档退出图谱、关系审核状态机+404+422、软删计数即时失效、重建零证据 stale 亮起不降级）；「不参与检索」由既有 `test_brain_search_related_concepts_confirmed_only` 覆盖未重复造

**门禁**

- [x] 后端四门禁全绿；提交：`feat(backend): 实现概念关系候选审核与过期检测（F4 CB-06）`

**已知口径（待后续票/用户裁决）**

- relation 候选 `evidence_count` 恒 0：CB-04 `_publish_relation_candidates` 只补缺不累计，本票如实暴露；若需「同三元组跨记录抽取累计」须改 CB-04 发布语义（涉及 DISMISSED/既存行是否回填），未擅动。
- 误 dismiss 的 relation 无恢复路径（confirm 仅接受 CANDIDATE，按工单字面）；DISMISSED 三元组不被重建复活，同名新关系也建不出来——将来如需恢复须新增显式恢复操作。
- CONFIRMED 关系一端 ARCHIVED 后：图谱/检索不再出现（既有过滤），列表行 stale=False（非「过期」语义）；前端 CB-11 可按两端状态另行渲染。
