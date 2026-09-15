# CB-08 — Agent 可观测性：区分抽取/检索/回答错误（复用 llm_call_logs）

**What to build:** 零第二套 SSE/任务系统的前提下，让构建与检索链路可归因：抽取错误 vs 检索错误 vs 回答错误可区分；日志不含敏感正文。

**Blocked by:** CB-07（大部分随 CB-04/07 落地，本票收口验证）。

**Status:** todo

**后端**

- [ ] 核对 llm_call_logs 覆盖：graph_name="course-brain"（构建抽取）与 "chat"（问答）可区分；model/prompt_version/token_usage_json/retrieval_count 已记
- [ ] 构建任务可追溯：processing_jobs.id / input_json.source_fingerprint / result_json.fingerprint 已落（CB-04）；抽取置信度随 relation.confidence、候选 relevance 落业务表
- [ ] 查询命中可追溯：chat 的 llm_call_logs.retrieval_count 反映概念扩展后的合并检索数；命中 Concept ID 进 search_library 返回（concepts[].concept_id，Agent 上下文自带）
- [ ] 用户审核结果可追溯：apply-review 写审计日志（loguru 最小元数据：course_id/decision 计数，无正文）
- [ ] 验证测试：三类错误（INVALID_STRUCTURED_OUTPUT=抽取、FTS 异常=检索、SSE error=回答）日志可区分；日志断言不含 prompt/转写正文

**门禁**

- [ ] 后端四门禁全绿；提交：`feat(backend): 收口 Course Brain 可观测性归因链路（F4 CB-08）`
