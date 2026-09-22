# 01 — 执行事实地基与操作历史（Run/Operation 落库）

**What to build:** 迁移 0030 落地 agent_runs / agent_operations / agent_activity 三表；第一阶段两类动作（建课程、加文本记录）确认执行后同事务写入 operation 行（单步不建 run）；提案 result_json 降级为 operation→proposal 的单向投影缓存（旧提案接口零变化）；新增操作历史查询与清理 API；设置页新增「操作历史」分区。用户可演示：确认建课 → 操作历史分区出现该条目（动作、目标、状态、结果、时间），既有确认卡/回执卡行为零变化。

**实施约束：** 实施决策全量见 [spec](../spec.md) 决策 1~5、21~22 与 Further Notes 框架加固项（快照三用、档位分流、authorization_json 等后续票消费的本票地基一次建齐）；不造轮子约束同处。

**Blocked by:** None — can start immediately.

**Status:** done

- [x] 迁移 0030：三表 DDL 按 spec 决策 2/3/22（operations 含 authorization_json、无持久 RUNNING、runs 含 WAITING_JOB 预留枚举）；agent_proposals proposal_type CHECK 一次改造为「存量五类型白名单＋`OP_` 前缀通配」——本阶段新类型统一 OP_ 命名空间（具体类型随 03/04/05 各票注册，如 OP_COURSE_UPDATE / OP_RECORD_MOVE / OP_BATCH），后续新动作零迁移；类型执法仍在判别 schema 注册表；全库 user_version 硬编码断言同步（先 grep 后改：仅 test_library.py:351 一处 29→30，其余已动态化）
- [x] 存量 APPLIED 提案不回填 operations（迁移测试断言新纪元起点，旧回执经既有提案查询仍可达）
- [x] 操作注册表适配器扩展：操作路径应用器执行成功后同事务写 operation（run_id 空、proposal_id 关联、payload 投影、result 回填）；ORGANIZE / MEMORY / RESEARCH_INGEST 旧应用器不经注册表、不写 operation（零改动）
- [x] result_json 单向投影：提案确认事务内由 operation 结果投影回写，AgentProposalOut 输出契约零变化（阶段一提案测试零回归）
- [x] authorization_json 授权依据：确认路径回接写 operation 时同步写入（档位＋触发指令摘录＋消息引用），02 直执行沿用同列——单步无 run 的授权事实唯一载体（ADR-0026）；形状=runs/schemas.OperationAuthorization（trigger=USER_CONFIRMED_PROPOSAL，instruction_excerpt 本阶段为空、02 回填）
- [x] 提案框架并发加固：reject 与失败回写（_mark_failed）改条件 UPDATE 抢占（终态守卫＋rowcount 判定，confirm 先例），消除与确认 / 重试并发的先读后写覆盖竞态；补并发回归（reject vs confirm 抢占、失败回写 vs 重试抢占）
- [x] 应用器非编码异常同样落 FAILED＋INTERNAL 稳定错误码（原子回滚＝未发生、FAILED 可重试），既有 CodedHTTPException 路径零变化
- [x] 查询 API：GET runs（分页 / 状态 / 会话过滤）、GET 单 run 详情（含逐 operation）、GET activity（模式切换审计流，本票无写入者、空态）＋GET operations（单步操作列表，操作历史分区消费）；OpenAPI 变更后 regenerate api-types
- [x] 清理 API：按终态 run 删除（run＋其 operations）＋批量清理已结束（终态 runs＋终态单步 operations）；活动 run / operation 拒绝清理（AGENT_RUN_NOT_FINISHED 稳定错误码）；提案（审批事实）永不删
- [x] 前端设置页「操作历史」分区：run 列表（状态过滤）展开逐 operation（action / 目标 / 状态 / 结果 / 错误码）＋审计区空态＋清理入口（单 run 删除＋批量清理已结束，二次确认）
- [x] 新增错误码登记＋zh/en 双语同步（AGENT_RUN_NOT_FOUND / AGENT_RUN_NOT_FINISHED）；公共执行与 runs 子包零领域 import 的 AST 防线延续
- [x] 门禁全套过（后端 pytest 784 绿 / ruff / pyright 0 错、前端 vitest / lint / build、OpenAPI --check）

**用户真机验收（单列，不代勾）：**

- 设置页操作历史分区真实呈现建课 / 加文本记录的操作条目；批量清理后列表如实减少、活动项不被清理。
