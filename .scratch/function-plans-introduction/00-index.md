# 功能计划索引（PRD v2.1 → 最小闭环拆分）

> 生成：2026-08-16（/grill-with-docs 拆分会话产物，两轮 grilling 共识）；2026-08-17 随本地优先范式转向（决策 #55 / ADR-0001）整体回写
> 消费方式：每份 plan 依次走 grill 流程 `to-spec → to-tickets → implement`，结合当时代码库真实状态
> 术语：遵循 `CONTEXT.md`（学习记录=Record、知识空间=课程统称、归类/升级/捕获）

## 拆分约定

- 范围：仅 MVP（Wave A + Wave B）建 plan 文件；P2+ 按决策 #48 于各阶段启动前详评，此处仅占位
- 每份 plan = 一个可独立验收的业务闭环；模板七节，≤70 行，不写技术实现
- 实现票由 to-tickets 按 tracer-bullet 纵切（桌面端→API→DB）再拆，plan 层不预设票

## 功能 plan（依赖拓扑序）

| # | 功能名称 | Wave | 前置依赖 | PRD 章节 | 文件 |
|---|---------|------|---------|---------|------|
| 01 | 课程管理增强 | A | Phase 0-05 | §4.2 | `01-course-enhancement.md` |
| 02 | 记录列表与详情 | A | 01 | §4.3.4 / §9.1 / §6.5 | `02-record-workspace.md` |
| 03 | 录音捕获 | A | 02（**POC 门槛先行**） | §4.3.1 | `03-recording.md` |
| 04 | 音频导入与转写管线 | A | 02、P0-07 | §4.3.2 / §4.3.3 | `04-transcription.md` |
| 05 | 文档导入 | A | 04 | §4.3.2 | `05-document-import.md` |
| 06 | AI 总结与 HITL | A | 04、05 | §4.4.1 | `06-ai-summary.md` |
| 07 | 知识点提取 | A | 06 | §4.4.2 | `07-knowledge-points.md` |
| 08 | 习题生成与作答 | A | 06 | §4.4.2 | `08-quiz.md` |
| 09 | Todo 清单 | A | 06 | §4.4.2 | `09-todo-list.md` |
| 10 | Markdown 导出 | A | 06、07 | §4.4.2 | `10-markdown-export.md` |
| 11 | 轻捕获与收件箱 | A（B 增段） | 02、06 | §4.3.0 / §6.6 | `11-capture-inbox.md` |
| 12 | AI 对话（自由+@记录） | A | 02、04、06、07 | §4.5 | `12-ai-chat.md` |
| 13 | 偏好设置 | B | P0-05、11 | §4.1 | `13-preferences.md` |
| 14 | 档案、供应商与数据目录 | B | P0-05 | §4.1 / §6.4 | `14-account-profile.md` |
| 15 | 模拟测试 | B | 08 | §4.4.2 | `15-mock-test.md` |
| 16 | 复习资料 | B | 06、07 | §4.4.2 | `16-review-materials.md` |
| 17 | 学习统计 | B | Wave A 功能集 | §4.1 | `17-learning-stats.md` |
| 18 | 全局搜索与命令面板 | B | 02、07 | §9.1 | `18-search-command.md` |
| 19 | 无 key 降级与健康面板 | B | 04、06、12 | §4.1 | `19-degradation-health.md` |

## Phase 0 承载（不重复拆分）

| 功能 | 承载票 |
|------|--------|
| 首启三步（选数据目录 / 配供应商 key / 角色卡，可跳过=功能级降级） | P0-05 |
| 课程新建 + 列表 | P0-05 |
| OpenAPI → api-types 类型链 | P0-06 |
| CI / 进程内 asyncio worker / .msi 发布（含 sidecar 打包）/ llm_call_logs 埋点骨架 | P0-07 |
| localhost 加固（随机端口 + 启动令牌 + 仅绑 127.0.0.1，#56，Phase 0 硬性项） | P0-06 |
| 启动滚动备份（backups/ 每日×7） | P0-07 |

## S0 承载（先行阶段，不建 plan 文件）

| 事项 | 承载方式 |
|------|---------|
| 录音链路 POC（WebView2 节流 / 分片 / 异常恢复 / 本地 ffmpeg 转码，§11-Q6） | 03 开工门槛（通过后方可开工） |
| sidecar 打包冒烟（PyInstaller 体积 / 杀毒误报 / 冷启动，§11-Q14） | P0-07 `.msi` 发布票准入条件 |

## 分散承载（写入对应 plan 的范围/规则行，勿重复拆分）

| 横切能力 | 承载 plan |
|---------|----------|
| learning_events 四事件（#43） | SUMMARY_CONFIRMED→06 / KNOWLEDGE_CONFIRMED→07 / QUIZ_ANSWERED→08 / QUIZ_TEST_COMPLETED→15 |
| sidecar SSE 状态推送（UI 轮询兜底，#8） | 04（首个真实信号源；02 先轮询兜底） |
| 全量导出/导入（原 P2 提前 Wave B，#55） | 14 |
| 空态引导卡（#42） | 各 plan 的空态范围行 |
| 总结评测黄金样本（#46） | 06；习题 Groundedness 样本→15 |
| 工作台导航骨架 + 顶部快速捕获条 | 02（各入口按钮随 03/04/05/11 挂载） |
| 今日页（最小版=HITL 待确认待办） | 02（随 06 生效）；统计卡随 17 |

## P2+ 占位（阶段启动前详评，#48；不建 plan 文件）

| 阶段 | 功能 |
|------|------|
| P2 | Segment 持久化 / Source Anchor 完整溯源 / 课堂标记（⭐❓📝）/ Learning Evidence / sqlite-vec 语义检索 / 网页剪藏 / 对话转学习资产 / @全部资料全局 RAG / 英文支持（ASR en + 输出语言）/ Chat 联网搜索（Tavily）/ 可选快照备份（WebDAV/S3 单向推送）/ 数据与隐私页 / 热词自动同步 |
| P3 | Course Brain（Concept 抽取消歧 / 课程级 RAG）/ Knowledge GPS v1 / 课件 Diff / @课程挂载 |
| P4 | Mastery / 遗忘雷达 / Misconception / Digital Twin v1 / 复习队列 |
| P5 | Socratic Tutor / Teach-back / 自适应测验+Transfer / Memory Rescue / 课前预习 |
| P6 | 动态计划 / Autopilot（Next Best Action）/ 今日建议 |
| P7 | Learning Profile / Passport / 快照 |
| P8 | Study Pod（可选协作） |

## 明确不做

见 PRD §5.2（排行榜 / OCR / 视频导入 / 通用会议笔记等）——不占位。
