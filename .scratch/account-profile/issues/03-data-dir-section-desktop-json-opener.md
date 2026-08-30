# 03 — 数据目录分区、desktop.json 与打开目录

**What to build:** 壳在 `app_config_dir()` 维护 `desktop.json`（`{data_dir, onboarded}`，ADR-0013）：启动读它解析数据目录（文件缺失/损坏回退 `home/KnowRealm`），sidecar 仍只认 `--data-dir` 参数。设置页新增"数据目录"分区：路径展示（只读）+"打开数据目录"（tauri-plugin-opener，真实打开资源管理器）。opener 引入的同时卸载 shell 插件，`learningAssetExport` 的 open 一并迁移。

**Blocked by:** None — can start immediately

**Status:** done（真机项待用户验收）

- [x] `desktop.json` 读写（Rust，app_config_dir；文件缺失/损坏/字段非法回退默认路径）
- [x] sidecar spawn 的 `--data-dir` 从 desktop.json 解析（替代写死 `home/KnowRealm`）
- [x] opener 插件引入（注册+capabilities 权限）+ `learningAssetExport` open 迁移 + shell 插件与对应权限卸除
- [x] 设置页数据目录分区骨架：路径只读展示+打开按钮；前端获取当前路径的方式（后端只读端点或壳 command）实施时定夺并落注记
- [x] cargo test（desktop.json 解析/回退）+ 前端测试；pyright/tsc/prettier 全绿
- [ ] 真机人工验收（用户执行）：打开按钮在资源管理器打开数据目录；手改 desktop.json 指向新空目录后重启、sidecar 使用该目录

> **实现注记（2026-08-30）**：
> - 前端获取路径走壳 command `get_data_directory`——desktop.json 只经壳 command 暴露当前路径，不进入 sidecar HTTP 契约（注记同见 `services/tauri/dataDirectory.ts`）。
> - 卸除 shell 插件的连带：sidecar spawn 从 shell 插件 CommandChild 迁到 `std::process::Command`；opener 仅授 `opener:allow-open-path`。
> - 门禁实测（2026-08-30）：cargo test 8 例全过（desktop_config 含缺失/损坏/非法回退 2 例）、前端 3 例过、tsc 零错、prettier 净；pyright 仅剩既有 `logging.py` 报错（与本工单无关）。
