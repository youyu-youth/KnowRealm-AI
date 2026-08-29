# 13 - 偏好设置

> Wave: B ｜ PRD: §4.1 偏好设置行 ｜ 决策引用: #51（v2.0 单一本地配置；2026-08-29 grilling 修订：窗口几何豁免、桌面行为消费走 Tauri 官方件）

## 功能描述 / 目标

单一本地配置 `config/settings.json` 的落地：偏好 + 本机行为合一读写（v2.0 合并原 user_settings / local_settings，无漫游概念）。选型原则：涉及桌面行为一律优先 Tauri 官方插件/API，不自写轮子（技术栈文档 v4.4）。

## 功能范围

**做（除窗口几何外全部写 config/settings.json，缺键=默认、未知键保留，即时生效）**：
- 深色模式 LIGHT/DARK/SYSTEM——`theme.css` 三态机制已就绪（`.dark`/`.light`/media query 自动跟随），切换=挂/摘 class
- 字体大小 S/M/L——根字号 15/16/18px，token 全 rem 等比缩放
- 时区：null=跟随系统（默认），可覆盖存 IANA 名；P4 复习提醒才消费，先存后用（列表=原生 `Intl.supportedValuesOf('timeZone')`）
- 关窗行为 TRAY（默认）/ EXIT——前端 `onCloseRequested` 分流，EXIT 复用 11 安全退出确认流，与托盘退出收敛同一 safeExit
- 开机自启（默认关）——官方 autostart 插件（lib.rs 注册 + capabilities 权限）
- 速记快捷键自定义（默认 Ctrl+Alt+N，供 11 消费）——官方 global-shortcut JS API 前端动态注册/注销；react-hotkeys-hook（useRecordHotkeys）录制控件，防中文输入法 `isComposing` 误录
- 上次界面恢复（`last_route`）：记忆除设置页外的最后路由，启动恢复，恢复失败兜底首页（术语见 CONTEXT.md「上次界面恢复」）
- 默认习题数量（`quiz_last_count` 迁入偏好分区，与习题生成对话框双入口同键同缓存）
- 窗口记忆（尺寸/位置/最大化）——官方 window-state 插件，**唯一豁免 settings.json**

**不做**：
- 语言切换（V1 隐藏；locale 字段不落——i18n 硬编码 zh，第二语言进 plan 时再引入）
- 图表/代码高亮双主题色板（存量页面随 theme 三态 CSS 变量自动跟随；专用色板随 17 等真实消费者交付，不预做）
- 关窗「每次询问」第三选项
- "数据与隐私"页（P2 细化）

## 核心业务流程

设置页偏好分区（单分区三小节：外观 / 桌面行为 / 通用）→ 控件级即改即存（PUT `/api/settings/preferences` 全字段 optional 部分更新，无保存按钮，失败行内报错并回显服务端事实）→ 前端即时应用（theme class / 根字号 / 官方插件 API）→ 重启保持

## 关键业务规则

- 全部偏好仅存 `config/settings.json`，不落第三处状态（#51）；换机随全量导出包迁移（14）——**窗口几何除外**：window-state 插件存自身配置文件，机器本地、不随导出迁移（desktop-ui.md 已同步修订）
- 桌面行为消费点在前端、写入者唯一=sidecar：快捷键注册/注销/冲突检测=global-shortcut JS API、关窗分流=`onCloseRequested`+`preventClose`+`hide`、自启=autostart 插件 JS API、窗口记忆=window-state 插件；**Rust 不新增偏好命令**
- 快捷键改键时序：试注册新键 → 成功注销旧键 → PUT 持久化；任一步失败回滚旧键并提示。键位规则=至少一个修饰键（Ctrl/Alt/Shift/Win）+ 一个非修饰键
- Rust 侧 11 交付的 `const SHORTCUT` / `handle_shortcut` / `desktop://open-quick-note` 事件链 / `on_window_event` / `get_desktop_lifecycle_status` 随注册点迁移删除（本次改动产生的孤儿代码）；托盘、`exit_application`、`hide_window_temporarily` 保留；11 相关测试（`AppShell.lifecycle.test.tsx`、lifecycle.rs 单测）同步改写
- 前端启动后按偏好完成快捷键注册与关窗策略挂载：启动间隙内快捷键不可用、关窗=直接退出（均接受，不做 Rust 兜底双轨）
- 深色模式全应用跟随：存量页面由 `theme.css` 双套 CSS 变量自动驱动；首帧按 SYSTEM 渲染、偏好到达后应用，接受一次骨架变色
- 时区/字号等存而未用的字段只保证存取正确，不伪造消费者

## 前置依赖

- 设置页框架已存在（原 P0-05 已随 Phase 0 取缔消解；现含档案分区）
- 11 已交付托盘、固定快捷键、关窗驻留与安全退出流——13 在其上接管可配置化，并把快捷键注册点迁移至前端

## 验收标准（出口线）

- [ ] 深色模式 LIGHT/DARK/SYSTEM 即时生效，SYSTEM 跟随 OS 变化，重启保持
- [ ] 字号 S/M/L 即时生效，重启保持
- [ ] 修改速记快捷键后新键生效（旧键失效）；系统级冲突提示并保持旧键
- [ ] 关窗行为 TRAY/EXIT 即时切换：TRAY 驻留托盘可从托盘/快捷键唤回；EXIT 复用安全退出确认流
- [ ] 开机自启开关真实写入/移除 OS 启动项
- [ ] 窗口尺寸/位置/最大化重启恢复；显示器拔除夹回可见区域（插件行为）
- [ ] 启动恢复上次界面（非设置页最后路由），恢复失败兜底首页
- [ ] 偏好持久化于 config/settings.json（缺键=默认、未知键保留）；窗口几何除外（插件自身文件）
- [ ] quiz_last_count 偏好分区与习题生成对话框双入口一致

## 选型记录（2026-08-29 grilling 定稿，先例：Clash Verge Rev）

| 能力 | 选型 | 备注 |
|---|---|---|
| 快捷键动态注册/冲突 | tauri-plugin-global-shortcut v2 JS API | 零新依赖（插件已装），补 capabilities 权限 |
| 关窗行为 | Tauri `onCloseRequested` + `preventClose` + `hide` | 与托盘退出收敛同一 safeExit |
| 开机自启 | tauri-plugin-autostart | lib.rs 注册 + capabilities |
| 窗口记忆 | tauri-plugin-window-state | #51 窗口几何豁免（desktop-ui.md 已修订） |
| 热键录制控件 | react-hotkeys-hook（useRecordHotkeys） | 唯一新前端依赖 |
| 时区列表 | 原生 `Intl.supportedValuesOf('timeZone')` | 不引 react-timezone-select |
| 主题三态 | 自有 `theme.css`（shadcn 标准三态） | 不引 next-themes（自带存储与后端持久化冲突） |
