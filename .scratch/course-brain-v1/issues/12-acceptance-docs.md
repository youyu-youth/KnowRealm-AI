# CB-12 — 全链路验收与文档收尾

**What to build:** 按 plan §十发布门禁逐项核验 + 全部文档同步。agent 侧验证止于自动化门禁，真机项单列用户清单不代勾。

**Blocked by:** CB-11。

**Status:** done（2026-09-16）

**自动化验收**（核验方式：`backend/tests/test_course_brain*.py` 47 项全绿 + 前端 grep + 评测文档核对）

- [x] 多来源课程首次构建（KP+Transcript+Document 共同产候选）—— `test_build_collects_multi_source_and_publishes_candidates`；构建内 `learning_events == 0` 断言同测
- [x] Candidate 确认/合并/忽略闭环；正式 Concept 不被重建覆盖（重跑断言）—— `test_apply_review_merge_migrates_records_and_anchors` / `test_rebuild_never_overwrites_confirmed_identity` / `test_rebuild_is_idempotent_and_reuses_confirmed_concept` / `test_dismissed_candidate_rebuilds_as_new_candidate`
- [x] Record 删除与课程移动后来源/计数/图谱失效正确 —— 删除=`test_soft_deleted_record_invalidates_graph_node_counts`；课程移动=`course_brain/service.py` 全部计数/来源查询带 `r.course_id = :course_id` 过滤（查询期排除）+ STALE 指纹触发重建
- [x] Source Anchor 时间/页码/对话跳转数据面正确 —— `test_concept_sources_anchor_kp_chat_and_soft_delete`（音频时间轴/文档页码/Chat 会话三类锚点 + 软删过滤）
- [x] 无 LLM Key 降级（等待态可浏览可手动维护）；LLM 构建失败恢复（旧图谱完好）—— `test_build_preflight_waits_for_provider_and_consent` / `test_build_failure_keeps_previous_graph`
- [x] B2 跨记录问答概念增强；"讲过几次 X"occurrences 去重 Record 计数 —— `test_brain_search_matches_concept_and_expands_segments` / `test_eval_dimension_occurrence_record_dedup`（合成评测维度三 2/2）
- [x] Learning Evidence 零污染（learning_events/learning_evidence 零新行）—— 多来源构建测试断言 `learning_events == 0`；learning_evidence 为事件流纯派生（水位消费），零事件即零证据
- [x] Course Brain 页面无 Mock（grep courseDetailInsights 零残留）—— 图谱链（CourseKnowledgeGraph/KnowledgeMapTab/mockKnowledgeNodes）grep 零残留；`courseDetailInsights` 其余导出仍被 GPS/概览示意卡有意消费（待统计域接入整体替换，CB-10 既定决策），非 Course Brain 页面范围
- [x] CB-01 结论归档 + sqlite-vec 口径明确 —— `docs/evaluation/course-brain-retrieval-baseline.md` 结论（四维全过→延后）与升级路径（terms 同义词列/query-time LLM/CB-VEC 票）已在档；本次同步扩展文档 §40.3 B5 行

**文档同步**

- [x] 数据模型 v2.7→v2.8（git mv 重命名；§4.6 三表标已实施+重建不覆盖语义；「SQLite 无部分唯一索引」论断更正为部分唯一索引库级兜底；表口径=设计 42 张不变、已实施 26 张、2 张 FTS 衍生表不计——工单原记「45 张」系预判笔误，0023 无超出 v2.7 设计的新表）并全库交叉引用同步：扩展文档 5 处（头部一句话读法/D9/§7 回写/A3 回写/§40.3 A0）、PRD 头部、技术栈（42→设计 42/已实施 26）、CONTEXT.md、根 AGENTS.md 权威文档表（断链修复+口径精确）；PROJECT_PROGRESS 两处「现 v2.6」过时表述一并更正
- [x] PRD v2.7 决策表/阶段表 F4 相关行更新（课程详情 Tab 行 :156 / 决策表 F4 行 :280 / Phase 3 行 :307 / 页面清单 :462）；扩展文档 §40.3 B 档新增 B7 行（F4 完结回写）+ B5 行补 CB-01 结论 + §40.4 序列图插入步与补记
- [x] `docs/后端错误码清单.md` 新码入册核对：6 个 COURSE_BRAIN 码已在册（CB-05/06 交付时入册）；CONTEXT.md 词条已随 CB-00 落（Concept / Course Brain / Record Concept / Concept Relation 四条核对在位）
- [x] PROJECT_PROGRESS.md 回写（158 行：头部/§2/§3 加 F4 行/§4 波次 15→16/§5 巨型 F4 进行时段落收敛为完结行，删除被 F4 取代的细节）
- [x] OpenAPI 类型最终 regenerate + `--check` 零 diff（exit 0，CB-05~08 后契约已稳定）

**门禁**

- [x] 后端四门禁全绿：pytest 550 passed（10:15）/ ruff check / ruff format --check（206 files）/ pyright strict 0 错误；前端门禁：test 458/459（唯一失败恒为 TodoPanel「生成候选后可修剪并整批采纳」已知并发抖动，单跑 8/8 绿，本票零前端代码改动、CB-11 基线 459 不变）/ lint / build ✓ / format:check（触及文件无前端文件）；.pytest-tmp 已删除
- [x] 提交：`docs: 回写 F4 Course Brain V1 交付结论`

**用户真机验收（不代勾）**：多来源课程首次构建全程；候选审核（重命名/合并/忽略）；来源跳转（时间定位/页码/Chat 徽章）；课程对话问"讲过几次 X"核对次数与来源；无 Key 状态浏览与手动创建；重建后人工确认内容不被覆盖；亮/暗/窄窗/减少动效；zh/en 切换；真实语料检索评测（CB-01 口径补真）。
