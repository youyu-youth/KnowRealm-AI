# 05 需求与生产路径核对

日期：2026-10-18；基点 `68a96c63bd8eb275ab86a8e404f410561a51535f`。本表只登记归属，运行结论及证据见 [05-implementation.md](./05-implementation.md)，不以映射代替验收。

## 真实入口与消费端

| 代号 | 生产链（均复用当前领域及授权） | 验收文件 |
| --- | --- | --- |
| R | `/api/plan-items/{id}/study`、`/start`、`/tab` → `learning_plan/study.py` → SQLite `learning_plan_items.study_*` → 资料学习 Tool 与 RecordStudyPage / RecordStudySession → 原计划行 | `backend/tests/test_record_study_loop.py`；`RecordStudyPage.test.tsx`、`RecordDetail.test.tsx` |
| P | `/api/plan-items/{id}/practice`、`/requirements`、`/preparations` → `learning_plan/practice.py` / `practice_worker.py` → `practice_requirements`、`practice_preparations`、ProcessingJob → `get_plan_practice`、`confirm_practice_requirements`、`prepare_plan_practice` / PracticePreparationPage | `backend/tests/test_practice_preparation.py`；`PracticePreparationPage.test.tsx` |
| T | `/practice/rounds` → `practice_round.py` → PLAN QuizTest、QuizTestItem.frozen_json、请求映射 → `start_plan_practice` / PracticeRoundCard、QuizTestPage | `backend/tests/test_practice_round.py`；`QuizTestPage.test.tsx` |
| G | `/api/quiz-tests/{id}/answers`、`/submit`、`/api/plan-items/{item_id}/practice/rounds/{id}/retries` → QuizTestService / grading_worker → QuizTestItem、LearningEvent、ProcessingJob → `retry_plan_practice_grading` / 评分覆盖、历史结果 | `backend/tests/test_practice_recovery.py`；`PracticePreparationPage.test.tsx`、`ChatOperationProposalCard.test.tsx` |
| C | 原计划项 `/complete` → PlanItemService / Operation → 首次 completed_at → `complete_plan_item` / 计划与今日投影；阅读/完成不生成验证性证据 | 上述 R/T/G；`test_learning_plans.py`、`test_learning.py`、`test_learning_consumer.py`、`test_mastery.py` |
| D | 迁移链 → 导出 HTTP / `data.archive` → 隔离恢复 / 启动 → 固定题面与作答；课程/记录 DELETE → DocumentCleanupService → 实际 DB 与文件清理 | `test_plan_practice_delivery.py`、`test_archive.py`、`test_document_cleanup.py`、`test_quiz_tests.py`、`test_quizzes.py` |

模型接缝仅替换外部推理或 HTTP 供应商，生产候选裁剪、参数验证、事务、JobRunner、授权及 SQLite 均保留；前端单元/集成的 MSW、Router、IPC 替身与真实原生结果分开。真实模型人工样本、供应商及预算未就绪，不从现有用户目录擅取样本或调用密钥。

## 50 条故事

表中用例均指上表对应测试文件内现有用例；只有 D 的交付组合是本票新增。真实模型的语义质量与真实桌面 150% 不随自动化通过。

| 故事 | 归属 | 实现及验收锚点 |
| --- | --- | --- |
| 1 | 01 / R | `test_bind_start_resume_and_complete_without_mastery` |
| 2 | 01 / R | `test_visit_identity_rebinding_and_restart` |
| 3 | 01 / R | `test_bind_start_resume_and_complete_without_mastery`：普通访问不反填 |
| 4 | 01 / R | 缺关联 → HTTP 确认 → 明确启动 |
| 5 | 01 / R | `test_mounted_agent_only_binds_after_human_confirmation` |
| 6 | 01 / R | `test_lifecycle_and_scope_are_enforced_at_http_writes` |
| 7 | 02 / P | `test_requirements_revision_and_owned_sources`；合并表单 |
| 8 | 02 / P | 保存 topic 与 plan_content 基线；真实相关性质量另验 |
| 9 | 02、03 / P/T | `test_exact_fifteen_requires_confirmed_eight_plus_seven_sources`；真实语义另验 |
| 10 | 02 / P | 明确 question_count、缺省/冲突表单及 schema 拦截 |
| 11 | 02 / P | 修订持久化、刷新与准备重放 |
| 12 | 02 / P | `test_sources_and_candidate_lifecycle_and_old_confirmation` |
| 13 | 02 / P | `test_confirmed_scope_ready_without_unconfirmed_model_scan` |
| 14 | 02 / P | 8+7 缺口 → 用户确认新修订 → READY |
| 15 | 02 / P | 不足不建卷，展示实际扫描与缺口 |
| 16 | 02 / P | 自有/跨课/共享/删除/未采纳候选隔离 |
| 17 | 02、03、05 / P/T/D | `test_five_types_resume_after_export_restore_and_directory_move` |
| 18 | 02 / P | 要求题型范围；五题型交付组合 |
| 19 | 03 / T | `test_round_freezes_fifteen_without_leaking_answers`；普通首次作答分离 |
| 20 | 03 / T | `test_concurrent_second_start_returns_same_round` |
| 21 | 03、05 / T/D | `test_round_same_across_replay_restart_and_grading`；6/15 导出恢复 |
| 22 | 03、04 / T/G | `test_frozen_paper_survives_source_change_and_invalidation` |
| 23 | 04 / G | `test_repractice_requires_confirmation_and_keeps_answers_until_commit` |
| 24 | 03、05 / T/D | 固定题面跨改写/移动/删除及生产清理后评分 |
| 25 | 03、05 / T/D | source_valid=false；页面来源不可跳转 |
| 26 | 03、05 / T/D | `test_production_cleanup_with_plan_practice[False]`：实际文件与 DB 清理 |
| 27 | 03、05 / T/D | `test_production_cleanup_with_plan_practice[True]`：课程删除隐藏并清理 |
| 28 | 04 / G | 显式重练，普通开始返回原轮 |
| 29 | 04 / G | `test_repractice_prioritizes_unused_and_concurrent_starts_share_round`；语义近重复另验 |
| 30 | 04 / G | 未交卷进度及放弃确认，取消仍保留旧轮 |
| 31 | 04 / G | `test_unsuccessful_repractice_preserves_answerable_round` |
| 32 | 03、04 / T/G | 唯一可答索引、原子切轮及旧答案保存 |
| 33 | 04 / G | `test_old_grading_finishes_after_new_round_without_changing_completion` |
| 34 | 04 / G | 最近启动轮次与历史 URL，晚到评分不切回 |
| 35 | 03、04 / T/G | 15/14/1 与 15/0/15 投影、页面覆盖量 |
| 36 | 03、04、05 / T/G/D | `test_completed_round_with_unscored_items_is_not_grading_complete`；五题型 0.9 |
| 37 | 04 / G | `test_retry_completed_partial_round_only_grades_missing_question` |
| 38 | 02、04 / P/G | 模型替身不可用/超时/无效输出与重试；真实供应商失败另验 |
| 39 | 02、03、04 / P/T/G | API、已装配 Tool、确认卡与未交卷卷面无答案 |
| 40 | 01、03 / C | `test_manual_completion_keeps_first_timestamp_after_objective_round` |
| 41 | 04 / G/C | 完成后重练及晚到评分不改首次完成事实 |
| 42 | 01、04 / R/G/C | 当前 ACTIVE 目标/计划的 DONE 项仍可进入 |
| 43 | 01、03、04 / R/T/G | 旧答题入口及重评提交时重验历史/完结/跳过 |
| 44 | 01、03 / R/C | 阅读/建卷/人工完成零验证性事件，沿既有掌握度链 |
| 45 | 01～04 / R/P/T/G | 已装配查询 Tool 返回同领域状态及站内入口 |
| 46 | 01～04 / R/P/T/G/C | 真实提案 → 确认/直接执行 → Operation 回执；Agent 不代答 |
| 47 | 02 / P | Tool 必填/确认 schema；缺目标/数量返回缺参，读答由用户完成 |
| 48 | 02～04 / P/T/G | `test_commit_rejects_changes_while_model_is_running`、`test_agent_downgrade_blocks_late_matching_result`、真实在途快照恢复 |
| 49 | 01～05 / R/P/T/G | DOM 焦点/返回及原生四主题、窄窗、字体、125%；150% 仍 NOT_RUN |
| 50 | 03、05 / D | 功能前 0051 旧项经生产启动升级、旧 0053 MOCK 升级、普通习题/模拟测试回归、固定内容备份恢复和搬移 |

## Q1～Q23

| Grill | 故事与归属 | 验收 |
| --- | --- | --- |
| Q1 | 1、7；01/02 | R/P 两类入口；其余类型不扩展 |
| Q2 | 40、44；01/03 | C 人工完成及零掌握度增量 |
| Q3 | 3；01 | R 明确启动身份 |
| Q4 | 12、13；02 | P 已确认资料 |
| Q5 | 20、21、28；03/04 | T/G 继续与明确重练 |
| Q6 | 2；01 | R 页签恢复 |
| Q7 | 4、5；01/02 | R/P 首次确认 |
| Q8 | 8、9、15；02/03 | P/T 足量去重；真实语义待验 |
| Q9 | 34；04 | G 最近启动与历史结果 |
| Q10 | 12；02 | P ACTIVE 既有题候选 |
| Q11 | 14～16；02 | P 确认扩源后 8+7 |
| Q12 | 10；02 | P 正整数及数量消歧 |
| Q13 | 7、11；02 | P 首次合并保存与修订 |
| Q14 | 16；01/02 | R 共享只读；P 共享不取题 |
| Q15 | 17、18；02/03/05 | D 五题型真评分组合 |
| Q16 | 35～38；04 | G 缺口、分母和定向重试 |
| Q17 | 22、23；03/04 | T/G 固定旧轮，新修订用于新轮 |
| Q18 | 41～43；01/04 | C 首次完成事实与只读护栏 |
| Q19 | 24～27；03/05 | D 实际清理、来源失效及课程生命周期 |
| Q20 | 31、37、38；02/04 | P/G 失败不丢已确认要求/答案；真实供应商另验 |
| Q21 | 45～48；01～04 | Tool / Operation / Service 生产同链 |
| Q22 | 29；04 | G 未用题优先、复用计数；真实近重复另验 |
| Q23 | 30～33；04 | G 6/15 确认、失败保留、唯一可答与旧轮晚到评分 |
