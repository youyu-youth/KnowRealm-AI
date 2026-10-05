# 数据模型升版提案：补登 0027~0039 迁移（v3.1 → v3.2）

**状态：待用户批准（批准前不动任何权威文档）**
**提出：工单 08 收口（2026-10-06）**；本工单更新不视为对升版的批准。

## 1. 实际差异（以迁移目录与文档登记核对为准）

`docs/KnowRealm-AI-数据模型-v3.1.md` 登记口径停在「**已实施 31 张（截至迁移 0026）**」。其后落库的迁移共 **13 个（0027~0039）**——工单预估缺项为 0030~0039，实际核对 0027（研究会话 V1）/0028/0029（通用 Agent 一阶段）同样晚于 v3.1 定稿日（2026-09-19），一并缺登。

### 1.1 新表 7 张（已实施 31 → 38）

| 表 | 迁移 | 波次 | 要点 |
| --- | --- | --- | --- |
| `agent_runs` | 0030 | 通用 Agent 二阶段 01 | auth_mode / instruction_text / plan_json+plan_version / status 七态（RUNNING/WAITING_USER/WAITING_JOB/COMPLETED/PARTIAL_COMPLETED/FAILED/CANCELLED）/ waiting_reason / cancel_requested；0038 补 `waiting_job_id` |
| `agent_operations` | 0030 | 同上 | run_id 可空 FK CASCADE / proposal_id / level / payload_json / snapshot_json / status 六态（不持久 RUNNING）/ attempts / result_json / undo_of + undone_by 自引用 SET NULL |
| `agent_activity` | 0030 | 同上 | AUTH_MODE_SWITCH 模式切换审计（本期无写入者，空表就位） |
| `learning_goals` | 0034 | 通用 Agent 三阶段 01 | **对 v3.1 P6 原设计的显式修正：新增 course_id 必填 FK（原设计为全局 learner 视角无归属）**；goal_type 五枚举 / scope_source 三值；单空间单 ACTIVE 部分唯一索引 |
| `learning_plans` | 0035 | 通用 Agent 三阶段 02 | (goal_id, plan_version) 唯一 + 同目标单 ACTIVE 部分唯一索引；effective_from/effective_to 版本链 |
| `learning_plan_items` | 0035 | 同上 | 四动作类型（STUDY_RECORD/PRACTICE_QUIZ/REVIEW_CONCEPT/CUSTOM）/ phase_title / priority / scheduled_date / user_locked / reason_json / record_id+concept_id 物理删除 SET NULL；0036 补 `completed_at`（完成时间戳，学习时长统计口径） |
| `course_shared_refs` | 0037 | 通用 Agent 三阶段 05 | course ↔ library_item 多对多；UNIQUE(course_id, library_item_id)（autoindex_2）+ 双 FK ON DELETE CASCADE；失效查询期派生不设列 |

### 1.2 存量表变更（零新表）

| 迁移 | 表 | 变更 |
| --- | --- | --- |
| 0027 | chat_sessions | 整表重建（legacy_alter_table）放开 mode CHECK 增 'RESEARCH'（研究会话 V1） |
| 0028 | agent_proposals | 整表重建：proposal_type CHECK + 'COURSE_CREATE'，新增 result_json 可空列（操作回执） |
| 0029 | agent_proposals | proposal_type CHECK + 'TEXT_RECORD_ADD' |
| 0030 | agent_proposals | proposal_type CHECK 一次改造为「存量五类型白名单 + OP_ 前缀 GLOB 通配」（后续新动作零迁移） |
| 0031 | chat_messages | ADD COLUMN executed_operations_json（直执行回执的消息流持久锚点） |
| 0032 | agent_proposals | ADD COLUMN snapshot_json（执行前快照） |
| 0033 | processing_jobs | 整表重建：job_type CHECK + 'AGENT_RUN' + one_active_agent_run 表达式唯一索引（json_extract run_id） |
| 0039 | processing_jobs | 整表重建：job_type CHECK + 'PLAN_DRAFT' + one_active_plan_draft 表达式唯一索引（json_extract goal_id） |

### 1.3 设计口径

- 正式表设计口径 **44 → 47 张**（agent_runs / agent_operations / agent_activity 三表为通用 Agent 二阶段新增设计，不在 v3.1 的 44 张内）；**已实施 31 → 38 张**（两张 FTS 衍生索引表不计，纪律同 ADR-0016）。

## 2. deferred 表登记（本期不实施）

以下三表维持设计稿状态，启用条件：

- **learning_agent_actions / learning_agent_feedback**（P6 Autopilot）：触发 = 自适应学习代理波次（扩展文档 §39/§40 后续）；前置 = 掌握度证据与计划执行数据充分积累。
- **teach_back_attempts**（P5 Teach-back）：触发 = Tutor 场景包（B3）立项。

## 3. 拟修改的权威文档与交叉引用（批准后执行）

| 文档 | 动作 |
| --- | --- |
| `docs/KnowRealm-AI-数据模型-v3.1.md` | **升版 v3.2 并重命名**（v3.1 → v3.2）；头部新增变更记录行（上表全部内容 + deferred 登记）；逐表节标注已实施与列差异 |
| `docs/KnowRealm-AI-功能需求基线-v2.8.md` | 头部数据模型版本交叉引用行跟进 v3.2 |
| `docs/技术栈设计与审查-v4.6.md` | 数据模型版本交叉引用跟进（如有）；§7.2 模块清单如无漂移不动 |
| `docs/knowRealm-AI-功能升级与创新扩展设计.md` | 头部交叉引用跟进；§44 如有版本引用同步 |
| `CONTEXT.md` | 仅当引用数据模型版本号时跟进（术语词条 01~07 波次已落，预计零改动） |
| `PROJECT_PROGRESS.md` | 提案批准标记从「待提案」翻「已批准 + 已执行」 |

历史「变更记录」行保持史实不改动；`backend/AGENTS.md` 的迁移清单如在执行时点有新迁移再一并核对。
