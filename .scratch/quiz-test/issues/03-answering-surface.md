# 03 — 卷面作答闭环（三档展示形式 × 五题型 × 答题卡）

**What to build:** 完整的作答体验：卷面页提供**单题（一页一题，键盘 ←→ 翻题）/ 分段（大题步骤条一屏一段）/ 整卷（连续滚动试卷文档）三档展示形式随时切换**（同步 URL），左侧答题卡常驻（格子跳题/进度/交卷按钮）；逐题提交一题一答不可改（答完锁定），客观题提交即判，简答提交待评；全部答完才可交卷；中断重进继续作答不丢已答；可放弃（ABANDONED 不落事件）。作答只写 `quiz_test_items`，永不触碰 quizzes 三列。视觉与交互参考二轮原型。

**Blocked by:** 01（五题型作答控件）、02（表/API/卷面路由）。

**Status:** ready-for-agent

**深度参考:** `.scratch/function-plans-introduction/15-mock-test.md`（卷面结构定稿段、关键业务规则）；原型 `apps/desktop/src/pages/prototype-mock-test.tsx`（三档形式/答题卡/控件形态的验证基线，实现时按定稿语义重写）

- [ ] 三档展示形式随切且 `?view=` URL 同步；单题档键盘 ←→ 翻题（输入框聚焦时不拦截）
- [ ] 答题卡：格子跳题、已答/当前态、进度条、交卷按钮（未答完禁用 + 提示）
- [ ] 一题一答锁定不可改；客观题提交即判（多选/填空全对制，复用 01 判分规则），简答提交锁定待评
- [ ] 逐题作答 API + `QUIZ_ANSWERED` 事件（键 `quiz-answered:test:{item_id}`）客观题提交即落、重放幂等不重复
- [ ] 中断重进：进行中测试可恢复继续作答，已答不丢、不产生重复事件
- [ ] 放弃 → ABANDONED，不落任何事件
- [ ] 测试作答只写 `quiz_test_items`，`quizzes.user_answer_json / answer_result / answered_at` 三列零触碰（测试守护）
- [ ] pytest（判分/事件/幂等/放弃）与前端 MSW（三档切换/锁定/答题卡/恢复）双侧绿
