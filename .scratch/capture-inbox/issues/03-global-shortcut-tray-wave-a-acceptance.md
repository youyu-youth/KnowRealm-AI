# 03 — 全局速记、托盘安全退出与 Wave A 验收

**What to build:** 让速记成为真正可长期驻留的 Windows 桌面能力：关闭窗口后应用继续运行，Ctrl+Alt+N 或托盘可重新显示并聚焦主窗口、打开唯一速记框，快捷键冲突不阻断应用；真正退出会保护活动录音和未保存文本并完整停止 sidecar。该票同时回归前两票的真实捕获、Inbox、归类和升级链路，以自动化、真实 HTTP、真实 Windows/Tauri 和实际渲染分别证明整个 Wave A 出口可交付。

**Blocked by:** 02 — 归类、升级与 Summary/HITL 交接.

**Status:** done

- [x] 初始化仓库已经安装的全局快捷键能力并注册固定 Ctrl+Alt+N；不读取或写入偏好配置，不提前实现快捷键自定义或开机自启。
- [x] 快捷键注册冲突或系统错误不阻止应用、sidecar 和应用内速记入口启动；当前应用会话只显示一次可理解的冲突提示。
- [x] 快捷键触发时显示并聚焦主窗口，再打开 QUICK_NOTE 模式；窗口已显示或速记框已打开时复用现有窗口与 Dialog，不叠加输入框。
- [x] 主窗口关闭请求转换为隐藏，不停止 sidecar、worker、快捷键或 recording session 恢复事实；从任务栏关闭和窗口关闭按钮保持一致。
- [x] 系统托盘最小菜单只提供“显示”和“退出”；显示动作恢复并聚焦主窗口，不增加设置、最近内容或其他推测功能。
- [x] 托盘退出先向前端请求安全判断；没有 RECORDING/PAUSED 会话且文本捕获框没有未保存正文时直接真正退出。
- [x] 存在活动录音时显示主窗口并明确提示最新未提交的内存分片可能丢失、已提交分片仍可恢复；取消后录音与应用继续运行。
- [x] 存在未保存速记或粘贴时显示主窗口并明确提示正文将丢失；同时存在两类风险时使用一个完整确认对话框，不串联重复确认。
- [x] 用户取消退出后窗口保持可见且数据不变；用户明确确认后执行 Tauri 退出并沿用既有退出清理完整停止 sidecar，不残留后台进程。
- [x] 原生层不缓存业务 recording session 或文本正文；录音事实继续来自现有 Query，未保存正文继续属于前端临时 UI 状态。
- [x] 优先复用现有 Tauri 与插件；如托盘能力需要启用现有 Tauri feature，只修改现有依赖声明，不安装新的第三方包或常驻辅助程序。
- [x] 全局事件、关闭隐藏、托盘显示与退出命令使用最小原生接口；不向 WebView 开放数据目录写权限，也不改变 sidecar 作为 SQLite 唯一写者的边界。
- [x] 为可独立表达的原生策略留下最小 Rust 测试或高层自动化：安全退出/需确认、取消/确认、重复快捷键不叠加；不得为测试搭建通用窗口状态框架。
- [x] 桌面测试覆盖原生事件 mock 后的显示、聚焦、唯一速记框、冲突提示、退出风险组合、取消与确认，以及捕获正文保留和键盘焦点。
- [x] 回归票 01：QUICK_NOTE/PASTE、1 MiB、所有 Capture Batch 来源课程可选、未归类真实状态、Inbox 查询/轮询/导航/重试/删除、重启持久化和零 Summary 调用全部通过。
- [x] 回归票 02：纯归类零 LLM、升级单个活动 Job、NOTE 编辑、COURSE_REQUIRED、详情升级、Provider/同意阻塞和本地提交不回滚全部通过。
- [x] 完成全仓 Python、桌面与 Rust 自动化门禁，包括 pytest、Ruff、Pyright、OpenAPI 生成一致性、桌面 test/lint/build、Rust fmt/check/clippy/build、格式检查及 `git diff --check`。
- [x] 使用真实 localhost socket 回归“文本捕获 → Inbox → 归类/升级 → 重启持久化”，并把 ASGI、真实 HTTP、MSW 与 SQLite 证据分别报告。
- [x] 真实 Windows/Tauri 验收关窗后进程仍在、隐藏状态 Ctrl+Alt+N 显示并聚焦、重复快捷键不叠加、实际快捷键冲突不阻断启动、托盘显示恢复窗口。
- [x] 真实 Windows/Tauri 验收无风险退出立即停止 sidecar、活动录音退出提示、未保存文本退出提示、组合风险提示、取消后继续运行、确认后进程完全退出。
- [x] 活动录音退出并重启后只声明已提交分片的既有恢复能力；不得把最新内存分片、长时后台录音或本票未验证的分片连续性报告为已通过。
- [x] 实际渲染检查覆盖 1440×900、1280×800、1099×720、亮色/深色、长中文标题、hover、focus、disabled、错误态和无整体横向溢出；不得以构建成功代替渲染证据。
- [x] 最终报告明确区分自动化、fake Provider、真实 localhost HTTP、真实 Windows/Tauri、实际渲染与既有 ASR 证据；本票不发起新的真实腾讯 ASR 或真实外部 LLM 请求。
- [x] Wave B 批量归类/筛选、分页、重新归类、快捷键自定义、开机自启、自动归类建议、网页剪藏及新 Provider 能力保持未实现，不以验收票名义扩入。

## 实施记录

- 原生层复用现有 Tauri 与 global-shortcut 插件，仅启用 `tray-icon` feature；固定快捷键、关闭隐藏、最小托盘和真正退出保持在一个窄生命周期模块内。
- 前端退出前重新读取活动录音事实，只在临时 UI 中跟踪未保存正文；重复快捷键复用现有 Dialog 并恢复正文焦点。
- 自动化通过：backend 213、desktop 159、Rust 7；Ruff、OpenAPI、ESLint、desktop build、Rust fmt/check/clippy/build 与 `git diff --check` 通过。全量 Pyright 仅保留既有 `backend/app/core/logging.py:46` 错误；全量 Prettier 仍有 64 个既有非本票文件，所有本票前端文件已单独通过。
- 真实 localhost HTTP 覆盖捕获、Inbox、归类/升级与持久化；真实 Windows/Tauri 覆盖关窗隐藏、全局快捷键、冲突降级、托盘显示、三类退出风险、取消/确认与 sidecar 完整退出。
- 实际渲染覆盖 1440×900、1280×800、1099×720 的明暗主题、长中文内容、hover/focus/disabled/error 与无整体横向溢出。
- 未发起新的腾讯 ASR 或外部 LLM；活动录音验收使用真实本地 sidecar/SQLite 会话但未授权麦克风，不能证明最新内存分片或音频连续性。
