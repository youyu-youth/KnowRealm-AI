# 后端重组为 Feature-first 模块化单体（modules/）

---
Status: accepted（2026-09-01，feat/arch-opt 一步到位重构定稿）
---

随着功能增长，layer-first（api/services/schemas/models 分层）出现结构性问题：同名业务域散落四层（习题域要看 7 个文件）；`models/document.py` 巨石化（单文件 11 张表，违背 §7.2"42 表按域分文件"的自定纪律）；分层没有阻止 services 内部横向依赖成网（capture→summary、三派生域→summary_derivation），只是让它不可见。未来 Agent/RAG/Memory/Tools 能力落地需要"一个能力一个归属地"。

**决定**：

- 后端采用 **Feature-first / Modular Monolith**：`app/modules/<域>/` 拥有该域全部代码（路由/服务/worker/models/schemas），`core/`（进程机制）、`db/`（engine/迁移/Base）、`shared/`（跨域无业务契约）保持横向层；**不做微服务**。
- 模块划分（按真实代码行为识别，非文件名）：平台四件套 `llm`（模型接入+llm_call_logs）/`jobs`（processing_jobs 队列+JobRunner）/`settings`（providers+consents+preferences）/`data`（数据目录导出导入备份）；业务域 `course`、`record`（中心聚合+LearningEvent）、`capture`（五入口）、`transcript`（ASR+文档解析+定稿，tencent 客户端在 `integrations/`）、`summary`（含 LangGraph 图与派生资格脊柱）、`knowledge_point`、`quiz`（含模拟测试与判分）、`todo`、`chat`、`profile`、`today`（跨域只读）。
- **依赖规则**：
  1. `modules → core/db/shared` 单向；`main.py` 为唯一组合根，可引用一切；
  2. 跨模块引用（**无论行为还是数据契约**）一律直达具体文件（`from app.modules.quiz.service import QuizService`），**包 `__init__.py` 只写 docstring、禁止任何再导出**；
  3. 模块间引用方向必须无环，法定方向 = 学习资产流水线：`capture → transcript → summary → {knowledge_point, quiz, todo}`，`chat`/`today` 在下游，`course`/`record` 为上游聚合，平台四件套可被任何模块引用且不引用业务模块；
  4. 路由薄层、事务边界等 rules/fastapi.md 既有纪律在模块内继续成立。
- 一次性迁移（A′：单工作窗内 6 个全绿 commit），HTTP 契约零变化（openapi 前后零 diff 验收）。

**实施中发现并定稿的两处规则修订**（相对最初 grilling 方案）：

1. **"契约经对方 `__init__` 公开面"被否决**：Python 导入子模块必先初始化父包，热切再导出的 `__init__` 使 course→jobs→record→course 在包初始化层成环（运行时 ImportError，与引用方向无关）。因此改为全部直达具体文件 + 空 `__init__`，包初始化环从此物理不可能，静态工具（pyright/ruff）行为与运行时一致。
2. **`RecordInvalidationNotifier` 落 `shared/events.py` 而非 record 模块**：它是零依赖的进程级 SSE 失效事件总线，被 jobs 平台与全部 worker 引用；放业务包会制造平台→业务的包初始化触发。

**随迁的两处行为等价调整**（jobs↔record 破环）：

- `ProcessingJobService.get/list_for_record` 中的记录可见性校验（原调用 `RecordService.get`）上移到路由层组合（api/processing_jobs 与 record jobs 端点先 `RecordService.get` 校验再委托），状态码与响应体逐字不变；jobs 平台从此不引用 record 行为。
- `QUIZ_COUNT_CHOICES` 从 quiz schema 移至 settings 模块（实际唯一使用者是偏好校验）；`LlmProviderTestOut`/`TencentAsrTestOut` 从 summary schema 移至 settings（供应商连接测试产物）。

## Considered Options

| 方案 | 结论 |
|------|------|
| **A. Feature-first modules/（一步到位）** | **采纳**——域内聚、为 Agent 能力提供归属地；单人仓库+全量测试+pyright strict 使单窗重构风险可控（实际 6 commit 全绿完成） |
| B. Feature-first 渐进绞杀（多周日批次） | 否决——总工作量相同，日历时间更长；两结构长期并存的心智成本更高 |
| C. 保持 layer-first，仅层内按域聚拢 | 否决——模块边界仍不存在，Agent/RAG 落地时仍缺归属地，等于推迟到更贵时重做 |
| D. 集中契约层（models/schemas 留横向层，仅行为模块化） | 否决——模块不拥有自己的表，自治性减半；空 `__init__` 方案已消除分散契约的环风险 |

## Consequences

- 迁移映射与模块模板见技术栈 v4.5 §7.2；`models/base.py`→`db/base.py`，`api/deps.py`→`shared/deps.py`，`ErrorResponse`→`shared/schemas.py`。
- 未来能力演进落位：Agent Runtime/ReAct/Plan-Execute/Reflection/Multi-Agent → 出现第二个推理循环使用者时建 `modules/agent/`（策略为 runtime 子包，不设顶级模块）；RAG → `knowledge_point` 届时扩展为 knowledge（retrieval 落位）；MCP → 各域 `integrations/` 子包起步，跨域共享再升 `modules/integrations/`；Memory → LangGraph checkpointer 既有形态，跨 agent 记忆出现第二个使用者时独立。**当前不预建任何空模块**。
- PyInstaller 打包尚无 spec 文件；未来首次打包须以实包冒烟验证模块树自动发现（记为打包工单验收项）。
- 依赖方向目前靠文档约定 + code review 把关；若后续出现违环，再评估引入 import-linter 门禁。
