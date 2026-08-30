# 06 — 首启三步向导

**What to build:** 壳读 desktop.json 判定首启（文件缺失或 `onboarded=false`）→ 首路由 `/onboarding`（AppShell 外，托盘/快捷键不绕过）。三步**全可跳过**：①数据目录——默认 `~/KnowRealm` 展示（"使用默认目录开始"=跳过）、"更改位置"（复用 03 的空目录选择）、"从导出包导入"（选 zip → spawn sidecar 带 `--import-archive`，失败向导内报错可重试）、OneDrive 检测（路径含 OneDrive 组件或 `%OneDrive%` 前缀 → 黄字警告不阻断）；②供应商卡——复用 02 卡组件，"稍后在设置中配置"=跳过（降级 #38 由空态引导兜底）；③角色卡——四选一+自我介绍，跳过=不建档（chat 中性默认已有）。完成（含全部跳过）：完成页提示"所有设置可稍后在设置页修改" → 写 `onboarded=true` → 进首页，向导永不再现、无"重新运行"入口。向导期间不记 last_route（13 号豁免扩展为"设置页与首启向导除外"）。

**Blocked by:** 02 — 供应商分区；03 — 数据目录分区、desktop.json 与打开目录；05 — 全量导出/导入与滚动备份

**Status:** ready-for-agent

- [ ] 首启判定：壳读 desktop.json → 路由分流；托盘/快捷键不绕过向导
- [ ] 向导①：目录默认/更改/从导出包导入分支（--import-archive 接线+失败可重试）/OneDrive 检测警告
- [ ] 向导②③：复用供应商卡与角色表单；跳过语义落地（接受默认/不建档）
- [ ] 完成：写 `onboarded`（经壳）→ 进首页；向导路由不写 last_route
- [ ] 前端测试（三步跳过/导入失败重试/完成态/last_route 豁免/非首启不出现）；pyright/tsc/prettier 全绿
- [ ] 真机人工验收（用户执行）：全新数据目录首启走完三步（含全跳过）后永不再现；OneDrive 路径出警告；导入恢复后②③显示已配置/已建档
