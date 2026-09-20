# 01 — 研究会话全栈闭环

**What to build:** 用户在聊天页新建菜单选「研究会话」，填研究问题（即会话标题）、选资料范围（默认全部资料，可选某课程 / 纯联网）、选是否联网（默认开，无搜索 key 时明示降级）；AI 回答按固定五节结构组织（已有证据 / 来源差异 / 冲突与缺口 / 暂定结论 / 建议保存的来源），结论挂引用角标、范围内无可引用证据时明确说明而非用常识补答；AI 对研究中发现的有价值外部来源主动生成「建议保存」入库提案，消息流就地确认卡逐条确认 / 拒绝，确认后走现有网页入库链路进入资料库；支持多轮追问深化；会话列表与标题栏显示「研究」徽章。规格全文见 `.scratch/research-session-v1/spec.md`。

**Blocked by:** None — can start immediately

**Status:** done

## 后端

- [x] `ChatMode` 新增 `RESEARCH`；会话创建请求 mode 放开为 `ASK | RESEARCH`（SOCRATIC_TUTOR / TEACH_BACK 继续不放开）
- [x] RESEARCH × scope 校验矩阵：只允许 ALL / COURSE / FREE，与 RECORD / LIBRARY_ITEM 组合拒绝 422（错误码登记 + zh/en 文案）
  - 实施偏差：`chat_sessions.mode` 列的 CHECK（0014 建、0026 重建）物理拦住 'RESEARCH'，spec「零迁移」不成立——0027 照 0015/0026 先例整表重建放开（`PRAGMA legacy_alter_table=ON` 防 FK 改写），零新列零数据变更；数据模型文档 :301 值域行已同步（升版重命名待用户拍板）
- [x] 研究会话独立 prompt：五节固定 Markdown 结构文本协议 + 无证据拒答纪律 + web 与本地 citation 类型不冒充 + FREE 明示「无本地资料范围」；prompt 版本 bump（`CHAT_RESEARCH_PROMPT_VERSION = chat-research-scope-v9`，普通会话维持 `chat-library-scope-v8`，按会话 mode 分流记入 llm_call_logs）
- [x] 工具挂载：RESEARCH + 非 FREE 挂 `search_library`；`web_search` 沿用每请求标志机制零改动；`propose_memory` 恒挂载沿用
- [x] 新工具 `propose_ingest`：仅 RESEARCH 会话挂载；ContextVar 绑定运行期上下文照 propose_memory 先例；超限拒绝而非截断（5 条 / URL 2048 字 / 标题 200 字）；提案类型复用 `RESEARCH_INGEST`（载荷 {url, title, course_id}，scope=COURSE 自动带课程 id，ALL/FREE 落 None）；溯源带 session_id，与手动提案口径一致
- [x] SSE 流内提案事件 + done 载荷新增 `research_proposals`（照 memory_proposals 全链路先例，零新 SSE 事件类型）
- [x] 后端测试：`tests/test_research_session.py` 17 例——创建矩阵（含拒绝组合 / mode 字面量仍受限）、研究 prompt 文本协议断言（五节/拒答/不冒充/FREE）、propose_ingest 未绑定 / 超限 / 成功建案三分支、挂载矩阵与 done 载荷形状（Fake chat model 先例 + llm_call_logs 记研究版本）
- [x] OpenAPI `--check` 零 diff + api-types regenerate（mode 字面量 `ASK | RESEARCH` 进契约）

## 前端

- [x] 新建菜单新增「研究会话」入口 + 创建弹窗三件：研究问题（必填，即标题，经 `?prompt=` 预填输入框）、范围（默认 ALL，三选一 radio + 课程子列表）、联网开关（默认 ON）
- [x] 联网默认值逻辑扩展：RESEARCH 会话默认 ON（`selectWebSearchEnabled` 增 research 参数，显式记忆优先）；无 Tavily key 时创建弹窗明示降级提示且开关置灰
- [x] 会话列表行 + 标题栏「研究」徽章（chat-accent 色系）；范围胶囊只读（点击=新建会话，沿用零改动）；空会话建议卡换研究特化示例（3 张研究建议卡）
- [x] done 载荷 `research_proposals` 防御性收窄解析（形状不符静默跳过）+ 消息流就地提案确认卡（确认 / 拒绝 / 已处理三态，`ChatResearchProposalCard`）；本轮展示为临时态（chatUiStore.turnMemory 扩 researchProposals）
- [x] i18n zh/en 同步新增（newMenu.research / badge.research / research.* / researchSuggestions.* / researchProposal.* / 错误码，一致性防线过）
- [x] 前端测试：`ResearchSessionDialog.test.tsx` 5 例（弹窗三件与校验 / 三范围提交载荷 / 无 key 降级）、`ChatResearchProposalCard.test.tsx` 4 例、`chatUiStore.test.ts` 3 例（联网默认语义）、`chatSessions.test.ts` +1（research_proposals 收窄）、`chat.test.tsx` +1（列表行与标题栏徽章 / 研究建议卡）

## 零改动确认（不得引入新逻辑）

- [x] Learner Memory 注入沿用现有 scope 逻辑；citations 校验、多回答引用聚合、工具状态卡、web 引用卡手动「建议保存」入口全部零改动

## 门禁

- [x] 后端 pytest（`--basetemp=.pytest-tmp`）721 passed + ruff + pyright 全绿；测后删除临时产物
- [x] 前端 vitest（全量 511 过，4 个失败文件=既有资源竞争抖动 TodoPanel/CourseBrain/QuizTests，单跑批 89/89 绿为稳定证据）+ lint + build（内嵌 tsc）全绿；触及文件 Prettier

## 实施备注（review 回写）

- 双轴 code-review 补齐：`docs/后端错误码清单.md` 登记 `CHAT_RESEARCH_SCOPE_INVALID`；CONTEXT.md「会话范围」词条修订 + 新增「研究会话」词条；评测黄金集 `docs/evaluation/research-session-golden-set.md`（10 题 × 四类 + 四指标门禁 + 复跑流程，真机首跑待用户）。
- 未采纳（judgement call，理由备案）：①确认卡/提案事件解析与 memory 先例成对重复——提取共享组件超出票面最小改动，两处并存留待第三次出现；②「研究问题=标题」经首条消息自动成题兑现（用户清空预填改发他句时标题随首条消息，与既有会话标题机制一致）；③FREE 会话用户显式关联网属意图外组合，prompt 已有诚实指引（无本地资料范围+无证据拒答），不在后端强拦。
