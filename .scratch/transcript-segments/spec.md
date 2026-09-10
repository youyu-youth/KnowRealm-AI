# F1 转写分片与来源时间轴（Transcript Segments + Source Timeline）

Status: ready-for-agent

## Problem Statement

转写目前是一整篇无结构纯文本。学习者想知道"老师在哪一分钟讲了 AOF"，只能通读全文；chat 回答的引用角标点了之后，跳到转写页整篇里高亮一段摘录，没有时间、没有句子边界——无法回答"这在课堂的哪个位置"。而事实上腾讯 ASR 每次都返回了句子级起止时间戳，PDF 解析时页码也天然可得，只是落地时被丢弃。存量记录、粘贴/速记、转写人工编辑等场景天然没有时间信息，目前没有统一的退化语义——要么报错，要么能力覆盖不全。

2026-09-09 两轮 grill 定稿（13 问全按推荐收敛）。本 spec 固化该轮全部裁决，范围对应扩展设计文档 §7（F1）与 §40.4 P2 统一序列第 1 步（A0：P2 数据地基第一步）。

## Solution

1. **来源时间轴**：课堂详情的转写页在浏览态升级为句级时间轴——行式排布（左时间戳、右句文本），多文件按课堂拼接时间轴连续编号；无时间戳的片段正常陈列（无时间标记）。
2. **句级引用定位**：chat 引用角标点击后，跳到转写页并定位到包含该摘录的句子（滚动 + 高亮 + 时间戳徽章）；原文已变动时维持现状"原文已变动"反馈。
3. **时间戳不再丢弃**：新音频转写自动获得句级时间轴；文档导入获得分片（PDF 带页码）；存量记录启动时幂等回填为无时间戳分片；转写编辑保存时逐句对齐，未改动句保留时间戳。
4. **锚点结构就位**：四张表（转写分片 / 文档分片 / 来源锚点 / 锚点链接）按数据模型 v2.3 落地，为后续学习证据（A3）、检索工具（A1）、AI 产物引用提供统一挂靠结构；本期锚点表零写入者。

## User Stories

**浏览**

1. As an 学习者, I want to 在课堂详情转写页浏览句级来源时间轴（时间戳 + 文本行式排布）, so that 快速定位某分钟讲了什么。
2. As an 学习者, I want to 无时间戳的片段在时间轴上以无时间标记形态陈列, so that 数据不全时时间轴仍可浏览而不是报错。
3. As an 粘贴/速记记录的学习者, I want to 这类记录继续以纯文本形态浏览（无时间轴）, so that 不同来源的展示形态各得其所。

**引用定位**

4. As an 对话用户, I want to 点击回答中的引用角标后跳到转写页并定位到对应句子（高亮 + 时间戳徽章）, so that 核对 AI 说的原话在课堂的哪个位置。
5. As an 对话用户, I want to 转写被编辑后引用原文找不到时得到"原文已变动"提示, so that 定位失败有明确反馈而不是无声失败。

**编辑**

6. As an 学习者, I want to 修正转写里几个错别字保存后，未改动句子保留原时间戳, so that 一次小编辑不毁掉整堂课的时间轴。
7. As an 学习者, I want to 编辑保存后新增/改动的句子以无时间戳形态进入时间轴, so that 时间轴始终反映当前内容而不是历史快照。
8. As an 学习者, I want to 编辑入口与现状一致（整篇文本编辑、乐观锁版本递增、下游产物按转写版本失效的既有链路不变）, so that 编辑行为对本功能无感知差异。

**新记录**

9. As an 音频导入者, I want to 转写完成后自动获得句级时间轴（腾讯 ASR 句子时间戳落地）, so that 无需任何额外操作。
10. As an 多文件记录的学习者（多段录音）, I want to 时间轴覆盖全部文件并按文件顺序连续编号, so that 整堂课一条时间轴。
11. As an 文档导入者, I want to PDF 按页获得分片（带页码）、DOCX/txt/md 按内容块分片（无页码）, so that 引用能落到页码或块。

**存量与升级**

12. As an 存量数据学习者, I want to 应用升级后已有记录自动补齐无时间戳分片（启动幂等回填、增量补新记录）, so that 旧记录也能获得句级定位能力。
13. As an 升级时刻正在转写的用户, I want to in-flight 转写任务按降级方式合并完成（不报错、不重跑、不重复计费）, so that 升级对我无感。

**结构（开发者）**

14. As an 开发者, I want to 四张表按数据模型 v2.3 §4.5 定稿结构落地（含时间戳列允许 NULL 的语义修正）, so that A3 学习证据、A1 检索工具、AI 产物引用直接挂靠。
15. As an 开发者, I want to 来源锚点以独立模块提供唯一入口（service + 读 API）, so that 跨域消费不散落各处。
16. As an 开发者, I want to 分片接口一次返回全部分片（不分页）, so that 前端时间轴一次渲染。
17. As an 开发者, I want to 后端 schema 变更后重新生成前端 API 类型, so that 契约链同步。
18. As an 开发者, I want to 回填幂等（重复启动不重复建分片）, so that 升级路径安全。

## Implementation Decisions

**四项根决策（grill 定稿）**

1. **事实源与编辑语义**：转写表 content 是唯一事实源，分片是派生定位层；编辑保存时**增量对齐重切**——逐句 `content_hash` 命中的句子保留原时间戳，新增/改动句时间戳置 NULL；不建分片多版本。时间戳 NULL = 全库唯一退化态（无时间轴来源），三处场景（存量回填 / in-flight 降级 / 编辑未命中句）共用同一语义。
2. **存量与降级统一**：启动幂等回填（沿用搜索索引回填先例）与 in-flight 旧任务降级合并共用"从纯文本建无时间戳分片"能力；回填按现有 content 结构切分（换行/段落）。
3. **交付边界**：数据地基 + 来源时间轴前端；不含音频回放、不含 AI 产物 graph prompt 引用改造、不含锚点写入者、不动搜索索引。
4. **结构归属**：转写分片/文档分片归 transcript 模块（写入路径本就在彼）；来源锚点/锚点链接独立 source_anchor 模块（对标 search 模块"跨域消费 + 唯一入口"先例）；锚点表本期**空表就位**（结构 + service + 读 API，零写入者——第一个写入者是后续 A1/A3/graph 升级票，chat 引用物化与手动锚点按钮均已否决，YAGNI）。

**数据表（迁移 0019，按数据模型 v2.3 §4.5 定稿 + 一处语义修正）**

- `transcript_segments`：id / transcript_id / record_id / file_id / sequence_no / record_start_ms / record_end_ms / file_start_ms / file_end_ms / speaker（恒 NULL 预留）/ content / content_hash；索引 (record_id, sequence_no)、(file_id, file_start_ms)、(record_id, record_start_ms)。**语义修正**：四个时间戳列允许 NULL（= 无时间轴来源），数据模型随本 spec 升 v2.4。
- `document_segments`：id / course_id / record_id（可空）/ record_file_id / course_material_id（CHECK 二者必须且只能一个非空）/ sequence_no / page_no（可空）/ section_title（可空）/ content / start_offset / end_offset / content_hash。course_material 挂靠路径列先建着（该表尚未存在，无外键），课件资料功能落地时再补约束。
- `source_anchors`：source_type（AUDIO_SEGMENT / DOCUMENT_SEGMENT / USER_NOTE / CHAT_MESSAGE）/ source_id / 各定位外键列（可空，Audio/Document 来源至少关联一个具体分片）/ start_offset / end_offset / page_no。
- `source_anchor_links`：resource_type（SUMMARY / KNOWLEDGE_POINT / QUIZ / MISCONCEPTION / CHAT_MESSAGE / RECORD_ANALYSIS）/ resource_id / source_anchor_id / relation_type（SUPPORTS / PRIMARY / CONTRADICTS / REFERENCES）；唯一约束 (resource_type, resource_id, source_anchor_id, relation_type)。
- 迁移纪律：新增迁移须同步全部 user_version 断言测试（当前 11 个测试文件）与导入归档版本上限逻辑。

**ASR 管道改造（票 2）**

- 腾讯客户端接住 ResultDetail 中每句的起止时间戳（现状在客户端边界即丢弃）；ASR 任务结构增加结构化句子列表。
- chunk 文本缓存从纯 txt 改为 JSONL（每句 text + 起止时间）；ASR checkpoint 结构相应扩展，旧 checkpoint（无句子信息）兼容读取。
- **in-flight 降级合并**：版本升级瞬间的旧 checkpoint / 纯 txt 缓存按纯文本合并为无时间戳分片，不重跑、不报错、不重复计费。
- 转写定稿（finalizer）合并各文件句子流写入 transcript_segments；多文件 record 时间轴 = 按 sequence_no 顺序、前序文件 duration_ms 累加（"课堂拼接时间轴"语义，非真实墙钟，已写入 CONTEXT.md「来源时间轴」词条）。

**文档分片（票 3）**

- PDF 逐页提取时分片（页码保留，现状提取后被丢弃）；DOCX 按内容块（段落/表格）分片、无页码；txt/md 按内容块分片、无页码。PPTX 维持现状不支持。

**纯文本建分片能力（票 4，回填与编辑重切共用）**

- 启动幂等回填：遍历无分片的已有转写，按现有 content 结构切分建无时间戳分片；增量补新记录；重复启动零副作用。
- 编辑增量对齐重切：PATCH 转写保存路径上，按句哈希对齐——命中句保留时间戳（分片行更新），未命中句时间戳 NULL；分片 id 换新时，既有锚点未来将退化 quote 定位（本期无锚点写入者，此为向后契约）。
- 粘贴/速记（轻捕获，无 record_file）**不建分片**：锚点未来走 USER_NOTE + 字符 offset；"有 transcript_segment = 有时间轴"保持清晰心智。

**API 与前端（票 5）**

- 新增 `GET /api/records/{record_id}/transcript/segments`：一次返回全部分片（不分页，2 小时课堂约 100-200KB 可接受）；现有 transcript 端点不内嵌分片（避免 content 双份传输）。
- TranscriptPanel 双模式：**浏览态从纯文本升级为行式时间轴**（左时间戳 mm:ss、超一小时进位 h:mm:ss，右句文本，密集排布）；**编辑态维持现有整篇 Textarea 不变**；无分片的记录浏览态回落纯文本。
- chat 引用句级定位走**前端匹配**：跳转后在已加载的分片中找 content 包含 quote 的分片 → 滚动 + 高亮 + 时间戳徽章；找不到走现状"原文已变动"兜底。后端 citations 契约零改、api-types 不因 chat 变更。
- 新 UI 文案 zh/en 同步（i18n 双语纪律）；UI 遵循 DESIGN.md 与现有设计令牌体系。

**明确不动**

- 搜索索引（search_index）不 segment 化——段落级命中随 A1 检索工具票做。
- summary / 复习资料 / KP / quiz / chat 的 prompt 与上下文组装全部不动（无 prompt_version 变更，不触发评测回归）。
- learning_events / learning_evidence 不动（A3 票做 Evidence Builder）。

## Testing Decisions

- **最高 seam 原则**：后端测试经 httpx AsyncClient 打内存 app（现有 conftest 模式）；ASR 管道用 fake ASR client（现有模式），断言到"分片落库 + 时间戳正确"而非内部函数。
- 迁移测试：断言四表结构、CHECK 约束、索引、user_version 顶格（现有迁移测试先例）。
- 回填/对齐重切：service 级测试（幂等性、hash 命中保留时间戳、未命中 NULL、多文件累加时间轴、降级合并）。
- API 测试：segments 端点（正常/无分片回落/软删过滤）。
- 前端：MSW mock segments API 的 TranscriptPanel 组件测试（时间轴渲染、无时间戳形态、编辑态不变、quote 定位与兜底），先例为现有 TranscriptPanel / ChatMessageList 测试。
- 门禁：backend pytest（`--basetemp=.pytest-tmp`）+ ruff + pyright；desktop vitest + tsc + prettier；api-types 漂移检查。

## Out of Scope

- **音频回放**（点击时间戳从某分钟播放原声）：独立后续票，方向已锁 = Tauri asset protocol（`convertFileSrc`）+ `<audio>`，零后端端点；票内需预研录音封装格式在 WebView2 的解码支持。
- **AI 产物自动引用**（summary/KP/quiz 生成时输出锚点）：graph prompt 工程 + 评测，随 A1 或独立票。
- **锚点写入者**（A1 检索工具引用 / A3 Evidence Builder / 用户手动锚点按钮）。
- **搜索索引 segment 化**（A1 票）。
- **PPTX 文档支持**（维持现状不支持，未来支持 PPTX 导入时随做分片）。
- **speaker 说话人分离**（列恒 NULL 预留）。
- **重新转写（re-transcribe）**、F2 课堂标记、F6 Evidence Builder 管道本体。

## Further Notes

- **6 票框架**（to-tickets 阶段正式拆）：
  1. 结构就位：迁移 0019 四表 + models + source_anchor 模块骨架（service + 读 API）；
  2. ASR 管道：时间戳接住 + JSONL 缓存 + finalizer 写分片 + in-flight 降级兼容；
  3. 文档分片：parser 页码保留 + document_segments 写入；
  4. 纯文本建分片：启动幂等回填 + 编辑增量对齐重切（同一 service）；
  5. API + 前端时间轴：segments 端点 + TranscriptPanel 浏览态时间轴 + chat 引用句级定位；
  6. 文档落盘：数据模型 v2.3→v2.4（NULL 语义 + 已实施标注）+ 扩展文档 §7 回写 + PRD 交叉引用同步。
  依赖：1 → 2/3/4（可并行）→ 5；6 收尾。票 2/3/4 交付时即有 API 可查分片，验收不阻塞票 5。
- **路线衔接**（§40.4）：本 spec = P2 统一序列第 1 步（A0）；下一步 A3 Evidence Builder（依赖锚点结构）；A1+A2（chat 检索工具 + 工具调用前端呈现）为并行槽，F1 落地后其检索粒度可升级为段落级。
- **Agent 能力融入定位**：本期零新 graph、零框架引入——分片是 A1 检索工具（命中粒度段落级）、A3 学习证据（source_anchor_id 挂靠）、未来 AI 产物引用（锚点链接契约）的供料层。
- **术语**：UI 与文档统一用「来源时间轴」（Source Timeline），"Evidence Timeline" 废弃；Evidence 一词专属「学习证据」（Learning Evidence）。CONTEXT.md「转写与溯源」分节已更新（片段时间范围可空语义 + 新增来源时间轴词条）。
