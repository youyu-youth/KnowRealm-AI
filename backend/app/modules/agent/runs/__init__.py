"""执行事实子包（通用 Agent 第二阶段工单 01）。

agent_runs / agent_operations / agent_activity 三表的模型、查询服务与
查询清理端点（Run 推进 worker 随工单 05 落地）。Operation 自始为执行事实
唯一源：第一阶段两类动作（课程创建 / 文本记录添加）确认执行后同事务写入
operation 行（单步不建 run，run_id 空）；依赖方向 agent → library，
零其他领域 import（公共执行流程零领域分支的 AST 防线延续覆盖本子包）。
"""
