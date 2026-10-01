# 04 — 计划 Tab 与今日待学

**What to build:** 学习计划获得日常执行面。知识空间详情页新增第 8 个计划 Tab：目标卡（标题 / 类型 / 期限 / 每日投入 / 整体进度）＋按阶段分组的计划项列表（日期、时长、状态、来源标记）＋项级内联编辑＋空态引导；今日页升级为双源合并——跨空间的学习计划项（排期日 ≤ 今天且未完成）与现有记录 Todo 并列分组、标注来源、勾选完成直接作用于计划项。

**Blocked by:** 03 — 计划编辑、完成与重生成

**Status:** done

- [x] 课程详情页新增 plan Tab（现 7 Tab 基础上第 8 个，tab 入 URL）：目标卡＋阶段分组计划项列表＋内联编辑（改日期 / 时长、完成、跳过）＋历史版本切换只读查看
- [x] 空态引导：无目标时引导"设定学习目标"并提示对话主路径（新建目标主路径＝对话，本 Tab 为手动兜底与日常执行面）
- [x] 今日页双源合并：跨空间计划项（scheduled_date ≤ 今天且未完成，跨空间目标各自排期并列展示）＋记录 Todo，分组标注来源；勾选完成与计划 Tab 状态一致；计划项完成时间戳进入今日学习时长统计（不进学习证据链）
- [x] zh / en 文案同步（两边 key 一致，en 缺失会被一致性防线拦截）
- [x] 前端测试：新端点 MSW mock、计划 Tab 组件与今日页双源组件（jsdom）、tab 路由
- [x] 门禁全绿：前端 vitest + 后端回归（若今日端点扩展涉及后端则含 pytest / OpenAPI --check）

## 实施备注

1. **后端新增 GET /api/today/plan-items**（today/service.list_due_plan_items）：跨空间待学计划项——PENDING、scheduled_date ≤ 今天、目标 ACTIVE、计划版本 ACTIVE、课程软删查询期过滤；排序＝排期日 → 空间名 → priority（逾期在前）。SKIPPED 是用户主动放弃不算待学；SUPERSEDED 版本与其项是只读进度不再催办。勾选完成走 03 已就位的课程嵌套端点（item_id + plan_id + course_id 三元组定位）。
2. **`local_today` 从 agent/tools/time_utils 迁至 learning_plan/scheduling**：today 模块要用同源锚点，而模块方向规则是 agent/today 均下游（领域模块不得 import agent），锚点本就是排期域语义，落领域侧后 agent 三处消费方改为 agent→learning_plan 方向导入（settings/config 注释同步）。
3. **趋势双源**：stats_trend 每日总量在记录捕获时长之上叠加 DONE 计划项预估时长（date(completed_at) 归日，UTC 口径与记录一致）；完成不产 learning_event（完成语义边界不变），跨版本求和＝每次完成只写一次 completed_at 的真实学习事实；课程软删即回落。TodayStatsOut.total_learning_ms 维持"仅音频记录"口径不变（OpenAPI 描述同步标注双源语义）。
4. **前端新建 learningPlan feature**：api/learningPlan.ts（keys/api/hooks，写操作按 learningPlan 前缀统一失效缓存——今日页勾选与计划 Tab 状态经同一缓存域自动一致，courseBrain 先例）＋ LearningPlanTab.tsx（目标卡 + 版本 Select 切换 + 阶段分组行 + 内联编辑）。读取面与执行面全部复用 03 端点，零后端新增写路径。
5. **版本切换 Select 必须传 items**：Base UI SelectValue 在弹层未挂载时无法从 children 反查 label、会回退显示原始 value（UUID）——传 items（value/label 对，CourseBrainReviewDrawer 先例）。jsdom 断言禁用态走 aria-disabled（Base UI 复选框渲染 span，B1 Switch 同坑）。
6. **planItemTypes 迁至 learningPlan feature**：03 时挂在 chat 下的共享映射（PLAN_ITEM_TYPE_KEYS）挪到领域家 features/learningPlan/planItemTypes.ts，chat 两个消费方改导入（chat→learningPlan 方向，完成 03 备案的"共享"语义）。
7. **今日页 TodaySummaryTodos 升级为 TodayTodos 双源清单**：计划项分组（勾选完成、逾期徽章、排期日标签、内容链接跳该空间计划 Tab）＋记录待办分组（原去确认链接原样保留）；双源皆空整块不出现（沿既有行为）。todayKeys.planItems 挂 learningPlan 前缀下（完成/编辑/跳过写操作的前缀失效自动覆盖今日页）。
8. **空态两档**：无 ACTIVE 目标 → 引导卡（CTA 链 /chat，注明对话主路径）；有目标无计划版本 → 引导生成草案。不建目标创建表单（工单只要求引导；目标 CRUD 走对话或既有端点）。
9. **MSW 默认 handlers 补 /api/today/plan-items → []**：否则所有渲染今日页的存量测试撞未处理请求、TodayTodos 渲染错误 alert 回归 TodayStatsBand 断言（实测踩中）。
10. **存量 pyright 三错顺手归零**：时间能力 v1 遗留（time_utils timezone_label 两处 + config.resolve_user_timezone 返回值 Optional 存根）——time_utils 加 require_aware 收窄助手（undo.py assert 收窄先例），config 就地 assert（settings 平台模块不得 import agent）。
11. **门禁**：后端 1030 绿（首跑 1028+1 环境抖动单跑绿）+ ruff/format/pyright 0；前端新增 10 用例（LearningPlanTab 6 + TodayTodos 4）+ 全量 633；全量并发下 TodoPanel/CourseBrainTab/QuizTests 存在历史性抖动（单跑全绿确认非回归）；OpenAPI regenerate + tsc + prettier 改动文件通过。
12. **双轴 review 修复五项（已补回归测试）**：①今日页勾选完成后趋势/统计当场刷新（useCompletePlanItem 成功再失效 todayKeys.all——「完成时间戳进入今日学习时长」当次上抬不等重进页面；learningPlanKeys 抽独立 api/keys.ts 纯键模块，today/api/keys.planItems 改引 learningPlanKeys.all，两侧纯键互引不成环）②编辑行无变更禁用保存（不发会被 _require_any_field 拒绝的空载荷）③两处 `as string` 补 enabled 收窄注释（desktop-react §2）④版本 Select label 三元抽 versionLabel(version, t) 一份两用（hook 不进 map 回调）⑤TodayTodos 复用导出的 toastMutationError、isOverdue/formatDueLabel 收敛 startOfDay 单口径。评审另指 total_learning_ms（仅音频）与趋势（双源）两口径并存——OpenAPI 已标注、属既有语义边界，工单不扩面。
13. **历史目标只读入口（GPT 审查 P2 修复）**：Tab 原先只取 ACTIVE 目标，目标完结/归档后整 Tab 空态、历史计划不可达（违反 spec 用户故事 16 追溯要求）。后端本就全状态返回（list_for_course 的 `status != ACTIVE` 只是排序键非过滤；versions/plan 端点无目标状态过滤），缺口纯在前端。修复＝默认仍跟 ACTIVE（执行面不变），无 ACTIVE 时回落最近历史目标只读展示并保留"设定新目标"引导卡；多目标时目标卡上方出现切换 Select（`{{title}} · 进行中/历史`，versionLabel 同式）；完结/归档目标执行面整体只读（editable 叠加 goal.status 判定，GoalCard 状态徽章 ACTIVE→进行中/COMPLETED→已完结/ARCHIVED→已归档）；GoalWorkspace 以 key={goal.id} 重挂载自动重置版本选择。i18n 新增 goalSelect 三键 + goalCard 状态两键（zh/en 同步）。**测试坑**：MSW 对带 query 的 path 只按 pathname 匹配且 use 数组按序 prepend——两个目标同 pathname `/plans` 的 handler 后注册者永远不被命中（5555 请求被 1111 fixture 劫走，症状＝目标卡已切换但版本/计划项仍是旧目标数据）；同 pathname 多 fixture 必须合并单 handler 按 query 分流。回归 2 用例已做对抗验证（sed 单点回退 fallback→红→恢复）。

## 用户真机验收清单

- [ ] 对话生成并确认一份计划后，进入该空间详情页第 8 个「计划」Tab：目标卡（类型/期限/每日投入/整体进度）与按阶段分组的计划项（日期、时长、类型、锁定标记、理由）呈现正确；直接改 URL `?tab=plan` 可达
- [ ] 就地编辑（改日期/时长/内容）即时生效且该项出现锁定标记；勾选完成/跳过后状态与今日页一致
- [ ] 重生成换新版本后，计划 Tab 版本切换器出现两版；切到历史版本显示「历史版本 · 只读」（无编辑/跳过、勾选禁用）
- [ ] 今日页出现「今日待学」双源：学习计划分组（含跨空间、逾期项带逾期徽章）与记录待办分组；勾选完成计划项后条目消失且计划 Tab 同步为已完成
- [ ] 完成计划项后今日统计趋势的当日总量包含该项时长（趋势图当日点上抬）
- [ ] 无目标空间打开计划 Tab 显示引导卡（CTA 跳对话）；有目标无计划显示生成引导
