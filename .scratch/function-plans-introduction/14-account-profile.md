# 14 - 档案、供应商与数据目录

> Wave: B ｜ PRD: §4.1（用户档案 / 首启 / 数据目录管理）/ §6.4 ｜ 决策引用: #52 #55 #11 ｜ 2026-08-30 grilling 定稿（补首启向导、拆 5 工单、ADR-0013）

## 功能描述 / 目标

无账号体系下的完整闭环：本地档案编辑（昵称/头像/角色/自我介绍）、设置页供应商分区（单 active）、数据目录管理（打开/更改/全量导出/导入/滚动备份）、首启三步向导（每步可跳过，一次性）。原 P2 的全量导出/导入提前 Wave B（#55）。首启三步从未随 Phase 0 落地（P0-05 已取缔），由本 plan 补齐。

## 功能范围（5 工单，按序交付）

**01 档案补全**
- nickname（≤20 字）进 ProfileOut/ProfileUpdate，随现有"保存档案"一键提交；profile 表列已在（迁移 0014），仅补 schema/service/前端
- 头像：dialog 选图（png/jpg/webp）→ 前端读字节 → `PUT /api/profile/avatar`（原始字节体）→ 后端校验魔数+≤2MB → 覆盖式写 `files/avatar.<ext>`、`avatar_file` 存相对路径 → `GET /api/profile/avatar` 返回 bytes（前端 blob URL 展示）、`DELETE` 清除；不做后端压缩/裁剪（CSS 圆形展示）；GIF/BMP 不收
- 昵称不进任何 AI prompt（`build_profile_snapshot` 不动）；空昵称侧边栏兜底占位
- 侧边栏底部用户区：头像+昵称，点击跳设置页档案区；不激活"学习画像"禁用导航项（那是 17 号入口）
- 角色建课联动：前端预选 `learning_context` 初值（STUDENT→SCHOOL、DEVELOPER/OFFICE_WORKER→CAREER，可改）；无档案/OTHER 不预选；后端不动（必填无默认的 API 语义保持）

**02 供应商分区**
- 设置页新增"供应商"分区（排布实施定）：**AI 服务卡**（base_url+api_key+model 单 active；DashScope 预设按钮一键填充 compatible-mode base_url + `qwen-plus`；连接测试复用现有 `POST /tests`）+ **语音转写卡**（`GET/PUT /api/settings/providers/tencent-asr`：secret_id/secret_key/region，空 key 保留旧值对齐 llm 模式；连接测试=TC3 调只读轻接口，**工单第一步调研**，选不出合适接口退化为格式校验）
- Embedding 不做配置 UI（V1 固定，卡内文案注明）
- 就地收敛：`ChatProviderSetup` 与 `SummaryPanel` 的 ProviderConfiguration 表单删除，改"未配置 → 提示 + 跳设置页"；可保留只读状态展示

**03 数据目录管理**
- 壳侧 `desktop.json`（app_config_dir，`{data_dir, onboarded}`）：`sidecar.rs:50` 写死路径改为读它，缺省回退 `home/KnowRealm`（ADR-0013）
- 打开数据目录：tauri-plugin-opener；shell 插件卸载，`learningAssetExport` 的 open 一并迁移
- 更改数据目录：dialog 选**空目录**（不存在可建、非空拒绝）→ 确认弹窗（预告迁移耗时与重启、AI 任务自动恢复）→ Rust command：复用安全退出的 sidecar 停止链 → 同盘 rename / 跨盘 copy-then-delete（进度事件）→ 写 desktop.json → process 插件 relaunch；失败清理目标半成品、原目录不动、不重启
- 设置页"数据目录"分区：路径展示（只读）+ 打开 + 更改 + （空库限定）"从导出包导入"兜底入口（04 交付后接入）

**04 全量导出/导入 + 滚动备份**
- 导出：`POST /api/settings/data-directory/export {include_secrets}`（同步端点+前端遮罩防重复，导出期间**不停写**）→ `exports/knowrealm-export-YYYYMMDD-HHMMSS.zip`：`manifest.json`（app_version、db user_version、created_at、include_secrets、文件清单）+ `knowrealm.db`（VACUUM INTO）+ `files/**` + `config/**`（默认排除 providers.json；勾选含时 UI 明示明文风险 #11）
- **实施第一步**验证导入临时文件确落 `cache/`（files/ 无竞态）；若不是，退化为导出前停 worker
- 导入：sidecar 启动参数 `--import-archive <zip>`，ensure_data_dir 后、目录锁与开库前校验落位（Python zipfile 标准库）：manifest/结构不符或 user_version>当前 → 拒绝且不留半成品；user_version<当前 → 落位后走现有迁移自动升级；RUNNING/PENDING 任务原样入包，新机 `recover_interrupted` 自动续
- 导入入口：首启向导①（05）+ 设置页空库限定兜底（无课程+无记录+无档案时可见，后端一个只读判断）
- 滚动备份：启动 lifespan 当日快照不存在则 `VACUUM INTO backups/knowrealm-YYYYMMDD.db`，仅保留最近 7 份自动清理

**05 首启三步向导**
- 判定：壳读 desktop.json——文件缺失或 `onboarded=false` → 首路由 `/onboarding`（AppShell 外，托盘/快捷键不绕过）
- ①数据目录：默认 `~/KnowRealm` 展示（"使用默认目录开始"=跳过）、"更改位置"（dialog 空目录）、"从导出包导入"（选 zip → spawn sidecar 带 `--import-archive`，失败向导内报错可重试）、OneDrive 检测（路径含 OneDrive 组件或 `%OneDrive%` 前缀 → 黄字警告不阻断）
- ②供应商卡：复用工单 02 卡组件；"稍后在设置中配置"=跳过（降级 #38 由空态引导兜底）
- ③角色卡：四选一+自我介绍；"跳过"=不建档（chat 中性默认已实现）
- 完成（含全部跳过）：完成页提示"所有设置可稍后在设置页修改" → 写 `onboarded=true` → 进首页；向导永不再现、无"重新运行"入口
- 向导期间不记 last_route（13 号豁免扩展为"设置页与首启向导除外"）

**不做**：
- 登录/账号/密码（#55）、应用锁（P3+ 评估）、Windows 凭据管理器（P3+ 评估，#11）
- 多供应商卡槽切换（单 active 语义，providers.json 不扩结构）
- 快照备份 WebDAV/S3（P2 单向推送）
- Embedding 配置 UI（V1 固定）
- 昵称/头像/角色进课程范围 AI 管线与 Learning Evidence；昵称不进任何 prompt
- 后端头像裁剪压缩、重跑向导入口、OneDrive 以外网盘检测、设置页 consent 管理 UI

## 核心业务流程

设置→档案：改昵称/头像/角色/自我介绍→保存生效（重启保持），侧边栏用户区同步展示。设置→供应商：AI 服务卡配置（或 DashScope 预设）→连接测试→总结/chat 走该端点；语音转写卡配腾讯 key→转写可用。设置→数据目录：打开/更改（停止→移动→重启）/导出/（空库）导入。首启：向导三步（皆可跳过）→完成进首页。换机：新机向导①选"从导出包导入"→数据完整恢复。

## 关键业务规则

- 角色改变语气与默认值，不改变能力集（#52）：永不进入课程范围 AI 管线与 Learning Evidence；昵称同理不进任何 AI prompt
- 角色改动对自由聊天"新会话生效不追溯"（与 12 验收联动）
- 供应商单 active："卡"=每类服务一张配置卡（AI 服务/语音转写），非多卡槽；providers.json `llm`/`tencent_asr` 单键结构不变
- LLM 可自选任意 OpenAI 兼容端点，DashScope 为默认预设（#55）；Embedding V1 固定无配置
- 密钥明文存 config/providers.json（#11）；导出默认不含、勾选含时明示明文风险
- 连接测试不得暗示或代替 ASR 外发同意；首次实际发送转码音频片段前仍由 04 独立告知并取同意
- 数据目录唯一事实源，同一时刻不可双写：更改目录必须经 停止 sidecar→移动→重启；目录锁随目录整体迁移
- 移动语义 copy-then-delete：成功前不动原目录；失败清理目标半成品并报错
- 导入仅空库（向导新目录或设置页空库兜底）；user_version>当前拒绝、<当前自动迁移；校验失败不留半成品
- 向导每步可跳过=接受默认；全部跳过亦算完成；onboarded 存壳侧 desktop.json 不随导出迁移（ADR-0013）
- 向导与设置页均不记 last_route

## 前置依赖

- 设置页框架已存在（原 P0-05 已随 Phase 0 取缔消解；现含档案分区）
- 11 已交付托盘/安全退出链（03 复用 sidecar 停止路径）；13 已交付偏好分区（last_route 豁免由 05 扩展）
- PRD §4.1 首启①的"可跳过"（=默认目录）为本次定稿修订表述，基线文档后续对齐

## 验收标准（出口线）

- [ ] 改昵称/头像/角色/自我介绍保存生效，重启保持；侧边栏用户区展示头像+昵称，空昵称占位兜底（01）
- [ ] 头像非 png/jpg/webp 或 >2MB 被拒；删除头像生效（01）
- [ ] 建课程按角色预选默认场景且可改；无档案/OTHER 不预选（01）
- [ ] 设置页供应商卡配置自定义端点→连接测试通过→总结/chat 走该端点（02）
- [ ] DashScope 预设一键填充（compatible-mode base_url + qwen-plus，可改）（02）
- [ ] 腾讯 ASR key 配置保存后转写可用；测试按钮为真实轻调用或格式校验（工单 02 第一步定）（02）
- [ ] 聊天/总结就地空态仅引导跳设置页，不再有就地表单（02）
- [ ] 打开数据目录在资源管理器打开（03）
- [ ] 更改数据目录（同盘/跨盘）→重启→数据完整；进行中 AI 任务自动恢复；失败原目录无损（03）
- [ ] 全量导出 zip→新机向导"从导出包导入"→数据完整（db 自动迁移、files/config 落位、进行中任务续跑）（04+05）
- [ ] 导出包 user_version 高于当前 app→明确拒绝且无残留（04）
- [ ] 导出默认不含 providers.json；勾选含时明示明文风险（04）
- [ ] 滚动备份启动生成当日快照、超额 7 份自动清理（04）
- [ ] 误跳过①后设置页空库可见导入入口并成功恢复；非空库隐藏（04）
- [ ] 新库首次启动出现向导，每步可跳过；完成（含全跳过）后永不再现（05）
- [ ] 向导①选目录命中 OneDrive→警告不阻断（05）

## 选型记录（2026-08-30 grilling 定稿，轮子优先原则）

| 能力 | 选型 | 来源/备注 |
|---|---|---|
| 打开数据目录/文件 | tauri-plugin-opener | Tauri 官方（shell.open 继任）；shell 插件随之卸载、learningAssetExport 迁移 |
| 重启 | tauri-plugin-process `relaunch()` | Tauri 官方 |
| 目录/图片选择 | tauri-plugin-dialog `open` | Tauri 官方已装，补 dialog:allow-open 权限 |
| 首启判定/路径持久化 | 壳侧 app_config_dir/desktop.json | ADR-0013；先例 Clash Verge Rev |
| 导入执行者 | sidecar `--import-archive` + Python zipfile | 标准库零新依赖；开库前落位（ADR-0013） |
| db 快照 | SQLite `VACUUM INTO` | SQLite 内置；导出/滚动备份共用，WAL 模式安全 |
| 目录移动 | Rust 同盘 rename / 跨盘 copy-then-delete | 进度事件；失败保原目录 |
| 头像 | dialog→前端字节→sidecar API | UI 不直读数据目录红线；不做压缩 |
| DashScope 预设 | compatible-mode base_url + qwen-plus 预填 | 可改 |
| 单 active 供应商 | providers.json 单键维持 | 多卡槽否决（YAGNI） |
