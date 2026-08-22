# 按流语义选择 SSE 请求方法

资源状态订阅使用带启动令牌的 authenticated GET，例如 `GET /api/records/{record_id}/events`；需要提交请求体的 AI/Chat 命令流使用 POST。两类流共用 `EventSourceResponse`、统一令牌注入和前端解析通道，但 Record 流只发送 `invalidate` 与 `record_id`，REST/SQLite 继续作为事实源。Record 仅在 `CONTENT_PROCESSING` 或 `SUMMARY_PROCESSING` 时保持连接；断线后立即刷新并每 2 秒轮询和重连，恢复连接或离开处理态即停止，不引入事件持久化、重放或 Last-Event-ID。
