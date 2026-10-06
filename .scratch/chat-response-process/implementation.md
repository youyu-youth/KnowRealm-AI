# AI 对话过程展示优化：实施与验收

实现范围沿用户已批准方案：紧凑两行摘要、按需展开、公开说明与正文分段、调用 ID 关联、过程持久化、失败/中断留痕与重新生成、80px 内自动跟随。复用 Deep Agents、领域 Service、授权与回执；展示事实不增加可调用 Tool，也不创建任务调度平台。

后端迁移 0041；REST 消息批量附带过程，SSE 保留原事件名并扩载荷；OpenAPI 和 TS 类型同步。公开说明由完整 AIMessage 的 tool_calls 判断，供应商原始 reasoning 不展示。普通无工具成功回答没有空过程入口。历史重新打开默认收起，当前手动展开不因完成重置。

自动化验证：

- 后端聊天、会话历史、保存知识点、授权模式、操作服务：184 项通过；覆盖同名并行、乱序结果、无查询参数、正文分离、失败/中断重试、重启截止用时、历史保存失败不重复工具调用。
- 前端聊天消息、流 Hook、SSE 解析及页面：62 项通过；包含十二次调用默认仅显示最新、展开保持、历史默认收起、待确认/保存异常、旧消息阅读不抢滚动、引用/草案/保存知识点回归。
- 触及文件 Ruff、Pyright、ESLint、Prettier、前端 build 与 OpenAPI/TS 契约检查通过。既有 PlanDraftEditor 的 Fast Refresh 警告与 Vite 大包提示不属于本次改动。

真实桌面验证（2026-10-06）：隔离 identifier/data-dir 的 Tauri 2 + WebView2 + 本地 FastAPI sidecar，模型使用本地 OpenAI SSE 桩，不调用真实供应商、不改用户数据。截图在 evidence/。

- 真实调用链十次并行工具调用全部记录；展开有十一条（含一条公开说明），320px 局部滚动有效，正文没有公开说明重复，完成后手动展开保持。
- 明/暗主题、980×720 原生窗口、原生 WebView 200% 缩放（1280×800 窗口对应 640×400 CSS viewport；DPR 1.25→2.5）、减少动效检查通过；无页面横向溢出。200% 下消息区较短，仍可滚动阅读；范围按钮横向滚动、标题单行截断，避免换行将消息区挤到零高度。
- Enter 展开正常；进程重启后成功过程与最终正文仍在，历史默认收起。
- 真实 SSE 停止后 REST 为 INTERRUPTED，未完成工具数为零、重新生成入口可用；重试后同一发起消息关联 INTERRUPTED / COMPLETED 两条不同过程记录，最终回答正常保存。

真实供应商兼容性与用户日常数据体验仍可按常规人工试用复核，不能将本地模型桩当作供应商验收。权威数据模型增补提案待批；PROJECT_PROGRESS 已同步实现事实。

## 2026-10-06 追加：过程行图标与「同文两遍」修复

真机反馈：过程卡展开后同一条文案出现两遍（第二行无图标、缩进与首行文字对齐）。查用户真实库（数据目录 `knowrealm.db` 的 WAL，12:41 那条过程）确认 entries 里只有 2 条 tool 条目、各一份、且该过程没有任何 commentary 条目——重复来自渲染层：每条目原先是行内 Collapsible，触发行与本行展开面板显示同一 `entryLabel`。

修复（仅前端，后端/迁移/契约零改动）：

- 行结构改为「左侧工具图标 + 单行文案 + 行尾状态图标」，删除行内 Collapsible 副本；点击整行改为**原地**展开（`aria-expanded`，同一句任何状态只显示一份，chevron 随展开态旋转）。
- 新增 `features/chat/toolIcons.ts`：37 个后端工具（含已退役 `search_transcript`）逐个 lucide 图标，未登记工具落兜底 `Wrench`；思考（公开说明）行用 `MessageSquareText` 专属图标；行尾状态图标覆盖五种状态，`title` 复用 `chat.process.toolStatus.*`。
- 渲染前对完全相同的思考文本去重（保留第一条）；工具行不去重，保证「N 次工具调用」与行数一致。
- 测试：`ChatMessageList.test.tsx` 增「展开后每条文案只出现一次 + 点击行原地展开不产生第二份」「相同思考文本只保留一条、相同文案工具行保留两条」；新增 `toolIcons.test.ts` 钉图标两两不同且不与兜底/思考图标重复。门禁：chat 相关 14 项、`tsc --noEmit`、`eslint --max-warnings 0`、`pnpm build` 全过；全量 656 通过，3 个失败文件（CourseBrainMastery/TodoPanel/SharedRefsTab）单跑 20 项全绿 = 既有并发抖动口径。
