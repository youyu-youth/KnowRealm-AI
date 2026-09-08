# 03 — 后端错误码化全量（γ′）

**What to build:** 后端全部错误响应附加稳定错误码，为前端按码翻译（04）提供契约前提——形如 `{"detail": "请先配置 LLM Provider", "code": "LLM_PROVIDER_NOT_CONFIGURED"}`，带动态值的附 `params` 对象。detail 中文原文保留不动，后端既有 pytest 断言零改动（γ′ 选型主因）。参数校验（422）与未捕获异常（500）落通用码，对话 SSE 错误的 code 值集补全；新增防线测试保证未来错误不得漏配。

**Blocked by:** None — can start immediately

> 并行备注：本票与 01 可安全并行（纯后端 + 契约，与 02 零接触）；api-types 生成物与 01 若撞，后合并者重新生成即可。

**Status:** done

- [x] 引入带错误码的 HTTPException 子类 + 统一异常处理器，序列化 `{detail, code, params?}` 形状
- [x] 错误码命名规范定稿：`MODULE_RESOURCE_PROBLEM` 大写下划线风格；产出全量错误码清单（随票落文档）
- [x] 全模块约 200+ 处错误 raise 机械替换为带码形式（按模块分批提交，每批测试全绿）
- [x] 422 → `REQUEST_VALIDATION_FAILED` 通用码；500 → `INTERNAL_ERROR` + `params.request_id`
- [x] 对话 SSE 错误事件 code 值集补全（事件形状不变，已有 code 字段）
- [x] 共享错误响应 schema 加可选 `code` / `params` 字段，openapi 导出后 api-types 重新生成
- [x] 防线扫描测试：生产代码禁止直接 raise 裸 HTTPException（必须走带码子类）
- [x] 既有 pytest 断言零改动全绿；新增代表性抽查（409 / 422 / 500 响应含 code）——过 spec 缝隙 5
- [x] ADR-0017 落盘：γ′ 附加字段 vs 纯结构化替换的选型权衡（难逆 / 惊讶 / 真实权衡三条件）
- [x] 门禁全绿（pytest / ruff / pyright）

## 实现备注（2026-09-08）

- **提交**：66ea634（基建）→ 1837caf / 2f964d8 / 97bbdce / 5d88431 / 2921260 / 2aa3fbb（六模块批次）→ 86ffea5（防线+抽查）/ 5247e50（文档）。
- **子类与处理器**：`app/shared/errors.py` 的 `CodedHTTPException(status_code, code, detail, params?)`；`main.py` 在 `StarletteHTTPException` 基类上注册统一处理器（MRO 覆盖子类），框架级 404/405 回退 `HTTP_ERROR`；422/500 处理器补通用码，500 附 `params.request_id`。
- **码值来源**：64 处 detail 已带 `CODE：中文` 前缀直接提取；192 处按 `资源_问题` 规范新配；跨模块同一条件复用同一码（如 `RECORD_NOT_FOUND` x15）。全量 105 个唯一业务码 + 4 通用码，见 `docs/后端错误码清单.md`。
- **SSE**：error 事件（`CHAT_CONTEXT_TOO_LARGE` / `CHAT_STREAM_FAILED` / `EMPTY_REPLY`）后端本已带 code，本次仅将值集收进清单文档，事件形状零改动。
- **抽查覆盖**：403（无令牌）/ 404（路由回退）/ 409（未配供应商发消息）/ 422（非法 body）/ 500（monkeypatch `RecordService.list_inbox` 抛错断言 `params.request_id`），`tests/test_error_codes.py`。
- **例外范围**：`QuizConflictResponse` / `TodoConflictResponse`（409 结构化冲突体，`blocked_reason` 分支）与 `ProcessingJobErrorCode`（job 轮询域枚举）不入码表；ASR 凭据测试的供应商错误映射统一落 `ASR_TEST_FAILED`。
- **机械替换方式**：AST 一次性脚本按 `(文件,行号)→码` 映射 + 前缀自动提取改写（仅 `quiz/test_service.py` 两个变量 detail helper 手改：`_ensure_course_active` 写死 `COURSE_ARCHIVED`、`_transition_to_grading` 加 `stale_code` 透传），脚本用后已删。替换后生产代码裸 `raise HTTPException` 为 0（防线 AST 扫描持续拦截）。
- **api-types**：`ErrorResponse` 加 `code`（必填）/ `params`（可选）后已重新 generate；因工作区含工单 01 未提交的偏好 `language` 契约，生成物**未随本票提交**，随 01 或后合并者入库（工单并行备注预期内）。
- **门禁**：pyright 0 错、ruff check 全绿（format --check 仅工单 01 在途文件不齐，非本票）；pytest 391 过 / 1 失败——`test_quizzes.py::test_quiz_last_count_preference_round_trip` 断言偏好全字段但缺 01 新增的 `language`，属 01 在途改动的既有失败，与本票无关（本票未改任何既有断言）。
- **code-review 备注**：schema 的 `code` 实现为**必填**（工单原文"可选 code/params"中的"可选"仅 params 成立）——与 ADR-0017「全部错误响应必有 code」一致，属有意偏差；已知改进点：`TRANSCRIPT_NOT_READY` 同码挂 404/409 两个状态（沿承旧码，按码翻译不受影响，后续宜统一）、防线测试对 `stale_code` 变量透传的码名不做字面校验（仅 2 处、调用点为字面量）。`.claude/rules/fastapi.md` §6 错误响应形状描述已落后于 ADR-0017，规则文件禁改，待所有者升版。
