# 03 — 前端工具状态卡 + 文档收尾

**What to build:** 前端消费 `tool_call` / `tool_result` SSE 事件：消息流内 inline 状态卡（"正在检索「query」"加载态 → "命中 n 条" / 失败态，多次检索逐条陈列，done / 中断后随流式态消失）；zh/en 文案同步。文档收尾：数据模型升 v2.5（新表 segment_search_index）、扩展设计文档 §40 A1 行回写实现形态修正、PROJECT_PROGRESS 同步。

**Spec 参考:** 同目录 `../spec.md`（前端呈现决策、Out of Scope——右栏不动、不持久化；实施前先读，票与 spec 不一致时以 spec 为准）。

**Blocked by:** 02

**Status:** done

- [x] SSE 解析（chatSessions）新增 `tool_call` / `tool_result` 分发；`useChatStream` 增工具状态临时态（与 streamedText 同生命周期、同清理路径：done 置空 / 切会话中止）
- [x] `ChatMessageList` 消息流内 inline 状态卡：加载态（正在检索「query」）→ 命中 n 条 / 失败态，多次检索逐条陈列；右栏上下文面板本轮不动
- [x] 新增 UI 文案 zh.json / en.json 同步（key 两侧一致，en 缺失会被一致性防线拦截）；OpenAPI / api-types 零变化（确认无漂移）
- [x] 测试（chat jsdom seam）：SSE 新事件分发、状态卡三态渲染与 done 后消失、文案键存在；前端门禁（pnpm test -- --maxWorkers=4 / lint / 触及文件 Prettier / build）
- [x] 文档收尾：数据模型 v2.4 → v2.5 升版重命名（segment_search_index 新表）+ 全库交叉引用同步；扩展文档 §40 A1 行回写（实现形态=分片级 FTS + 挂载内单工具，与 §40.2 原设想差异及两事实依据）；PROJECT_PROGRESS.md 对应小节更新；GLOSSARY.md 如有新术语（如「分片索引」）补词条

**交付注记（2026-09-13）：**

- 前端：`chatSessions.ts` 增 `ChatToolCallPayload` / `ChatToolResultPayload` 与两事件分发（畸形载荷忽略：query/hits/ok 类型不匹配即丢弃）；`useChatStream.ts` 增 `ChatToolActivity[]` 临时态（tool_call 追加在途卡、tool_result 回填最后一张在途卡；与 streamedText 同清理路径：`clearTransientState` 统一用于 done、error、abort、异常四处，send 起始另置空）；`ChatMessageList.tsx` 流式气泡内渲染检索过程卡（`ToolActivityCard` 三态早返回 + 共享样式常量；`aria-label=检索过程`；加载态行内 Spinner、成功态 Search 图标 +「query」命中 n 条、失败态 CircleAlert + `text-destructive` 文本；`bg-surface-subtle` + 6px 圆角 + 12px 文本，无边框无阴影；滚动跟随纳入 toolActivities.length）。
- 设计：遵循 DESIGN.md §6 状态与进度（图标 + 文字，不只靠颜色）、§8 后台处理（行内 spinner，无假进度/呼吸动效）、§11 动效（失败只更新图标/文字）；右栏工具开关维持示意态未动（B1 接真）。
- 文案：`chat.tools.activity.{label,running,hits,failed}` zh/en 同步（en 另配 `hits_one`/`hits_other` 复数形态）；i18n 一致性测试（3 项）通过。
- 测试：`chatSessions.test.ts` +1（事件顺序与畸形载荷忽略）；`chat.test.tsx` +1（三态逐条陈列、done 后消失、历史只留正文）；前端全量 `pnpm test -- --maxWorkers=4` 426/426、`pnpm lint`、触及文件 Prettier（CRLF 工作区已按 LF 副本核验全清白）、`pnpm build`（内嵌 tsc）全绿；`pnpm --filter @knowrealm/api-types check` 零漂移。
- 文档：数据模型 v2.4→v2.5 重命名（§4.5 增 FTS5 虚拟表 `segment_search_index` 说明与 v2.5 变更记录行，虚拟表不计正式表数）；交叉引用同步（根 AGENTS.md、GLOSSARY.md、PRD v2.7 头部、技术栈 v4.5 §SQLite 行、扩展设计文档 §0/§40、backend/AGENTS.md 迁移纪律 0020 + SSE 现状）；扩展文档 §40.1/§40.2/§40.3 A1+A2 行/§40.4 并行槽回写；GLOSSARY.md 增「分片索引」「检索过程」词条；PROJECT_PROGRESS 同步（最后更新 / A1+A2 三票完结 / AI 对话行 / 规划中 / 技术债 / 426 全量证据）。
- 遗留：`.claude/rules/fastapi.md` §5 / `.claude/rules/desktop-state.md` §5 的事件清单落后于实现（实际七事件，含 `tool_call`/`tool_result`；`interrupt` 尚未在 chat 命令流发出）——rules 为规范正本禁改，已在 backend/AGENTS.md 明示"以代码为准、rule 待同步"，建议后续落 ADR-0019 或单独 rules 修订票。
- 遗留处置（2026-09-14）：已解决——ADR-0019 落盘（事件清单扩展决策与载荷契约），两份 rules 正本 §5 与 docs/rules/ 两份镜像同步为八事件全集，backend/AGENTS.md"待同步"备注解除，PRD v2.7 API 清单行同步。
