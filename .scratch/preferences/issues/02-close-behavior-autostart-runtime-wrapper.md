# 02 — 桌面行为：关窗行为与开机自启（Tauri 运行时包装落成）

**What to build:** 用户可把关窗行为在「驻留托盘（默认）/ 直接退出」间切换并即时生效，退出复用 11 的安全确认流（活动录音/未保存文本先确认）；开机自启开关真实写入 / 移除 OS 启动项。桌面行为的 Tauri 调用全部收拢进新建的偏好运行时包装模块（全 feature 唯一新测试接缝），Rust 侧关窗硬编码同票删除、不留双轨。（裁决与契约细节见 `.scratch/preferences/spec.md`）

**Blocked by:** 01 — 偏好分区、部分更新契约与即改即存模式

**Status:** done

- [x] `close_behavior`（TRAY 默认 / EXIT）与 `autostart`（默认 false）两键入契约，校验与部分更新沿用 01 基座；api-types 重生成
- [x] `services/tauri` 偏好运行时包装模块落成（沿 `lifecycle.ts` 的 `isTauri` 守卫先例）：关窗与自启全部经它调官方件，组件不直触插件 API
- [x] 关窗分流挂 `onCloseRequested`：TRAY=`preventClose`+`hide`；EXIT=收敛到与托盘退出**同一 safeExit**（确认后退出）
- [x] Rust `on_window_event` 关窗处理删除；启动间隙（偏好未载入）关窗=直接退出（接受，不做双轨兜底）
- [x] autostart 插件在 builder 注册 + capabilities 权限；开关变更即调 enable/disable；启动不对账（系统层漂移不处理）
- [x] 偏好分区「桌面行为」小节进入：关窗行为选择 + 自启开关，即改即存同基座模式
- [x] 包装边界假 API 测试（关窗分流调用序列、自启 enable/disable 时机）+ 控件 MSW 测试；cargo test 剩余全绿
- [ ] 真机人工抽验：TRAY 关窗后可从托盘 / 快捷键唤回；EXIT 走确认流；自启开关在任务管理器启动项可见（正式验收留 05）

## 实现注记（2026-08-29）

- 关窗机制实测确认：JS 挂 `onCloseRequested` 后窗口**不再走 Rust 默认关闭**，由 handler 决定——preventDefault 则保窗，否则基座自动 `destroy()`。包装分流：TRAY=`preventDefault`+`hide`；EXIT=`preventDefault`+收敛 `requestSafeExit`（与托盘退出同一确认流）；null（偏好未载入）不拦截走 destroy 直接退出。**挂载前**（前端未跑完）无监听器，Rust 默认关窗即退出——「启动间隙直接退出」由挂载时序天然成立，无需任何双轨。
- 偏好查询**持续失败**亦落入 null 态（启动间隙语义的延长）：关窗直接退出、不经确认流。此时 sidecar 大概率不可用，safeExit 的录音检查同样不可达；属 spec「不做 Rust 兜底双轨」豁免范围，接受。
- `closeBehaviorRef` 渲染期同步写入（latest-ref）：偏好 PUT 成功即改缓存 → AppShell 重渲染 → ref 更新，关窗行为切换即时生效无需重挂。
- autostart 写序：**先 OS enable/disable 后 PUT 持久化**——OS 失败即行内报错、不动偏好（开关显示即真实生效）；PUT 失败回显服务端事实，会话内 OS 与偏好可能漂移，按 spec「启动不对账」明示不处理。
- capabilities 新增四项：`core:window:allow-hide`（TRAY 隐藏）、`core:window:allow-destroy`（基座默认路径）、`autostart:allow-enable/disable`；未开 `autostart:default` 整组（最小权限）。
- Rust：删 `handle_window_event`/`should_hide_on_close` 及 `close_policy_only_hides_main_window` 单测；`SHORTCUT`/`handle_shortcut`/`get_desktop_lifecycle_status` 按 03 票界**保留**。builder 注册 `tauri_plugin_autostart`（依赖此前已装未接线）。
- `CloseBehaviorPreference` 从 api-types 派生（`PreferencesOut["close_behavior"]`），遵守 desktop-react.md §3 禁手写重复；审查后删掉了零引用的 `isDesktopPreferencesRuntimeAvailable` 导出（挂载守卫复用 lifecycle 的 `isDesktopLifecycleAvailable`，同为 `isTauri`）。
- Pydantic bool 宽松转换：`autostart: "yes"` 会被接受为 true（lax str→bool），校验矩阵用 `"maybe"` 固化拒绝路径；前端类型系统保证只发 boolean。
- 全量并发下 TodoPanel/KnowledgePointPanel/settings.test 档案用例间歇超时为**既有抖动**（单独跑全绿，01 注记同类），与本票无关。
- 真机人工抽验按用户指示本次未执行，随 05 人工验收一并做（上项保留未勾）。
