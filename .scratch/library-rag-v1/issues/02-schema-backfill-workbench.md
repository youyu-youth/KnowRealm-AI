# 02 — Schema、存量回填与基础工作台

**What to build:** 数据库升级到资料库 Schema（四张新表 + 存量结构改造 + 升级前快照保护）；现有录音、音频、文档、粘贴、速记经幂等后台回填，在 `/library` 以统一工作台呈现——默认可浏览、左侧智能视图与领域分类、顶部四分类、筛选进 URL、详情检查器展示来源/派生 Record/处理与 RAG 可用性。回填期间捕获、总结、问答等现有功能零中断。

**Blocked by:** 01 — 契约与评测地基.

**Status:** done（2026-09-19）

- [x] 迁移一次建齐四张新表（`library_items` / `library_item_records` / `agent_proposals` / `learner_preferences`）+ 存量改造：document_segments / source_anchors 预留列 `course_material_id` 统一改名 `library_item_id` 并补 FK、`source_anchors.course_id` 改可空、`chat_sessions.scope` CHECK 扩五档并新增 `library_item_id`、`processing_jobs` 增 library_item_id 关联与 job_type 扩展（WEB_FETCH / LIBRARY_BACKFILL / INDEX_REBUILD）；全库 user_version 断言同步 → `migrations/0026_library_foundation.sql`（DDL 与 contract §1 终稿零漂移；ORM/source_anchor/finalizer 同步改名；断言零同步=C2 动态化结论成立，backend/AGENTS.md 已更新 0026）
- [x] 首次应用新 Schema 前自动创建独立升级前数据库快照；Schema 失败停止启动并保留旧数据 → `data/archive.py ensure_pre_upgrade_snapshot`（VACUUM INTO、每目标版本一份不覆盖、失败抛错终止启动；main.py 于 run_migrations 之前调用）+ 升级路径测试（0025 旧库带数据升级无损）
- [x] `LIBRARY_BACKFILL` 幂等后台 Job：`record_files` 原件复用不复制字节、PASTE / QUICK_NOTE 生成文本型条目、建立 M:N 关联、索引补建；稳定游标、可重试、可恢复、不重跑已成功处理链；回填进度与失败在工作台可见 → `library/backfill.py`（rowid 游标+块短事务+result_json 检查点；一轮零新建=停滞终止防自旋；启动入队+5 个 capture 创建点同事务入队钩子+写回兜底三层保障；索引补建由既有启动幂等回填覆盖，模块注释备案；进度/失败经列表响应 `backfill` 字段进前端横幅）+ 幂等/续跑/e2e 测试
- [x] `/library` 基础工作台：默认可浏览；左侧三组扁平导航（智能视图=全部/最近/收藏/待整理，归档与回收站视图随工单 05 接内容；领域分类=资料来源/学习记录/学习资产；最近 Course + 查看全部仅作筛选器）；顶部四分类（全部/资料来源/学习记录/学习资产）+ 二级筛选（来源类型/资产类型/Course/处理可用性/归档状态/时间）；筛选与视图进 URL search params；列表/网格两态；整页不纵向滚动、列表与检查器各自滚动 → LibraryPage.tsx 重构（URL 契约 domain/view/layout/sourceType/availability/courseId/q/sel/selType；可用性 chips+Course 左导航+网格含三域卡片）；**遗留**：资产类型与时间排序筛选待 05/07（当前资产域仅知识点一种类型、排序固定 updated_at desc，控件无语义）、归档状态随 05
- [x] 详情检查器按对象动态展示：资料条目（安全预览/来源元数据/处理与 RAG 可用性/派生 Record 跳转）、Record（来源与学习资产）、学习资产（所属 Record 与 Source Anchor）；技术状态从 processing_jobs / Segment 事实派生 → 三对象检查器 + 四态可用性派生（PROCESSING/RETRIEVABLE/FAILED/EMPTY，解析链任务类型限定）；**遗留**：Record 检查器的资产明细与资产 Source Anchor 展示待 05/06（资产明细在记录页已全量存在，02 给回链+跳转；KP.source_anchor_id P1 恒 NULL 无数据可展示）
- [x] 列表内搜索命中标题、来源与元数据（导航级查询，不是 RAG）→ 三列 LIKE（contract 02 实施记录备案实现口径）
- [x] 收藏与待整理智能视图接真（待整理=未归类/未命名规范资料）→ favorite 列+PATCH 端点+收藏视图；待整理=未归类（V1 口径；「未命名规范」检测无可靠信号，随 05 整理提案增强）
- [x] agent_proposals 通用提案框架落地：确认/拒绝端点 + 按 proposal_type 路由到应用器的框架与错误码（本票无任何提案生成方，生成方随 05/06）→ `library/proposals.py`（应用器注册表、apply 失败=主事务回滚+独立小事务落 FAILED 诊断+422；clear/restore_appliers 测试隔离助手）+ `/api/proposals` 三端点 + 错误码 PROPOSAL_NOT_FOUND/ALREADY_DECIDED/APPLY_FAILED zh/en
- [x] 迁移与回填幂等测试（重复执行状态不变）；回填期间与新写路径零回归；工作台前端 MSW 测试（URL 状态恢复、检查器动态展示）；zh/en 文案同步 → 后端 9 测试（升级路径/快照/幂等/游标续跑/可用性/端点契约/e2e 粘贴入队/提案框架 service+路由）+ 全量 611 绿；前端 6 测试（默认浏览/URL 恢复/待整理/检查器动态/收藏 PATCH/回填横幅）+ 全量 471/472（唯一失败=TodoPanel 已知并发抖动单跑 8/8 绿）；i18n 防线 3/3

## 备注

- 四张表集中在一次迁移（含 06 用的 learner_preferences 与 agent_proposals）：迁移编号由 01 冻结、避免多票各自建表撞 user_version 与断言同步。
- 真机验收统一收敛在工单 07 的清单，本票不单列。
- **实施补充**：联邦视图按 contract §2.2 预留口新增两枚只读端点 `GET /api/library/records`（含 library_item_ids 回链）与 `GET /api/library/assets`（02=已确认知识点，含 detail）；`PATCH` 02 仅 favorite（重命名/归类/归档/删除随 05）；ingest 归 03（02 新写路径=capture 同事务入队钩子）。
- **评审修复**（双轴 code-review）：断 capture↔library 模块环（backfill 文件行改原生 SQL）、escape_like 公共化至 search/tokenizer、可用性过滤 total 口径、linked_records 计数语义、块预算耗尽不再假 SUCCEEDED（记可重试 FAILED）、ProposalType 未知值防御、网格视图补资产域、回填失败横幅、左导航领域分类去「全部」+补「查看全部」、可用性筛选 chips、endpoints 测试 worker 竞态修复（seed 前等回填终局，三连绿）。
- **测试口径调整**：5 个既有套件的「零业务行」断言排除系统级 LIBRARY_BACKFILL 任务行（意图=无捕获业务残留，系统任务不属该口径）；模拟注册失败的触发器限定捕获链任务类型。
