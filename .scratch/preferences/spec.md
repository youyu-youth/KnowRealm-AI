# 偏好设置

Status: ready-for-agent

## Problem Statement

KnowRealm 的设置页目前只有「个人档案」一个分区。关窗驻留托盘与速记快捷键 Ctrl+Alt+N 是 11 交付时的**硬编码**行为——用户改不了；深色模式、字体大小、时区、开机自启、界面恢复等偏好在 PRD §4.1（决策 #51：单一本地配置 `config/settings.json`）里承诺过，但没有任何设置入口。用户对应用外观与桌面行为的控制权为零：想换深色只能等系统、想换快捷键只能忍着冲突、怕关窗打断速记却不敢改任何东西。

## Solution

设置页新增「偏好」分区（单分区三小节：**外观**＝深色模式 + 字体大小；**桌面行为**＝关窗行为 + 开机自启 + 速记快捷键；**通用**＝时区 + 默认习题数量）。除窗口几何外全部偏好存 `config/settings.json`（经 sidecar API 读写，缺键=默认、未知键保留），**控件级即改即存**（无保存按钮，失败行内报错并回显服务端事实），重启保持。

桌面行为的消费一律走 **Tauri 官方件**（2026-08-29 grailing 定稿，技术栈 v4.4）：快捷键注册/注销/冲突检测=global-shortcut 插件 JS API（前端）、关窗分流=`onCloseRequested`、开机自启=autostart 插件、窗口记忆=window-state 插件（**#51 唯一豁免**：窗口几何存插件自身配置文件，机器本地、不随导出迁移）。Rust 侧不新增偏好命令，11 交付的 Rust 侧注册/关窗硬编码随之删除。

## User Stories

1. As an 学习者, I want to 在设置里选择浅色 / 深色 / 跟随系统三种外观, so that 不同光线环境与个人习惯下都舒适。
2. As an 学习者, I want to 切换深色模式后全应用立即变色, so that 不用重启或刷新就能看到效果。
3. As an 学习者, I want to 选「跟随系统」时应用随 Windows 深浅色自动切换, so that 与系统外观保持一致、不用手动跟。
4. As an 学习者, I want to 我的外观选择重启后保持, so that 每次打开都是我喜欢的样子。
5. As an 学习者, I want to 在小 / 中 / 大三档字号间切换, so that 屏幕距离与视力情况不同也能舒服阅读。
6. As an 学习者, I want to 字号切换即时生效且布局不破, so that 调整过程所见即所得。
7. As an 学习者, I want to 字号选择重启后保持, so that 不用每次重新调。
8. As an 学习者, I want to 时区默认跟随系统, so that 不设置也正确。
9. As an 学习者, I want to 需要时手动覆盖时区, so that 人在异地或习惯不同时时间显示符合预期。
10. As an 学习者, I want to 时区设置被安全保存等待未来的复习提醒使用, so that 到时候不用再配置一遍。
11. As an 学习者, I want to 点窗口关闭钮默认驻留托盘, so that 速记快捷键与后台处理不因随手关窗中断。
12. As an 学习者, I want to 可把关窗行为改成直接退出, so that 不想常驻时的选择权在我。
13. As an 学习者, I want to 退出时若有活动录音或未保存文本先确认, so that 误关不丢数据。
14. As an 学习者, I want to 可选择开机自启（默认关）, so that 常用时不必每次手动找图标启动。
15. As an 学习者, I want to 自启开关真实写入 / 移除系统启动项, so that 设置即生效、不骗人。
16. As an 学习者, I want to 速记快捷键默认 Ctrl+Alt+N, so that 装好即用、零配置。
17. As an 学习者, I want to 自定义速记快捷键, so that 与其他软件冲突或习惯不同时可以换。
18. As an 学习者, I want to 改键时按"按下即录"的方式输入组合, so that 不用背键名格式。
19. As an 学习者, I want to 新键与系统其他全局热键冲突时得到提示且旧键保留, so that 改键失败不把快捷键弄丢。
20. As an 学习者, I want to 改键成功后旧键立即失效、新键立即生效, so that 不会出现两个键都能唤起。
21. As an 学习者, I want to 中文输入法开着时录制不受干扰, so that 录到的组合就是我要的组合。
22. As an 学习者, I want to 重启应用回到上次停留的页面（设置页除外）, so that 继续上次的工作不用重新点进去。
23. As an 学习者, I want to 上次页面已不存在时回到默认页, so that 不会打开一个错误界面。
24. As an 学习者, I want to 在偏好里设置默认习题生成数量, so that 每次生成不必重复选档。
25. As an 学习者, I want to 偏好里的数量与习题生成对话框的记忆始终一致, so that 两处改动不打架。
26. As an 学习者, I want to 窗口大小、位置与最大化状态重启恢复, so that 工作台布局保持我的习惯。
27. As an 学习者, I want to 拔掉外接显示器后窗口回到可见区域, so that 窗口不会丢在屏幕外。
28. As an 学习者, I want to 所有偏好改动即时保存、无需点保存按钮, so that 改完就走不会忘保存。
29. As an 学习者, I want to 保存失败时看到明确错误且界面回到真实值, so that 不会误以为已保存。
30. As an 学习者, I want to 偏好随全量导出包迁移到新机（窗口几何除外）, so that 换机不用重新配置。

## Implementation Decisions

### 存储与契约（后端）

- `config/settings.json` 扁平键：`theme`（LIGHT/DARK/SYSTEM，默认 SYSTEM）、`font_scale`（S/M/L，默认 M）、`timezone`（IANA 名或 null=null 跟随系统）、`close_behavior`（TRAY/EXIT，默认 TRAY）、`autostart`（bool，默认 false）、`quick_note_shortcut`（accelerator 串，默认 "Ctrl+Alt+N"）、`last_route`（路由串或 null）；既有 `quiz_last_count` 与两个 consent 键原样共存。
- **缺键即默认**，首启不回写默认值；读改写机制天然保留未知键（consent 不被冲掉）。
- `PUT /api/settings/preferences` 改为**全字段 optional 部分更新**（merge 语义，保留 PUT 动词），响应恒返回全量 `PreferencesOut`；现有 quiz_last_count 调用方传法不变、天然兼容。
- 校验：枚举字段白名单拒绝；快捷键串必须"≥1 个修饰键（Ctrl/Alt/Shift/Win）+ 恰一个非修饰键"且可被 Tauri 解析；timezone 必须是 `Intl.supportedValuesOf('timeZone')` 合法值或 null；非法 422。
- OpenAPI → api-types 重新生成。

### 前端（设置页与外观应用）

- 设置页新增「偏好」分区（三小节：外观 / 桌面行为 / 通用），与档案分区的按钮式保存并存；偏好全部**控件级即改即存**，失败行内报错并回显服务端事实。
- 主题应用器：DARK=挂 `.dark`、LIGHT=挂 `.light`、SYSTEM=双摘（`prefers-color-scheme` 自动跟随，`theme.css` 三态机制已就绪）；首帧按 SYSTEM 渲染、偏好到达后应用，接受一次骨架变色，不做阻塞预取。
- 字号：根字号 15/16/18px（S/M/L），token 全 rem 等比缩放；M=不写键。
- 时区控件：搜索式下拉（Combobox），数据源=原生 `Intl.supportedValuesOf('timeZone')`，默认项「跟随系统」（存 null）。
- 上次界面恢复：路由变化时写 `last_route`（**设置页路由不参与记忆**），启动时恢复，目标不存在由现有 NotFound/错误态兜底回首页。
- `quiz_last_count` 双入口（偏好分区 + 习题生成对话框）写同一键、统一失效同一 query key。
- 热键录制控件：react-hotkeys-hook `useRecordHotkeys` + 中文输入法 `isComposing` 防呆；提交时序=**试注册新键 → 成功注销旧键 → PUT 持久化**，任一步失败回滚旧键并提示。

### Tauri 运行时包装（新模块，单一新接缝）

- `services/tauri/` 下新增偏好运行时包装（沿 `lifecycle.ts` 的 `isTauri` 守卫先例），收拢全部官方件调用：global-shortcut 注册/注销、`onCloseRequested` 挂载、autostart enable/disable、（消费方）window-state 由插件自理无需包装。
- 关窗分流：TRAY=`preventClose` + `hide`；EXIT=收敛到与托盘退出**同一个 safeExit**（活动录音/未保存文本确认 → 退出命令）。
- 前端启动后按偏好完成快捷键注册与关窗策略挂载；启动间隙内快捷键不可用、关窗=直接退出（接受，不做 Rust 兜底双轨）。
- capabilities 补 global-shortcut（register/unregister/isRegistered）与 autostart、window-state 权限。

### Rust（删代码 + 注册插件）

- 删除：`SHORTCUT` 常量、`handle_shortcut`、`desktop://open-quick-note` 事件链、`on_window_event` 关窗处理、`get_desktop_lifecycle_status`（`shortcut_available` 改由前端注册结果直接可知）——均为注册点迁移产生的孤儿代码。
- 保留：托盘（显示/退出）、`exit_application`、`hide_window_temporarily`（录音最小化在用）。
- builder 注册 `tauri_plugin_autostart` 与 `tauri_plugin_window_state`（依赖已装/新增，见技术栈 v4.4）；窗口几何恢复、最大化、显示器夹回全部由插件承担，Rust 不持有偏好逻辑。

### 测试接缝（已与用户确认）

五接缝：①后端 HTTP API（pytest+临时数据目录）；②前端 Vitest+RTL+MSW；③Tauri 运行时包装边界（假 Tauri API 注入）；④Rust cargo test 仅回归（无新接缝）；⑤真机验收**人工执行**。

## Testing Decisions

- 好测试只断言**接缝上的外部行为**（HTTP 响应与文件落盘、渲染结果与请求负载、包装边界收到的调用序列），不断言内部实现细节。
- 后端：沿 settings/preferences 既有 pytest 接丝——部分更新合并、缺键默认、未知键（consent）保留、校验矩阵（枚举×快捷键格式×时区合法性）、写后读回等价。
- 前端：沿面板 MSW 先例——分区渲染、每控件即改即存负载、失败回显、主题 class/根字号应用、路由记忆排除设置页、双入口缓存同步。
- 包装边界：沿 `AppShell.lifecycle.test.tsx` 对 `services/tauri` 的 mock 先例——改键时序（成功/冲突回滚/PUT 失败回滚）、关窗分流、启动挂载顺序。
- Rust：被删代码的单测同步删除，剩余 cargo test 全绿即为门禁；不为插件注册写新单测。
- 真机验收（人工）：按 13 号计划九条验收标准执行——真实快捷键冲突、托盘驻留/退出、OS 启动项、跨重启窗口几何与显示器拔除、OS 主题跟随。自动化通过不得宣称为真机验收。

## Out of Scope

- 语言切换与 `locale` 字段（V1 隐藏；i18n 硬编码 zh，第二语言进 plan 时再引入）
- 图表 / 代码高亮**专用**双主题色板（存量页面随 theme 三态 CSS 变量自动跟随；色板随 17 等真实消费者交付）
- 关窗「每次询问」第三选项
- 「数据与隐私」页（P2 细化）
- 时区的行为消费者（P4 复习提醒；本票只保证存取正确）
- 窗口几何跨机迁移（机器本地，不进导出包）
- 自启状态启动对账（用户在系统层手动禁用导致的漂移不处理）
- Rust 侧新增任何偏好命令；settings.json 之外的第二处偏好存储
- PRD 决策表 #51 行的原文改写（随下次 PRD 升版并入；豁免权威表述已在 desktop-ui.md / 技术栈 v4.4）

## Further Notes

- 共识回写已完成（2026-08-29）：`CONTEXT.md` 新术语「上次界面恢复（Last Route）」；`docs/rules/desktop-ui.md` 偏好规则修订（窗口几何豁免 + Tauri 官方件消费）；技术栈文档升 v4.4；13 号功能计划重写定稿。
- 先例：Clash Verge Rev（Tauri 2，关窗驻留/自启偏好存自家 verge.yaml，与本项目 settings.json 同构）。
- 实现时 11 的相关测试（`AppShell.lifecycle.test.tsx`、lifecycle.rs 单测）随注册点迁移改写；速记框打开路径从「Rust emit 事件」改为「JS 注册回调直调」。
- 唯一新前端依赖 react-hotkeys-hook；唯一新 Tauri 插件 window-state（autostart 依赖已装未接线）。
