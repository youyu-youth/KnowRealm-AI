# 06 — Learner Memory V1：可治理的学习者长期记忆

**What to build:** 学习画像新增「AI 记忆」区域：显式学习偏好可查看、编辑、删除；观察偏好带置信度、证据数与确认时间，经用户确认才生效且永不覆盖显式偏好；对话中说「记住……」出现就地确认卡片；每轮实际注入了哪些记忆可查看；外部处理同意扩展到记忆外发并可单独关闭（关闭后记忆保留本地、本地检索不受影响）；离线时记忆管理全部可用。

**Blocked by:** 02 — Schema、存量回填与基础工作台.

**Status:** done（2026-09-20，代码与自动化门禁完结；真机验收统一收敛在工单 07 清单）

- [x] `LearnerProfileService` 聚合偏好、掌握度、误区、近期学习证据与目标，按任务与会话范围生成限长、可重建的 Learner Context；Agent 运行前由确定性中间层注入，模型不能扩大读取范围；全局显式偏好可跨 Agent、Course 状态不越界注入、ALL 只取任务所需最小集合、受字符预算约束 → `learner/service.py` `build_learner_context`（全局显式+观察偏好跨会话；课程状态=Mastery Engine 同源 `classify_status` 派生的 CONFIRMED 概念状态计数+薄弱概念 top5，仅进对应课程范围〔RECORD/LIBRARY_ITEM 取挂载对象所属课程〕；ALL/FREE 仅全局偏好；预算 `LEARNER_CONTEXT_MAX_CHARS=2000` 先到先得）；注入点=`agent/context.py` SYSTEM 末尾（语言/联网指引之前，计入预算）；**备案**：误区/目标当前无实施表（misconceptions/learning_goals 未建模）、近期证据已由掌握度快照聚合——按「零复制事实源」原则不编造数据，待对应表落地后在此扩展
- [x] 记忆写入仅两类入口：用户在学习画像直接编辑显式偏好；结构化学习证据或用户明确「记住」生成 MEMORY 提案、确认后由 LearnerProfileService 写入 `learner_preferences`（复用 02 提案框架，本票落 MEMORY 生成方与应用器）；普通聊天零静默提取 → 应用器 `learner/service.py::apply_memory_proposal`（learner/routes 导入即注册，先例 organize）；生成方=对话 `propose_memory` 工具（EXPLICIT，恒挂载任意会话，docstring 约束仅在用户明确「记住…」时调用）；**备案**：OBSERVED 应用器/payload/端点/治理 UI 全就位，但「结构化学习证据→观察偏好」的推导算法与触发时机 spec 未定义，V1 不内置自动触发器（普通聊天零静默提取），未来生成方经 `POST /api/proposals` 即接通
- [x] 对话中 MEMORY 提案就地确认卡片：确认写入、拒绝零变更；观察偏好带置信度/证据计数/时间，不覆盖用户显式偏好 → SSE done 载荷扩展 `memory_proposals`（工具 ToolMessage 解析派生，零新事件类型，对齐 ADR-0019）；前端 `ChatMemoryPanel` 就地确认卡（confirm/reject 端点）；观察与显式物理分列（observed_* 列独立），观察写入路径不触碰显式列
- [x] 本轮对话实际使用的记忆在 UI 可查看；Learner Context 只影响解释方式与建议，不改变 Mastery、Evidence、Quiz 判分等确定性数值 → done 载荷 `memory_used`（实际注入条目）+ ChatMemoryPanel 展示（当轮语义不落库）；聚合为只读查询，课程状态经 Mastery Engine 同源纯函数派生，零写入
- [x] 外部处理同意扩展：第一次范围问答前告知将发送相关来源片段与最小必要记忆并取得绑定供应商身份的同意，地址/密钥变化后重新确认；设置页「在 AI 中使用长期记忆」独立开关，关闭=不外发但本地可管理、本地检索不受影响 → 注入前提=`memory_outbound_enabled`（settings.json 偏离项键 `learner_memory_outbound_enabled`，默认开启）AND `llm_consent` 当前供应商指纹有效（复用既有 consent，fail-closed：accept 派生 `memory_injection_allowed`，`_session_context` 默认 False）；开关端点 `PUT /api/learner/memory-outbound`；学习画像「AI 记忆」区展示开关+同意状态（失效提示重去 AI 服务确认）
- [x] 日志不记录记忆正文；全量导出/备份与升级前快照包含 learner_preferences；离线时查看、编辑、删除、本地聚合可用，依赖 LLM 的建议明确降级不产伪结果 → 工具/注入路径仅记元数据；导出/备份/升级快照=整库 VACUUM INTO 天然包含；记忆管理全部本地端点，关闭外发/离线零依赖 LLM
- [x] 硬门禁自动化用例：未经确认零写入、关闭外发后零发送、删除后零再次注入、Course 状态零越界注入；zh/en 文案同步 → `tests/test_learner_memory.py` 17 例：提案创建后零行、accept 派生标志三态（consent 无效/授予/开关关闭）、injection_allowed=False 零注入、PUT 清空后零注入、课程 B 概念不入课程 A 上下文、OBSERVED 确认后显式列逐字节不变；`tests/test_chat_streaming.py` 工具面矩阵同步（propose_memory 恒挂载）；错误码 `LEARNER_OBSERVED_KEY_NOT_FOUND`（404）登记错误码清单+zh/en errors 文案；i18n settings.learnerMemory/chat.memory zh/en 21+10 键

## 备注

- 本票只依赖 02（表+提案框架），不依赖资料库主线 03~05，可并行推进；须在 07 集成验收。
- Mastery / Misconception / Goal 保持各自事实源，本票零复制；不新建 `learner_profiles` 或通用 `memories` 表。
- **实施记录（2026-09-20）**：①MEMORY 提案 payload 判别 schema（`MemoryProposalPayload`，EXPLICIT/OBSERVED 双形态）落 `library/schemas.py` 并注册进 `_PAYLOAD_SCHEMAS`（`POST /api/proposals` 放行 MEMORY），应用器在 learner 域注册——避免 library↔learner 模块环（先例：ChatScope 落 library）；②SSE done 载荷加可选字段 `memory_used`/`memory_proposals`（向后兼容），不扩 ADR-0019 事件类型集合；③`propose_memory` 工具超限（>5 条或单条 >100 字）返回 `ok=false` 由模型告知用户，不静默截断（确认卡不得展示被改写的内容）；④已知遗留（非本票引入）：`stream_chat_reply` 中 search_library/web_search 的 ContextVar reset 在跨 task 中断场景存在与本票 memory reset 相同的跨 context 隐患（memory 侧已 try/except ValueError 防护，先例路径未动，挂载会话中断时理论可触发）；⑤test_document_import 1 例在 HEAD 上既有失败（stash 验证与本票无关）。
