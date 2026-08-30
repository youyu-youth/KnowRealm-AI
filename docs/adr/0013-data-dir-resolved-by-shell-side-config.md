# 数据目录位置与首启标记由壳侧外部配置解析

---
Status: accepted（2026-08-30，plan 14 grilling 定稿）
---

数据目录是唯一事实源（ADR-0001），但"数据目录在哪"这一事实本身不能存进数据目录：壳（Tauri）在读到路径之前无法 spawn sidecar，首启判定（是否进向导）更发生在 sidecar 存在之前；换机导入则必须发生在 sidecar 打开数据库之前——解压覆盖自己正持有的 db 文件不可行。**决定**：壳在 `app_config_dir()` 维护 `desktop.json`（`{data_dir, onboarded}`），作为数据目录路径与首启完成标记的唯一存储；导入以 sidecar 启动参数 `--import-archive <zip>` 承载，在 `ensure_data_dir` 之后、获取目录锁与开库之前由 Python zipfile（标准库）完成校验落位；设置页"更改数据目录"由 Rust command 编排——复用安全退出的 sidecar 停止链 → 同盘 rename / 跨盘 copy-then-delete（带进度事件）→ 写回 desktop.json → relaunch。

## Considered Options

| 方案 | 结论 |
|------|------|
| **A. 壳侧 app_config_dir 单 json** | **采纳**——文本可读可备份，Tauri 标准 path API；桌面壳先于 sidecar 存在，天然解决启动时序（先例：Clash Verge Rev） |
| B. Windows 注册表 | 否决——难随用户备份搬移，跨平台差，对开源用户不可见 |
| C. 标记存数据目录内（config/settings.json） | 否决——鸡生蛋：首启判定与路径解析都发生在 sidecar 读到它之前 |
| D. 导入由 Rust 侧解压 zip | 否决——需新增 zip crate 依赖，且 manifest/user_version 校验被迫与 sidecar 的导出实现分裂两处 |

## Consequences

- 壳读取自身配置文件不属于"UI 不直读数据目录"红线的违反（该红线指 WebView 不得绕过 sidecar 访问业务数据目录）。
- `desktop.json` 不随全量导出迁移：换机后新机无此文件，自然进入首启向导；`onboarded` 在向导完成时写入新机本地。
- 用户手工删除数据目录而 desktop.json 仍在：`onboarded=true` 照常启动，等价于老用户清空数据（接受，不做对账）。
- 数据目录锁文件 `.knowrealm.lock`（preserve_lock_file）随目录整体迁移，无需特判。
- sidecar 不感知 desktop.json：仍由命令行 `--data-dir` 接收路径，唯一变化是壳从"写死 home/KnowRealm"改为"读 desktop.json、缺省回退默认路径"。
