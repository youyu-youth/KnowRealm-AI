# 05 — 共享来源引用

**What to build:** 同一份资料被多个知识空间复用而不改变归属、不重复入库。用户把已属于"机器学习"空间的论文引用到"Agent 工程"空间：被引用资料的内容进入新空间的课程问答与检索（引用行标注共享来源）；但新空间对引用资料只读——不能生成总结 / 知识点 / 习题，资产仍只在原空间。资料软删时引用失效提示、30 天回收站恢复则引用自动复活、永久删除后引用清理；归属迁移不影响引用。

**Blocked by:** None — can start immediately（与 01~04 并行）

**Status:** done（2026-10-01，自动化门禁全绿，剩用户真机验收〔清单见文末〕）

- [x] 迁移落地共享引用表：course_id ＋ library_item_id，(course_id, library_item_id) 唯一、创建时间；条目物理删除时引用级联清理（0037；双 FK ON DELETE CASCADE，测试断言 PRAGMA）
- [x] 失效为查询期派生：条目软删即失效（展示"来源已删除"）、恢复即复活，不设失效状态字段；归属迁移不影响引用（测试断言）
- [x] 领域 Service 与 API：课程嵌套引用端点（列表 / 添加 / 删除）；删除引用不动原资料（library/shared_refs.py + shared_refs_routes.py，HTTP 与 Agent 应用器共用事务内核心）
- [x] 检索覆盖：新空间 COURSE 范围问答与检索纳入被引用资料的 Record 内容，引用行标注共享来源（retrieval 三路 SQL + 概念扩展继承 + message_service 材料 + citations shared 标志 + EvidenceHit.shared_source + 前端徽章）
- [x] 资产只读校验：新空间对引用资料拒绝生成总结 / 知识点 / 习题（新错误码登记 zh / en）；引用不授予改、删、迁移原资料权限（SHARED_REF_ASSET_READ_ONLY，防线在三个生成 Service；前端错误码翻译 + 共享 Tab 常驻只读 Alert 承载语义提示——前端生成入口当前不带空间上下文，409 由后端执法、语义说明由常驻 Alert 承载〔设计取舍：记录详情页无空间视角，不为防线引入伪上下文〕）
- [x] Agent 工具：list_shared_refs（只读）、add_shared_ref / remove_shared_ref（写，确认卡＋授权＋审计）（OP_SHARED_REF_ADD/REMOVE L1 注册 + 前端 CARD_BY_TYPE +2 确认卡可渲染可确认）
- [x] 前端：课程详情页呈现本空间引用清单与增删入口（第 9 个「共享资料」Tab，?tab=shared 入 URL）；课程问答引用行标注"共享来源"；被引用资料失效时展示"来源已删除"提示；新空间对引用资料生成资产被拒的错误提示（Alert 内联）——zh / en 文案同步、api-types 重新生成（errors 四码翻译 + 共享 Tab 常驻只读 Alert；生成被拒的具体 409 转译就绪，触发面留给未来带上下文的调用方〔Agent 写路径接入时〕）
- [x] 测试：引用增删查与失效派生语义、课程问答覆盖范围（引用资料可检索、资产生产被拒）、Agent 工具确认行为（后端 11 新测试 + 前端 4 新用例）
- [x] 门禁全绿：pytest（独立 basetemp）+ ruff + pyright + OpenAPI --check + 前端测试（后端全量 1040 绿〔1 失败为前后端并行资源争抢单跑绿〕；前端全量 634 绿〔6 失败同为并发抖动单跑绿〕；prompt 版本/挂载矩阵/citations dict 断言四处既有测试同步跟进）

参考：[spec.md](../spec.md) 共享来源引用（User Stories 20~25）、共享引用语义段。

## 实施要点（2026-10-01 备案）

- 迁移 0037 `course_shared_refs`；TEXT 主键占 sqlite_autoindex_1、UNIQUE 约束是 _2（测试断言 PRAGMA index_list 的 origin='u'；foreign_key_list 第 7 列才是 on_delete）。
- 失效派生唯一口径 = `shared_alive_item_ids / shared_alive_record_ids`（library/shared_refs.py）：条目 ACTIVE＋未软删。message_service 材料与资产防线复用同一谓词；retrieval.py 因 text SQL 家族另持 `_SHARED_RECORD_IDS_SQL / _SHARED_ITEM_IDS_SQL` 常量（词法同源）。
- 检索覆盖只动 COURSE 档（record 分片 / 条目直挂 / asset 导航三路 + 概念扩展经 `_EXPANSION_COURSE_SQL` 引用同常量自动继承）；shared 标志仅 COURSE 档判定（RECORD/LIBRARY_ITEM/ALL 恒 false）。
- 资产只读：`REQUEST_COURSE_ID`（可选 query「请求方知识空间」）定义在领域模块，summary/knowledge_point/quiz 三路由复用；Service 层执法——记录不属于该空间且经存活共享条目覆盖 → 409 SHARED_REF_ASSET_READ_ONLY；原空间视角与无关上下文放行（不越权拦截，交由生成链自身校验）。
- Agent：一文件两动作（operations/shared_ref.py），L1、快照提交期固化（add 双目标态：确认窗口内归属迁移/改名即 OPERATION_SNAPSHOT_STALE）；undo_reason = 引用增删可直接反向操作。prompt chat-library-scope-v23 / chat-research-scope-v24。
- 前端：features/sharedRefs（candidates 键在 keys.ts）；remove 用 apiFetchNoContent（204 空体）；LibraryItemOut 有必填 availability（测试假数据须带）。
- 双轴 review 修复五项：确认卡 CARD_BY_TYPE 漏注册两类型（默认档不可确认——功能断裂级）、REQUEST_COURSE_ID 从路由文件移领域模块（消路由互导）、资产防线内联 join 收拢回复用谓词、Row 位置索引改具名列、前端手写 queryKey 归位 keys.ts。
- 外部审查修复（10-01）：共享的**无分片纯文本资料**（粘贴形态）在 COURSE 档检索不到正文——正文只在 transcript（FTS 分片路径永不命中），而兜底 `_SCOPE_FALLBACK_SQL` 无 COURSE 键（内存库复现：同关键词 LIBRARY_ITEM 命中、COURSE 空）；修复 = COURSE 键兜底仅覆盖共享记录集（`_SHARED_RECORD_IDS_SQL`，条目存活内联），本课程自己的无分片记录与 ALL 档维持 contract §4 不兜底口径（test_library_retrieval.py:544 注释同步）；测试 = seed_full_corpus 加纯文本条目 + `test_retrieval_shared_segmentless_text_fallback`（命中+shared 标志+隔离+本课程速记不兜底四断言）；后端全量 1041 绿。
- 外部审查修复二（10-01）：remove 提案快照缺引用行身份——旧移除提案可删掉确认窗口内删了重建的新引用（复现 APPLIED，违反 ADR-0026「确认绑定对象版本」）；修复 = `SharedRefRemoveStateSnapshot` 加 `ref_id`（`_require_ref` 返回行 id 入快照），删重建 → 行身份变化 → OPERATION_SNAPSHOT_STALE（提案 FAILED + 422 errorCode，新引用保留）；前端确认卡对 snapshot 宽松取字段零影响、OpenAPI 语义零 diff（--check 报的漂移系仓库 openapi.json 被 Prettier 折行的既有格式差异，改动前后语义比对均相等）；测试 = `test_remove_proposal_stale_after_ref_recreate`（正常确认删除对照 + stale 保留双路径）。
- 外部审查修复三（10-01）：添加引用对话框只取 `listItems({limit:100})` 前端过滤——全库超 100 条时首屏外资料无页面入口、首屏 100 条全属本空间时空态误报「暂无可引用」（组件测试复现：MSW total=120 全本空间 → 误报文案出现）；修复 = 对话框加标题搜索框（250ms 去抖、q 传后端全库命中，对齐资料库页面「q+固定 limit 无分页 UI」既有惯例）+ 空态区分（total 超单页时提示「仅列出最近更新的前 N 条，可搜索」不再误报）；candidates queryKey 加 q 维度；zh/en +2 键（searchPlaceholder/truncated）；测试 = `首屏条目全属本空间时不误报无候选，搜索可命中列表之外的资料`。
- 外部审查修复四（10-01）：共享引用缓存与 Agent 操作、资料生命周期不同步（违反 desktop-state.md「mutation 成功后精确失效相关列表/聚合 key」；staleTime 60s + 不 refetchOnWindowFocus → 旧数据最长 60s）——独立前缀 `["sharedRefs"]` 无人失效：Agent 确认/直执行/撤销重试只失效 proposals/sessionOperations/runs、资料软删/恢复/永久删/归属迁移只失效 libraryKeys.all（组件测试双向复现：独立前缀红、合并绿）。修复 = ① `sharedRefsKeys.all` 挂 `[...libraryKeys.all, "sharedRefs"]`（资料生命周期失效 libraryKeys.all 自动覆盖，泛化到未来 library mutation）；② decide 确认/拒绝按 `SHARED_REF_PROPOSAL_TYPES` 条件失效；③ useChatStream.finally 同 proposals/runs 同口径补失效（流中直执行类型不可知）；④ 两回执卡 undo/retry 补无条件失效（补偿动作类型跨闭包不可知，低频动作代价一次重取）。测试 = `资料软删后共享引用清单同步失效`（harness：同 client 渲染 Tab + useLibraryItemAction）；坑 = 软删契约是 200+LibraryItemOut 非 204（204 仅物理删除路径，apiFetch 需 JSON 体）。
- 外部审查修复五（10-01）：remove 确认卡只显示资料标题、无目标空间——同一资料被多空间引用时无法核对移除哪条关系（add 卡有「引用落点课程」行、remove 缺失不对称；hint 却写「解除本课程的引用」；组件测试复现：卡上无课程名）。修复 = 快照 `SharedRefRemoveStateSnapshot` 加 `course_name`（capture 经 `CourseService.get` 读取，课程不可达 → COURSE_NOT_FOUND 404 零提案——软删课程页面本无入口、Agent 链一致拒绝；顺带获得「确认窗口内课程改名 → stale」与 add 同口径）+ 前端 remove 卡加「移除引用的课程」行（快照回落 payload.course_id）+ zh/en `targetCourse` 键（hint 措辞「本课程」→「该课程」对齐）；测试 = 前端「移除共享引用确认卡展示目标空间与资料」+ 后端 stale 测试正常路径补快照契约断言（course_name）。

## 用户真机验收清单（不代勾）

1. 课程详情出现第 9 个「共享资料」Tab；`?tab=shared` 直达可恢复。
2. 添加引用：对话框只列归属其他空间与未归类的资料（本空间归属与已引用被过滤）；已归属条目经对话让 Agent 引用被拒并如实转述（SHARED_REF_ITEM_OWNED）。
3. 引用后：在本课程问答中检索到被引用资料内容，引用行带「共享来源」标注；原空间引用行无标注。
4. 资料软删（资料库回收站）后：共享 Tab 该行出现「来源已删除」且课程问答检索不再命中；恢复后引用与检索自动恢复。
5. 资料永久删除后：共享 Tab 引用行消失（级联清理）。
6. 对话让 Agent 添加/移除共享引用：默认档出确认卡（课程与资料名预览），确认后生效、拒绝不动；自动档 L1 直执行带回执。
7. 共享 Tab 常驻「共享资料只读」说明；在本课程对共享资料发起生成（总结等）无入口（语义由 Alert 说明），原空间生成不受影响。
8. 归属迁移：把被引用资料移到第三个课程后，本课程引用仍在、检索照常覆盖。
