# 03 — 速记快捷键：注册点迁移前端与自定义改键

**What to build:** 先把速记快捷键的注册权从 Rust 迁到前端（经官方 global-shortcut JS API，行为与 11 交付完全等价，Rust 侧注册与事件链孤儿代码同票删除）；再在其上叠加自定义改键——按下即录的组合输入（防中文输入法误录）、改键成功旧键立即失效新键立即生效、系统级冲突提示并保持旧键。（裁决与契约细节见 `.scratch/preferences/spec.md`）

**Blocked by:** 02 — services/tauri 偏好运行时包装模块

**Status:** ready-for-agent

- [ ] `quick_note_shortcut` 键入契约：默认 Ctrl+Alt+N；校验=至少一个修饰键（Ctrl/Alt/Shift/Win）+ 恰一个非修饰键且可被 Tauri 解析，非法 422；api-types 重生成
- [ ] 注册点迁移：启动时前端按偏好经 global-shortcut JS API 注册（经 02 的包装模块），回调直开速记框（不再经 Rust emit 事件链）；启动间隙快捷键不可用（接受）
- [ ] Rust 删除：`SHORTCUT` 常量、`handle_shortcut`、`desktop://open-quick-note` 事件链、`get_desktop_lifecycle_status`（`shortcut_available` 由前端注册结果直接可知）；保留托盘、`exit_application`、`hide_window_temporarily`；capabilities 补 global-shortcut 权限
- [ ] 11 相关测试改写（`AppShell.lifecycle.test.tsx`、lifecycle.rs 单测删改），迁移前后行为等价由测试证明
- [ ] react-hotkeys-hook（useRecordHotkeys）录制控件进入桌面行为小节，含 `isComposing` 输入法防呆
- [ ] 改键时序=试注册新键 → 成功注销旧键 → PUT 持久化；任一步失败回滚旧键并提示
- [ ] 包装边界测试（成功序列 / 注册冲突回滚 / PUT 失败回滚）+ 控件 MSW 测试
- [ ] 真机人工抽验：默认键与改键后均可唤起速记框、旧键失效（正式验收留 05）
