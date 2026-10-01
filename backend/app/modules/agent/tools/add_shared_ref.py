"""添加共享引用薄工具（通用 Agent 第三阶段工单 05）：add_shared_ref 动作的工具壳。

把归属其他知识空间的资料引用到本空间（原归属不变、内容进入本空间问答检索，
但对引用资料只读——不能生成总结 / 知识点 / 习题）。确认卡预览引用关系
（快照由后端提交时同事务固化，模型不提供）。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.operations.shared_ref import ADD_SHARED_REF_ACTION
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import SharedRefPayload

# 工具名（langchain @tool 注册名 = 函数名）。
ADD_SHARED_REF_TOOL_NAME = "add_shared_ref"


@tool(args_schema=lenient_tool_args_schema(SharedRefPayload))
async def add_shared_ref(**kwargs: Any) -> str:
    """当用户想把其他知识空间（课程）的资料引用到当前课程共享使用时使用：创建一条待确认的共享引用提案。

    需要 course_id（引用落点课程）与 library_item_id（被引用资料条目，可先用
    list_library_items 查找）；已归属本课程的资料无需引用（会被拒绝）。
    引用后资料内容进入本课程问答检索（标注共享来源），但本课程对它只读——
    不能生成总结、知识点或习题。用户在确认卡确认后引用才会生效。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation(
        runtime,
        ADD_SHARED_REF_ACTION,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
