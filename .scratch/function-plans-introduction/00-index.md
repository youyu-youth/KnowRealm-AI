# 功能计划索引（PRD v2.1 → 最小闭环拆分）

> 生成：2026-08-16（/grill-with-docs 拆分会话产物，两轮 grilling 共识）；2026-08-17 随本地优先范式转向（决策 #55 / ADR-0001）整体回写；同日澄清实施顺序：页面与真实功能优先，取消独立 S0 / 全量 Phase 0 前置
> 消费方式：每份 plan 依次走 grill 流程 `to-spec → to-tickets → implement`，结合当时代码库真实状态
> 术语：遵循 `CONTEXT.md`（学习记录=Record、知识空间=课程统称、归类/升级/捕获）

## 拆分约定

- 范围：仅 MVP（Wave A + Wave B）建 plan 文件；P2+ 按决策 #48 于各阶段启动前详评，此处仅占位
- 每份 plan 的**最终出口**必须可独立验收；中间里程碑可以是明确标注未完成范围的 tracer bullet，不得把部分接通宣称为整个 plan 完成
- 实现票由 to-tickets 按 tracer-bullet 纵切（桌面端→API→DB）再拆；工程基础随首个消费者进入同一纵切，不单独堆成开工阶段
- 本索引是当前依赖与顺序来源；已有 plan 文件进入 `to-spec` 时须先消除旧 S0 / Phase 0 / 隐含依赖，再生成实现票

## 功能 plan（依赖拓扑序）

| # | 功能名称 | Wave | 前置依赖 | PRD 章节 | 文件 |
|---|---------|------|---------|---------|------|
| 01 | 工作台骨架与课程管理 | A | 桌面工程已初始化；按需基础随本 plan 首个真实功能交付 | §4.2 / §9.1 | `01-course-enhancement.md` |
| 02 | 记录列表与详情 | A | 01 | §4.3.4 / §9.1 / §6.5 | `02-record-workspace.md` |
| 05 | 文档导入 | A | 02；按需引入最小 worker/`processing_jobs` | §4.3.2 | `05-document-import.md` |
| 06 | AI 总结与 HITL | A | 05（首闭环）或 04（后续来源）；至少一条真实来源接通；按需引入最小 Provider/日志/Checkpointer | §4.4.1 | `06-ai-summary.md` |
| 04 | 音频导入与转写管线 | A | 02；复用 05 已落的 worker 基础 | §4.3.2 / §4.3.3 | `04-transcription.md` |
| 03 | 录音捕获 | A | 02、04；录音 POC 是本 plan 首张实现票 | §4.3.1 | `03-recording.md` |
| 07 | 知识点提取 | A | 06 | §4.4.2 | `07-knowledge-points.md` |
| 08 | 习题生成与作答 | A | 06 | §4.4.2 | `08-quiz.md` |
| 09 | Todo 清单 | A | 06 | §4.4.2 | `09-todo-list.md` |
| 10 | Markdown 导出 | A | 06、07 | §4.4.2 | `10-markdown-export.md` |
| 11 | 轻捕获与收件箱 | A（B 增段） | 02、06 | §4.3.0 / §6.6 | `11-capture-inbox.md` |
| 12 | AI 对话（自由+@记录） | A | 02、06、07；05 或 04 至少一条真实 Transcript 来源 | §4.5 | `12-ai-chat.md` |
| 13 | 偏好设置 | B | 11 | §4.1 | `13-preferences.md` |
| 14 | 档案、供应商与数据目录 | B | 01、06（扩展首闭环 Provider 切片） | §4.1 / §6.4 | `14-account-profile.md` |
| 15 | 模拟测试 | B | 08 | §4.4.2 | `15-mock-test.md` |
| 16 | 复习资料 | B | 06、07 | §4.4.2 | `16-review-materials.md` |
| 17 | 学习统计 | B | Wave A 功能集 | §4.1 | `17-learning-stats.md` |
| 18 | 全局搜索与命令面板 | B | 02、07 | §9.1 | `18-search-command.md` |
| 19 | 无 key 降级与健康面板 | B | 04、06、12 | §4.1 | `19-degradation-health.md` |

## 当前起点与首个真实闭环

- 当前事实：Tauri 2 + React 桌面工程壳、样式与依赖已经初始化；尚无导航、路由、页面和业务功能。不得把“工程已初始化”写成“Phase 0 已完成”。
- 页面起步：01 先按 `DESIGN.md` 完成工作台壳、导航、路由、真实空态与全局状态边界，再在同一骨架内开发课程页面；后续页面只扩展内容区，不重复设计应用外壳。
- 首个实现顺序：`01-A 工作台骨架 → 01-B 最小课程真实闭环 → 01-C 课程管理完整出口 → 02 Record 工作区 → 05 单文件文档导入 → 06 AI 总结与 HITL`。
- 工作台骨架不是静态页面批量铺设：未实现入口必须禁用或进入明确的未接入状态，不使用示例数据、死按钮或假成功；课程页从真实空态开始，并在同一 plan 内接通本地数据。
- 所有桌面页面统一遵循 `DESIGN.md` 的 Continuous Work Surface：稳定侧栏与捕获栏、Zero Card Chrome、亮/暗色、键盘焦点、无整体横向溢出及规定桌面尺寸；各功能 plan 不另起视觉体系。
- 首个出口：真实 TXT/MD/PDF 单文件经 localhost API 落盘 → Transcript → 结构化总结 → 调整 → 确认；Provider/处理失败可恢复，`SUMMARY_READY` 跨重启可继续。
- Wave A-0 只是一条真实 tracer bullet；DOCX/PPTX、多文件、超长文档 map-reduce 与完整黄金样本补齐前，不得宣称 plan 05/06 完成。

## 按需工程基础（不建独立 Phase 0 plan）

| 功能 | 承载票 |
|------|--------|
| 数据目录、SQLite WAL 与迁移体系、课程新建 + 列表 | 01；随首个持久化功能一起交付 |
| FastAPI sidecar、OpenAPI → api-types 类型链、localhost 加固（随机端口 + 启动令牌 + 仅绑 127.0.0.1，#56） | 01；随首个 localhost API 一起交付 |
| 工作台导航、路由、顶栏、真实空态与全局状态边界 | 01；先于课程页面交付，后续 plan 复用 |
| 进程内 asyncio worker、`processing_jobs` 与处理中轮询 | 05；随首个后台任务一起交付 |
| 单一 active LLM Provider、`llm_call_logs`、LangGraph Checkpointer | 06；随首个 AI 功能一起交付 |
| 启动滚动备份（backups/ 每日×7） | Wave A-0 退出前；数据库产生真实业务数据后验证 |
| 档案/角色卡、完整 Provider 卡、数据目录迁移与导出 | 14，不前置到首个闭环 |
| CI、`.msi` 发布、sidecar 打包与新机安装冒烟 | 首次可分发里程碑，不阻塞此前页面与功能 |

## 录音与分发风险验证（不建独立 S0）

| 事项 | 承载方式 |
|------|---------|
| 录音链路 POC（WebView2 节流 / 分片 / 异常恢复 / 本地 ffmpeg 转码，§11-Q6） | 03 的首张实现票；不阻塞 01/02/05/06 |
| sidecar 打包冒烟（PyInstaller 体积 / 杀毒误报 / 冷启动，§11-Q14） | 首次可分发 `.msi` 的准入条件；不与录音 POC 捆绑 |

## 首个 Provider 切片与验证节奏

- 只支持一个 active LLM Provider：DashScope 预设或自定义 OpenAI 兼容端点；字段仅 `kind/api_key/base_url/model`。多卡 CRUD、切换、健康面板和用量统计留在 14/19。
- 连接测试必须用保存的 model 执行最小真实结构化生成，正式总结复用同一 Provider 客户端；只测 TCP、HTTP 或 `/models` 不算通过。
- GET 不返回原 key；空 key 更新保留旧值，清除必须显式操作；自定义地址仅接受不含内嵌凭据的绝对 `http/https` URL，默认校验 TLS，跨主机重定向不得携带 Authorization；前端不直连 Provider；日志不得记录 key、Authorization、Transcript 或总结全文。
- 未配置 Provider 时 Record 保持 `SUMMARY_PENDING`；配置完成后继续，不新增状态，不把可恢复缺配置写成永久失败。
- 非平凡逻辑随功能留下最小可运行检查；较大业务闭环完成后集中跑集成、浏览器关键路径与回归；`.msi` 安装测试留到首次可分发里程碑。

## 分散承载（写入对应 plan 的范围/规则行，勿重复拆分）

| 横切能力 | 承载 plan |
|---------|----------|
| learning_events 四事件（#43） | SUMMARY_CONFIRMED→06 / KNOWLEDGE_CONFIRMED→07 / QUIZ_ANSWERED→08 / QUIZ_TEST_COMPLETED→15 |
| sidecar SSE 状态推送（UI 轮询兜底，#8） | 05 先随首个 worker 落轮询兜底；04 随音频长任务接入 SSE，并复用同一 Record 查询入口 |
| 全量导出/导入（原 P2 提前 Wave B，#55） | 14 |
| 空态引导卡（#42） | 各 plan 的空态范围行 |
| 总结评测黄金样本（#46） | 06；习题 Groundedness 样本→15 |
| 工作台导航骨架 + 顶部快速捕获条 | 01（各入口按钮随 03/04/05/11 挂载；未挂载前明确禁用/未接入） |
| 今日页内容宿主 | 01 只建真实空态；HITL 待办随 06 生效，统计卡随 17 |

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
