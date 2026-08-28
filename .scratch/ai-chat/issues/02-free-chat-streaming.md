# 02 — 自由聊天流式闭环（含中断、并发与降级）

**What to build:** 在对话页发消息即得完整可用的自由聊天体验：受理立即出现状态反馈，回答逐字流式渲染，完成后消息落库、重开历史完整，连续追问记得近 10 轮。生成中断后半截回答不落库、重试不产生重复提问；生成中不能连发第二条；未配置 AI 服务时进入空态并可就地配置、配完即用。底层：agents 工厂新增流式纯文本生成路径（llm_call_logs 只记元数据）、create_agent 复用既有 checkpointer、POST SSE 端点（token / status / citation / interrupt / done / error，受理即发首条 status）。

**Blocked by:** 01 — 档案切片、三表迁移与对话管理骨架

**Status:** in-review

- [x] 发送后立即收到首条 status 事件；事件序列 status → token… → done 可自动化断言；token 逐字渲染
- [x] 用户与助手消息落 chat_messages；重开会话完整显示历史
- [x] 上下文含创建时的 SYSTEM 快照 + 近 10 轮（经 ChatOpenAI 流式 stub 捕获断言）；第 11 轮时最旧轮不进上下文
- [x] 中断（客户端断开 / 用户停止）→ 生成取消、半截 assistant 内容不落库、用户消息保留（uvicorn 断开 = 生成器 aclose，在生成器边界直接验证；ASGITransport 不传导断开，经探针确认）
- [x] 会话末尾存在"无回复 user 消息"时，再次发送视为补答：复用原 user 行、无重复行（补答请求的文本更新原行内容，见实现裁量）
- [x] 同会话在途第二条发送返回 409；前端流式期间禁用发送
- [x] 流内异常转 error 事件不断流；error 后可继续发问
- [x] 无供应商：`/chat` 可进，"未配置 AI 服务"空态 + 就地配置（复用既有供应商配置），配置完成即可发送
- [x] llm_call_logs 只落元数据（graph_name=chat），无对话正文进任何日志
- [x] OpenAPI → api-types 同步；后端（流式 stub 捕获输入）+ 前端（SSE fetch stub 回放）测试齐备
- [ ] 人工：改角色后新对话语气变化、存量对话不变；首事件 ≤3s 体感
