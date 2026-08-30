# 04 — 更改数据目录（停止→移动→重启）

**What to build:** 设置页"更改数据目录"：dialog 选**空目录**（不存在可建、非空拒绝）→ 确认弹窗（预告迁移耗时、重启、进行中 AI 任务自动恢复）→ Rust command 编排：复用安全退出的 sidecar 停止链 → 同盘 rename / 跨盘 copy-then-delete（进度事件）→ 写 desktop.json → process 插件 relaunch。失败清理目标半成品、原目录无损、不重启。RUNNING 任务中断由重启后 `recover_interrupted` 自动恢复；目录锁文件随目录整体迁移。

**Blocked by:** 03 — 数据目录分区、desktop.json 与打开目录

**Status:** done（真机项待用户验收）

- [x] dialog 选目录（不存在可创建、非空拒绝）+ 确认弹窗文案（耗时/重启/任务恢复预告）
- [x] Rust `change_data_directory` command：复用安全退出停止链、同盘 rename、跨盘 copy-then-delete+进度事件、desktop.json 写回、relaunch（tauri-plugin-process 引入+权限）
- [x] 失败路径：清理目标半成品、原目录不动、前端报错不重启
- [x] cargo test（移动策略/失败回退可测部分）+ 前端测试（确认/进行中/失败状态机）；pyright/tsc/prettier 全绿
- [ ] 真机人工验收（用户执行）：同盘与跨盘各一次迁移→重启→数据完整；进行中 AI 任务重启后自动恢复；失败注入后原目录无损

> **实现注记（2026-08-30）**：
> - 编排顺序一处微调：跨盘 copy 路径在**删源之前**写 desktop.json（即 copy → 写配置 → 删源）。这样任一环节失败都能靠重启恢复到一致状态：copy 失败原目录完好（清理目标）；配置写回失败时源目录未删（copy 路径回退目标即可）；删源失败时配置已指向完整新目录（重启即生效，残留可手动删）。同盘 rename 路径与工单原序列完全一致。
> - Windows 细节：`fs::rename`（MoveFileEx）不能以目录替换已存在目录 → move 前先摘掉 prepare_target 已验证的空壳目标；跨盘判定用 rename 报错（raw 17 / EXDEV / CrossesDevices）兜底，不用 unstable 的 volume API。
> - 错误协议：`MigrationError`（thiserror）Display = `CODE` 或 `CODE: io 明细`，经 command 的 `serde::Serialize` 以字符串传回，前端 `migrationErrorCopy.ts` 按 `": "` 切分映射文案；错误码全集 `DATA_DIRECTORY_{SAME,NESTED,NOT_EMPTY,MIGRATION_FAILED,CONFIG_WRITE_FAILED,SOURCE_CLEANUP_FAILED}`。
> - 权限：capabilities 仅新增 `dialog:allow-open` 与 `process:allow-restart`；relaunch 走 `services/tauri/lifecycle.ts` 封装（desktop-tauri.md §1）。
> - 门禁实测（2026-08-30）：cargo test 19 例全过、clippy -D warnings 零告警；前端相关 30 例过、tsc 双配置零错、prettier/eslint 净；pyright 仅剩既有 `logging.py` 报错（与本工单无关）。TodoPanel 全量跑的既有抖动经 stash 基线对照确认与本工单无关（单跑通过）。
> - **真机验收发现并已修（2026-08-30）**：tauri dev 下迁移成功但重启后一直白屏——relaunch 出的新进程脱离 tauri CLI，CLI 退出连带杀掉 vite dev server，新进程 WebView 加载 devUrl 失败（sidecar 本身拉起正常，新目录 db shm/wal 有活动为证）。修法：`import.meta.env.DEV` 构建不自动 relaunch，弹窗提示手动重启；生产构建（前端资源内嵌）保持自动 relaunch。
> - **真机验收再发现并已修（2026-08-30）**：迁移成功后开发构建不自动 relaunch，应用停留在"sidecar 已停、前端存活"的窗口期——关窗/托盘退出会被"暂时无法确认录音状态，已取消退出以保护数据"永久拦截（只能靠任务管理器结束），且设置页全部请求 Failed to fetch、重试无响应。修复：新增前端 `restartPending` 标记（迁移成功，或 stop 之后的错误码 `MIGRATION_FAILED`/`CONFIG_WRITE_FAILED`/`SOURCE_CLEANUP_FAILED` 置位；prepare 校验错误不置位，sidecar 仍存活）；安全退出据此跳过录音状态检查——后端已不存在、无录音可保护，未保存速记风险仍保留；dev 的 manualRestart 弹窗改为不可关闭、唯一按钮"退出应用"。生产 relaunch 失败的残留路径同样靠该标记保证可退出。门禁：DataDirectorySection 9 例 + AppShell 生命周期 6 例 + 设置页路由 22 例全过；tsc 双配置/prettier/eslint 净。
