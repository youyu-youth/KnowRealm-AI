# PROJECT_PROGRESS.md — 项目进度总览（Agent 交接文档）

> **用途**：任何 Agent（或人）接手开发前先读本文档，即可在不重读全部文档/代码的情况下恢复项目上下文。
> **更新规约**：完结工单、合并分支、落定重大决策时，同步更新本文档对应小节；只保留当前有效信息，过期信息直接删除。
> **最后更新**：2026-09-11（Desktop「课堂详情」按视觉参考完成重设计）

## 1. 项目概述

**KnowRealm-AI** 是开源的**本地优先**个人学习工作台（Tauri 2 桌面应用 + FastAPI sidecar）：把课堂录音、音频导入、文档、粘贴文本、闪念速记统一「捕获」，经 ASR 转写与 AI 总结（人工确认）转化为可编辑、可追溯的学习资产（总结 / 知识点 / 习题 / 模拟测试 / Todo / 复习资料），并提供基于记录内容的 AI 对话问答与全局搜索。

- **给谁用**：一切学习知识的人（学生、程序员、上班族、终身学习者）。
- **产品铁律**：零部署（.msi 即用）、无账号、桌面端永不强制登录（ADR-0014）；数据全部落在用户可见可搬移的本地目录。**新能力先过两问**：① 数据是否落在本地可见可搬移的目录？② 是否要求用户多装任何东西？
- **核心闭环**：捕获 → ASR 转写 → AI 总结（人工确认）→ 知识点 / 习题 / Todo → AI 问答。
- **长期方向**：「学习助手」→「个人学习大脑」（掌握度 / 遗忘复习 / 自适应学习），路线见扩展设计文档 §39/§40。

---

## 2. 当前开发阶段

**基线功能已全部实现，处于「扩展功能（F 系列）+ 质量收尾」阶段。**

- 基线（PRD 决策表 #1~#59 绝大多数）代码完结，约 15 个功能波次仅剩**用户真机验收**（按惯例由用户执行，Agent 验证止于自动化门禁，不代勾）。
- 扩展 F1「转写分片 / 来源时间轴」**六票 + 07 补票全部完结**（06 文档收尾：数据模型升 v2.4 重命名、扩展文档 §7 回写、全库交叉引用同步、backend/AGENTS.md 0019）；锚点两表空表就位，剩用户真机验收。
- Desktop 全局框架与 `/`「今日」页已按新版 `DESIGN.md` 完成重设计：冷中性设计令牌、分层应用壳、课程侧栏、紧凑 Command 入口、Toast / Tooltip / 状态标签与今日页「学习链 → 行动/资产 → 统计」阅读顺序均已落地；范围外页面只继承主题基础，不改业务布局。
- `/inbox` 已改为高密度桌面工作区：真实统计、来源/状态筛选、URL 可恢复搜索与分页、多选批量归类/升级/删除、Transcript 预览及宽屏常驻右栏/窄屏 Dialog 均已落地；并按用户提供的视觉参考强化彩色统计图标、分组筛选按钮、列标题、独立圆角记录行、约 30% 宽右侧检查器及主次操作按钮。真实空态可主动查看醒目标注且完全只读的本地示意数据，未新增后端接口。
- `/spaces`「知识空间」已按视觉参考完成重设计：标题 + 场景/状态胶囊筛选 + 排序 + 「更多筛选」子菜单（收纳教育阶段/课程类型）+ 网格/列表视图切换；课程卡片含场景图标、状态徽章、统计三格（记录/知识点/最近更新）、学习进度条与打开/编辑/⋯删除；右栏四模块（知识空间统计 / 最近活跃课程 / 待归类内容 / 最近活动）；新建课程改为右侧 Sheet 抽屉（学习场景三卡片按钮 + 只读初始状态 + 简介 200 字计数）。筛选/排序/视图全部在客户端完成（一次全量拉取，URL search params 可恢复），后端零改动。课程级聚合统计与周活跃、待归类、活动流后端暂无接口，按惯例用确定性示意数据并以「示意」标签明示（`spacesInsights.ts`，统计域接入后整体替换）；右栏「待归类内容」唯一真实入口为 `/inbox`。卡片「编辑」经 `/spaces/$courseId?edit=1` 直达编辑态。
- `/spaces` 动效与材质打磨（对齐 DESIGN.md §5/§11/§13）：进度条一次性生长（560ms，`transform: scaleX`，`prefers-reduced-motion` 下瞬时到位）为唯一传入动画；网格/列表切换 150ms 淡入 + 4px 位移并统一顶部间距；卡片/列表行 hover 改为 120ms 边框/色面过渡并移除常驻阴影（面板改 `surface-raised`，暗色 hover 仅边框增强以避免"凹陷"观感）；Sheet 出入场 160/180ms；元数据由 `text-ink-faint` 提至 `text-ink-muted` 满足 4.5:1。收件箱暂保留旧柔阴影语言，待后续统一。
- `/spaces/$courseId`「课堂详情」已按视觉参考完成重设计：面包屑 + 课程头（按课程 id 确定性生成封面、关注本地态、打开课程）+ 六标签（概览 / 学习记录 / 模拟测试 / 课程脑图 / 知识GPS / 课程对话，`?tab=` 可恢复）；概览双栏（核心概览｜知识概念图谱｜最近学习记录 + 学习上下文｜知识GPS｜AI 洞察｜重点推荐），右栏课程信息面板（编辑改为右侧 Sheet，`?edit=1` 仍自动打开；删除保留为面板底部操作）；知识图谱支持力导图/树状图切换与全屏 Dialog。课程级统计/掌握度/图谱/对话为确定性示意数据（`courseDetailInsights.ts`，「示意」标签明示），最近学习记录与相关资源为真实数据；「打开课程」跳最近一条记录（无记录 toast 引导顶部捕获）、「和课程聊一聊」跳 `/chat`、示意区内的「去学习」toast 提示；后端与 API 零改动。
- 课堂详情门禁：`pnpm test -- --maxWorkers=4` 412/412（新增 13 条）、`pnpm lint`、触及文件 Prettier、`pnpm build`（内嵌 tsc）均通过；真实 Tauri sidecar 经 WebView2 CDP 完成亮/暗 × 1536×842 / 1280×800 / 1100×720 与字号 S/M/L（15/16/18px）目检：字号 L 下核心统计卡自动降为 2×2、卡片头自动换行、内部双栏保持；动效在 `prefers-reduced-motion: no-preference` 模拟下核对（进度条生长 0.56s、标签内容切换 0.15s、记录行 hover 0.12s，reduce 下全部关闭）；⚠️ 本机 Windows 关闭动画效果，WebView 默认报告 reduce，动效证据为 CDP 模拟值。
- 下一扩展方向（扩展文档 §40.4「P2 统一序列」）：F1 ✅ → A1+A2 并行槽位；B3「Tutor 提前」尚待用户决策，**不要擅自开工**。

---

## 3. 已完成功能（代码已实现、自动化门禁通过）

> 状态标签说明：工单状态存在四代变体 `done` / `completed` / `resolved` / `in-review`，**均视为已完成**（历史惯例差异，见 §8 漂移说明）。下列各项除特别注明外，均剩「用户真机验收」。

| 域 | 功能 | 备注 |
| --- | --- | --- |
| 捕获 | 课堂录音（托盘/全局快捷键）、音频导入、单文件文档导入、文本捕获+闪念速记、捕获收件箱（归类/升级/移交总结）、全局快捷键+托盘 | 录音文件不经云端（ADR-0002/0004），云 ASR 前强制同意（ADR-0006） |
| 转写 | 腾讯云 ASR 管道、密封批次生命周期、失败重试恢复、文档删除清理 | ASR 管道已接句级时间戳（F1 票 02） |
| **F1 分片** | 迁移 0019 四表 + source_anchor 模块；ASR 句级时间戳→JSONL→`/records/{id}/segments`；文档分片 DocumentBlock + document-segments 端点；存量回填 + 编辑对齐重切；**前端来源时间轴（三态浏览视图、quote 内联高亮+时间戳徽章、分片重拉三处）+ chat 引用句级定位**；文档记录接入块级时间轴（07 补票） | 票 01~07 完结；文档收尾=数据模型 v2.4、扩展文档 §7 回写；降级双场景（无时间戳/无分片）已处理 |
| 总结 | Provider 优先的总结生成、调整/确认/恢复（人工确认制） | LangGraph 图之一；>30k 长文的 map-reduce **未做**（见 §5） |
| 知识点 | 候选生成、人工审核确认、重生成与转写联动 | |
| 习题 | 四题型生成/采纳/重生成、客观题作答、简答题完成 | |
| 模拟测试 | 五题型建卷、作答面、逐题 LLM 评分+交卷、结果页+摘要侧栏、崩溃恢复重评 | QUIZ_TEST_COMPLETED 幂等；失败题排除分母 |
| Todo | 手动 CRUD、生成/采纳/修剪、用户接管语义 | 接管即脱离批次（ADR-0011） |
| 复习资料 | 生成（上下文=转写全文+总结辅助）、HITL 确认对话框、版本链编辑、导出接入 | LangGraph 图之二；RAG 已否决 |
| AI 对话 | 档案（角色+自我介绍）、会话管理、流式自由对话、记录挂载上下文、引用（citations）+转写失效联动、知识点讲解入口 | LangGraph 图之三：`create_agent` 循环（#53），**tools=[] 空置预留**检索工具 |
| 课程 | 工作台骨架、课程 CRUD、发现页、详情编辑、归档退出 | ARCHIVED 前置护栏三道闸门已校验；归档/恢复 UI 未做（有意推迟） |
| 记录 | 真实记录列表、记录详情（总结/转写面板化）、记录删除退出 | |
| 学习统计 | 后端七口径统计端点、前端统计带+5 图（真实数据） | 七口径=JOIN records+子表 deleted_at 双过滤 |
| Desktop 界面 | 全局 `canvas → sidebar → paper` 框架、224/64px 响应式侧栏、52px 顶栏、课程快捷入口、Base UI Tooltip / Toast / 状态标签；「今日」页学习链、行动/资产双列、真实六指标 + 7/30 天趋势与次级洞察图；「收件箱」统计筛选、多选批量操作、紧凑列表与响应式内容预览；「知识空间」胶囊筛选 + 网格/列表视图、课程卡片（统计/进度）与右栏洞察、新建课程 Sheet 抽屉；「课堂详情」面包屑 + 课程头、六标签、知识图谱双视图（力导/树状）+ 全屏、概览双栏 + 课程信息面板（编辑 Sheet / 删除） | 无后端、API 或数据结构变更；无后端支持区域（右栏统计/活动、卡片聚合统计、课程级概览/掌握度/图谱/对话、相关推荐）以确定性示意数据 + 「示意」标签明示且只读；筛选/排序/视图/标签为客户端实现，URL 可恢复 |
| 全局搜索 | FTS5+jieba 应用层分词（ADR-0016）、写路径同事务同步 11 挂点、Ctrl+K 命令面板、`/library` 资产库视图 | 统一索引表；软删查询期回表过滤；启动幂等回填 |
| 设置 | 偏好（外观/通用/关闭行为/自启/快捷键自定义/重启恢复）、档案（昵称/头像）、LLM/ASR 供应商卡+连通性手动测试、数据目录（切换/迁移/重启，desktop.json）、全量导出/导入/滚动备份、首启向导四步、**服务与用量分区（30 天 LLM 用量聚合+趋势图+缺 key 徽章）** | 单 active 供应商；连通性仅手动（真实计费） |
| 界面语言 | 中英全量切换（含首启向导语言步）、en.json 全量真译+一致性防线、后端错误码化（ADR-0017 附加字段）、前端错误码翻译消费+壳层命令码化 | 内容语言与界面语言解耦（prompt 固化指令） |
| 导出 | 总结/知识点本地导出、习题/Todo 本地导出（markdown） | 聚合导出验收待用户（ready-for-human） |
| 评测 | 习题 Groundedness 评测样本集与评审 checklist（docs/evaluation/） | 样本采集待用户（阻塞项） |

---

## 4. 进行中 / 部分完成

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 用户真机验收 | 约 15 个波次 | account-profile / preferences(04 恢复) / 模拟测试 / 复习资料 / 学习统计 / 全局搜索 / 服务用量 / 界面语言 / F1 分片等，验收项在各工单内单列，**不代勾**（preferences 05 整票=验收票，deferred） |

---

## 5. 待开发 / 规划中

**明确待做（已有工单）：**

- `ai-summary/03-long-summary-quality-recovery`（`ready-for-agent`，8 项未勾）：>30k 长总结 map-reduce、90s 超时/不自动重试语义、手动重试复用 Job、ACTIVE 校验、llm_call_logs 字段补全、评测样本。⚠️ 这是**唯一一张实质性未做的旧功能票**；现状是 chat 侧对 >30k 转写做降级提示（`chat/graph.py` CHAT_TRANSCRIPT_MAX_CHARS=30000），总结侧无长文处理。
- `markdown-export/03` 聚合导出（`ready-for-human`，代码完成仅剩用户验收后关票）。

**规划中（未拆票，勿直接开工）：**

- 扩展文档 §40.4「P2 统一序列」：F1（✅ 已完成）→ **A1+A2 并行槽位**（Agent 能力建设，对应基线 #53/#24 已定项的细化）；B3「Tutor 提前」与 F2/F3（课堂相关）**待用户决策**。
- 习题 Groundedness：待用户采集真实样本（阻塞项）+ 06 总结黄金样本另议；回归触发=prompt_version/模型变更。⚠️ prompt_version 至今未 bump，启用评测前需处理。
- 未来候选库路线图（带触发条件，见记忆/后端轮子审计）：检索 FTS5 trigram→sqlite-vec、复习调度 fsrs、导出 fpdf2、pytest-cov/timeout；APScheduler/LanceDB/本地 whisper 已否决。
- 产品层扩展方向五新场景包：见扩展文档 §39.4（仅评审记录，**非用户已批准**）。

---

## 6. 项目架构现状

```
KnowRealm-AI（pnpm workspace + uv 后端，无根 package.json）
├─ apps/desktop/          Tauri 2 + React + TS 桌面端
│  ├─ src/pages/          TanStack Router 文件路由（今日 index、inbox、chat.*、library、
│  │                      onboarding、records.$recordId、settings、spaces.* 课程与测试）
│  ├─ src/features/       14 个功能域（chat/courses/records/search/settings/today/library/
│  │                      recording/audio-import/document-import/text-capture/inbox/
│  │                      quiz-tests/onboarding）
│  ├─ src/styles/         tokens.css(@theme) / theme.css / globals.css / animations.css 分层
│  └─ src-tauri/          Rust 壳：sidecar 拉起、托盘、全局快捷键、数据目录解析（ADR-0013）
├─ backend/               FastAPI sidecar（uv 管理，py312，feature-first 模块化单体 ADR-0015）
│  ├─ app/modules/        18 模块：capture/chat/course/data/jobs/knowledge_point/llm/profile/
│  │                      quiz/record/review_material/search/settings/source_anchor/summary/
│  │                      today/todo/transcript
│  ├─ app/shared/         deps/errors(带码 HTTPException)/events/prompts/schemas
│  ├─ app/core/           data_dir/logging/loop/version
│  ├─ app/db/             engine/base/migrations（SQL 迁移执行器，PRAGMA user_version 推进）
│  └─ migrations/         0001~0019 手写 SQL，四位编号连续递增不可跳号
├─ packages/api-types/    OpenAPI → TS 类型生成（后端 schema 变更后必须重新 generate）
├─ docs/                  权威文档 + ADR + 评测 + 规则镜像（正本在 .claude/rules/）
└─ .scratch/              工单 tracker（25 个 feature 目录）
```

**LangGraph（后端三图）**：`summary/graph.py`（总结生成）、`review_material/graph.py`（复习资料）、`chat/graph.py`（create_agent 循环，tools 预留空位）。无独立 agent 服务，「Agent 能力」以工具挂载形式演进（见扩展文档 §40）。

**任务系统**：`modules/jobs` JobRunner——SQLite 单属主任务循环（ADR-0012），ASR/总结/KP/习题/复习/评分/回填等全走此通道；崩溃恢复与幂等由各 worker 自理。

**数据库**：SQLite 单文件（knowrealm.db），唯一事实源；软删（deleted_at）贯穿；写路径搜索索引同事务 upsert。



## 7.  技术债务 / 文档漂移

**技术债务 / 临时实现：**

- **learning_events 表零消费者**、chat graph `tools=[]` 空置——均为预留（§40 A 档建设的挂点），非缺陷但勿误删。
- **总结侧无长文 map-reduce**（仅 chat 侧有 >30k 降级提示）；`prompt_version` 从未 bump，评测回归机制启用前需补。
- 供应商连通性测试用腾讯 `GetAsrVocabList` 只读接口近似（LLM 测试=真实计费生成，故仅手动）。
- 前端全量测试默认并发时，资源竞争会使不同 5 秒用例偶发超时；失败文件单跑均通过，本次以 `pnpm test -- --maxWorkers=4` 的 394/394 作为稳定全量证据。
- 分支未合并堆积：`feat/extend-dev-05` 领先 main 34 提交；本地尚存多个历史 feature 分支（feat/dev-01~04、arch-opt 等）。

**本机环境坑（跑门禁前必读，详见 §9 命令）：**

- 后端 pytest **必须** `--basetemp=.pytest-tmp`（系统临时目录 WinError 5 拒绝访问）。
- 日常开发只跑 `pnpm --filter @knowrealm/desktop tauri dev`（壳自动拉 sidecar）；手动跑后端必须独立 data-dir。壳 panic 不清理 sidecar 会留孤儿 python 占数据目录锁 →「sidecar health check timed out」，用 taskkill 清残留，查 `logs\backend.log`。

---

## 8. 其他

**常用命令：**

```bash
# 后端（backend/ 下，uv 管理）
uv run pytest --basetemp=.pytest-tmp          # 全量测试（测完删临时目录）
uv run ruff check . && uv run ruff format --check .
uv run pyright                                 # strict
uv run python -m scripts.export_openapi ../../packages/api-types/openapi.json --check

# 前端（apps/desktop/ 下）
pnpm test && pnpm lint && pnpm format:check && pnpm build   # build 内嵌类型检查
pnpm --filter @knowrealm/desktop tauri dev     # 完整壳（自动拉后端+ffmpeg 预备）

# 契约生成（后端 schema 变更后）
pnpm --filter @knowrealm/api-types generate
```
