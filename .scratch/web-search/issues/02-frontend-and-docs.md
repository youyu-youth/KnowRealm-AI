# 02 — B1 前端接线与文档收尾：开关接真、web 引用外链、设置卡

**What to build:** 右栏「联网搜索」开关从示意态接真——开=发消息带 `web_search` 标志，自由聊天默认开、挂载默认关，按会话本地记忆；无 key 时置灰并引导去设置页。引用列表分流渲染：web 条目为外链（点击系统浏览器打开），record 条目照旧跳转写页；工具状态卡对 `web_search` 显示「正在搜索网络」文案。设置页「服务与用量」新增搜索供应商卡（key 掩码/保存/清除/手动测试）。收尾全部文档回写。

**Blocked by:** 01（后端端点与引用契约就位、api-types 已重生成）。

**Status:** ready-for-agent

- [ ] api-types 消费：ChatCitation 分流（`source:"web"` → 标题+域名+Globe 图标外链，点击经 opener 插件开系统浏览器；record 条目照旧跳转写页）；key 兼容两类条目
- [ ] webSearch 开关接真：状态从全局示意 store 迁到按会话记忆（Zustand，重启重置），默认值自由 ON / 挂载 OFF；发消息请求带 `web_search` 标志
- [ ] 无 key 降级：经设置端点获知可用性，开关 disabled + tooltip 引导设置页；聊天不受影响
- [ ] 工具状态卡按 tool 名分流文案：`web_search` →「正在搜索网络「query」」/「找到 n 条结果」/ 失败态（沿用 A2 卡形态与生命周期）
- [ ] 设置页「服务与用量」新增搜索供应商卡：key 输入/掩码显示/保存/清除 + 手动测试按钮（文案注明真实消耗 1 credit 与「搜索词将发送至 Tavily」知情说明）
- [ ] 其余三工具开关（knowledgeBase/codeRun/documentParse）维持示意态不动
- [ ] zh.json / en.json 同步新增全部新文案（key 两侧一致）
- [ ] 文档回写：扩展文档 §40.3 B1 行标记已实施 + §40.4 第 3 步完成标记；数据模型文档就地补 `citations_json` web 条目结构说明（零表变更不升版，变更记录加行）；CONTEXT.md 视需要补「网络引用」词条；PROJECT_PROGRESS.md 同步
- [ ] 测试全过（开关状态→请求参数、无 key 置灰、web 引用外链渲染分流、工具卡文案、zh/en key 一致——jsdom 现有 chat 测试模式扩展）
- [ ] 门禁：pnpm test（--maxWorkers=4）/ lint / 触及文件 Prettier / build 全绿
- [ ] 提交 `feat(desktop): 接线联网搜索开关与网络引用外链（B1 票 02）` 与 `docs: 回写票 02 完结与 B1 交付结论`

**用户真机验收（不代勾）：** 真机 Tauri 下开关切换生效、无 key 置灰态、web 引用点开系统浏览器、设置卡配置全流程、亮暗两态。
