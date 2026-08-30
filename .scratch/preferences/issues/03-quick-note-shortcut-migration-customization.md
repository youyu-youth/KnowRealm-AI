# 03 — 速记快捷键：注册点迁移前端与自定义改键

**What to build:** 先把速记快捷键的注册权从 Rust 迁到前端（经官方 global-shortcut JS API，行为与 11 交付完全等价，Rust 侧注册与事件链孤儿代码同票删除）；再在其上叠加自定义改键——按下即录的组合输入（防中文输入法误录）、改键成功旧键立即失效新键立即生效、系统级冲突提示并保持旧键。（裁决与契约细节见 `.scratch/preferences/spec.md`）

**Blocked by:** 02 — services/tauri 偏好运行时包装模块

**Status:** done

- [x] `quick_note_shortcut` 键入契约：默认 Ctrl+Alt+N；校验=至少一个修饰键（Ctrl/Alt/Shift/Win）+ 恰一个非修饰键且可被 Tauri 解析，非法 422；api-types 重生成
- [x] 注册点迁移：启动时前端按偏好经 global-shortcut JS API 注册（经 02 的包装模块），回调直开速记框（不再经 Rust emit 事件链）；启动间隙快捷键不可用（接受）
- [x] Rust 删除：`SHORTCUT` 常量、`handle_shortcut`、`desktop://open-quick-note` 事件链、`get_desktop_lifecycle_status`（`shortcut_available` 由前端注册结果直接可知）；保留托盘、`exit_application`、`hide_window_temporarily`；capabilities 补 global-shortcut 权限
- [x] 11 相关测试改写（`AppShell.lifecycle.test.tsx`、lifecycle.rs 单测删改），迁移前后行为等价由测试证明
- [x] react-hotkeys-hook（useRecordHotkeys）录制控件进入桌面行为小节，含 `isComposing` 输入法防呆
- [x] 改键时序=试注册新键 → 成功注销旧键 → PUT 持久化；任一步失败回滚旧键并提示
- [x] 包装边界测试（成功序列 / 注册冲突回滚 / PUT 失败回滚）+ 控件 MSW 测试
- [ ] 真机人工抽验：默认键与改键后均可唤起速记框、旧键失效（正式验收留 05）

## 实现注记（2026-08-30）

- **校验器来源**：Python 白名单逐 token 对照 global-hotkey 0.8（Tauri global-shortcut 底层）`hotkey.rs` 的 `parse_key`/`parse_hotkey` 源码抄录；修饰键表本就无 META/WIN（仅 OPTION/ALT、CONTROL/CTRL、COMMAND/CMD/SUPER、SHIFT、CMDORCTRL 变体），故 `Meta+X` 422 是忠实镜像而非遗漏；`Ctrl+N+A`/`N+Ctrl` 422 对应 Tauri 的 InvalidFormat（修饰键须在前且恰一主键）。白名单与前端 `shortcutAccelerator.ts` 的 KEY_CODES/MODIFIER_CODES 是跨语言双份维护（注释互指），扩键集需两侧同步。
- **useRecordHotkeys 产物格式坑**（v5.3.3 源码核实）：录制产物不是裸 event.code——修饰键先进别名表（ControlLeft→ctrl、MetaLeft→meta），其余小写并剥掉首个 `key|digit|numpad` 子串（KeyP→p、Digit1→1、Numpad1→1）。映射表按此格式编写；小键盘数字与主行数字不可区分（都录为数字），小键盘运算符/媒体键落白名单外报「不支持的按键」。
- **挂载/改键竞态防护**（code-review 双轴均点名，已修+测试）：①mount 以 `isRegistered` 前置去重——改键完成后偏好缓存刷新触发的重挂不会对已注册键重复 register（会失败并误报不可用）；②mount 在途落定时若改键已换键则撤销本次注册；③rebind 的旧键读取后移到新键注册成功之后，覆盖在途挂载落定的键。对应三个编排用例（holdRegister/releaseRegister 门闩）。
- **capabilities** 补齐 spec 字面三项：register/unregister/isRegistered（isRegistered 因竞态防护实际用上了）。
- **Esc 取消录制**：spec 只要求 isComposing 防呆，Esc 取消与「取消」按钮是录制控件可用性补充（按错组合有反悔途径），code-review 标为 scope creep，明示保留。isComposing 防呆实现为 capture 阶段 window 守卫拦截（stopPropagation 后 document 冒泡阶段的 hook 监听收不到）。
- **closeBehaviorRef 改写**（02 交付物，非本票范畴）：02 的渲染期 `ref.current =` 赋值在当前 eslint `react-hooks/refs` 规则下报错、阻塞本票 lint 门禁，改为 useEffect 内赋值；渲染到提交之间的极窄窗口读到的旧值也是合法策略值，行为等价。`local_config.py` 中 close_behavior 三元折叠为当前 ruff format 版本强制（HEAD 的展开形态是旧工具产物）。
- **conflict 语义**：register 失败统一按「已被其他应用占用」提示（spec 故事 19 的冲突语义）；键已过后端+映射双重白名单，解析失败不可能，瞬时系统故障罕见，接受不细分。
- **门禁**：桌面 vitest 221 全绿 / tsc / eslint / prettier；后端 pytest 297 全绿 / ruff / api-types check；cargo test 6 全绿 / clippy。pyright 仅剩既有 logging.py:46 遗留。`fireQuickNote` 参数按 desktop-react.md §3 用字面量联合（code-review 指出后修正）。
- 真机人工抽验按 02 先例随 05 人工验收一并执行（上项保留未勾）。
