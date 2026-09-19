# 02 — Schema、存量回填与基础工作台

**What to build:** 数据库升级到资料库 Schema（四张新表 + 存量结构改造 + 升级前快照保护）；现有录音、音频、文档、粘贴、速记经幂等后台回填，在 `/library` 以统一工作台呈现——默认可浏览、左侧智能视图与领域分类、顶部四分类、筛选进 URL、详情检查器展示来源/派生 Record/处理与 RAG 可用性。回填期间捕获、总结、问答等现有功能零中断。

**Blocked by:** 01 — 契约与评测地基.

**Status:** ready-for-agent

- [ ] 迁移一次建齐四张新表（`library_items` / `library_item_records` / `agent_proposals` / `learner_preferences`）+ 存量改造：document_segments / source_anchors 预留列 `course_material_id` 统一改名 `library_item_id` 并补 FK、`source_anchors.course_id` 改可空、`chat_sessions.scope` CHECK 扩五档并新增 `library_item_id`、`processing_jobs` 增 library_item_id 关联与 job_type 扩展（WEB_FETCH / LIBRARY_BACKFILL / INDEX_REBUILD）；全库 user_version 断言同步
- [ ] 首次应用新 Schema 前自动创建独立升级前数据库快照；Schema 失败停止启动并保留旧数据
- [ ] `LIBRARY_BACKFILL` 幂等后台 Job：`record_files` 原件复用不复制字节、PASTE / QUICK_NOTE 生成文本型条目、建立 M:N 关联、索引补建；稳定游标、可重试、可恢复、不重跑已成功处理链；回填进度与失败在工作台可见
- [ ] `/library` 基础工作台：默认可浏览（无关键词也有内容）；左侧三组扁平导航（智能视图=全部/最近/收藏/待整理，归档与回收站视图随工单 05 接内容；领域分类=资料来源/学习记录/学习资产；最近 Course + 查看全部仅作筛选器）；顶部四分类（全部/资料来源/学习记录/学习资产）+ 二级筛选（来源类型/资产类型/Course/处理可用性/归档状态/时间）；筛选与视图进 URL search params；列表/网格两态；整页不纵向滚动、列表与检查器各自滚动
- [ ] 详情检查器按对象动态展示：资料条目（安全预览/来源元数据/处理与 RAG 可用性/派生 Record 跳转）、Record（来源与学习资产）、学习资产（所属 Record 与 Source Anchor）；技术状态从 processing_jobs / Segment 事实派生
- [ ] 列表内搜索命中标题、来源与元数据（导航级查询，不是 RAG）
- [ ] 收藏与待整理智能视图接真（待整理=未归类/未命名规范资料）
- [ ] agent_proposals 通用提案框架落地：确认/拒绝端点 + 按 proposal_type 路由到应用器的框架与错误码（本票无任何提案生成方，生成方随 05/06）
- [ ] 迁移与回填幂等测试（重复执行状态不变）；回填期间与新写路径零回归；工作台前端 MSW 测试（URL 状态恢复、检查器动态展示）；zh/en 文案同步

## 备注

- 四张表集中在一次迁移（含 06 用的 learner_preferences 与 agent_proposals）：迁移编号由 01 冻结、避免多票各自建表撞 user_version 与断言同步。
- 真机验收统一收敛在工单 07 的清单，本票不单列。
