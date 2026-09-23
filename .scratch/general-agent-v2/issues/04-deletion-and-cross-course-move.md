# 04 — 删除与跨课迁移

**What to build:** 接入 L3 删除动作（Record 软删、课程软删）与 L2 跨课迁移：删除类确认卡完整呈现级联影响（课程删除＝当前记录清单与计数）；批准后执行前影响扩大（新增记录）则旧批准失效；课程删除的掌握度重算编排从 HTTP 路由收拢为领域应用函数（HTTP 与 Agent 共用）；跨课迁移作为新领域服务落地——记录内容与记录级资产随记录移动，原课程概念 / 历史作答 / 学习证据保留历史归属。用户可演示：「把这 3 条记录移到课程 B」→ 确认卡列出 3 条记录 → 确认后记录出现在课程 B、原课程历史测试仍可回看。

**实施约束:** 实施决策见 [spec](../spec.md) 决策 14~15、17~18（迁移不触碰清单＝quiz 存量绑定 / quiz_test_items / learning_events / learning_evidence / record_concepts；习题主概念同课程校验只管新绑定；活动处理 job 进行中拒绝迁移）。

**Blocked by:** 03 修改与归档动作（复用快照机制）。

**Status:** done

- [x] record.soft_delete（L3）：复用既有记录删除领域语义（RecordService.soft_delete_core 事务内核心收拢，与 HTTP 路由共用）；确认卡影响预览（记录级资产计数：知识点/习题/Todo/复习资料/有无总结）；快照固化影响清单（资产计数进 RecordDeleteSnapshot，预览后资产新增＝实质差异失效）
- [x] course.soft_delete（L3）：编排收拢为 course 域应用函数 CourseService.apply_soft_delete（级联软删记录＋取消非终态任务＋录音会话脱钩＋掌握度重算＋consumer 重试一体，spec 决策 15），HTTP 路由与 Agent 应用器共用；既有课程删除路由测试零改动通过（test_courses 删除链路 + test_mastery 软删即重算断言均零改动绿）
- [x] 删除影响清单快照与执行前重验：课程删除快照固化记录清单（id+标题，id 排序稳定序列化）与计数；批准后新增记录等实质差异 → OPERATION_SNAPSHOT_STALE 失效、重新预览授权（Q8 场景断言测试 test_delete_course_stale_when_record_added_after_approval：新记录不被悄悄纳入删除）；记录删除同款（资产新增失效）
- [x] updated_at 纪律防线：记录软删 / 课程软删 / 跨课迁移写路径断言 updated_at 严格前进（seed 钉死过去固定时刻，test_agent_delete_and_move 各确认应用用例）
- [x] move_cross_course 领域服务（HTTP 与 Agent 共用、事务内，record/move.py）：修改 record.course_id＋重建搜索索引（同事务幂等）＋目标课程存在且 ACTIVE 校验（classification 口径）；该记录存在非终态处理 job → RECORD_MOVE_JOB_IN_PROGRESS 稳定错误码拒绝（等待处理完成）
- [x] record.move_course 动作（L2）注册＋薄工具；快照存原 course_id（RecordStateSnapshot，06 票 Undo 反向迁移补偿数据）
- [x] 迁移语义断言：知识点 / 总结 / Todo / 复习资产随记录可见于目标课程（挂 record_id 天然随走＋行级零变化断言）；quiz 存量 concept_id、quiz_test_items、learning_events / learning_evidence、record_concepts、quiz_tests 行零触碰（表行断言 test_move_record_preserves_history_attribution）；旧课程历史测试仍可回看（quiz_tests.course_id 固化）
- [x] 习题主概念「同课程 CONFIRMED」校验只管新绑定、不回溯存量（迁移后目标课程概念绑定成功 / 原课程概念 QUIZ_CONCEPT_INVALID 拒绝，经 QuizService.set_concept 公开方法断言）
- [x] 删除 / 迁移在帮我批准档的 L3 逐项确认与完全访问档直执行（依赖 02 分流，注册表零改动验证 test_delete_and_move_auth_mode_dispatch：AUTO_APPROVE 下 L3/L2 均落提案、FULL_ACCESS 直执行带授权依据与快照）
- [x] 新增错误码登记（RECORD_ALREADY_IN_COURSE / RECORD_MOVE_JOB_IN_PROGRESS 进 docs/后端错误码清单.md）＋zh/en 双语同步；api-types regenerate（ProposalType +3）
- [x] 门禁全套过（后端 pytest 全量 839 绿〔AST 防线随收拢形态适配：Course 域内聚接线免检/Record 域调用方接线检测/实现层豁免〕 / ruff / pyright 0 错、前端 tsc / lint / build / vitest〔全量 9 失败均为既有并发抖动、单跑逐文件核实绿〕、OpenAPI --check exit 0）

**实施备注：**

- 掌握度重算挂钩 `MasteryService.schedule_recompute_after_commit`（after_commit 事件＋闭包 once 标志）：重算须读已提交状态（删除事务持写锁时并发新会话读旧态/撞 SQLITE_BUSY），回滚不触发；返回任务容器供 HTTP 路径同步等待（既有「软删即重算」语义保持、test_mastery 零改动通过），Agent 确认路径忽略容器后台执行（重算会话由 session.bind 派生同引擎池；失败落 stale 哨兵交启动恢复闭环，HTTP 路径另有 consumer ≤30s 自愈）。
- 类体内 `list[...]` 注解陷阱：`CourseService.list` 静态方法遮蔽内置 list，返回注解整体引号化 `"tuple[int, list[asyncio.Task[None]]]"`。
- 迁移不重算掌握度：learning_events/evidence 的 course_id 写入时固化＝历史归属，迁移不产生有效证据变化（spec 决策 18 天然成立）；record_concepts 读取期按记录所属课程过滤（course_brain 既有口径）零改动。

**用户真机验收（单列，不代勾）：**

- 真实数据迁移一条已总结记录到另一课程：目标课程可见记录与资产、原课程掌握度与历史作答保留、全局搜索能搜到迁移后记录。
- 批准删除课程后、执行前向该课程新增一条记录 → 确认失败并要求重新预览。
- 有总结任务进行中的记录迁移被拒并提示等待完成。
