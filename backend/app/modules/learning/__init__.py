"""学习事件域：学习行为事实流（learning_events）与派生证据（learning_evidence）。

learning_events 模型维持 record 域现位不迁移（历史先例）；事件写入统一经
本模块 events.write_learning_event——传入业务事务会话、幂等键冲突静默跳过。
证据模型、消费循环与只读查询落本模块。
"""
