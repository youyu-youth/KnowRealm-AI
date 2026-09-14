# SSE 事件清单扩展：tool_call / tool_result（工具调用流）

---
Status: accepted（2026-09-13 chat-retrieval-tool grill 定稿，2026-09-14 落 ADR 并同步 rules）
---

挂载会话检索（PRD #59，A2 过程透明）要求把 Agent 工具调用过程透出到前端：SSE 流内显示"正在检索「关键词」→ 命中 n 条"状态卡。原六事件清单（`token`/`status`/`citation`/`interrupt`/`done`/`error`）只表达"结果流"，无法表达"工具执行中"的过程态。事件清单是前后端共享契约，且两份编码规范（`fastapi.md` §5 / `desktop-state.md` §5）均以"固定为"措辞钉死清单，变更不可静默，故落 ADR。

**决定**：AI/Chat 命令流新增 `tool_call` / `tool_result` 两事件，SSE 事件全集从六种扩为八种：

- **载荷**：`tool_call` = `{tool, query}`（工具名 + 检索词）；`tool_result` = `{tool, hits, ok}`（命中数；工具失败 `ok:false`）。事件不进 OpenAPI schema（与 `citation` 同惯例）。
- **序列**：`status → (tool_call → tool_result)* → token… → citation… → done / error`；工具调用可多轮，正文 token 与工具事件穿插时按实际到达顺序转发。
- **使用范围**：仅 AI/Chat 工具调用流；Record 失效通知流不受影响（仍只发 `invalidate`）。
- **`interrupt` 澄清**：保留给需要前端确认界面的流，chat 命令流当前尚未发出——清单中的 `interrupt` 是全集口径而非 chat 现状。
- **消费侧容错**：前端解析器对畸形载荷（类型不匹配）直接忽略，不中断流。

## Considered Options

| 方案 | 结论 |
|------|------|
| **扩清单（+`tool_call`/`tool_result`，复用既有 SSE 通道）** | **采纳**——最小增量；与 `token`/`citation` 同一解析与令牌通道；不持久化、随流生灭，历史消息仍只有正文 + 引用 |
| 复用 `status` 事件塞工具信息 | 否决——`status` 是阶段语义，工具过程需要成对的开始/结束事件，塞载荷会破坏其单一职责 |
| WebSocket / 独立工具通道 | 否决——为单一功能引入第二推送通道，违背"不引入 Realtime"既定边界（ADR-0008） |

## Consequences

- 两份编码规范正本（`.claude/rules/fastapi.md` §5 / `.claude/rules/desktop-state.md` §5）与 `docs/rules/` 发布镜像已同步为八事件清单；`backend/AGENTS.md` 的"rule 待同步"备注随之解除。
- 事件清单消费即冻结：新增事件须扩清单并落 ADR；前端对未知事件类型应忽略不报错。
- 工具轨迹不持久化（`done` 后状态卡随流式态消失），历史消息契约不变；将来若要"历史也看检索过程"需另立决策。
