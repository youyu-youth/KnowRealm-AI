"""学习计划域（通用 Agent 第三阶段，spec 里程碑一）：学习目标与学习计划。

工单 01 落地学习目标（learning_goals）；工单 02 落地学习计划与计划项
（learning_plans / learning_plan_items + 生成与确认）；共享引用随后续
工单进入本模块。目标挂单个知识空间，单空间同时至多一个进行中目标
（部分唯一索引存储层保证）；Agent 写动作经操作注册表（agent/operations）
与页面共用本域 Service。
"""
