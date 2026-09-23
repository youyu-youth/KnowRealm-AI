-- 通用 Agent 第二阶段工单 02 P2 修复：直执行回执的消息流持久锚点。
-- assistant 行落库本轮直执行 operation_id 列表（spec 用户故事 33：清理后
-- 消息流旧回执卡降级「历史已清理」占位、消息不删——锚点随消息持久，
-- 清理 operation 后「锚点在、查询空」即占位，跨重启成立）。
-- 可空列 ADD COLUMN，无需整表重建（chat_messages 列惯例：JSON 文本列不加 CHECK）。
ALTER TABLE chat_messages ADD COLUMN executed_operations_json TEXT;
