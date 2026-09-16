# CB-08 — Agent 可观测性：区分抽取/检索/回答错误（复用 llm_call_logs）

**What to build:** 零第二套 SSE/任务系统的前提下，让构建与检索链路可归因：抽取错误 vs 检索错误 vs 回答错误可区分；日志不含敏感正文。

**Blocked by:** CB-07（大部分随 CB-04/07 落地，本票收口验证）。

**Status:** done

**后端**

- [x] 核对 llm_call_logs 覆盖：graph_name="course-brain"（构建抽取，graph_node="extract"）与 "chat"（问答，graph_node="generate"）可区分；model/prompt_version/token_usage_json 已记（既有测试断言 `course-brain`/`course_brain_v1` 与 `chat`/`chat-concept-v6`）
- [x] 构建任务可追溯：processing_jobs.id / input_json.source_fingerprint（request_build 写入）/ result_json.fingerprint（worker 落盘）已核实在位（CB-04）；抽取置信度 relation.confidence、候选 relevance 落业务表已核实
- [x] 查询命中可追溯：`write_llm_call_log` 增 `retrieval_count` 参数（None=未检索 / 0=检索无命中 / n=命中合计），`stream_chat_reply` 按 `RETRIEVAL_TOOL_NAMES`（search_transcript/search_library，互斥挂载故无跨工具双计；web_search 不混入）累计 tool_result 命中并写入两条埋点（成功+失败轮）；命中 Concept ID 经 search_library `concepts[].concept_id` 返回（CB-07 已落，测试已断言）
- [x] 用户审核结果可追溯：apply-review 事务成功后写 loguru 审计 `course_brain_review_applied`（course_id + 五类决策计数，键复用 `ReviewDecisionType`；无概念名/正文）；409 回滚不留痕
- [x] 验证测试：三类错误可区分——INVALID_STRUCTURED_OUTPUT（course-brain 埋点+job FAILED，test_extraction_failure_llm_log_distinguishes_error）、FTS 异常（检索工具内部捕获→ok=false 错误载荷+`chat_tool_failed` warning+埋点 0 命中，test_fts_exception_streams_failure_and_logs_warning）、SSE error（chat 埋点 CHAT_STREAM_FAILED，test_provider_failure 扩展断言）；retrieval_count 三态（1/None/0）+ 日志全列无正文断言（test_llm_call_logs_retrieval_count_and_no_body）
- [x] 实施新增：search_transcript / search_library 工具体异常捕获返回 ok=false 载荷（同 B1 web_search 先例）——此前 FTS 异常会炸整轮流并与回答错误（CHAT_STREAM_FAILED）混淆，归因不可能；工具参数校验失败路径（ToolMessage error）不变

**门禁**

- [x] 后端四门禁全绿（pytest 550 / ruff check+format / pyright 0 错 / openapi 零 diff）；提交：`feat(backend): 收口 Course Brain 可观测性归因链路（F4 CB-08）`（96e75f4）
