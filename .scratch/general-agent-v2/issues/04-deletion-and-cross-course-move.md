# 04 — 删除与跨课迁移

**What to build:** 接入 L3 删除动作（Record 软删、课程软删）与 L2 跨课迁移：删除类确认卡完整呈现级联影响（课程删除＝当前记录清单与计数）；批准后执行前影响扩大（新增记录）则旧批准失效；课程删除的掌握度重算编排从 HTTP 路由收拢为领域应用函数（HTTP 与 Agent 共用）；跨课迁移作为新领域服务落地——记录内容与记录级资产随记录移动，原课程概念 / 历史作答 / 学习证据保留历史归属。用户可演示：「把这 3 条记录移到课程 B」→ 确认卡列出 3 条记录 → 确认后记录出现在课程 B、原课程历史测试仍可回看。

**实施约束:** 实施决策见 [spec](../spec.md) 决策 14~15、17~18（迁移不触碰清单＝quiz 存量绑定 / quiz_test_items / learning_events / learning_evidence / record_concepts；习题主概念同课程校验只管新绑定；活动处理 job 进行中拒绝迁移）。

**Blocked by:** 03 修改与归档动作（复用快照机制）。

**Status:** ready-for-agent

- [ ] record.soft_delete（L3）：复用既有记录删除领域语义；确认卡影响预览（记录级资产计数）；快照固化影响清单
- [ ] course.soft_delete（L3）：编排收拢为 course 域应用函数（级联软删记录＋取消非终态任务＋录音会话脱钩＋掌握度重算＋consumer 重试一体），HTTP 路由与 Agent 应用器共用；既有课程删除路由测试零改动通过＝收拢验收锚点
- [ ] 删除影响清单快照与执行前重验：批准后新增记录等实质差异 → 稳定错误码失效、重新预览授权（Q8 场景断言测试）
- [ ] updated_at 纪律防线：记录软删 / 课程软删 / 跨课迁移写路径在既有测试中断言 updated_at 变化（spec 决策 12，同票 03）
- [ ] move_cross_course 领域服务（HTTP 与 Agent 共用、事务内）：修改 record.course_id＋重建搜索索引＋目标课程存在且 ACTIVE 校验；该记录存在非终态处理 job → 稳定错误码拒绝（等待处理完成）
- [ ] record.move_course 动作（L2）注册＋薄工具；快照存原 course_id（06 票 Undo 用）
- [ ] 迁移语义断言：知识点 / 总结 / Todo / 复习资产随记录可见于目标课程；quiz 存量 concept_id、quiz_test_items、learning_events / learning_evidence、record_concepts 行零触碰（表行断言）；旧课程历史测试仍可回看
- [ ] 习题主概念「同课程 CONFIRMED」校验只管新绑定、不回溯存量（迁移后目标课程新绑定走新课程概念断言）
- [ ] 删除 / 迁移在帮我批准档的 L3 逐项确认与完全访问档直执行（依赖 02 分流，注册表零改动验证）
- [ ] 新增错误码登记＋zh/en 双语同步；api-types regenerate
- [ ] 门禁全套过（后端 pytest / ruff / pyright、前端 vitest / lint / build、OpenAPI --check）

**用户真机验收（单列，不代勾）：**

- 真实数据迁移一条已总结记录到另一课程：目标课程可见记录与资产、原课程掌握度与历史作答保留、全局搜索能搜到迁移后记录。
- 批准删除课程后、执行前向该课程新增一条记录 → 确认失败并要求重新预览。
- 有总结任务进行中的记录迁移被拒并提示等待完成。
