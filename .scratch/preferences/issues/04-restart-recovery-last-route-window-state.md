# 04 — 重启恢复：上次界面与窗口记忆

**What to build:** 重启应用回到上次停留的页面（设置页除外，页面已不存在则回默认页），窗口大小、位置与最大化状态原样恢复、显示器拔除后夹回可见区域。窗口几何由官方 window-state 插件全权承担，前端 / Rust 不自写几何逻辑，也不进 `config/settings.json`（#51 窗口几何豁免）。（裁决与契约细节见 `.scratch/preferences/spec.md`）

**Blocked by:** 01 — 部分更新契约（`last_route` 键）

**Status:** ready-for-agent

- [ ] `last_route` 键入契约（路由串或 null）；api-types 重生成
- [ ] 路由变化时写 `last_route`，设置页路由不参与记忆；启动时恢复，目标不存在由现有 NotFound/错误态兜底回首页
- [ ] window-state 插件在 builder 注册 + capabilities 权限；尺寸/位置/最大化恢复与显示器夹回全部为插件行为，无自写几何代码
- [ ] 前端测试：路由记忆排除设置页、恢复失效兜底；cargo test 全绿
- [ ] 真机人工抽验：重启后页面与窗口状态恢复、外接显示器拔除后窗口在可见区域（正式验收留 05）
