# B2 跨记录 / 课程级问答（scope 扩展 + search_library + 跨记录引用）

Status: done

## Problem Statement

AI 对话只能挂载单条记录（`ChatSessionCreate.record_id` 单值）：课程学习天然是跨记录的——用户想问「这门课整体讲了什么」「对比第 2 次和第 5 次课的观点」，AI 却一次只能看一条转写；不归属任何课程的收件箱资料（#24：泛化用户群的资料常不属任何「课」）更是完全没有问答入口。前端「课程 / 全部资料」范围胶囊是禁用占位，课程详情页「对话」Tab 是示意假数据。

## Solution

1. **会话范围四档**：`scope = FREE / RECORD / COURSE / ALL`——把挂载范围从「自由 / 单记录」扩为「单记录 / 课程 / 全部资料」（决策 #22/#24、扩展文档 §0 D5、§40.3 B2）；`chat_sessions.course_id` 列（0014 起存在、零写入）启用语义。
2. **第二个检索工具 `search_library`**：课程 / 全部范围会话挂载（与 `search_transcript` 互斥），跨记录分片 FTS（命中带记录标题与时间 / 页码）+ 零命中才 LIKE 兜底（覆盖粘贴 / 速记等无分片记录）。
3. **记录标题清单上下文**：课程 / 全部会话不塞任何转写正文，system 喂「范围内记录清单（标题 + 日期 + 有无转写）+ 检索指引 + 跨记录引用格式」——清单是回答「有哪些材料 / 哪次课讲了什么」的最低必要事实。
4. **跨记录引用契约**：引用行 `[n] 逐字摘录（来源：记录标题）`；校验器按标题定位记录 → 该记录内逐字 + 模糊对齐；定位失败全范围逐字扫描兜底；归属由校验器裁定，落库 `record_id` + `record_title` 快照。
5. **web_search 挂载语义延伸**：课程 / 全部范围视同挂载（默认关、可开、材料优先指引）。

## User Stories

**课程问答**

1. As an 课程学习者, I want to 在课程范围内提问「这门课讲了什么」「帮我梳理这门课的知识脉络」, so that 不必逐条打开记录自己拼。
2. As an 课程学习者, I want to 问跨记录对比问题（「第 2 次和第 5 次对 X 的说法有何不同」）时 AI 检索多条记录作答, so that 对比类学习问题有据可依。
3. As an 课程学习者, I want to 从课程详情页「对话」Tab 一键发起该课程范围的会话, so that 入口在学习的现场。

**全部资料问答**

4. As an 资料不归属课程的用户, I want to 在「全部资料」范围问「我所有资料里关于 X 的内容」, so that 收件箱里的零散资料也可被问答（#24）。
5. As an 用户, I want to 空范围（课程暂无记录 / 库里没资料）时 AI 如实告知没有资料, so that 不被编造内容误导。

**引用与过程透明**

6. As an 跨范围会话用户, I want to 回答引用标明来自哪条记录（标题），点击跳到那条记录的转写页, so that 跨记录结论可逐条溯源。
7. As an 跨范围会话用户, I want to 消息流内看到「正在检索学习资料」状态卡（沿用 A2 形态）, so that 检索过程可见。
8. As an 跨范围会话用户, I want to 引用摘录仍是逐字原文（校验不过就丢弃该条）, so that 逐字校验契约不因跨记录而稀释。

**入口与边界**

9. As an 对话用户, I want to 范围胶囊接真：点「课程」选课开新会话、点「全部资料」直接开新会话, so that 图 1 的范围切换成为真实能力。
10. As an 对话用户, I want to 挂载记录的课程被归档 / 课程被删除后，相关会话只读并明示, so that 材料失效不产生误导回答。
11. As an 跨范围会话用户, I want to 联网搜索开关默认关、开启后仍「材料优先」(so that 挂载语义在课程 / 全部范围不稀释)。

**开发者**

12. As an 开发者, I want to scope 是显式列、`mode` 轴不动（恒 ASK，留给 B3）, so that 范围与交互形态两轴正交。
13. As an 开发者, I want to 记录范围会话（含 >30k 降级、`search_transcript`）行为零变更, so that A1 契约不被回归。
14. As an 开发者, I want to SSE 事件协议零改动（tool 名分流已通用）、api-types 重新生成, so that A2/B1 协议不破。
15. As an 开发者, I want to 零新依赖、一条迁移（0022）, so that 变更面收敛在后端 agent/search 域与前端 chat 域。

## Implementation Decisions

**根决策（2026-09-14 grill 十问定稿，用户全按推荐拍板）**

1. **显式 `scope` 列**（迁移 0022）：`chat_sessions` 加 `scope TEXT NOT NULL DEFAULT 'FREE'` + CHECK 四值；存量行回填（`record_id` 非空 → RECORD，否则 FREE）；`mode` 恒 ASK 不动（与 B3 Tutor 形态轴正交）。数据模型文档 v2.6→v2.7。
2. **范围会话内不可变**：与 record_id 现状一致；「可切换」由「点其它胶囊 = 新建会话流程」承接（D5）。不做范围 PATCH。
3. **课程范围 = 该课程全部未软删记录**（含尚无转写的，靠清单可见、搜不到原文属如实）；ARCHIVED 课程拦截创建（409，与前置护栏家族同语义）；课程事后软删 → `course_deleted` 运行时推导 → 会话只读（对齐 `record_deleted` 先例）。
4. **ALL = 全部未软删记录，含收件箱未归类**（#24），无开关。
5. **上下文 = 记录标题清单**：行格式「标题 + 日期（YYYY-MM-DD）+ 无转写者标注（暂无转写）」，按 updated_at 降序；清单字符预算约 4000（约百条），超出取最近并注明「共 N 条，仅列最近 M 条」。>30k 降级分支仅属 RECORD，COURSE/ALL 天然不存在。
6. **跨记录引用契约**：模型引用行 `[n] 逐字摘录（来源：记录标题）`（标题照抄清单原文）；解析容忍全 / 半角括号与书名号包裹。校验：标题等值定位候选记录 → 逐字命中直接过；重名多候选逐一逐字验证取首过者；无候选 → 全范围逐字扫描取首包含者；逐字不过 → 仅在标题定位的记录内模糊对齐（复用 `_align_quote`）；全范围兜底只做逐字 `in` 扫描、**禁止全范围模糊对齐**（性能红线）。归属由校验器裁定，模型只写标题。落库条目 `{index, source:"record", record_id, record_title, quote}`（title 为创建时快照；历史行无此键 → None，前端降级不显示）。`CHAT_PROMPT_VERSION` bump v5。
7. **`search_library` 工具**：ContextVar 绑 `{scope: COURSE|ALL, course_id}`（每轮生成前绑定，模式同 `search_transcript`）；与 `search_transcript` 互斥挂载——RECORD 会话只挂 `search_transcript`，COURSE/ALL 只挂 `search_library`，FREE 不挂。检索 = 跨记录分片 FTS（去掉 record_id 过滤、按需加 course 过滤、软删过滤照旧、命中带 record_id + record_title + content + time/page），top-8 纯 BM25；FTS 零命中才 LIKE 兜底（整 query 子串、窗 ≤400 字，覆盖无分片记录；个人量级 #24 背书）。
8. **web_search**：COURSE/ALL 视同挂载语义——默认关、可开；开启追加同款「材料优先」指引；前端开关记忆维持按会话、默认值按范围取。
9. **前端三件套接真**：`ChatScopeChips` 交互（点课程 → 选课 Dialog → 建会话；点全部资料 / 自由 → 直接建会话）；`NewChatButton` 菜单增「课程问答 / 全部资料」入口；课程详情 `CourseChatTab` CTA 改为创建该课程范围会话并跳转、示意消息流退场。

**后端契约与实现落点**

- `ChatSessionCreate`：增 `scope: ChatScope`（默认派生：不传时 record_id 非空 → RECORD 否则 FREE，旧调用方零破坏）与 `course_id`；校验矩阵——RECORD 必带 record_id、COURSE 必带 course_id 且课程存活未归档（404 CHAT_COURSE_NOT_FOUND / 409 CHAT_COURSE_ARCHIVED，登记错误码清单）、FREE/ALL 两者必须为空、`knowledge_point_id` 仍限 RECORD。
- `ChatSessionOut`：增 `scope`、`course_deleted`；`course_id` 语义启用（COURSE 会话 = 挂载课程；RECORD 会话维持现状运行时派生）。前端现零消费会话级 course_id，无兼容负担。
- 会话失效：COURSE 会话课程软删后 list/get 标 `course_deleted: true`、accept 拒绝（409），实现同 `record_deleted` 先例。
- `SegmentSearchService.search_scope_segments(session, course_id | None, query, limit)`：两条跨记录 SQL（JOIN records 取 title、deleted_at 过滤照旧、`(:course_id IS NULL OR r.course_id = :course_id)`）。
- `context.py`：`build_context_messages` 增可选 `library` 材料（与 `record` 互斥）——指令 + 引用格式约定 + 清单 + 检索指引；清单注入在语言 / 联网指令之前、预算计量一致。
- `citations.py`：单记录入口零改动；新增跨记录解析（分流：行内含 URL → web 条目照旧；含「（来源：…）」→ 跨记录 record 路径；否则按旧摘录规则在……仅 RECORD 会话，跨范围会话该形态直接走全范围兜底）。
- `message_service` / `stream_chat_reply`：`SessionPromptContext` 增 scope 与库材料；装配矩阵扩为 scope（FREE/RECORD/COURSE|ALL）× web_search；`_cited_excerpts` 对 COURSE/ALL 会话天然返回空（record_id 为 None），零改动。
- SSE：`tool_call/tool_result` 协议零改动；工具卡载荷 `hits` 数量语义不变。

**前端落点**

- 工具卡文案按 tool 名加 `search_library` 一支（「正在检索学习资料」/「命中 n 条 / 失败」，zh/en 双语）。
- 引用列表：record 条目显示 `《record_title》` + 摘录（无 title 的历史行降级为现状展示）；点击照旧 `useOpenCitation` 按 `citation.record_id` 跳转（零改动，天然支持跨记录）。
- 右栏「当前挂载上下文」卡按 scope 展示：课程名 + 记录数 / 全部资料 + 记录数 / 单记录现状；webSearch 开关默认值按 scope（COURSE/ALL 同挂载 = 关）。
- 会话行 / 标题栏补范围标识（课程名 / 全部资料），自由 / 记录现状不变。
- zh.json / en.json 同步；api-types 重新生成。

## Testing Decisions

好测试只断言外部行为，复用现有 seam：

1. **chat streaming seam**（fake model 工具循环）：scope×web_search 装配矩阵的工具可见面；`search_library` 调用与 SSE 事件序列不变式；清单注入断言；RECORD 会话行为与现状逐字一致（回归）。
2. **citations 纯函数 seam**：跨记录解析矩阵——标题唯一定位 / 重名逐一验证 / 无候选全范围兜底 / 模糊对齐仅限标题定位记录 / 兜底与对齐全失败丢弃 / web 行分流照旧 / 正文剥离。
3. **SegmentSearchService seam**：跨记录命中排序、course 过滤、软删（record/transcript）过滤、命中带标题。
4. **会话端点 seam**：创建校验矩阵（缺参 422、课程 404/409、默认派生、FREE/ALL 拒绝携带 id）、course_deleted 只读与 accept 409。
5. **前端 jsdom seam**（现有 chat 测试模式）：胶囊交互建会话（选课 Dialog / 全部资料）、NewChatButton 菜单、工具卡 search_library 文案、引用标题显示与无 title 降级、webSearch 默认值按 scope、zh/en key 一致。

## Out of Scope

- B3 Tutor 模式（mode 轴启用）；B5 sqlite-vec / 语义检索。
- 会话内范围切换（PATCH）；跨会话记忆；检索 / 搜索快照持久化。
- 课程聚合统计接入对话、归档 / 恢复 UI、范围胶囊外的会话批量管理。
- 全局 SearchService（search_index）任何改动。

## Further Notes

- 单票闭环交付（用户定规：功能涉及前后端不拆票，一张工单完成）：01 全栈票（后端契约与工具 → 前端接线 → 文档收尾），commit 按域分次（type(scope) 规范不变）。
- 迁移 0022 落地时同步 grep 全部硬编码 `user_version` 断言（0020 时 11 处，随迁移递增）。
- 文档收尾随票 02：数据模型 v2.7 升版重命名 + 全库交叉引用同步；扩展文档 §40.3 B2 行回写 + §40.4 第 4 步标记；CONTEXT.md 视需要补「会话范围」「跨记录引用」词条；PROJECT_PROGRESS 同步。
