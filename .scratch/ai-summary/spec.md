# AI 总结与 HITL

Status: ready-for-agent

## Problem Statement

KnowRealm 已能从真实文档和音频来源形成 Transcript，并将 Record 推进到 SUMMARY_PENDING，但学习链在这里停止。用户无法配置 LLM、明确同意外发、生成结构化总结、调整结果或确认落定；今日页也无法呈现真正需要人工处理的总结待办。

本功能还是项目首个 LangGraph、LLM Provider、Checkpoint、LLM 调用日志和学习事件消费者。如果把运行态当业务事实、在恢复 interrupt 时重复调用模型、静默截断长文、批量消费所有待总结记录或把 Transcript 写入日志，会同时破坏可恢复性、费用边界和本地优先隐私合同。

## Solution

Plan 06 交付一条真实纵向闭环：用户配置一个 active LLM Provider，通过合成 Transcript 完成结构化连接测试，并明确同意把 Transcript 发送给该供应商。正常新 Transcript 在配置、同意和 ACTIVE 课程条件满足时自动创建 Summary Job；缺少条件时保持 SUMMARY_PENDING，由当前 Record 显示服务端给出的下一步动作，不批量扫描历史 Record。

每次 LLM 生成对应一条可查询 Summary Job。固定 Summary Graph 使用按 Record 与 Transcript source_version 隔离的 thread_id；生成节点产出不可变 Summary 版本，review 节点 interrupt 等待确认或调整。调整使用同一 Transcript、上一版总结和用户反馈生成新版；新版成功后才使上一版过时。确认在单个业务事务中落定 Summary、Record 和幂等 Learning Event。

短 Transcript 单次生成；超过 3 万 Unicode code point 时按段落保持顺序分块并递归 map-reduce，任何阶段不得截断。单次 LLM 请求 90 秒超时且不自动重试。初次失败令 Record 进入 FAILED；调整失败保留上一版 SUMMARY_READY。Transcript、总结、Prompt、密钥不进入日志。

桌面端沿用现有 Record Summary 页签、Record SSE 失效通知和 Continuous Work Surface。SUMMARY_READY 同时进入今日页待办；确认后移除。未实现的知识点、习题和 Todo 只依据 COMPLETED 建立真实门禁，仍明确标注未接入。

## User Stories

1. As an 学习者, I want to 在应用内配置一个 LLM Provider, so that 我不必手改配置文件。
2. As an 学习者, I want to 使用 DashScope 预设或自定义 OpenAI 兼容地址, so that 我可以选择自己的模型服务。
3. As an 学习者, I want to Provider 只包含地址、密钥和模型, so that 当前配置保持最小清晰。
4. As an 学习者, I want to GET Provider 时看不到原始密钥, so that 界面读取不会泄露凭据。
5. As an 学习者, I want to 空密钥更新保留原密钥, so that 修改模型时无需重复粘贴密钥。
6. As an 学习者, I want to 显式清除 Provider 密钥, so that 我能撤销本机保存的凭据。
7. As an 学习者, I want to 自定义地址拒绝内嵌凭据和非 HTTP(S) URL, so that Authorization 不会被错误发送。
8. As an 学习者, I want to 连接测试使用合成内容, so that 测试服务时不会外发真实资料。
9. As an 学习者, I want to 连接测试走正式结构化 Schema, so that 名义兼容但不能总结的端点不会被误报成功。
10. As an 学习者, I want to 配置凭据后仍明确同意外发, so that 保存密钥不会自动授权发送 Transcript。
11. As an 学习者, I want to 外发同意绑定供应商身份, so that 地址或密钥变化后旧授权不能沿用。
12. As an 学习者, I want to 同一供应商只切换模型时保留同意, so that 正常模型调整不会重复打断我。
13. As an 学习者, I want to 缺 Provider 或同意时 Record 保持 SUMMARY_PENDING, so that 可恢复条件不会伪装成永久失败。
14. As an 学习者, I want to 配置完成后只生成当前 Record, so that 应用不会批量外发历史资料并消费 token。
15. As an 学习者, I want to 正常新 Transcript 自动进入总结, so that 唯一自动 AI 触发点能衔接捕获流程。
16. As an 学习者, I want to Transcript 编辑后显式点击重新生成, so that 保存文本不会产生意外费用。
17. As an 学习者, I want to 只有 ACTIVE 课程触发总结, so that 归档知识空间不会继续消费服务。
18. As an 学习者, I want to 提交生成在 2 秒内返回 Job 标识, so that UI 不被模型调用阻塞。
19. As an 学习者, I want to 看到 SUMMARY_PROCESSING 状态与 Job 进度, so that 我知道总结仍在运行。
20. As an 学习者, I want to 每次生成有独立 Job, so that 初次、调整和失败历史可区分。
21. As an 学习者, I want to 每个总结绑定 Transcript source_version, so that 结果不会覆盖新编辑的文本。
22. As an 学习者, I want to 迟到结果被取消且不保存正文, so that 旧输入不能污染当前总结。
23. As an 学习者, I want to 应用重启后继续看到待确认总结, so that HITL 不依赖前端内存。
24. As an 学习者, I want to 隔天仍可确认同一总结, so that review 没有会话时限。
25. As an 学习者, I want to 总结包含一句话主题, so that 我能快速识别核心内容。
26. As an 学习者, I want to 总结包含 500～1000 字摘要, so that 内容既完整又可读。
27. As an 学习者, I want to 总结按章节与分点结构展示, so that 我可以扫描主要脉络。
28. As an 学习者, I want to 无效结构化输出明确失败, so that 不完整结果不会静默入库。
29. As an 学习者, I want to 单次 LLM 请求 90 秒后终止, so that 失联请求不会无限占用 worker。
30. As an 学习者, I want to 模型失败不自动付费重试, so that 每次额外消费都由我决定。
31. As an 学习者, I want to 手动重试复用失败 Job, so that 页面不会制造重复任务。
32. As an 学习者, I want to 初次失败显示可恢复 FAILED 状态, so that 我能理解并重试。
33. As an 学习者, I want to 调整失败时仍可确认上一版, so that 已有可用结果不会丢失。
34. As an 学习者, I want to 输入 1～1000 字调整反馈, so that 我能要求更简洁或侧重某主题。
35. As an 学习者, I want to 调整结合 Transcript、上一版和反馈, so that 新版本针对当前结果改进。
36. As an 学习者, I want to 新版成功后才使上一版过时, so that 失败不会破坏可确认版本。
37. As an 学习者, I want to 调整次数不受业务限制, so that 我能迭代到满意结果。
38. As an 学习者, I want to 确认时携带当前 Summary ID, so that 旧页面不能确认新版本。
39. As an 学习者, I want to 重复确认得到同一结果, so that 双击和网络重试不会重复写事件。
40. As an 学习者, I want to 确认后 Record 进入 COMPLETED, so that 后续能力获得真实门禁。
41. As an 学习者, I want to 确认动作落一个 SUMMARY_CONFIRMED 事件, so that 学习行为可追溯。
42. As an 学习者, I want to 删除 Record 后仍保留追加型学习事件, so that历史行为不会被级联清除。
43. As an 学习者, I want to 今日页只显示 SUMMARY_READY, so that 行动流只呈现真正需要我的事项。
44. As an 学习者, I want to 从今日待办直达对应 Summary, so that 我能快速完成确认。
45. As an 学习者, I want to 确认后待办立即移除, so that 今日页与业务事实同步。
46. As an 学习者, I want to 未实现的后续按钮仍明确不可用, so that COMPLETED 不会制造假功能。
47. As an 学习者, I want to 3 万字以内单次生成, so that 常规材料不承担无谓分块复杂度。
48. As an 学习者, I want to 超过 3 万字按段落保持顺序分块, so that 长文不会静默截断。
49. As an 学习者, I want to 单个超长段落也完整处理, so that 异常排版不会导致内容丢失。
50. As an 学习者, I want to reduce 输入过长时递归归并, so that 任意长度材料都不因中间结果溢出而被截断。
51. As an 学习者, I want to 每次调用记录模型、Prompt 版本、token 和耗时, so that 总结成本与故障可观测。
52. As an 学习者, I want to 日志不包含 Transcript、总结、Prompt 或密钥, so that 本地资料不会进入观测记录。
53. As an 学习者, I want to 查看当前总结和历史版本 API, so that版本链可以被后续界面回溯。
54. As an 学习者, I want to 当前界面只展示可操作版本, so that本票不因历史浏览器扩大复杂度。
55. As an 开发者, I want to 默认测试使用可注入假模型, so that CI 不需要密钥或 token。
56. As an 开发者, I want to 通过显式命令评审 20 条匿名样本, so that qwen-plus 质量证据与默认回归分离。
57. As an 开发者, I want to 长文样本证明所有输入片段参与生成, so that 禁止截断可以自动回归。
58. As an 开发者, I want to ASGI、SQLite、Checkpoint、桌面渲染和真实 Provider 证据分层报告, so that 假模型测试不会冒充真实 AI 闭环。

## Implementation Decisions

- 使用固定 Summary StateGraph，不使用 Agent、工具或联网能力。
- `summary_json` 固定为 `sections: [{ heading, points }]`；topic、abstract 独立持久化。
- 输出按 Unicode 字符约束：topic 1～80，abstract 500～1000，sections 1～12，每节 points 1～8，heading 1～80，每点 1～500。
- 每次 LLM 生成对应一条 Summary Job；调整失败复用该失败 Job重试，不让已成功 Job 回退运行态。
- Graph thread_id 为 `summary-{record_id}-source-{source_version}`；Checkpoint 只存运行态，Summary 版本链与确认结果落业务库。
- 缺 Provider/同意时不建 Job；API 返回 `NONE / CONFIGURE_PROVIDER / GRANT_CONSENT / GENERATE / RETRY` 判别动作。
- Provider 同意绑定 `base_url + api_key` 指纹；模型变更不使同意失效。
- 初次生成失败令 Record FAILED；调整失败保留 SUMMARY_READY；迟到结果 Job=CANCELLED 且只记 STALE_TRANSCRIPT 元数据。
- 确认携带 summary_id；事件幂等键为 `summary-confirmed:{summary_id}`，source_type=AI_SUMMARY。
- learning_events 的业务标识为逻辑引用，不使用级联外键。
- 版本 API 提供当前与列表/详情；V1 UI 只展示当前版本。
- 今日页只查询 SUMMARY_READY；后续资产入口保持未接入。

## Testing Decisions

- 主要高层 seam 是受启动令牌保护的 ASGI API：覆盖 Provider、提交、Job、Summary、调整、确认、历史与今日待办。
- SQLite 迁移测试覆盖 fresh/upgrade、唯一约束、追加事件和 Transcript 版本竞态。
- Graph 使用 InMemorySaver 与可注入假模型验证 interrupt/resume；单独使用 AsyncSqliteSaver 验证跨应用重启恢复。
- 桌面端使用 MSW + Testing Library 按可访问角色验证用户行为，不断言内部 Query 状态。
- 真实 qwen-plus 只通过显式评审命令运行 20 条匿名样本；默认测试不得访问网络。
- 最终证据分为静态检查、单测、ASGI/SQLite、真实 sidecar/HTTP、浏览器渲染、真实 Provider 六层。

## Out of Scope

- 知识点、习题、Todo、复习资料及其可点击实现。
- Summary 历史版本浏览界面。
- 多 Provider 卡片 CRUD、用量面板和健康中心。
- 联网搜索、RAG、Source Anchor 与 Segment 持久化。
- 自动重试、批量扫描 SUMMARY_PENDING 或后台批量消费 token。
- `.msi` 安装和发布流水线。

## Further Notes

- 默认质量基线只对 DashScope qwen-plus 负责；自定义端点必须通过正式 Schema 连接测试，但不承诺相同内容质量。
- `langgraph.db` 与 `knowrealm.db` 同目录不同文件；不手工查询 LangGraph 内部表。
- 当前实现必须复用 Record 失效通知与 REST 事实源，不新增第二条 Summary SSE。
