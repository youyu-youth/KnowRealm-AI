# 03 — 接管语义落地（ADR 0011）

**What to build:** 让「用户改过/做完的 AI 待办永不随批次换代消失」成为可验证事实：对已生效（ACTIVE）的 AI 条目，用户编辑内容或勾选 DONE 即触发**接管**——该条脱离批次生命周期，此后新批次采纳只把仍 ACTIVE 的旧批行置 SUPERSEDED，被接管项与手工项同等保留。候选态修剪不算接管。UI 无视觉变化，纯行为票。（机制与反方案见 `docs/adr/0011-user-takeover-detaches-ai-todos-from-batch.md`，契约见 `.scratch/todo/spec.md`）

**Blocked by:** 02 — AI 生成候选、修剪与批次生命周期

**Status:** ready-for-agent

- [x] 接管谓词落进 01 的勾选与编辑端点：`generation_status = ACTIVE` 且 `source = AI` 的行被编辑 content 或勾选 DONE（任一方向）即置 `generation_status = NULL`；`generated_from_summary_id` 溯源保留、`source` 不翻转；取消勾选不回退（NULL 幂等）；删除 ACTIVE 的 AI 项 = 直接软删，不涉接管
- [x] 完整接管场景验证：生成 → 采纳 → 部分条目勾 DONE / 编辑 → 换代重新生成并采纳新批 → 被接管项与手工项保留可见，仅仍 ACTIVE 的旧批行置 SUPERSEDED
- [x] DRAFT 候选的修剪（编辑 / 删除）不触发接管——项仍属批次、随采纳整体 ACTIVE
- [x] 手工项行为不因谓词变化而改变（回归）
- [x] 后端 HTTP 全流程测试覆盖上述场景；接管谓词对手工行为无扰动的回归断言
