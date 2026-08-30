# 04 — 重启恢复：上次界面与窗口记忆

**What to build:** 重启应用回到上次停留的页面（设置页除外，页面已不存在则回默认页），窗口大小、位置与最大化状态原样恢复、显示器拔除后夹回可见区域。窗口几何由官方 window-state 插件全权承担，前端 / Rust 不自写几何逻辑，也不进 `config/settings.json`（#51 窗口几何豁免）。（裁决与契约细节见 `.scratch/preferences/spec.md`）

**Blocked by:** 01 — 部分更新契约（`last_route` 键）

**Status:** done

- [x] `last_route` 键入契约（路由串或 null）；api-types 重生成
- [x] 路由变化时写 `last_route`，设置页路由不参与记忆；启动时恢复，目标不存在由现有 NotFound/错误态兜底回首页
- [x] window-state 插件在 builder 注册 + capabilities 权限；尺寸/位置/最大化恢复与显示器夹回全部为插件行为，无自写几何代码
- [x] 前端测试：路由记忆排除设置页、恢复失效兜底；cargo test 全绿
- [ ] 真机人工抽验：重启后页面与窗口状态恢复、外接显示器拔除后窗口在可见区域（正式验收留 05）

## 交付回写（2026-08-30）

- 后端：`last_route` 入 `PreferencesOut`/`PreferencesUpdate`（部分更新、显式 null=回默认页、默认值写盘删键沿基座）；load 侧非字符串兜底 null，路径存在性不做后端校验（前端 NotFound 兜底，工单明示）。
- 前端（`AppShell.tsx`）：恢复只尝试一次、仅当停在默认页（桌面启动总落 `/`，同时防显式打开路径被覆盖）；恢复导航经 in-flight 标记不触发写入；`/settings` 前缀不参与记忆；默认页写 null（settings.json 不落盘等价默认）；写入复用 `useSavePreference`（自 PreferencesSection 导出），错误不消费（非用户发起的编辑，失败只损失一次恢复）；偏好载入前的导航不记忆（启动间隙极短，沿快捷键间隙取舍）。只记 pathname，不含 search（页面级恢复，简单至上）。
- Rust：`tauri-plugin-window-state = "2"` 新增依赖 + builder 注册 + `window-state:default` 权限；窗口几何全归插件，零自写几何代码；前端零新依赖（未装 JS 包）。
- 测试：后端补 last_route 往返/显式 null 清除/类型拒绝/损坏兜底；前端新增 `AppShell.lastRoute.test.tsx`（恢复、NotFound 兜底、导航写入+设置页排除+回默认页写 null）；QuizPanel/TodoPanel mock 适配为有状态偏好仿真（PUT 响应合并当前状态，防固定快照失真）。
- 门禁：pytest 323 passed、pyright 仅既有 logging.py:46、vitest 26 文件 255 passed、tsc 通过、cargo test 21 passed。
- code-review 结论：已修——偏好写入改走 useMutation（desktop-state.md §2.2）、QuizPanel 断言与路由写入序列解耦、注释补齐取舍理由；遗留：`.claude/rules/desktop-ui.md` 正本「窗口记忆存 settings.json」表述漂移（03 票遗留的规则正本同步问题，rules 文件本票不动，待用户决策）。
- 真机抽验未执行，留用户与 05 票。
