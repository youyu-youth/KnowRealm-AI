# 本地优先：数据目录是唯一事实源

---
Status: accepted（2026-08-17，PRD 决策 #55）
---

v1.x 全系设计为服务端优先（Supabase Postgres 云端唯一事实源 + 桌面端仅缓存），源于"先选 Supabase 再谈个人定位"的顺序错误；用户于 2026-08-17 澄清真实意图为本地优先。**决定**：用户可见的本地数据目录（SQLite + 原始文件）是唯一业务事实源；Python 后端以 Tauri sidecar 形态随 `.msi` 分发、UI 经 localhost 访问；同一数据目录由 sidecar 持有进程生命周期操作系统排他锁，保证最多一个写者；云端从必需依赖降为可选增强——V1 仅全量导出，P2 可选快照备份（WebDAV/S3，单向推送），**双向同步永不做**；Supabase（Auth/Storage/Realtime/RLS/pgvector）整体除名。

## Considered Options

| 范式 | 代表 | 结论 |
|------|------|------|
| A. 纯本地桌面（无任何云） | Jan、Cherry Studio | 落选——课堂录音不可再生，完全无异地通道风险过高 |
| **B. 本地优先 + 可选云备份** | Obsidian、思源、AnythingLLM 桌面版 | **采纳** |
| C. 服务端优先（云托管或 docker 自托管） | Khoj、Meetily、v1.x 原案 | 否决——Supabase free 档装不下 5h 音频（50MB 单文件/1GB 存储），Pro $25/月，东京机房需代理；单用户场景下 Auth/RLS/Realtime/Storage 是纯开销；自部署用户要跑 docker compose 违背"下载即用" |

## Consequences

- 登录/认证整体删除，首启改为三步（选数据目录 → 配供应商 key → 角色卡）；取代 v1.x 红线 #1/#35/#49 与决策 #3/#17/#37/#54 登录部分。
- 多设备降级为"全量导出 → 导入"；user_settings/local_settings 合并为本地配置文件。
- pgvector → sqlite-vec；procrastinate → processing_jobs 自研队列；RLS/JWT → 无（本地单用户，localhost 单写者）；第二个 sidecar 在迁移和 worker 启动前因目录锁失败而退出，进程退出/崩溃由 OS 自动释放锁。
- `feat/dev-01-desktop-loop` 分支的 Auth/JWKS/RLS/直连实现随之作废（分支已标 deprecated；Windows 工程陷阱经验保留在团队记忆）。
- 决策时点代码沉没成本 ≈ 0（main 仅有 scaffold），是转身的最后免费窗口。
