# 03 — 向课程添加文本记录（复用验证）

**What to build:** 学习者说"向 Python 学习课程添加这条记录"并给出文本，Agent 查找消歧课程后出确认卡（明示"保存后将尝试生成 AI 总结"），确认后记录保存并收到回执卡（记录入口 + 总结任务真实状态）。第二动作复用 02 公共机制，作为扩展性验收锚点。

**实施约束：** 不造轮子——优先复用 deepagents / langgraph / langchain 现成 API 与仓库已验证模式（`@tool`、`AgentConfig` 装配、`ProposalService`、领域 Service）；框架用法先经 `langchain-docs` / `langchain-reference` / `context7` 任一 MCP 或 `.agents/skills/` 相关 skills 查证（详见 spec Further Notes）。

**Blocked by:** 02 自然语言创建课程。

**Status:** done

- [x] TEXT_RECORD_ADD 复用 02 的 operations 注册与提案链：公共流程零改动（仅注册新动作 + 新薄工具）——扩展性硬验收
- [x] 文本捕获事务内核心抽取：Record(SUMMARY_PENDING) + Transcript + 搜索索引 + 资料库回填同事务；HTTP 与应用器共用，既有捕获路由测试零改动通过
- [x] 总结 job 维持事务外 best-effort；result_json 回写 {record_id, summary_job_id | 提交失败错误码}
- [x] 回执卡三态如实呈现：记录已保存 ≠ 总结已生成 ≠ 可检索；总结提交失败展示可重试入口指引
- [x] 确认卡明示"保存后将尝试生成 AI 总结"；用户要求"只保存不总结"时如实告知当前不支持（不绕过、不谎称）
- [x] 目标课程归档/不存在 → 提案 FAILED + 稳定错误码，零悬挂记录；执行前重新校验
- [x] 正文超限（1 MiB）与空正文 → 稳定错误码，模型可转述；标题取首行 100 字对齐领域
- [x] 幂等：确认重放不重复建记录；总结失败不重复建记录
- [x] 写目标解析与会话范围解耦：FREE 会话可向消歧出的课程添加记录，资料读取范围不变
- [x] zh/en 文案同步；新错误码登记；门禁全套过

## 实施备注

- **复用验证（扩展性硬验收）**：`registry.py` 与 `proposals.py` 零改动（git diff 证明）；03 = `operations/text_record_add.py`（动作常量 + 应用器 + `register_operation` 导入即注册）+ `tools/add_text_record.py`（薄工具，docstring 面向模型含消歧指引与「只保存不总结不支持」如实告知）两个新文件，载荷契约 `TextRecordAddPayload/Result` 入 `agent/schemas.py`（02 review 定下的归属）。挂载=恒挂载段追加（`_resolve_agent_config`）+ `OPERATION_TOOL_NAMES` 加名 + prompt bump `chat-library-scope-v11` / `chat-research-scope-v12`。
- **事务内核心**：`TextCaptureService.create_core(session, body) -> record_id`（正文 normalize/空/超限校验 + 课程存在/归档重校验 + Record(SUMMARY_PENDING/NOTE) + Transcript + `upsert_record_index` + `ensure_backfill_enqueued`，调用方拥有事务）；`create` 改为前置 capture_type/速记约束 + 调 core + 事务外 best-effort 总结（原行为）。既有 `test_text_captures` 零改动通过（错误码与顺序不变，仅空正文/超限校验从事务前移入事务内——客户端不可见）。
- **总结提交在确认事务内 best-effort（spec 决策 6「事务外」的字面偏离，评审判定忠实且更优）**：应用器在确认事务内同 session 调 `SummaryService.enqueue_if_eligible_in_transaction`（新公开辅助：provider/同意检查只读配置文件不入库，`_enqueue` 异常仅记日志 + 错误码返回、不回滚记录创建）——job 行与 record/APPLIED/result_json 原子提交。理由：纯事务外方案在提案应用器场景有真实洞（主事务持 SQLite 写锁时独立事务死锁；或崩溃后记录已 APPLIED 重放 409、job 永久丢失）；best-effort 语义（失败不连累记录、错误码进 result_json、回执如实三态）完整保留。`TEXT_RECORD_ADD_SUMMARY_ENQUEUE_FAILED` 按任务侧结果码先例不入错误码码表（清单「不入码表的范围」已注明，zh/en errors 段有文案）。（03 review 修复 P1：`except Exception` 曾包住 `_enqueue` 的 `session.flush()`——DBAPI 级失败后 session 进 rollback-only，吞错返回带 record_id 的半成功回执而主事务注定回滚；修复=job 写入包 `begin_nested()`（SAVEPOINT），flush 失败只回滚到保存点、session 恢复、主事务照常提交；SAVEPOINT 可靠性经真实 engine 配置探针实证〔项目 engine 未配 pysqlite workaround，不能假设〕；补数据库级注入〔坏 CHECK 行 flush 炸→记录幸存+回执记失败码+零 job 行〕与业务性注入〔带码异常→best-effort 保持〕两测试）
- **data_dir 进程级绑定**：应用器契约只拿 session（`request.app.state` 不可达），`core/data_dir.py` 新增 `bind_data_dir`/`bound_data_dir`（lifespan 绑定一次、收尾解绑；测试直调应用器自行绑定）。review 备案：fastapi.md「core/ 无状态」字面与「公共流程零改动」硬验收冲突时取后者，绑定属数据目录进程机制非业务状态；未绑定时总结按未触发处理（生产恒绑定）。
- **载荷校验**：`course_id` 用 UUID pattern（str 而非 UUID 类型——`lenient_tool_args_schema` 派生 `annotation | None` 对非 str 原语在 OpenAI tool schema 序列化上不稳）；正文空 → `min_length=1` 缺失项、超 1 MiB → model_validator 模型级 detail（对齐 02 条件必填先例，模型转述）；领域核心兜底同口径（EMPTY_TEXT/TEXT_TOO_LARGE）。
- **前端**：`ChatOperationProposalCard` 泛化双类型——`labelKey` 按类型分发文案键、拆 `SettledProposalRow`/`ActionableProposalRow`/`ProposalPreviewFields` 子组件（review 修复：JSX 超 150 行硬违规 + 三元散布收敛）；TEXT_RECORD_ADD 确认卡=目标课程名（既有课程 API 按 id 拉取，spec 决策 14；不可读如实提示）+ 正文摘要（折叠空白截断 120 字）+「保存后将尝试生成 AI 总结」明示；回执三态=已提交生成中 / 未触发（AI 未配置或未同意外发）/ 提交失败+记录页重试指引；记录入口 `/records/$recordId`。`panelTitle` 泛化「操作提案」；DecisionOverride 泛化为 `{status, result}`。（03 review 修复：GPT P3「类型分派散落」属实——`CARD_BY_TYPE` 配置表收敛〔label 前缀 + PreviewFields + SettledRow + 类型清单四分派点聚合单表，先例=ToolActivityCard 的 TOOL_ACTIVITY_META〕，拆 `CourseCreate`/`TextRecord` 两组类型子组件，14 用例零改动通过证明 DOM 零变化）
- **迁移 0029**：agent_proposals 整表重建放开 `TEXT_RECORD_ADD` 进 CHECK（0028 先例）；`supported_user_version()` 自动 29，全库断言仅 test_library 一处字面量同步（28→29）。
- **测试**：后端 11 项新用例（未绑定/签名同源防线/缺失项/超限 detail/未知键/PENDING 创建零记录/确认应用全量断言含索引与回填/幂等 409 零重复/provider 配置下 job 提交/课程不存在 FAILED 零悬挂/归档 FAILED/拒绝零事实）；挂载矩阵与 prompt 版本断言同步（7 处列表 + v11/v12）。前端 5 项新用例（确认卡预览+提示、确认回执+总结已提交、三态恢复、FAILED 可重试、课程不可读兜底）。
- **门禁**：后端 pytest 全量 **759 passed 满绿** + ruff/format + pyright 0 错 + OpenAPI `--check` 零 diff；前端 vitest 全量 533/534（唯一失败为 TodoPanel 既有并发抖动，单跑 8/8 绿）+ lint + build（内嵌 tsc）+ i18n 一致性防线 + 触及文件 Prettier；api-types regenerate（ProposalType 枚举 +TEXT_RECORD_ADD）。
- **双轴 code-review**：Spec 轴判定忠实（零缺失零越权；事务内 best-effort 偏离被评「忠实且更优」；两处字面偏差备案：超限走 detail 非稳定码〔02 先例一致〕、三态措辞按 APPLIED 时刻快照解读）；Standards 采纳 1（组件拆分子组件），备案不采纳 4（data_dir 全局=硬验收优先、enqueue 三变体=事务边界有意不同、UUID 正则=langchain 派生安全、vi.mock=文件既有先例）。
