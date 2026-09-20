# 05 — 生命周期、AI 整理与提案闭环

**What to build:** 资料的完整生命周期治理（重命名、归类、归档/恢复、软删回收站 30 天、删除前展示关联、重新抓取=新条目、Course 移动不级联、失败重试、索引重建）；「AI 整理」先做确定性重复与处理异常检查，再给出结构化标题与 Course 归类建议供逐项确认；研究会话可对 web_search 候选来源提出「建议保存」提案，确认后经业务入库；全部提案经 `agent_proposals` 持久化、跨重启不丢失、确认前零事实变更；数据目录导出/恢复包含资料。

**Blocked by:** 03 — 统一入库与网页剪藏闭环; 04 — RAG Agent 闭环.

**Status:** done（2026-09-19 实施完毕，剩用户真机验收）

- [x] 生命周期动作全套 API + UI：重命名、归类/取消归类、归档/恢复（退出默认浏览与来源召回，`include_archived=false` 统一过滤）、软删（不级联 Record）、删除前展示派生 Record、失败重试、重建索引 — 契约 §2.3 八端点全落地：`PATCH`（title/course_id/favorite 三字段，model_fields_set 判别缺省与显式 null）、`/archive`·`/unarchive`（409 ALREADY_*）、`DELETE`（软删）/`?permanent=true`（204）、`/restore`、`/retry`、`/refetch`、`/rebuild-index`；检索侧归档/软删过滤 04 已落（本票零改动）；UI=检查器生命周期操作区 + EditItemDialog（重命名/归类）+ DeleteItemDialog（派生 Record 展示与不级联明示）
- [x] 资料条目回收站智能视图：仅含软删资料、30 天内恢复（校验 content_hash、索引缺失幂等重建）、UI 明示不含 Record/学习资产；归档智能视图接内容；物理清理仅在保留期届满且无活动引用时执行 — 左导航六视图（+归档/回收站）；默认视图排除 ARCHIVED、archived 视图独占、trash 视图仅软删行（行内显示删除时间、隐藏收藏）；trash 横幅明示不含 Record/学习资产；restore=快照哈希校验（WEB 用 metadata.content_hash、单文件 DOCUMENT 用列哈希，聚合/TEXT 无锚跳过）+ search_index/segment_search_index 同事务幂等重建；启动期 `purge_expired_trash`（30 天届满 + 无未软删派生 Record 才物理删，失败仅记日志同容错级）
- [x] 重新抓取/重新导入：同 URL/路径内容变化创建新条目，不覆盖旧快照、不建版本表；Course 移动重新计算可见范围、派生 Record 不静默跨 Course 移动 — refetch=ingest_web 强制 allow_duplicate（旧条目原样保留，UI 提示「将创建新条目」）；归类只改 library_items.course_id（检索层按 li.course_id 查询期重算），Record.course_id 不动（端点测试断言）
- [x] AI 整理闭环：确定性重复项与处理异常检测（不耗 LLM）+ LLM 结构化标题与 Course 归类建议（ORGANIZE 提案）+ 逐项确认应用；拒绝不改事实；标签建议不在本票 — `POST /organize/scan`（重复哈希组/失败条目/未归类计数，零 LLM）+ `/organize/propose`（OpenAiCompatibleOrganizeModel 结构化输出→逐条 ORGANIZE 提案；幻觉 course_id 降级为仅标题、幻觉 item_id 跳过；输入为全部 ACTIVE 条目非仅未归类——标题规范建议对已归类条目同样成立）；应用器=标题+归类原子应用；OrganizeDialog=确定性结果展示 + 生成按钮 + 待审提案逐项确认/拒绝
- [x] 研究入库提案（RESEARCH_INGEST）：研究会话 web_search 候选 →「建议保存」提案卡（来源/标题/目标 Course 逐项确认）→ 业务 ingest 创建资料条目与处理任务；搜索摘要不成为资料事实、未成功抓取前不进 RAG、不生成锚点 — chat web 引用卡「保存为资料」→ `POST /api/proposals`（就地确认卡）→ 应用器复用 `create_web_ingest_rows`（ingest_web 抽出的事务内核心）：条目+Record+WEB_FETCH 任务同事务落库、payload.title 作初始展示标题（抓取成功后页面真标题覆盖）、正文只来自真实抓取、分片/锚点由 web_fetch_worker 成功写回才产生
- [x] 提案持久化闭环：PENDING/APPLIED/REJECTED/FAILED 状态流转、payload 按 proposal_type 判别校验（禁任意 SQL/路径/Shell）、确认后领域 Service 原子应用、失败留稳定错误码可重试；跨重启待审提案不丢失（不依赖 Graph 悬挂） — 通用创建端点 `POST /api/proposals`（ORGANIZE/RESEARCH_INGEST 载荷 schema 判别校验，落库前经 model_dump 清洗——未知键不持久化）；**confirm 扩为接受 FAILED 重试**（APPLIED/REJECTED 仍终局 409），`_mark_failed` 同步接受 FAILED（错误码可更新）；应用器注册=organize.py 模块导入即注册；零 Graph 依赖
- [x] 全量导出 → 空库恢复：资料条目、快照、关联、引用仍可用；派生索引可重建不作为不可替代内容 — 导出天然含资料（VACUUM INTO 全库 + files/**）；测试 seed 条目+链接+快照文件→export→restore 空目录→条目/关联/快照/origin_uri 全部可读
- [x] 自动化用例：提案未确认零事实变更、资料软删/归档零级联误删 Record 与学习资产、回收站恢复后可检索性恢复；zh/en 文案同步 — tests/test_library_lifecycle.py 10 例：端点契约（重命名/归类含 Record 不级联断言/归档 409 语义/视图切换/软删零级联/restore 409 与成功/permanent 409 防线）、保留期清理（存活 Record 拦截/届满清理/Record 不动）、重试+refetch+非 WEB 422、索引重建 worker（删索引行→process_one→行回来+SUCCEEDED）、整理扫描/提案确认拒绝/应用失败落 FAILED、研究入库全链路（坏 payload 422/未确认零变更/确认建条目零分片/重复 URL FAILED+稳定码可重试语义）、恢复哈希校验+索引重建、导出恢复；前端 LibraryPage 15 例（+归档动作/删除确认/回收站恢复+彻底删除/AI 整理扫描与确认）+ chat 建议保存卡 1 例；错误码 9 枚与 UI 文案 zh/en 同步、防线通过

## 备注

- 提案通用框架（确认/拒绝端点+应用器路由）已随 02 落地，本票补 ORGANIZE / RESEARCH_INGEST 生成方与应用器。
- **实施级决策备案**：①`confirm` 接受 FAILED 再确认（工单「失败留稳定错误码可重试」的直接实现，contract §2.4 的「已决 409」语义收窄为 APPLIED/REJECTED 终局）；②物理删除 `?permanent=true` 不要求先进回收站（409 防线相同，UI 仅从回收站暴露）；③purge 不直接删快照文件——files/ 生命周期归 Record 清理周期与孤儿清理（Record 软删/消亡时文件最终被既有周期收走，避免误删 RecordFile 引用的文件）；④refetch 恒建新条目（03 定案「判重锚=URL 哈希」的自然结果；「内容变化才建新条目」需先抓取比对，与「不覆盖旧快照」冲突，从简恒新条目交用户取舍）；⑤OrganizeDialog 待审区列出全部 PENDING 提案（含 RESEARCH_INGEST）——跨重启可见性的补偿入口。
- 双轴 review（Standards+Spec）修复已落地：路由 LLM 编排下沉 `OrganizeService.propose_with_llm`（fastapi.md §1）、LLM 输出字段补 description（data-layer.md §2）、前端手写类型改 api-types 导入 + queryKey 进 libraryKeys 工厂（desktop-react/state §2）、`ProposalStatus` 枚举替换裸串+ignore、`_PARSE_JOB_TYPES`/`_linked_record_ids` 公开消重（lifecycle 复用 service）、payload 落库前判别清洗（未知键不持久化）、RESEARCH_INGEST title 确认后被消费（初始展示标题）、organize 输入扩为全部 ACTIVE 条目（标题建议不限于未归类）、DeleteItemDialog 死参数删除、window.alert 改内联提示、扫描失败不再静默。
- 备案不修：ACTIVE/ARCHIVED 裸串（02 起既有先例）、DELETE 204 与 response_model 的 type:ignore（契约冻结单端点双语义）、ChatCitationList 手写 promise 链（组件级状态简洁，引 useMutation 无净收益）、`["__none__"]` SQL 占位（既有先例）。

## 用户真机验收清单（不代勾）

> 启动：`pnpm --filter @knowrealm/desktop tauri dev`（壳自动拉 sidecar）。

- [x] 生命周期：选中条目 →「重命名 / 归类」改名与换课生效、取消归类回到未归类；「归档」后默认列表消失、「归档」视图可见、「取消归档」回到默认
- [x] 删除确认：删除对话框列出派生记录并明示不会级联；软删后条目进「回收站」视图（显示删除时间），派生记录在学习记录域不受影响
- [x] 回收站：横幅说明不含 Record/学习资产；「恢复」回到默认视图；「彻底删除」经二次确认后条目消失（有存活派生记录时被 409 拦截并提示）
- [x] 失败重试与重抓：失败 WEB 条目「重试」回到解析中；「重新抓取」提示创建新条目、旧快照保留
- [x] 重建索引：点击后无感成功（列表可用性不变）；重启应用后失败态保持稳定
- [x] AI 整理：顶部入口打开 → 确定性检查（重复/失败/未归类计数）；配置 LLM 后「生成 AI 建议」产出提案，逐条「应用/拒绝」生效且拒绝无副作用
- [x] 建议保存：开启联网搜索的会话中，web 引用卡「保存为资料」→ 就地确认 → 资料库出现新条目并进入「解析中」
- [x] 提案跨重启：留一条待审提案重启应用，/library「AI 整理」中仍可见并可处理
- [x] 回归：既有入库/判重/收藏/AI 解读不受影响；全量导出→空库恢复后资料条目、来源 URL 与快照预览可用
