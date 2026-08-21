# 03 — 删除取消与文档资产清理

**What to build:** 用户删除正在解析或已经失败的文档 Record 后，后台任务不会继续写回 Transcript 或恢复该记录；软删除满 30 天后，文档原件、Transcript、文件关联、处理任务和 Record 会以可恢复、可重复执行的顺序物理清理，随 Course 删除的 Record 也遵循同一资产生命周期。

**Blocked by:** 01 — 单文件文档导入完整主链

**Status:** completed

- [x] 现有 Record 删除事务同时把该 Record 的 PENDING/RUNNING Job 置为 CANCELLED；SUCCEEDED、FAILED、CANCELLED 等终态 Job 不被重写，重复删除保持既有 404 语义。
- [x] Course 软删除其 Record 时应用相同的任务取消规则，并继续保证 Course、Record tombstone 与非终态 Job 更新在单个事务中提交或回滚。
- [x] Worker 在解析前以及写 Transcript、Job 结果或 Record 状态前检查 Record deleted_at 和 Job 当前状态；发现软删或 CANCELLED 后停止执行、丢弃内存结果和临时产物，不再写入业务产物。
- [x] 自动化竞态测试覆盖 PENDING、RUNNING、解析完成但提交前删除三种时点，均证明 Job=CANCELLED、Record 不可见且没有后续 Transcript 或状态回写；终态任务删除行为不回归。
- [x] Record 详情复用现有删除确认和导航行为；处理中或失败状态均可删除，取消不发送请求，失败保留上下文，成功后停止轮询并清理相关前端缓存。
- [x] 启动清理覆盖独立软删除和随 Course 软删除的所有 Record；以可控时钟判断 30 天边界，未满期限的文件和业务行保持不变。
- [x] 满 30 天的文档 Record 先处理受控路径下的原件和临时产物，再物理删除 Transcript、record_files、processing_jobs 和 Record；父 Course 的物理删除排在后代文档资产清理之后，不能让外键级联提前隐藏文件目标。
- [x] 清理只接受解析后仍位于数据目录允许子树的相对路径，拒绝目录穿越、绝对路径和指向活跃实体的路径；正常重复导入和相同原始文件名不能互相删除。
- [x] 文件已不存在视为幂等成功；文件处理或数据库提交失败时保留或恢复可再次定位的清理目标，下次启动可继续处理，不留下无法追踪的原件或指向错误文件的活跃行。
- [x] 孤儿清理只删除能够证明属于未提交导入或已物理清理实体的文件，不按文件名、年龄或 content_hash 猜测；补偿失败产生的孤儿有可控测试入口和明确日志错误码。
- [x] 可控时钟与真实临时文件系统测试覆盖 29 天/30 天边界、独立 Record、随 Course 删除、文件缺失、路径越界、文件操作失败、数据库失败、重复执行和重复内容隔离。
- [x] 真实 sidecar 重启验证已删除 Record 不会恢复、CANCELLED Job 不会再次领取、到期资产最终消失且未到期资产保留；测试只操作独立临时数据目录。
- [x] 桌面测试与人工渲染检查覆盖处理中删除、失败删除、确认/取消、焦点恢复、停止轮询、错误提示以及明暗主题和既定桌面尺寸。
- [x] 以功能开始前的固定基线完成 Standards 与 Spec 两轴审查；最终报告分开列出静态、数据库、文件系统、ASGI、真实 socket、桌面组件和渲染证据，并明确多文件、Inbox、SSE、Summary/AI、OCR 与 MSI 仍不在本功能范围。
