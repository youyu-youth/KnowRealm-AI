# 01 — 档案切片、三表迁移与对话管理骨架

**What to build:** 用户在设置页看到"档案"区块（角色四选一 + 自我介绍 ≤200 字），可保存并回显；左栏"AI 对话"入口进入 `/chat`：空态引导卡、新建自由对话（创建时即把角色与自我介绍快照为一条 SYSTEM 消息，未建档用中性默认）、对话列表按最近更新排序、可重命名、可删除（弹窗明示"不可恢复"）；点进 `/chat/$sessionId` 显示明确的"消息功能未接入"状态。底层一次落迁移 0014（chat_sessions / chat_messages / profile 三表），测试库版本断言与后端目录文档的迁移版本表述同步推进。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] 设置页"档案"区块：角色四选一 + 自我介绍（≤200 字校验），保存持久化、重开回显
- [ ] 档案读取/更新接口只暴露 `primary_role` 与 `about_me` 两字段；未建档时读取返回空档案语义不报错
- [ ] 迁移 0014 一次建 chat_sessions（软删）/ chat_messages（追加型）/ profile（全列）三表；测试 `PRAGMA user_version` 断言推进；后端目录文档迁移版本行更新
- [ ] `/chat` 空态引导卡；新建自由对话即时出现在列表；列表按 updated_at 倒序
- [ ] 创建自由对话落一条 SYSTEM 快照消息（角色 + 自我介绍；未建档中性默认）——落库内容自动化断言
- [ ] 重命名即时生效；删除有"不可恢复"确认弹窗，删除后不再出现（软删）
- [ ] `/chat/$sessionId` 显示明确的"消息功能未接入"状态，无死按钮、无假成功
- [ ] OpenAPI → api-types 生成物同步
- [ ] 后端测试（ASGITransport + 完整迁移重放）与前端测试（MSW + getByRole）齐备
- [ ] 人工：档案表单交互与空态引导文案
