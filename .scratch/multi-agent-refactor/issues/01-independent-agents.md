# 01：general / knowledge 独立入口闭环

Type: task
Status: needs-info
Blocked by: Q5 最终共享理解确认；文档提案已获 Q6 批准
规格：[spec.md](../spec.md) §1～4、10～12。

## 用户结果

用户可在现有新建对话流程明确选择通用助手或本地知识助手，结合原有资料范围创建对话；刷新、重启后归属不变。旧入口维持 general，knowledge 没有业务写入或联网工具。

## 改动边界

- [x] 依据 Q6 批准提案登记 ADR-0030、旧 ADR 阶段差异与术语；不改 rules。此项是文档登记，不是实现验收。
- [ ] 会话 DDL 增加固定 agent_id 与旧记录默认 general；Pydantic、Service、创建/列表/详情贯通。
- [ ] 提供真实 GET /api/agents；使用两项静态能力配置，不添加动态注册框架。
- [ ] 保存 AgentConfig 的全部扩展点；复用原模型工厂、build_agent 及治理 Middleware。
- [ ] general 既有能力保留；knowledge 使用专业只读提示与 search_library 白名单，FREE 不扩大范围。
- [ ] 输入准入和装配看到的工具面一致；不是仅在 UI 隐藏写入口。knowledge 恶意请求写工具不得触发 Service/Operation。
- [ ] 原 mode/scope 合法矩阵保留；knowledge 在任何 mode 不产生网络检索或入库提案，不绑定另一套消息体系。
- [ ] NewChatButton、统一创建 mutation、范围切换和身份显示同步；旧课程/资料 CTA 默认不变。
- [ ] zh/en 同 key；主题、键盘、长文本及窄窗适配；knowledge 联网/写操作状态准确解释。
- [ ] OpenAPI/api-types 重新生成；新增 HTTP 错误码按现有三方登记（确有新增时）。

## 验证路径

公开 POST /api/chat-sessions → SQLite agent_id → POST turns → 原双槽 Worker → 真实 build_agent → 模型替身实际观察 tools/system → 工具调用和来源复核 → 持久响应/会话 GET → 前端展示。

使用独立临时 SQLite 和真实 app/Worker；模型替身仅替换供应商。固定数据包含两个课程、跨课资料、归档及软删来源、旧会话与 FREE。

- [ ] 自动化：旧载荷默认/重启归属、未知身份拒绝、不可 PATCH 改 Agent、范围隔离、FREE 无本地召回、knowledge 零写入、general 原写路径回归、五扩展点不丢失。
- [ ] 现有回归：test_chat_sessions.py、test_chat_streaming.py、test_context_budget.py、相关前端聊天创建测试；仅在新增行为无覆盖处补测试。
- [ ] 真实 API/SQLite/Worker + 模型替身：以上生产链贯通，保存输入观察和真实查询证据。
- [ ] 真实模型：实际命中本地检索并有可打开引用；没调用工具记 NOT_TRIGGERED。
- [ ] 浏览器：各当前主题、窄窗、字号、中英、键盘与错误状态；不代替原生。
- [ ] Tauri/WebView2 与 Windows 125%/150%/200%：选择、创建、重启读回和引用定位，未执行保持 NOT_RUN。

## 桌面重复步骤

隔离 data-dir 创建课程 A/B 和各自标记资料 → 新建 knowledge/COURSE A → 询问标记内容并尝试要求创建课程 → 只出现 A 合法来源且业务无新增 → 刷新/重启检查 Agent 身份 → 新建 general 检查原确认卡行为 → FREE 知识请求应说明缺少挂载范围。

证据保存 `../01-implementation.md`（实施时创建），包含命令、基点、数据库查询、替身范围、PASS/FAIL/NOT_TRIGGERED/NOT_RUN；临时数据库与日志不 add/commit。结束只清理本票创建的隔离资源，不修改用户数据目录。

## 完成定义

上述独立入口具有可复查生产链证据、范围检查及契约通过；本票完成不表示委派已实现，不关闭未执行真实验收项。按批准范围更新项目进度。
