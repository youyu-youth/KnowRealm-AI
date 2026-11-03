# KnowRealm-AI ![平台：Windows x64](https://img.shields.io/badge/Windows-x64-0078D4)

[![Tauri 2](https://img.shields.io/badge/Tauri-2-24C8D8)](apps/desktop/src-tauri/Cargo.toml) [![React 19](https://img.shields.io/badge/React-19-149ECA)](apps/desktop/package.json)

[English](README.md) | **简体中文**

KnowRealm-AI 是本地优先的个人学习与 AI 工作台，帮助学生、程序员、职场人士和终身学习者收集材料、整理知识，并通过自然语言完成学习任务。

<p align="center">
  <img src="apps/desktop/src-tauri/icons/128x128.png" width="88" height="88" alt="KnowRealm 应用图标" />
</p>

**[下载 Windows 版](https://github.com/youyu-youth/KnowRealm-AI/releases/latest)** | [快速开始](#安装与快速开始) | [常见问题](#常见问题) | [源码开发](#源码开发) | [问题反馈](https://github.com/youyu-youth/KnowRealm-AI/issues)

无需注册账号，学习数据保存在本机可查看、可迁移的目录中。当前提供 Windows x64 桌面安装包，无需单独部署服务器。项目持续开发中，发布版功能与限制以对应的[版本说明](https://github.com/youyu-youth/KnowRealm-AI/releases)为准。

## 功能概览

| 功能         | 可以做什么                                                                                                     |
| ------------ | -------------------------------------------------------------------------------------------------------------- |
| 统一捕获     | 课堂录音、导入音频与文档、粘贴文本、闪念速记和网页剪藏                                                         |
| 内容整理     | 将材料转写或解析为正文，生成总结，经确认后形成知识点、习题、待办和复习资料                                     |
| 知识空间     | 按课程和学习场景组织记录，查看课程概念图谱与知识关联                                                           |
| 资产库与搜索 | 集中浏览资料来源、学习记录和已确认资产，筛选、归类并搜索本地内容                                               |
| AI 对话      | 在指定资料范围内提问，查看回答引用并返回来源；可选开启联网搜索                                                 |
| AI 助手执行  | 让通用助手查询或创建课程、添加文本记录、制定和调整学习计划，按授权方式执行并返回结果；知识助手专注只读资料问答 |
| 练习与复习   | 生成习题、进行模拟测试、整理复习资料，并跟踪学习证据与概念掌握情况                                             |
| 桌面体验     | 明暗主题、中英文界面、全局搜索、速记快捷键和托盘常驻                                                           |

从捕获材料开始，经过转写或解析、总结与确认，逐步形成可编辑、可追溯的学习内容，用于检索、问答、练习和复习。

## 界面预览

### 知识空间（深色主题）

按职业技能、学业学习和兴趣自学组织课程，支持轨道、列表和卡片视图。

![KnowRealm 知识空间深色主题桌面截图](docs/img/desktop/PixPin_2026-10-30_15-00-47.png)

### 资产库（浅色主题）

在同一工作区浏览文档、音频、学习记录与学习资产，并按课程和类型筛选。

![KnowRealm 资产库浅色主题桌面截图](docs/img/desktop/PixPin_2026-10-30_15-01-41.png)

> [!NOTE]
> 截图中的部分统计、学习进度和音频波形为界面示意，应用内有相应标注。

## 安装与快速开始

### 1. 安装桌面应用

前往 [GitHub Releases](https://github.com/youyu-youth/KnowRealm-AI/releases)，下载 Windows x64 的 `.msi` 安装包并运行。安装包已包含本地后端和 FFmpeg，无需安装 Python、Node.js 或开发工具；桌面界面依赖 WebView2 Runtime。

首次打开应用，按向导选择数据目录并完成设置。发布附件中的 `SHA256SUMS.txt` 可用于核对安装包是否完整。

> [!IMPORTANT]
> v0.1.0 安装包尚未代码签名，Windows 可能显示未知发布者提示。该版本请使用新数据目录，不要用它打开较新开发版的数据；具体兼容限制见 [v0.1.0 发布说明](https://github.com/youyu-youth/KnowRealm-AI/releases/tag/v0.1.0)。

### 2. 配置需要的 AI 服务

在设置中按需填写自己的服务凭据：

| 服务           | 配置内容                                | 用途                                      |
| -------------- | --------------------------------------- | ----------------------------------------- |
| 大语言模型     | OpenAI 兼容接口地址、模型名称和 API Key | AI 对话、总结、知识点、习题及学习计划生成 |
| 腾讯云语音识别 | SecretId、SecretKey 等凭据              | 录音和导入音频转文字                      |
| Tavily（可选） | API Key                                 | AI 对话中的联网搜索                       |

> [!IMPORTANT]
> 本地优先指学习数据存储在本机。使用在线 AI、语音识别或联网搜索时，相应内容会发送至所配置的服务商，并可能产生服务费用，请按应用提示确认外部处理。

### 3. 开始一次学习

1. 导入文档或粘贴一段文本。
2. 配置大语言模型后生成总结，检查并确认需要保留的内容。
3. 基于资料提问并查看引用，或继续整理知识点、进行练习和制定学习计划。

### 支持的导入格式

| 类型 | 格式                           | 要求与限制                                                             |
| ---- | ------------------------------ | ---------------------------------------------------------------------- |
| 文本 | `.txt`、`.md`                  | 使用 UTF-8 编码                                                        |
| 文档 | `.pdf`、`.docx`                | PDF 须包含可提取的文字且无需密码，暂不支持扫描版 PDF 的文字识别（OCR） |
| 音频 | `.mp3`、`.aac`、`.wav`、`.m4a` | 单文件最长 5 小时；转写需配置腾讯云语音识别凭据                        |

## 数据存储

默认数据目录为 `%USERPROFILE%\KnowRealm`，可在应用设置中打开或迁移，也可使用数据导出与恢复功能。

```text
KnowRealm/
├── knowrealm.db     学习记录、资产与任务数据
├── files/           原始材料及业务文件
├── config/          应用设置与服务商配置
├── cache/           处理缓存
├── exports/         导出文件
└── backups/         备份文件
```

## 常见问题

### 不配置 AI 服务也能使用吗？

可以。不配置 AI API Key，也可以导入和阅读文档、保存文本、整理课程以及搜索已有内容。AI 总结和对话需要配置大语言模型，音频转写使用腾讯云语音识别；网页剪藏和联网搜索需要网络连接。

### 如何备份数据或迁移到另一台电脑？

在设置中导出数据，再在目标电脑的应用中使用数据恢复功能导入。同一电脑调整存储位置时，可使用设置中的数据目录迁移功能。跨版本恢复前，请先确认数据兼容性。

## 系统架构与技术栈

KnowRealm-AI 由桌面界面和随应用启动的本地后端组成。Tauri 负责窗口、托盘、快捷键和后端进程管理；React 界面通过本机 API 访问业务能力。页面操作与 AI 助手复用业务服务和受控操作入口，SQLite 保存业务数据与任务状态，原始材料保存在本地文件目录中。

| 部分       | 主要技术                                                       |
| ---------- | -------------------------------------------------------------- |
| 桌面界面   | Tauri 2、React 19、TypeScript、Vite、Tailwind CSS 4、shadcn/ui |
| 本地后端   | Python、FastAPI、SQLAlchemy、SQLite                            |
| AI 与任务  | LangChain、LangGraph、Deep Agents，以及本地持久化任务队列      |
| 检索与解析 | SQLite FTS5、jieba、PyMuPDF、python-docx、FFmpeg               |

```text
KnowRealm-AI/
├── apps/desktop/       React 界面与 Tauri 原生功能
├── backend/            本地 API、业务服务、AI 能力与后台任务
├── packages/api-types/ 前后端共享的接口类型
├── scripts/            仓库检查与验证脚本
└── docs/img/desktop/   桌面应用截图
```

## 源码开发

以下为 Windows x64 的源码运行与打包方式。仓库使用 pnpm workspace 管理前端、uv 管理后端，根目录没有 `package.json`。

### 准备环境

| 工具                     | 要求                                                                                 |
| ------------------------ | ------------------------------------------------------------------------------------ |
| Git、PowerShell          | 使用 PowerShell 7 执行仓库检查脚本                                                   |
| Node.js、pnpm            | 推荐 Node.js 24 和 pnpm 11.2.2，与当前 CI 保持一致                                   |
| Python、uv               | Python 3.12 及以上，推荐 3.13；使用 uv 管理后端依赖                                  |
| Rust 与 Windows 构建环境 | Rust 稳定版 MSVC 工具链、Visual Studio Build Tools 的 C++ 桌面开发组件及 Windows SDK |
| WebView2 Runtime         | 用于运行 Tauri 桌面界面                                                              |

### 安装依赖并启动

在 PowerShell 中执行：

```powershell
git clone https://github.com/youyu-youth/KnowRealm-AI.git
cd KnowRealm-AI

pnpm install --frozen-lockfile
uv sync --frozen --directory backend

pnpm --filter @knowrealm/desktop tauri dev
```

首次运行开发命令时会自动下载并校验 FFmpeg，需要网络连接。启动命令会同时拉起桌面窗口、前端界面和本地后端，无需另行启动后端。

### 修改与检查

界面与交互位于 `apps/desktop/src/`，原生桌面能力位于 `apps/desktop/src-tauri/`，后端按业务模块组织在 `backend/app/modules/`。修改后端接口后，重新生成 `packages/api-types/` 中的共享类型；修改界面文案时，同步维护中英文翻译。

以下命令均在仓库根目录执行：

```powershell
# 检查当前改动的代码规范与类型
pwsh -NoProfile -File scripts/check-changed.ps1

# 检查并构建前端，不生成桌面安装包
pnpm --filter @knowrealm/desktop build

# 顺序运行前后端全量测试
uv run --frozen --directory backend python -m scripts.run_tests all

# 后端接口变更后重新生成共享类型
pnpm --filter @knowrealm/api-types generate

# 检查接口类型是否与后端一致
pnpm --filter @knowrealm/api-types check
```

### 构建 Windows 安装包

完成上述环境准备和依赖安装后，在仓库根目录执行：

```powershell
pnpm --filter @knowrealm/desktop release:msi
```

该命令会准备 FFmpeg、打包本地后端、构建前端并生成 MSI。默认输出目录为 `apps/desktop/src-tauri/target/release/bundle/msi/`。开发版与发布版的数据结构可能不同，切换版本前请导出备份，并使用独立数据目录。

## 反馈与贡献

欢迎通过 [Issues](https://github.com/youyu-youth/KnowRealm-AI/issues) 反馈问题或提出建议。报告问题时，请附上应用版本、Windows 版本、复现步骤和相关日志，提交前移除 API Key 等敏感信息。

提交 Pull Request 时，请说明解决的问题、主要改动和验证结果。
