# CB-11 — 审核工作台：候选审核 / 合并选择 / Relation 审核 / 手动创建 / 批量操作

**What to build:** 用户不进聊天即可完成 Course Brain 管理的审核界面：候选审核抽屉 + Relation 审核区 + 手动创建 + 批量确认/忽略。所有写操作有明确反馈（Toast/乐观更新后回填）。固定工作区 + 局部滚动，符合桌面设计规范。

**Blocked by:** CB-10。

**Status:** todo

**前端**

- [ ] 候选审核抽屉：候选列表（抽取描述/来源预览/merge 建议徽章）+ 单条操作（确认/重命名后确认/合并到已有（Concept 选择器）/忽略）+ 批量确认/忽略
- [ ] Relation 审核区：候选关系列表（source→target/类型/置信度）逐条确认/忽略；过期徽章展示
- [ ] 手动创建 Concept：名称/描述/类型/重要度表单（复用现有表单组件风格），直接 CONFIRMED
- [ ] 概念归档操作（CONFIRMED→ARCHIVED 二次确认）；"待归档"徽章展示（stale_archivable）
- [ ] 审核后状态联动（REVIEW→READY 派生、图谱/列表/候选计数刷新）
- [ ] 组件测试：审核闭环全链路（MSW）、批量操作、错误反馈（409 撞名等）
- [ ] i18n zh/en 同步补齐

**门禁**

- [ ] pnpm test / lint / Prettier / build；提交：`feat(desktop): 实现课程大脑候选审核工作台（F4 CB-11）`
