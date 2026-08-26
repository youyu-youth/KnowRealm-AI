# 01 — Summary / 知识点单项导出与 Tauri 保存闭环

**What to build:** 让用户从 Record 详情顶部的统一导出菜单，把当前 Tab 的已确认 Summary 或正式知识点保存为本地 Markdown 文件。该纵切同时交付真实的系统保存对话框、文本写入、保存反馈和按需打开文件，因此完成后用户已能在 Windows 上独立使用两类单项导出，而不是只得到序列化工具或尚未接线的 UI。

**Blocked by:** None — can start immediately.

**Status:** done

> 2026-08-26 完成记录：序列化 16 测试 + 组件 12 测试（MSW/Tauri mock）+ 全仓 110 测试 + tsc/eslint/build + cargo check/fmt/clippy/build 全绿；真实 Windows 验收在 dev 应用上完成——中文标题“test录音1111”的 Summary 与知识点两份文件实际落盘并按字节核对（UTF-8 无 BOM、纯 LF、末尾换行、结构正确、无内部元数据），取消无副作用，同名覆盖走系统确认框，中文目录（E:\knowrealm-export-acceptance\中文目录）保存成功，“打开文件”用系统默认编辑器（Typora）打开且页内成功状态保留。离线导出一项由代码路径保证：导出仅访问 localhost sidecar 与 Tauri IPC，无外部请求。

> 双轴 code-review 后的修正：Tauri 插件调用收口到 `services/tauri/learningAssetExport.ts`（符合 .claude/rules/desktop-tauri.md §1）；转义集补方括号（链接/图片语法）；`save()` 异常归入写失败提示；回退 RecordDetailPage 的无关重排。已知取舍：`fs:allow-write-text-file` 的 scope 为 `**`（.claude/rules/desktop-tauri.md §3 禁全盘 scope 与"用户自选任意保存位置"的产品要求冲突）——本功能按工单要求的 fs 插件路径实现，命令面仅 write_text_file 一个、路径一律来自用户确认的系统对话框；若需收紧为受限目录白名单，会破坏任意盘符保存，需产品层重新决策。

- [x] Record 详情标题区出现键盘可用的统一导出菜单；当前 Tab 为 Summary 或知识点且存在可导出内容时，“导出当前 Tab”可用，其他 Tab 或无正式内容时禁用并说明原因。
- [x] 每次触发都通过既有 localhost API 重新读取当前资产，不依赖未挂载 Tab 的缓存；读取完成后形成不可变快照，再打开系统保存对话框。
- [x] Summary 只有当前响应状态为 CONFIRMED 时可导出；未确认版本不回退导出旧版本，也不进入保存流程。
- [x] Summary Markdown 以 Record 展示标题为一级标题、Summary 为二级标题，包含主题、摘要和原顺序的结构化分点；不包含内部 ID、模型、prompt 版本或导出时间。
- [x] 知识点只导出当前未删除的 ACTIVE 项，排除 DRAFT 与 SUPERSEDED；顺序与页面一致，每项包含名称、详情、`importance/5` 和非空标签。
- [x] Summary 与知识点的纯文本字段不会通过 `#`、`*`、反引号或原始 HTML 破坏 Markdown 结构；可见文本和段落换行不丢失。
- [x] 聚合与单项序列化共用的最小能力采用显式资产白名单和小型纯函数；不建立插件系统、模板引擎或自动扫描 Tab 的机制。
- [x] 使用仓库已安装的 Tauri dialog、fs 与 shell 能力完成保存、文本写入和按需打开文件；仅补充主窗口所需的最小插件注册与 capability，不新增依赖、不拼接 shell 命令写文件。
- [x] 单项默认名分别为 `{Record展示标题}-总结.md` 与 `{Record展示标题}-知识点.md`；过滤 Windows 非法字符、控制字符、尾部点/空格和设备保留名，空标题复用“未命名学习记录”，最终扩展名为 `.md`。
- [x] 文件以 UTF-8 无 BOM、LF 写入，区块之间一个空行且文件末尾一个换行；相同输入生成相同内容。
- [x] 用户取消保存时不写文件、不报错、不显示成功；同名覆盖交给系统保存对话框确认。
- [x] 资产读取、Markdown 组装和文件写入失败分别显示可理解的页内错误；权限不足、磁盘满或路径无效时不得出现成功状态。
- [x] 保存成功后显示页内状态和“打开文件”动作，不自动启动外部程序；打开失败单独提示且不推翻文件已保存的事实。
- [x] 外部网络断开但 localhost sidecar 与资产可用时仍能导出；导出不创建数据库事实、不写导出历史、不产生 learning_events。
- [x] 纯序列化测试覆盖 Summary、知识点、转义、稳定换行和文件名清理；Record 详情组件测试通过 MSW 与 Tauri 边界 mock 覆盖菜单、最新读取、禁用态、取消、读写失败、保存成功和打开失败，只断言外部行为。
- [x] Tauri 配置通过 Rust 静态检查与桌面构建；真实 Tauri Windows 验收使用中文 Record 标题和中文目录验证实际落盘字节、UTF-8 无 BOM、LF、取消、同名覆盖和“打开文件”。jsdom、MSW 或构建成功不能替代该项。

