# 06 — Run 等待与结果绑定

**What to build:** Run 状态机补齐长任务两块拼图。其一：步骤提交后台 job 后 Run 进入 WAITING_JOB 等待，job 完成后自动接续推进（另设启动对账兜底——重启后扫描等待中的 Run、核对所等待 job 的终态决定续跑 / 失败 / 部分成功）；其二：前一步骤的输出（如新建课程的 id）可绑定为后续步骤的参数。以最小场景（单资料导入 → 建课）验证机制。

**Blocked by:** None — can start immediately（与 M1 并行）

**Status:** ready-for-agent

- [ ] Run 计划契约扩展：步骤输出按字段路径引用（如新建课程 id）注入后续步骤参数；依赖仍只表达先后与成功
- [ ] WAITING_JOB 激活：步骤提交 job 后 Run 置 WAITING_JOB（该状态此前仅预留零写入者）；job 完成主动触发 Run 推进（与现有 AGENT_RUN 无状态触发 job 联动）
- [ ] 启动对账兜底：扫描 WAITING_JOB 的 Run、核对等待 job 终态决定续 / 败 / 部分成功（掌握度 consumer 自愈同模式）；对账幂等
- [ ] 等待中取消：未提交步骤停止、已提交 job 保留回执；断开 SSE 不当作业务取消（沿用二阶段语义）
- [ ] 最小验证场景：单资料导入 → 建课 Run 全链（等待 → 唤醒 → 结果绑定 → 完成），聊天卡呈现等待状态
- [ ] 测试：job 终态注入（成功 / 失败 / 部分失败）、重启重放对账（WAITING_JOB 恢复正确分流、已完成步骤不重做）、等待中取消、结果绑定注入正确性
- [ ] 门禁全绿：pytest（独立 basetemp）+ ruff + pyright + OpenAPI --check

参考：[spec.md](../spec.md) M2 执行闭环段（User Stories 30~32 部分）、多资料长任务前置机制。
