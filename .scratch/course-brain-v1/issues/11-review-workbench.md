# CB-11 — 审核工作台：候选审核 / 合并选择 / Relation 审核 / 手动创建 / 批量操作

**What to build:** 用户不进聊天即可完成 Course Brain 管理的审核界面：候选审核抽屉 + Relation 审核区 + 手动创建 + 批量确认/忽略。所有写操作有明确反馈（Toast/乐观更新后回填）。固定工作区 + 局部滚动，符合桌面设计规范。

**Blocked by:** CB-10。

**Status:** done（2026-09-16，5c2789b）

**前端**

- [x] 候选审核抽屉：候选列表（抽取描述/来源预览/merge 建议徽章）+ 单条操作（确认/重命名后确认/合并到已有（Concept 选择器）/忽略）+ 批量确认/忽略
  - 实施备注：Sheet 抽屉（CourseBrainReviewDrawer）。行内=勾选+名称+description（line-clamp-2）+「疑似重复」徽章+确认/忽略/⋯菜单；点击行展开来源预览（首批锚点 quote 前 3 条，useConceptSources 仅展开行拉取）。重命名/合并表单在 ⋯ 菜单触发后行内展开，展开时挂载以候选名/建议 target（suggested_target_id）为初值，收起即销毁重置。单条=单决策请求；批量=勾选项合成一次 apply-review（候选列表上限 200 = 后端 decisions 上限，天然设防）。错误经 ApiError 展示翻译后错误码文案（409 撞名内联 Alert）；成功 Toast「已处理 n 项审核决策」。
- [x] Relation 审核区：候选关系列表（source→target/类型/置信度）逐条确认/忽略；过期徽章展示
  - 实施备注：CourseBrainRelationReview 工作区内嵌 SurfaceCard，待审核/已确认 ToggleChip 筛选（status 派生只看概念候选，READY 态也可能有候选关系，故常驻显示）；relation_type 六值走 i18n、未知值 defaultValue 回落；stale 徽章「证据已失效」仅 CONFIRMED 关系（查询期派生不落库）；列表 max-h 局部滚动，不撑破固定工作区。
- [x] 手动创建 Concept：名称/描述/类型/重要度表单（复用现有表单组件风格），直接 CONFIRMED
  - 实施备注：CourseBrainCreateConceptSheet（Sheet+表单，CreateCourseSheet 模式）；类型 Select=五常值（与抽取提示词一致），重要度 1~5 Select；source=USER_CONFIRMED 由后端落；409 撞名内联 Alert（ApiError 翻译）+成功 Toast；复用 ui/Textarea 组件。
- [x] 概念归档操作（CONFIRMED→ARCHIVED 二次确认）；"待归档"徽章展示（stale_archivable）
  - 实施备注：CourseBrainConceptDetail 面板 CONFIRMED 概念显示「归档概念」按钮 → CourseBrainArchiveDialog 二次确认（DeleteCourseDialog 模式）→ 成功 Toast 并关闭详情面板；stale_archivable「来源已全部失效」徽章 CB-10 已覆盖列表行与详情面板。
- [x] 审核后状态联动（REVIEW→READY 派生、图谱/列表/候选计数刷新）
  - 实施备注：写 hooks（applyReview/archive/createConcept）既有 `courseBrainKeys.all` 前缀失效 → 快照/概念/关系/来源自动重拉；REVIEW→READY 由后端快照派生（candidate_count=0），测试断言审核后「已就绪」标签出现、「审核候选」按钮消失；审核成功回调清空详情选中（防已处理候选的悬空详情）。
- [x] 组件测试：审核闭环全链路（MSW）、批量操作、错误反馈（409 撞名等）
  - 实施备注：CourseBrainReview.test.tsx 8 用例（全链路 confirm+快照联动+Toast/重命名 new_name/合并默认建议 target/批量一次两决策/relation 确认+stale 徽章/手动创建+409 撞名内联反馈/归档二次确认+面板关闭/apply-review 失败内联错误且快照不变）。测试坑：候选名与 Relation 区 source/target 名同文，定位候选行须用 checkbox aria-label 的 closest("li")+within。
- [x] i18n zh/en 同步补齐
  - 实施备注：brain.review 段 +33 键、relationType 六值、create/archive 段；en applied 用 `_one/_other` 复数（duration 先例）；删除 CB-09 预埋但未消费的 review.applyFailed（错误反馈走 ApiError 具体文案更有价值）；一致性防线过。

**门禁**

- [x] pnpm test / lint / Prettier / build；提交：`feat(desktop): 实现课程大脑候选审核工作台（F4 CB-11）`
  - 459/459 全绿（TodoPanel/QuizTests 既有并发抖动两用例单跑复绿）；lint / 触及文件 Prettier / build 通过。code-review 双轴（Standards/Spec）无硬违规，5 项判断性建议全采纳：concepts/relations 查询序列化提取 brainListPath、BRAIN_PAGE_LIMIT 常量共享（api 层导出）、CandidateRow 拆 RenameForm/MergeForm/SourcePreview 子组件（表单状态下沉）、en applied 复数键、Relation 列表局部滚动。真机验收（亮/暗/窄窗实机观感）留用户侧。
