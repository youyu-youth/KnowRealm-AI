# 02 — 候选审阅、手工补充与批次确认

**What to build:** 用户在候选批次内逐条编辑（名称/详情/标签/五星重要度）、删除不需要的候选、手工补充自己的知识点（即时保存的独立行）；点「确认保存」后候选批次整体生效为正式学习资产、旧 AI 批次自动过时、一次确认动作落一条幂等的 KNOWLEDGE_CONFIRMED 学习事件；不满意可丢弃整批重来；确认之后仍可继续编辑、删除、补充。

**Blocked by:** 01 — 知识点生成候选（页签落地与生成闭环）

**Status:** completed

- [x] 候选行内编辑名称、详情、标签（≤5 个）、重要度（1~5 五星可编辑）与单条删除（软删）即时保存；DRAFT 与 ACTIVE 行复用同一套编辑交互
- [x] 手工新增立即落库为 ACTIVE 独立行（batch_id 与 generated_from_summary_id 为空），确认前后行为一致，关闭窗口不丢
- [x] 批次确认在单事务完成：前置校验批次绑定的 Summary 仍为 CONFIRMED 且课程仍 ACTIVE（否则 409 并引导丢弃后重新生成）→ 本批 DRAFT 置 ACTIVE、既有其他 AI ACTIVE 批次置 SUPERSEDED、落 KNOWLEDGE_CONFIRMED 事件
- [x] 事件契约：source_type=KNOWLEDGE_BATCH、source_id=batch_id、幂等键 `knowledge-confirmed:{batch_id}`、metadata 含 batch_id/confirmed_count/generated_from_summary_id；重复确认幂等返回现状；确认后的手工增删改不再落事件
- [x] 丢弃批次软删整批 DRAFT 行，回到可重新生成的初始态
- [x] 确认后持续编辑：ACTIVE 行可编辑、软删、继续手工补充；已保存列表默认按重要度降序
- [x] 过时批次数据保留且可通过 `?include=superseded` 查询回溯（数据不丢即回溯口径，不做历史查看 UI）
- [x] 后端测试覆盖确认事务、事件幂等与唯一约束、SUPERSEDED 语义、手工行保留；桌面 MSW 测试覆盖审阅交互、确认、丢弃与确认后编辑

## Verification

- 后端：全量 `128 passed`（知识点用例 15 个，新增 7 个覆盖确认事务+换代换代/归档 409、删光行后的重复确认幂等与幂等键唯一约束、双批次 SUPERSEDED 与手工行保留、丢弃、确认后增删改不落事件）；Ruff 通过，变更文件 Pyright `0 errors`。
- 桌面端：全量 `62 passed`（新增 6 个 MSW 用例：星级即时调整/编辑/删除、手工补充、确认后列表稳定、确认 409 引导、丢弃回初始态、确认后持续编辑）；TypeScript/Vite 生产构建与 ESLint 通过；api-types 已再生成并通过 schema check。
- 幂等锚点实现为「事件幂等键存在即返回现状」：确认后即使删光整批行，重复确认仍 200 幂等；并发确认由幂等键唯一约束 + IntegrityError 兜底。
