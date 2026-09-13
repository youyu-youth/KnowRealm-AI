# 03 — 前端工具状态卡 + 文档收尾

**What to build:** 前端消费 `tool_call` / `tool_result` SSE 事件：消息流内 inline 状态卡（"正在检索「query」"加载态 → "命中 n 条" / 失败态，多次检索逐条陈列，done / 中断后随流式态消失）；zh/en 文案同步。文档收尾：数据模型升 v2.5（新表 segment_search_index）、扩展设计文档 §40 A1 行回写实现形态修正、PROJECT_PROGRESS 同步。

**Spec 参考:** 同目录 `../spec.md`（前端呈现决策、Out of Scope——右栏不动、不持久化；实施前先读，票与 spec 不一致时以 spec 为准）。

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] SSE 解析（chatSessions）新增 `tool_call` / `tool_result` 分发；`useChatStream` 增工具状态临时态（与 streamedText 同生命周期、同清理路径：done 置空 / 切会话中止）
- [ ] `ChatMessageList` 消息流内 inline 状态卡：加载态（正在检索「query」）→ 命中 n 条 / 失败态，多次检索逐条陈列；右栏上下文面板本轮不动
- [ ] 新增 UI 文案 zh.json / en.json 同步（key 两侧一致，en 缺失会被一致性防线拦截）；OpenAPI / api-types 零变化（确认无漂移）
- [ ] 测试（chat jsdom seam）：SSE 新事件分发、状态卡三态渲染与 done 后消失、文案键存在；前端门禁（pnpm test -- --maxWorkers=4 / lint / 触及文件 Prettier / build）
- [ ] 文档收尾：数据模型 v2.4 → v2.5 升版重命名（segment_search_index 新表）+ 全库交叉引用同步；扩展文档 §40 A1 行回写（实现形态=分片级 FTS + 挂载内单工具，与 §40.2 原设想差异及两事实依据）；PROJECT_PROGRESS.md 对应小节更新；CONTEXT.md 如有新术语（如「分片索引」）补词条
