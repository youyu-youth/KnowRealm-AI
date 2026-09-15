# CB-09 — 前端状态与接口接入：api-types / hooks / i18n

**What to build:** OpenAPI 类型更新 + Course Brain query/mutation hooks + 状态机驱动 + zh/en 文案。MSW handler 扩展。为 CB-10/11 页面供地基。

**Blocked by:** CB-08（后端 API 冻结）。

**Status:** todo

**前端**

- [ ] `pnpm --filter @knowrealm/api-types generate`（新端点全量类型）
- [ ] `features/courses/api/` 增 courseBrainApi + courseBrainKeys + hooks：useCourseBrainSnapshot（BUILDING 轮询）/ useCourseBrainConcepts / useConceptSources / useTriggerBuild / useApplyReview / useCreateConcept；写操作失效快照与概念列表缓存
- [ ] 状态机六态派生 hook（EMPTY/BUILDING/REVIEW/READY/STALE/FAILED ← snapshot.status + 候选计数）
- [ ] i18n：`spaces.courseDetail.brain.*` 全套（状态栏/图谱/列表/审核/来源/空态引导/错误码表新码），zh/en 两边 key 一致（一致性防线）
- [ ] MSW handlers 扩展 brain 端点默认态（未构建 EMPTY）
- [ ] hooks 单测（MSW：快照态轮询、审核 mutation 失效链）

**门禁**

- [ ] pnpm test -- --maxWorkers=4 / lint / 触及文件 Prettier / build；提交：`feat(desktop): 接入 Course Brain 状态与数据 hooks（F4 CB-09）`
