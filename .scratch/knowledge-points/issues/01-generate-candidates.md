# 01 — 知识点生成候选（页签落地与生成闭环）

**What to build:** 总结已确认（Record=COMPLETED）的学习记录在「知识点」页签一键生成候选知识点：后端经注入的生成模型缝做单次结构化调用（无 LangGraph），从课程上下文 + 已确认 Summary + 转写中提取候选，成功即整批落库为 DRAFT 行并在页签可见；超长转写仅基于 Summary 提取且界面明示；失败可手动重试；前置条件不满足或已有在途候选时给出诚实的空态、指引与 409；未接入能力的占位页签一次对齐 PRD 命名。

**Blocked by:** None — can start immediately

**Status:** completed

- [x] 迁移新建 knowledge_points 表（generation_status 单列状态 DRAFT/ACTIVE/SUPERSEDED、软删、importance 与 tags 字段约束）并新增 KNOWLEDGE_EXTRACTION 任务类型；每 Record 至多一个 PENDING/RUNNING 知识点任务的部分唯一索引生效
- [x] 生成前置校验：存在当前 CONFIRMED Summary、课程 ACTIVE、Provider 已配置、外发同意有效——任一缺失返回明确 action_required/409 且不建 Job；已存在在途 DRAFT 批次时再生成 409
- [x] 应用工厂提供知识点生成模型注入缝（镜像 Summary 模型缝）；worker 单次结构化生成，prompt 含课程 learning_context/education_stage/depth + 确认 Summary + 转写全文；转写超过 3 万 Unicode code point 时仅送 Summary 且响应标识输入模式，UI 明示「基于总结提取」
- [x] 严格 Pydantic 校验（1~20 条、名称/详情/标签边界、importance 为 1~5 整数）：违规 Job FAILED（LLM_OUTPUT_INVALID），不自动修正、不自动付费重试；手动重试复用失败 Job；单次请求 90 秒超时
- [x] 成功即在单事务落整批 DRAFT 行（batch_id 即生成 Job id）；批次溯源（model/prompt_version/候选条数/输入模式）写入 Job result_json；调用埋点落 llm_call_logs；prompt 与输出全文不进日志
- [x] 读端点返回已保存行 + 在途 DRAFT 批次行 + action_required 全状态机（GENERATE/CONFIRM/RETRY/NONE、active_job_id、blocked_reason）
- [x] 「知识点」页签落地：未确认总结时的空态引导指向总结页签、生成按钮、任务轮询进行中态、失败重试、候选列表展示；占位页签一次对齐 PRD 命名（知识点/习题/复习/Todo/Ask AI，未接入者禁用并说明）
- [x] 后端 ASGI + 真实迁移库 + 假生成模型的全栈测试与桌面 MSW 测试通过（含 409 矩阵、Schema 违规 FAILED、超长转写输入模式）

## Verification

- 后端：`119 passed`；新增知识点闭环用例 `6 passed`；Ruff 通过，变更文件 Pyright `0 errors`。全项目 Pyright 仍有既有 `app/core/logging.py:46` 一处错误。
- 桌面端：`54 passed`，TypeScript/Vite 生产构建与 ESLint 通过，UI 反模式检测无发现；OpenAPI 类型已同步。
- 真实本地 HTTP + SQLite 读取返回 `CONFIRM / FULL_TRANSCRIPT / 2 条候选`。真实外部 LLM 未调用；Chrome 远程调试权限未放行，因此本轮未取得浏览器渲染截图。
