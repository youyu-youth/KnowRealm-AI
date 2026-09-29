# 03 — 计划编辑、完成与重生成

**What to build:** 用户对计划获得精细控制：草案确认卡升级为可编辑（改日期、改时长、删项、排序）；落库后的计划项可就地编辑、勾选完成或跳过（每次改动有操作审计）；目标或偏好变化时可要求重新生成——新版本生效、旧版本只读保留，用户手动锁定过的项原样带入不被 AI 重排。

**Blocked by:** 02 — 计划数据与生成确认链路

**Status:** ready-for-agent

- [ ] 草案确认卡可编辑：改日期 / 改时长 / 删项 / 排序四操作，确认后按编辑结果落库
- [ ] 项级编辑 Service：就地修改当前版本计划项（日期 / 时长 / 内容）、完成、跳过；每次改动落 Operation 审计；用户手动编辑过的项由 Service 置 user_locked
- [ ] 重生成 Service：新 plan_version、旧版 SUPERSEDED 只读保留、user_locked 项原样带入新版本；历史版本可只读查询（含进度记录）
- [ ] 完成语义边界：勾选完成不产 learning_event、不直接修改 Concept Mastery（测试断言两表零写入）；学习时长统计由计划项完成时间戳单独承载（今日统计带口径，页面呈现随 04）
- [ ] Agent 工具：update_plan_item、complete_plan_item（写，确认卡＋授权＋审计）、regenerate_plan（写，确认卡、产新版本）
- [ ] 测试：编辑 / 完成 / 跳过 / 重生成语义（版本链、user_locked 保留、SUPERSEDED 只读）、learning_events 与 user_concept_mastery 零写入断言、Agent 工具确认与授权行为
- [ ] 门禁全绿：pytest（独立 basetemp）+ ruff + pyright + OpenAPI --check + 前端测试（草案卡编辑交互）

参考：[spec.md](../spec.md) 计划执行与调整（User Stories 12~17）、生成确认与版本语义段。
