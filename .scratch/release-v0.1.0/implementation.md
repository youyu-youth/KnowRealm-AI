# v0.1.0 Windows 首发记录

## 范围

- 基点 main：17b39a0653922aa9824286e0b92c6f6da22f8cd3，不合入后续 Chat 工作台开发。
- 新增 PyInstaller 构建依赖组与 prepare-sidecar.ps1，使用目录包避免每次启动解压整个后端。
- 发布入口：pnpm --filter @knowrealm/desktop release:msi。独立发布配置包含后端程序、运行时和 57 份迁移；原有 FFmpeg 及许可证继续随包。
- Rust 正式版直接执行后端程序，开发模式保留 python -m app.server。不新增产品 API、模型调用或权限。
- 用户授权直接在 main 完成首发，由 v0.1.0 标签固定提交。

## 验证

- PASS：独立 pnpm frozen 安装与 uv 锁文件安装；运行时依赖版本保持原样，仅增加构建工具。
- PASS：scripts/check-changed.ps1，前端全量 lint、格式、生产构建，后端 Ruff、格式和 Pyright。
- PASS：发布配置与 package.json Prettier；PowerShell 打包脚本解析和生成物自检。
- PASS：cargo test --release --features tauri/custom-protocol --lib sidecar::tests，4 项通过；cargo clippy --release --features tauri/custom-protocol -- -D warnings 通过。
- PASS：真实 PyInstaller 后端与 MSI 安装目录分别在空 PATH 下验证访问保护、新建课程、粘贴记录、中文搜索、TXT/PDF/DOCX 导入、FFmpeg 转码及重启持久化，SQLite 完整性正常，user_version=57。
- PASS：Windows MSI 安装成功（退出码 0）；本机无管理员权限，使用 ALLUSERS=""、MSIINSTALLPERUSER=1 安装到当前用户 Programs/KnowRealm。
- PASS：真实安装版 Tauri/WebView2 完成四步首启向导，进入今日页。测试使用临时数据，退出后恢复原 desktop.json 与窗口配置。
- 首轮真实进程回归：13 通过、2 启动限时失败。日志：.pytest-tmp-runs/20261101T123524Z-64bb9e6d/backend/。
- 原始 main 独立环境复测两失败用例：双进程检查仍在依赖导入前超出 10 秒，归档拒绝通过。证据：E:/workspace/project/my/KnowRealm-AI-release-baseline-17b39a0/.pytest-tmp-runs/20261101T124556Z-78fa46e1/backend/。
- 发布工作区两用例复测同为 1 失败、1 通过，保留原超时和失败，不扩大等待上限。日志：.pytest-tmp-runs/20261101T124847Z-21c5d22e/backend/。
- cargo fmt --check 发现既有 data_migration.rs 和 sidecar.rs 迁移段格式差异；本次未改这些段落，未顺手全库格式化。
- 首次封装因提前启动测试程序占用输入文件而失败；退出后重新运行 tauri bundle 成功。重复封装提示 bundle type 标记已被先前构建替换；本产品未接自动更新。
- NOT_RUN：完整前后端测试、真实模型/腾讯 ASR、另一台无开发环境的 Windows、默认管理员安装界面、真实系统缩放矩阵。

## 发布与数据边界

- MSI：KnowRealm_0.1.0_x64_en-US.msi，安装包未代码签名。
- 本机现用开发数据库为 63，首版仅支持到 57；验收不打开或降级开发数据库，不改变原数据目录配置。
- GitHub Release 附 MSI 与 SHA256SUMS.txt，正式发布前重新下载并比对安装包散列值。
- 临时驱动器、测试数据、日志及安装包均不加入提交。未修改规范/权威需求文件。
