# 02 — 桌面行为：关窗行为与开机自启（Tauri 运行时包装落成）

**What to build:** 用户可把关窗行为在「驻留托盘（默认）/ 直接退出」间切换并即时生效，退出复用 11 的安全确认流（活动录音/未保存文本先确认）；开机自启开关真实写入 / 移除 OS 启动项。桌面行为的 Tauri 调用全部收拢进新建的偏好运行时包装模块（全 feature 唯一新测试接缝），Rust 侧关窗硬编码同票删除、不留双轨。（裁决与契约细节见 `.scratch/preferences/spec.md`）

**Blocked by:** 01 — 偏好分区、部分更新契约与即改即存模式

**Status:** ready-for-agent

- [ ] `close_behavior`（TRAY 默认 / EXIT）与 `autostart`（默认 false）两键入契约，校验与部分更新沿用 01 基座；api-types 重生成
- [ ] `services/tauri` 偏好运行时包装模块落成（沿 `lifecycle.ts` 的 `isTauri` 守卫先例）：关窗与自启全部经它调官方件，组件不直触插件 API
- [ ] 关窗分流挂 `onCloseRequested`：TRAY=`preventClose`+`hide`；EXIT=收敛到与托盘退出**同一 safeExit**（确认后退出）
- [ ] Rust `on_window_event` 关窗处理删除；启动间隙（偏好未载入）关窗=直接退出（接受，不做双轨兜底）
- [ ] autostart 插件在 builder 注册 + capabilities 权限；开关变更即调 enable/disable；启动不对账（系统层漂移不处理）
- [ ] 偏好分区「桌面行为」小节进入：关窗行为选择 + 自启开关，即改即存同基座模式
- [ ] 包装边界假 API 测试（关窗分流调用序列、自启 enable/disable 时机）+ 控件 MSW 测试；cargo test 剩余全绿
- [ ] 真机人工抽验：TRAY 关窗后可从托盘 / 快捷键唤回；EXIT 走确认流；自启开关在任务管理器启动项可见（正式验收留 05）
