# 数据模型增补提案：回答过程事实（迁移 0041）

状态：待用户批准；本次实施不修改或重命名权威数据模型文档。

在既有 0027～0040 补登提案基础上，增补 `chat_response_processes`。每次生成一行，重试新建过程，不覆盖失败或中断尝试。仅保存展示事实，不承担 ChatTurn 调度、后台执行、业务授权或操作恢复。

| 字段 | 类型与约束 | 用途 |
| --- | --- | --- |
| id | TEXT PRIMARY KEY | 过程 UUID |
| session_id | TEXT NOT NULL，chat_sessions FK CASCADE | 所属会话 |
| user_message_id | TEXT NOT NULL，chat_messages FK CASCADE | 发起消息；多次尝试可共用 |
| assistant_message_id | TEXT NULL，chat_messages FK SET NULL | 成功回答关联 |
| status | TEXT NOT NULL，CHECK 四态 | RUNNING / COMPLETED / FAILED / INTERRUPTED |
| started_at / updated_at | UTC ISO8601 TEXT NOT NULL | 开始与最后一次保存时间 |
| ended_at | UTC ISO8601 TEXT NULL | 终结时间 |
| elapsed_ms | INTEGER NOT NULL DEFAULT 0，CHECK >= 0 | 用时 |
| entries_json | TEXT NOT NULL DEFAULT '[]' | 有序公开说明及工具调用事实 |

索引：`(session_id, started_at, id)`；无软删字段，沿会话/消息生命周期清理。过程条目分为公开说明（模型消息 ID、文本）与工具（tool_call_id、工具名、简短对象、状态、检索命中数）。工具状态含 RUNNING / SUCCEEDED / FAILED / INTERRUPTED / AWAITING_CONFIRMATION，提案创建不代表业务已执行。

创建、说明确认、调用开始/结束与终结时短事务保存，不逐 token 写库。正常成功时回答与过程终态同事务提交；过程写入异常记录错误并提示保存不完整，不重放业务操作。启动将遗留 RUNNING 收为 INTERRUPTED，结束时间取 updated_at，不计算停机时长。

审批后：将本表纳入数据模型的已实施表、字段、索引与状态说明，并按既有升版提案同步交叉引用；计数在升版时重新核对实际迁移链。
