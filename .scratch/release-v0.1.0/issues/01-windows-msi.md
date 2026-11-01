# v0.1.0 Windows 首发

Status: ready-for-agent

来源：main 的 17b39a0653922aa9824286e0b92c6f6da22f8cd3，只补发布必需的打包连接。
用户已授权以 main 最终提交创建 v0.1.0 标签并发布 GitHub Release。
不新增产品能力，Agent 继续复用原 Tool/API/Service，无新增权限或模型调用。

## 验收路径

锁文件安装 → PyInstaller 后端目录包 → Tauri MSI → Release 附件 → 重新下载并核对 SHA256 → Windows 安装/解包 → 正式桌面与后端启动 → API/SQLite 持久化与重启。
测试使用本次独立临时数据目录，不能让旧版打开开发分支的数据库。真实模型、另一台干净电脑和 Windows 各档系统缩放分别记录，不以构建通过代替。

- [ ] 后端包包含运行时、迁移、分词数据及动态导入依赖
- [ ] 正式桌面只传业务启动参数，开发模式保留 python -m app.server
- [ ] 相关现有回归、类型/格式检查与 MSI 构建
- [ ] 打包后的真实 API/SQLite/FFmpeg 和桌面启动验证
- [ ] main 推送，v0.1.0 标签与附件版本一致
- [ ] Release 下载 SHA256、安装与重启验证
- [ ] 干净 Windows 电脑、真实模型及系统缩放验收（人工）

## Comments

2026-11-01：在 E:/workspace/project/my/KnowRealm-AI-release-v0.1.0 独立工作目录直接检出 main，保留原开发分支与目录。
