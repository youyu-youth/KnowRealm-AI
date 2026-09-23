# 03 — 单对象修改与归档动作（执行前快照机制）

**What to build:** 落地「执行前快照」机制并接入首批 L1 修改与归档动作：课程修改、课程归档 / 恢复（归档写路径首次落地，历史推迟决策收口）、资料条目重命名 / 归类 / 归档 / 恢复。每个动作确认卡展示 before/after 预览（读快照）；确认前用户手动改过同一对象则旧提案失效（稳定错误码），不覆盖新修改；快照同时作为 06 票 Undo 的补偿数据。用户可演示：「把课程 X 改名为 Y」→ 确认卡 before/after → 确认生效 → 回执可跳转；预览后自己在页面改了名 → 确认失败并提示重新确认。

**实施约束:** 实施决策见 [spec](../spec.md) 决策 12、14、16（快照由后端在提交时同事务读取固化，模型不提供；不给业务表加 version 列；updated_at 微秒精度＋before 值＋级联清单即版本依据；ORGANIZE 类型不迁注册表、只补纪律）。

**Blocked by:** 01 执行事实地基与操作历史。

**Status:** done

- [x] 注册项快照声明扩展：OperationSpec 新增 capture_state（快照读取器）与 target_resolver（目标定位）可选声明；提交时 submit_operation 同事务固化 snapshot_json 进提案行（迁移 0032：agent_proposals 加 snapshot_json 可空列；目标读取与提案创建原子、目标不存在结构化拒绝零提案）；快照形状按动作 pydantic 模型声明（CourseStateSnapshot / LibraryItemStateSnapshot，extra=forbid 判别校验）
- [x] 执行前重验：注册表适配器（scoped_applier）统一重读当前态与固化快照逐字段比对（updated_at＋before 值双保险），不匹配或快照缺失 → OPERATION_SNAPSHOT_STALE 稳定错误码失效（旧批准作废、提案 FAILED 可重试、业务零覆盖）；直执行同事务固化快照进 operation（无预览等待期、重验天然成立），快照随 operation 行落库供 Undo 补偿
- [x] updated_at 纪律防线：课程修改 / 归档 / 恢复与条目重命名 / 归类 / 归档 / 恢复全部写路径在既有测试中断言 updated_at 严格前进（test_library_lifecycle 各写操作后 > 前值、test_courses 归档端点逐级前进；Agent 动作测试 seed 钉死过去时刻同款断言）
- [x] course.update（L1）：CourseService.update_core 事务内核心收拢（HTTP 路由与 Agent 应用器共用，场景 / 阶段或深度条件校验同源）；工具面已滤 None（模型无法传显式 null），应用器按「值非 None＝要修改」过滤与 exclude_unset 语义闭环
- [x] course.archive / course.restore（L1）：CourseService.set_status_core 新归档写路径（幂等守卫 COURSE_ALREADY_ARCHIVED / COURSE_ALREADY_ACTIVE）＋HTTP 端点 POST /api/courses/{id}/archive、/unarchive（library 先例）；既有 ARCHIVED 读取护栏三道闸门零改动；spaces 信息面板补手动归档（二次确认对话框）/ 恢复（直接执行 + toast）入口
- [x] library_item.update（L1，标题 / 归类；收藏与取消归类不接入）＋library_item.archive / restore（L1）：LibraryLifecycleService.patch_core / set_archived_core 事务内核心收拢（HTTP 路由与 Agent 应用器共用同一校验链）
- [x] ORGANIZE 应用器补纪律：propose 同事务固化 OrganizeSnapshot（updated_at＋before title/course_id）；apply_organize 执行前重验（有快照才重验、旧提案无快照沿用现行路径不重验）＋before/after 进结果投影；类型不迁注册表
- [x] before/after 确认卡泛化：CARD_BY_TYPE 配置表加六类型行（PreviewFields 读 proposal.snapshot 呈现旧值删除线→新值，归档 / 恢复类呈现目标＋影响提示行）；回执卡呈现修改结果＋课程 / 条目入口跳转；AgentProposalOut 契约新增 snapshot 字段透出
- [x] 默认档落提案（现状链路，请求批准档行为零变化测试钉住）；02 已上线时自动档按 level 继承直执行（AUTO_APPROVE 档 L1 直执行测试：零提案、operation 行携带快照与授权依据、注册表零改动验证）
- [x] 新增错误码登记＋zh/en 双语同步（OPERATION_SNAPSHOT_STALE / COURSE_ALREADY_ARCHIVED / COURSE_ALREADY_ACTIVE）；api-types regenerate（ProposalType 新枚举值＋snapshot 字段＋两新端点）；prompt 版本 bump（chat-library-scope-v13 / chat-research-scope-v14，工具可见面变化）
- [x] 门禁全套过（后端 pytest 全量 819 绿 / ruff / pyright 0 错、前端 vitest 单跑全绿〔全量 12 失败均为既有并发抖动、单跑逐文件核实绿〕/ lint / build、OpenAPI --check exit 0）

**用户真机验收（单列，不代勾）：**

- 真实会话完成一次课程改名与一次条目归类：确认卡 before/after 准确，确认后页面即时可见。
- 预览后在页面手动修改同一对象，再点确认 → 明确失败原因（目标已变化），重新确认后按新值执行。
- 课程归档后课程不再接受新资料（既有护栏）；恢复后恢复正常；spaces 菜单手动归档入口可用。
