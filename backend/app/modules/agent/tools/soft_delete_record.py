"""软删除学习记录薄工具（通用 Agent 第二阶段工单 04）。

删除是高风险操作（L3）：任何授权档位下都逐项确认，确认卡呈现记录与记录级
资产计数（总结 / 知识点 / 习题 / Todo / 复习资料），批准后执行前资产发生
变化则提案失效、需重新预览。工具名 = 注册项 action（流式分发按名识别）。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.record_soft_delete import SOFT_DELETE_RECORD_ACTION
from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import RecordSoftDeletePayload

# 工具名（langchain @tool 注册名 = 函数名）。
SOFT_DELETE_RECORD_TOOL_NAME = "soft_delete_record"


@tool(args_schema=lenient_tool_args_schema(RecordSoftDeletePayload))
async def soft_delete_record(**kwargs: Any) -> str:
    """当用户想删除一条学习记录时使用：创建一条待确认的记录删除提案。

    需要目标记录 id（record_id，可先用 search_library 查找）。删除会连同该记录
    的总结、知识点、习题、Todo 与复习资料一并移除（可在确认卡查看数量）。
    删除是高风险操作，即使用户已开启自动批准也需要逐项确认。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation(
        runtime,
        SOFT_DELETE_RECORD_ACTION,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
