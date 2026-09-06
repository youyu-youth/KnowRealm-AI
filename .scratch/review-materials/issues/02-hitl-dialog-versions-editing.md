# 02 — 弹窗 HITL 工作台：确认、反馈调整、版本链与手动编辑

**What to build:** 生成完成后弹窗成为 HITL 工作台——预览三段并可【确认】定版、【反馈调整】不限次重生成（新版本、旧版退场数据保留）、【手动编辑】就地生效；历史版本可回看；转写更新后旧资料得到非阻塞过期提示。（裁决与契约细节见 `.scratch/review-materials/spec.md`）

**Blocked by:** 01 — 首次生成与复习页签阅读态

**Status:** ready-for-agent

- [ ] 确认端点：`POST /api/records/{id}/review-material-confirmations`——GENERATED → CONFIRMED（confirmed_at 落行），幂等（重复确认返回现状）；确认不锁编辑；不发 learning_event
- [ ] 反馈调整端点：`POST /api/records/{id}/review-material-adjustments`——feedback 1~1000 字绑当前版本，202；graph 经 `Command(resume="ADJUST")` 携反馈恢复 regenerate → 新行 version_no+1 置 GENERATED、旧版置 SUPERSEDED；对 CONFIRMED 版本再调整同流程；prompt 版本化自 review_adjust_v1 起；调整任务受 one-active 守卫
- [ ] 版本链端点与回看：`GET /api/records/{id}/review-materials`（只读版本列表）+ 前端版本列表切换查看 UI（照总结版本列表先例）；无一键回滚
- [ ] 弹窗 HITL 工作台：生成完成自动打开、关闭后页签保持阅读态、操作按钮重开；三段预览复用 01 渲染组件；确认/反馈调整操作与状态反馈（调整中轮询、新版本到达刷新预览）
- [ ] 手动编辑端点：`PATCH /api/records/{id}/review-material`——速记/大纲文本 + 重点清单整体提交，**就地更新当前版本：不换代、不迁移状态、updated_at 刷新**；编辑 CONFIRMED 版本无需重新确认（导出条件不变）；可编辑三段全量（速记/大纲 Markdown 源码、重点清单条目增删改）
- [ ] 弹窗编辑态 UI：速记/大纲 Markdown 源码 textarea（field-sizing 坑注意 Dialog 撑开问题）、重点清单条目编辑器（增删改）；保存即就地生效返回阅读态
- [ ] 转写过期提示：读端点在行上 transcript_source_version < 当前 source_version 时返回过时标记；前端非阻塞提示「转写已更新，可重新生成」；旧内容不删不覆盖；`generated_from_summary_id` 仅溯源、总结换代不阻塞
- [ ] OpenAPI → api-types 重新生成
- [ ] 测试：S1（调整 resume 产生新版本且旧版 SUPERSEDED、确认幂等、PATCH 不换代不迁移状态、编辑 CONFIRMED 后导出前置语义不变、调整任务 one-active、feedback 空值/超长 422、换代/转写变更后提交被拒）+ S4（弹窗确认流、反馈调整流、编辑流、版本切换、过期提示、生成完成自动打开弹窗）
