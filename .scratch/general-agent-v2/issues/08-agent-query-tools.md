# 08 — 对象查询工具族扩展（插队票）

**What to build:** 补齐批量整理链路的目标枚举前置缺口：①`search_courses` 扩展——query 改可选，省略=枚举全部课程（更新时间降序）；②新只读工具 `list_course_records`——按 course_id 列课程全部记录；③新只读工具 `list_library_items`——按 source_type / course_id / q 可选过滤列资料条目。三工具统一 limit 形态：数量由用户话术决定（要全部给全部、要 N 给 N），省略=返回全部受硬上限 100 保护，超限 total+truncated 如实透出不静默丢弃。全部只读 L0、零提案零授权零快照、恒挂载全部会话类型、计入统一每轮 6 次预算与字符累计；前端零改动。底层复用既有查询（`CourseService.list(q=None)` / `RecordService.list_for_course` / `LibraryService.list_items`），零新 SQL 零迁移。

**实施约束:** 决策见 [grill](../grill.md) 插队票 Q23～Q32（2026-09-28 定稿）；spec 决策 14（每对象族一个类型化只读工具，禁万能 query）与决策 16（共享预算）延续；关键词消歧分支上限 8 与行为不变；availability 过滤不进 V1；两新工具不进操作注册表（只读，无 operation 事实）。

**Blocked by:** 工作区工单 05 阈值口径修复先行提交（在途未提交改动：runs/plans.py、runs/service.py、tests/test_agent_batch_run.py；工作区纪律非代码依赖）。

**Status:** done（2026-09-28 实施完结；实施记录见文末）

- [x] `search_courses` 扩展：query 可选（省略=枚举全部，limit 统一形态）；docstring 更新（枚举语义 + 关键词消歧语义分流）；既有「空查询拒绝」行为测试改写
- [x] `list_course_records` 新工具：course_id 必填 + limit 可选；复用 `RecordService.list_for_course`；返回 id/标题/来源类型/总结状态/创建时间；课程不存在=结构化「未找到」指引回 search_courses（禁猜 id 纪律）
- [x] `list_library_items` 新工具：source_type（AUDIO/DOCUMENT/WEB/BOOK/TEXT）/course_id/q 三维可选 + limit 可选；复用 `LibraryService.list_items`；返回 id/标题/source_type/归属课程名/更新时间/total
- [x] limit 统一形态：省略=全部（硬上限 100）、指定照传（同受硬上限）、超限 total+truncated+模型如实转述指引；calls_used 上限执法与 chars_fed 累计（search_courses 先例）；工具异常 ok=false 不炸整轮流
- [x] 挂载：`_resolve_agent_config` 恒挂载段追加两新工具（全部会话类型）
- [x] prompt bump：普通/研究会话各 +1（枚举工具使用指引：先列后改、按用户话术传 limit）
- [x] GLOSSARY.md「对象查询工具族」词条扩充（枚举语义与 limit 形态）
- [x] 测试：三工具行为用例（枚举/过滤/limit/硬上限/课程不存在/预算执法），并入既有 agent 工具测试族
- [x] 门禁：后端 pytest / ruff / pyright、OpenAPI --check（无新端点应零 diff）；前端零改动无门禁要求

**实施记录（2026-09-28）：**

- 共享形态落 `agent/tools/listing.py`：`LIST_HARD_LIMIT=100`、`resolve_list_limit`（省略=上限/照传/非正数拒绝）、`truncated_notice`（三工具逐字一致）、`invalid_limit_message`、`dump_payload`（统一 JSON 载荷，键名参数化）。
- search_courses 双分支：枚举分支带 total；关键词消歧分支固定上限 8 行为不变（limit 不生效，docstring 已注明）；空白 query 视同省略=枚举（原「空查询拒绝」用例改写为枚举断言）。
- list_course_records：`RecordService.list_for_course` 返回 None=课程不存在→结构化未找到+指引回 search_courses；记录状态字段=Record.status（RecordStatus 枚举原值）。
- list_library_items：默认视图语义（排除 ARCHIVED 与软删）随 `LibraryService.list_items` 继承；q 实际匹配标题/来源链接/元数据（docstring 如实描述，宽于 grill「标题搜索」表述属复用继承）；非法 source_type/UUID/limit 均结构化拒绝。
- prompt：`CHAT_ENUMERATION_GUIDANCE`（先列后改 + limit 跟随话术）注入 `build_context_messages` 与批量指引同段；版本 `chat-library-scope-v16` / `chat-research-scope-v17`；4 处逐字断言测试同步。
- 双轴 code-review 通过（Spec 无缺失无越界；Standards 4 条判断性提示已修：`_payload` 三胞胎收敛进 listing.py、错误文案引用常量防漂移、`shown_limit` 命名统一、关键词分支死赋值消除；另修 2 处 docstring 措辞失真）。
- 门禁：后端 pytest 全量 899 绿 + ruff + pyright 0 错 + OpenAPI --check 零 diff；前端零改动。

**用户真机验收（单列，不代勾）：**

- 对话实测三类话术：「我有哪些课程」「列出课程 X 的所有记录（要求指定条数变体）」「资料库里有哪些网页剪藏 / 全部资料」。
- 记录数超硬上限的课程（如有）→ 模型如实转述「共 N 条已列前 100」。
