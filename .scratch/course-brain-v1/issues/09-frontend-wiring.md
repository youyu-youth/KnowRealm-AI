# CB-09 — 前端状态与接口接入：api-types / hooks / i18n

**What to build:** OpenAPI 类型更新 + Course Brain query/mutation hooks + 状态机驱动 + zh/en 文案。MSW handler 扩展。为 CB-10/11 页面供地基。

**Blocked by:** CB-08（后端 API 冻结）。

**Status:** done

**前端**

- [x] `pnpm --filter @knowrealm/api-types generate`（schema.d.ts 已含全部 brain 端点类型，generate 零 diff 验证）
- [x] `features/courses/api/` 增 courseBrainApi + courseBrainKeys + hooks：useCourseBrainSnapshot（BUILDING 轮询，2s，`refetchInterval` 条件回调）/ useCourseBrainConcepts / useConceptSources（conceptId 可空 + enabled 门）/ useTriggerBuild / useApplyReview / useCreateConcept；写操作经 `useInvalidateBrain` 失效 `courseBrainKeys.all` 前缀（confirm/merge 联动快照计数、图谱、列表与来源锚点，前缀失效比逐键枚举不易漏，code-review 两轴均认可）
- [x] 状态机六态派生 hook：`useCourseBrainView` 返回判别联合 `{phase:"loading"} | {phase:"error"} | {phase:六态, snapshot}`（候选计数已由后端折入 status，派生等价）
- [x] i18n：`spaces.courseDetail.brain.*` 全套 46 键（status/statusHint 六态、build、graph、concepts、review、sources、emptyGuide），zh/en 两边 key 一致（一致性防线测试兜底）；errors 表新增 6 码 COURSE_BRAIN_BUILD_IN_PROGRESS/CONCEPT_EXISTS/CONCEPT_NOT_FOUND/CONCEPT_STATE_INVALID/RELATION_NOT_FOUND/RELATION_STATE_INVALID（zh/en 按字母序插入）
- [x] MSW handlers 扩展 brain 端点默认态：GET brain（EMPTY 快照 helper）、concepts []、relations []、concepts/{id}/sources（空来源）
- [x] hooks 单测 `courseBrain.test.tsx`（@vitest-environment jsdom + renderHook，本仓首个 renderHook 用例）：BUILDING 态 2s 轮询至 READY 后停止（vi fake timers 循环推进）；apply-review 成功后按前缀失效链重取快照（请求体断言）

**门禁**

- [x] pnpm test --maxWorkers=4（448/448）/ lint / 触及文件 Prettier / build 全绿；提交：`feat(desktop): 接入 Course Brain 状态与数据 hooks（F4 CB-09）`（526c364）

**实施备注**：code-review 双轴过审无硬违规；采纳 4 小修（sources 键接受 null、删未引用 BrainReviewDecision 别名、测试 fixture 改 CourseBrainPhase 字面量联合、MSW 补 sources 默认态）；vi.mock 基址字面量重复为仓库 chatSessions.test.ts 先例不动。
