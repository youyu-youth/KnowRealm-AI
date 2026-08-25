# 02 — 批次采纳与重新生成联动

**What to build:** 候选审阅后整批「采用」：该批转 ACTIVE 成为可作答题库、旧 AI 批自动置 SUPERSEDED 并退出列表（API 可回溯）；确认弹窗提示旧批剩余未答数但不阻塞；与重新生成构成完整循环；转写 / 总结换代后已采纳批次不失效，在途候选的采用被 409 阻止并引导重生成。（细节见 `.scratch/quiz/spec.md`）

**Blocked by:** 01 — 生成候选批次与档位记忆

**Status:** completed

- [x] 采纳端点单事务：该批 DRAFT→ACTIVE、既有其他 AI ACTIVE 批→SUPERSEDED；重复采纳幂等返回现状（并发由约束兜底）
- [x] 采纳前置：绑定的 Summary 仍 CONFIRMED 且课程仍 ACTIVE，否则 409 + blocked_reason=SUMMARY_SUPERSEDED 并引导丢弃重生成
- [x] 批次采纳不落任何 learning_event（四事件无 QUIZ_CONFIRMED 槽位——采纳是管理动作，不是学习行为）
- [x] 生成 → 审阅 → 采用 → 再生成 → 再采用 全循环可用；候选在途期间旧 ACTIVE 批内容不受影响
- [x] SUPERSEDED 批次默认从读端隐藏；`?include=superseded` 可回溯（含行上作答态字段）
- [x] 桌面端：采用 / 丢弃动作、确认弹窗附「旧批次剩 N 题未作答」提示且不阻塞；采用后旧批退出列表、新批平滑进入
- [x] 换代场景测试：转写编辑使旧 Summary 置 SUPERSEDED 后，ACTIVE 批仍出现在读端；在途 DRAFT 的采用被 409 阻止
- [x] 后端 ASGI 全栈测试与桌面 MSW 测试通过
