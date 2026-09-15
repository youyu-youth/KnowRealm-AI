# CB-04 — 多来源收集与构建 Worker（job_type=CONCEPT_EXTRACTION）

**What to build:** `course_brain/worker.py` WorkerSpec + 构建触发端点。启用 processing_jobs SQL CHECK 预留值 `CONCEPT_EXTRACTION`（Python 枚举补成员，零表重建，ADR-0022）。record_id=None 课程级任务。LLM 结构化抽取 → 确定性归一化 → 候选/挂接/锚点 → 原子发布。

**Blocked by:** CB-03。

**Status:** todo

**后端**

- [ ] `ProcessingJobType.CONCEPT_EXTRACTION` 枚举成员（SQL 已有值，零迁移）
- [ ] 多来源收集：未软删记录（ARCHIVED 拦截二次校验）→ 已确认/手动 KP（ACTIVE）+ Transcript Segment + Document Segment + 对话转 KP 的 Chat 锚点保留（经 knowledge_point_id 桥）
- [ ] 分块与预算：按 Record 分块，转写 ≤30k 全文（复用 KP TRANSCRIPT_LIMIT 惯例）、超长降级已确认摘要+KP 清单；文档分片拼入，块总预算 40k 上限
- [ ] LLM 抽取：with_structured_output(Pydantic v2，字段带 description)——`concepts[]{name, description, concept_type, importance, evidence[]{quote≤120, source_hint}}` + `relations[]{source, target, relation_type, confidence}`；复用 Provider 配置/consent preflight/重试/崩溃恢复/INVALID_STRUCTURED_OUTPUT/PROVIDER_REQUEST_FAILED
- [ ] 归一化：strip→空白折叠→全角转半角→casefold；与 CONFIRMED 概念 normalized_name 完全一致→自动挂接（幂等，重复构建不重复建节点）；全新→CANDIDATE；不改 CONFIRMED 名称/描述
- [ ] 锚点建立：evidence.quote 在该记录 segment 内容中逐字子串定位→AUDIO_SEGMENT/DOCUMENT_SEGMENT 锚点+CONCEPT/SUPPORTS 链接（复用 SourceAnchorService 写入函数）；定位失败跳过该条并计数
- [ ] 原子发布：单事务写候选+record_concepts+锚点+relation 候选；失败回滚不破坏上一版图谱；result_json={fingerprint, concept_count, candidate_count}、input_json={provider_fingerprint, source_fingerprint}
- [ ] 触发端点 `POST /api/courses/{id}/brain/builds`：课程存活+非 ARCHIVED、无 key 409 LLM_PROVIDER_UNCONFIGURED、无同意 409 AI_CONSENT_REQUIRED、RUNNING 重复触发 409
- [ ] main.py worker_factories 接线 + recover_interrupted
- [ ] LLM 埋点：graph_name="course-brain"、prompt_version="course_brain_v1"（经 llm/service 统一入口）
- [ ] 测试：多来源共同产候选、重复构建幂等（不重正式节点）、失败保旧图谱、不发学习事件（learning_events 零行）、consent/无 key 等待态、崩溃恢复

**门禁**

- [ ] 后端四门禁全绿；提交：`feat(backend): 实现 Course Brain 构建任务与多来源抽取 Worker（F4 CB-04）`
