可以。下面是结合原 F4 方案、当前 B2 实现和未来 Agent 路线重新定制后的开发计划。

核心原则是：

> F4 一次发布形成完整用户闭环；内部按阶段开发。
> Course Brain 做可信的课程知识底座，Agent 通过稳定接口消费它，但 F4 本身不做成复杂 Agent 系统。

# F4 Course Brain V1 开发计划

## 一、前置假设

本计划按以下口径执行：

1. F4 作为一个 Epic 开发，全部核心票完成后一次发布。
2. Course Brain 以 Course 级 Concept 为中心，不是知识点聚合页。
3. 首版真实来源包括：
   - 已确认或手动创建的 Knowledge Point。
   - Transcript Segment。
   - Document Segment。
   - 对话转知识点携带的 Chat Message 来源。
4. AI Summary 只辅助导航，不作为事实来源或 Learning Evidence。
5. 构建和更新由用户显式触发，避免后台自动产生 LLM 费用。
6. 不新增 LangGraph 图、不引入 SubAgents、MCP 或通用 Skills 运行时。
7. 先使用 Concept 扩展加现有 FTS；sqlite-vec 由真实检索评测决定是否纳入本 Epic。
8. Knowledge GPS、Mastery、课件 Diff 不属于本次 F4 范围。

这些假设应在编码前完成设计评审，评审通过后再拆入 `.scratch/course-brain-v1/`。

------

## 二、产品目标

用户能够完成以下完整流程：

```
进入课程
  → 构建 Course Brain
  → 系统从多类课程内容抽取 Concept 候选
  → 用户确认、重命名、合并、忽略
  → 获得真实课程概念图谱
  → 查看每个 Concept 的原始来源
  → 用课程对话查询 Concept
  → 回答可定位到记录、时间或页码
  → 课程内容变化后提示重新构建
```

最终出口问题：

> “老师这学期关于 MVCC 一共讲过几次？”

系统必须按真实记录和来源计算，并列出每次出现的课程记录、原文、时间或页码，不能由 LLM 自行猜测次数。

------

## 三、领域边界

### 核心对象

| 对象              | 级别            | 含义                                    |
| ----------------- | --------------- | --------------------------------------- |
| Knowledge Point   | Record          | 某一条记录提炼出的学习资产              |
| Concept           | Course          | 跨多条记录归一后的课程规范概念          |
| Concept Relation  | Course          | Concept 之间的课程知识关系              |
| Record Concept    | Record ↔ Course | Concept 在某条记录中的出现情况          |
| Source Anchor     | 原始来源        | Transcript、Document、Chat 的可回跳位置 |
| Learning Evidence | 学习行为        | 用户是否理解、答对、回忆成功的证据      |

必须坚持：

```
Knowledge Point ≠ Concept
Concept Source ≠ Learning Evidence
AI 推断 ≠ 用户掌握
Course Brain Memory ≠ LangGraph Checkpoint
```

### 来源策略

| 来源                   | F4 V1 | 用途                           |
| ---------------------- | ----- | ------------------------------ |
| 已确认 Knowledge Point | 是    | 高质量 Concept 种子            |
| Transcript Segment     | 是    | 补充概念并提供课堂原文、时间   |
| Document Segment       | 是    | 补充概念并提供页码、章节       |
| 对话转知识点           | 是    | 以 KP 进入，并保留 Chat Anchor |
| AI Summary             | 辅助  | 只用于导航、压缩上下文         |
| User Note / Marker     | 暂缓  | 等真实写入者完成后接入         |
| Course Material        | 暂缓  | 当前真实业务链完成后接入       |
| Web/MCP 内容           | 暂缓  | 必须先保存到本地课程资料       |

构建时默认使用全部有效来源，不提供复杂的来源配置界面；前端来源筛选只影响浏览，不影响构建，避免用户漏选资料。

------

## 四、Agent 架构边界

### 4.1 Course Brain 深模块

新增：

```
backend/app/modules/course_brain/
├── models.py
├── schemas.py
├── service.py
├── worker.py
└── routes.py
```

对 UI、B2 Tool 和未来 Agent 暴露一个小接口：

```
class CourseBrainService:
    async def get_snapshot(course_id): ...
    async def request_build(course_id): ...
    async def search(course_id, query, limit=8): ...
    async def apply_review(course_id, decisions): ...
    async def get_concept_sources(concept_id): ...
```

模块内部隐藏：

- 多来源收集。
- 分块。
- Concept 归一化。
- 候选消歧。
- Source Anchor 建立。
- FTS 检索。
- 关系扩展。
- 状态过滤。
- 上下文预算控制。

不创建只有一个实现的 Repository Interface、Factory 或 Adapter Registry。

### 4.2 Agent 读取权限

当前 Agent 只允许：

- 搜索已确认 Concept。
- 获取 Concept 的来源。
- 查询相关 Concept。
- 找出 Concept 出现在哪些 Record。
- 基于原文生成回答。

Agent 搜索结果使用结构化合同：

```
CourseBrainSearchResult
├── matched_concepts
│   ├── concept_id
│   ├── canonical_name
│   └── matched_terms
├── occurrences
│   ├── record_id
│   ├── record_title
│   ├── source_anchor_id
│   ├── source_type
│   ├── quote
│   └── position
└── related_concepts
```

Agent 只能看到 `CONFIRMED` Concept；候选数据只进入人工审核界面。

### 4.3 Agent 写入权限

F4 V1 不提供 Agent 写工具。

未来可以新增：

```
propose_concept
propose_concept_merge
propose_concept_relation
```

但执行链必须是：

```
Agent 建议
  → CANDIDATE
  → 用户审核
  → 业务 Service
  → knowrealm.db
```

Agent、Tool、Skill、MCP 和 SubAgent 永远不能直接写业务表。

### 4.4 Memory 分工

```
knowrealm.db
├── Concept
├── Relation
├── Record Concept
├── Source Anchor
└── Learning Evidence

langgraph.db
├── 会话 Checkpoint
├── Agent 执行状态
└── interrupt / resume 状态
```

不使用 DeepAgents Filesystem Memory 或 StoreBackend 保存课程事实。

------

## 五、数据与后台任务

### 5.1 数据库迁移

下一迁移预计为 `0023_course_brain.sql`，新增：

- `concepts`
- `concept_relations`
- `record_concepts`

扩展：

```
source_anchor_links.resource_type += CONCEPT
```

不新增：

- `concept_sources`
- `concept_aliases`
- `course_brain_runs`

来源关系直接复用现有 Source Anchor；构建状态和来源指纹复用 `processing_jobs.input_json/result_json`。

### 5.2 Concept 状态

```
CANDIDATE
CONFIRMED
ARCHIVED
```

规则：

- 新抽取 Concept 默认 `CANDIDATE`。
- 与正式 Concept 规范名完全一致时自动关联，不重复创建正式节点。
- 语义相似只产生合并建议。
- 手动创建的 Concept 可直接成为 `CONFIRMED`。
- 重新构建不能修改用户确认过的名称和描述。
- 失去全部有效来源的 Concept 标记待归档，不直接删除。

### 5.3 Relation 状态

```
CANDIDATE
CONFIRMED
DISMISSED
```

所有 AI 推断关系必须先进入 `CANDIDATE`。

### 5.4 构建任务

新增：

```
ProcessingJobType.COURSE_BRAIN_BUILD
```

构建流程：

```
校验 Course
  → 收集有效 Record
  → 收集 KP / Transcript Segment / Document Segment
  → 按 Record 分块
  → LLM 结构化抽取
  → 确定性 normalized_name
  → 匹配已有正式 Concept
  → 写入候选和 Record 映射
  → 建立 Source Anchor
  → 生成关系候选
  → 原子发布构建结果
```

复用现有：

- `JobRunner`
- Provider 配置与用户同意
- LLM 调用日志
- 结构化输出校验
- 失败重试
- 崩溃恢复
- `INVALID_STRUCTURED_OUTPUT`
- `PROVIDER_REQUEST_FAILED`

不使用 LangGraph 执行该 Pipeline。

------

## 六、B2 与 Tool 接入

当前不新增 `search_course_brain` Tool，先增强现有 `search_library`：

```
search_library(query)
  → CourseBrainService.search()
  → 匹配 Confirmed Concept
  → 扩展检索词和目标 Record
  → SegmentSearchService 检索原文
  → 返回带 Source Anchor 的结果
```

例如：

```
用户问题：“可见性是怎么实现的？”
Concept 匹配：“MVCC”
扩展词：“MVCC、ReadView、快照读、事务可见性”
原文检索：Transcript / Document Segment
最终引用：仍然是原始课程内容
```

这样：

- B2 保持一个稳定 Tool。
- Agent 不需要理解数据库结构。
- Concept 只负责语义理解和检索导航。
- 引用仍然来自原始事实来源。
- 后续 Tutor 出现时，可以直接把同一个查询接口包装成独立 Tool。

需要同步升级 Chat Prompt 版本，并明确：

- 优先使用已确认 Concept。
- Concept 描述不能直接冒充原文引用。
- 统计“讲过几次”必须按去重后的 Record 或 Anchor 计算。
- 不得通过模型主观估算出现次数。

------

## 七、前端闭环

复用现有 `CourseKnowledgeGraph` 的 ECharts、暗色主题、全屏、拖拽和缩放能力，替换 `mockCourseKnowledgePoints()`。

### 页面状态

```
EMPTY       尚未构建
BUILDING    正在构建
REVIEW      存在待审核候选
READY       已可使用
STALE       课程内容发生变化
FAILED      构建失败，可重试
```

### 页面组成

1. 构建状态栏。
2. Concept 图谱和列表双视图。
3. 候选审核抽屉。
4. Relation 审核区。
5. Concept 详情面板。
6. 来源列表。
7. 来源类型筛选。
8. 重新构建入口。

### 审核操作

- 确认。
- 重命名后确认。
- 合并到已有 Concept。
- 忽略候选。
- 确认或忽略 Relation。
- 手动创建 Concept。

### 来源跳转

- Transcript：打开 Record 并定位时间。
- Document：打开对应记录和页码。
- Knowledge Point：打开记录知识点。
- Chat：打开原会话和消息。

首版不做图上拖拽创建关系；编辑操作放在列表或详情面板中。

------

## 八、实施阶段和工单顺序

## 阶段 0：合同与评测门禁

### CB-00 设计合同

内容：

- 固化 Concept、Candidate、Relation、Source、Evidence 语义。
- 固化 Agent 读写边界。
- 固化 API 和结构化搜索结果。
- 确认 Source Anchor 复用方案。
- 明确 sqlite-vec 决策标准。

验收：

- 产品、数据、Agent、HITL 边界没有冲突。
- 形成可评审规格。
- 未评审通过前不写业务代码。

### CB-01 检索基线评测

内容：

- 从真实课程整理课程级查询样本。
- 覆盖同义词、简称、跨记录统计和原文定位。
- 评估 FTS 加 Concept 扩展的召回情况。

出口：

- 通过：sqlite-vec 延后。
- 主要失败来自词汇不重合：增加 CB-VEC 工单，并在 F4 发布前完成。

------

## 阶段 1：领域数据地基

### CB-02 数据模型与迁移

实现三张 Concept 表和 `CONCEPT` Source Anchor Link。

验收：

- 外键、唯一约束、状态枚举、软删除语义正确。
- 迁移和回滚式升级测试通过。
- ORM 与数据库一致。

### CB-03 Course Brain 查询模块

实现：

- `get_snapshot`
- `search`
- `get_concept_sources`

验收：

- 只返回当前 Course 数据。
- Agent 查询只能看到 `CONFIRMED`。
- 删除、归档、跨课程数据不会泄漏。
- 返回结果有长度和数量上限。

阶段目标：

> 不依赖 LLM，已经可以手动创建 Concept，并被统一查询模块读取。

------

## 阶段 2：构建与审核闭环

### CB-04 多来源收集和构建 Worker

实现：

- `COURSE_BRAIN_BUILD`
- 多来源收集
- 分块抽取
- 结构化输出
- 来源指纹
- 错误恢复

验收：

- KP、Transcript、Document 可以共同生成候选。
- 重复执行不会重复产生正式 Concept。
- 构建失败不破坏上一次正式图谱。
- 不自动产生 Learning Evidence。

### CB-05 Concept Resolution

实现：

- 确定性名称归一化。
- 完全一致自动挂接。
- 相似项生成合并建议。
- 用户确认、重命名、合并、忽略。
- 正式 Concept 保护。

验收：

- 重新构建不能覆盖用户结果。
- 合并后 Record 和 Anchor 映射完整。
- 跨 Course 不能合并。

### CB-06 Relation 和 Concept Evolution

实现：

- 关系候选。
- 人工确认或忽略。
- 来源变化后的过期检测。
- 内容删除、课程移动后的失效清理。

验收：

- 关系不会未经确认进入正式图谱。
- 旧来源不再参与检索。
- 正式 Concept 不因一次抽取缺失被直接删除。

阶段目标：

> 存量课程可以构建、审核、更新并长期维护 Course Brain。

------

## 阶段 3：Agent-ready 接入

### CB-07 B2 Course Brain 检索增强

实现：

- `search_library` 调用 `CourseBrainService.search`。
- Concept 匹配和检索词扩展。
- 原始 Segment 引用。
- 次数和 Record 去重。
- Chat Prompt 版本升级。

验收：

- RECORD 会话不受影响。
- COURSE 会话可使用 Concept 增强。
- ALL 会话不会错误混入其他课程 Concept。
- 候选 Concept 不进入 Agent 上下文。
- 引用仍能通过现有校验器。

### CB-08 Agent 可观测性

记录：

- `prompt_version`
- `model`
- 构建任务 ID
- 来源指纹
- Token 用量
- 抽取置信度
- 用户审核结果
- 查询命中的 Concept ID

验收：

- 可以区分抽取错误、检索错误和回答错误。
- 日志不记录完整敏感正文。
- 不新增第二套 SSE 或任务系统。

阶段目标：

> B2 已经成为 Course Brain 的第一个真实 Agent 消费者，后续 Agent 可以复用同一个查询接口。

------

## 阶段 4：前端产品闭环

### CB-09 前端状态和接口接入

实现：

- OpenAPI 类型更新。
- Query/Mutation Hooks。
- 构建、失败、过期、审核状态。
- 中英文文案同步。

### CB-10 Course Brain 真实页面

实现：

- 替换 Mock。
- 图谱和列表。
- Concept 详情。
- 来源查看和跳转。
- 空态、失败态、重试。

### CB-11 审核工作台

实现：

- Concept 审核。
- 合并选择。
- Relation 审核。
- 手动创建。
- 批量确认和忽略。

验收：

- 用户不需要进入聊天就能完成 Course Brain 管理。
- 所有写操作有明确反馈。
- 固定工作区和局部滚动符合现有桌面设计规范。
- 亮色、暗色、窄窗和减少动效模式通过。

阶段目标：

> 当前 Mock 课程图谱完全退出，形成用户可见、可维护、可追溯的完整 F4。

------

## 阶段 5：发布验收

### CB-12 全链路验收与文档收尾

必须覆盖：

- 多来源课程首次构建。
- Candidate 确认、合并、忽略。
- 正式 Concept 不被重建覆盖。
- Record 删除和课程移动。
- Source Anchor 时间、页码、对话跳转。
- 无 LLM Key 降级。
- LLM 构建失败恢复。
- B2 跨记录问答。
- “讲过几次 X”按真实来源回答。
- Learning Evidence 不被污染。
- Course Brain 页面无 Mock。

文档同步：

- 功能需求基线。
- 数据模型。
- 扩展设计。
- `GLOSSARY.md`。
- 必要时新增 ADR。
- `PROJECT_PROGRESS.md`，保持 200 行以内。
- OpenAPI 类型。

------

## 九、验证命令

后端：

```
cd backend
uv run pytest --basetemp=.pytest-tmp
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run python -m scripts.export_openapi ../packages/api-types/openapi.json --check
```

测试后删除 `.pytest-tmp`。

前端：

```
cd apps/desktop
pnpm test -- --maxWorkers=4
pnpm lint
pnpm build
```

契约更新：

```
pnpm --filter @knowrealm/api-types generate
```

真实桌面验收：

```
pnpm --filter @knowrealm/desktop tauri dev
```

自动化测试只能证明逻辑和构建；来源跳转、图谱交互、窄窗和 WebView2 表现需要真实 Tauri 验收。

------

## 十、最终发布门禁

只有以下条件全部满足，才能称为 F4 Course Brain V1 完成：

- 多来源数据真正进入 Concept 构建。
- 用户完成候选审核闭环。
- Concept 和 Relation 可长期维护。
- 每个 AI 使用的 Concept 可回到真实来源。
- Course Brain 页面完全使用真实数据。
- B2 已消费 Course Brain，而不是另建重复 Tool。
- Agent 不能直接写正式 Concept。
- Agent 不能把推断写成 Evidence。
- `knowrealm.db` 与 `langgraph.db` 职责没有混淆。
- 重新构建不会破坏人工确认结果。
- 无 LLM Key 时已有数据仍可浏览和手动维护。
- sqlite-vec 是否进入本次版本已有明确评测结论和文档口径。

这份计划对原方案最重要的调整，是把 `CourseBrainService` 的结构化查询接口、Agent 只读边界、HITL 写入原则和可观测性提前成为 F4 的正式验收项；同时仍坚持不用多 Agent、SubAgents 或通用工具框架来实现一个本质上可由可靠后台 Pipeline 完成的功能。