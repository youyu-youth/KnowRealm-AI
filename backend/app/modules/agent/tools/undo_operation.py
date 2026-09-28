"""撤销薄工具（通用 Agent 第二阶段工单 06）：undo_operation。

用户要求撤销此前的操作（「撤销刚才的改名 / 把刚才的迁移改回去 / 反悔」）时
使用：传该操作回执中的 operation_id。走三档授权——默认档落 OP_UNDO 提案等
确认，自动档直执行并给回执；不可撤销的动作（记录删除、课程删除）会返回
明确原因。取消不冒充撤销（已取消的任务只是不再新增动作）。
"""

import json

from langchain_core.tools import tool

from app.modules.agent.runs.undo import submit_undo
from app.modules.agent.runtime import current_agent_runtime

# 工具名（langchain @tool 注册名 = 函数名）。
UNDO_OPERATION_TOOL_NAME = "undo_operation"


@tool
async def undo_operation(operation_id: str) -> str:
    """当用户想撤销此前已执行的操作时使用：创建一条撤销请求（补偿该操作的执行前状态）。

    需要目标操作的 operation_id（此前操作回执或执行结果 JSON 中的 operation_id）。
    重命名、归类、归档 / 恢复、跨课迁移可撤销；撤销前会校验目标是否被后续修改过，
    已被修改则拒绝并说明原因。记录删除、课程删除不可撤销（会返回明确原因）。
    用户确认撤销请求后才会执行补偿；执行档位足够时直接执行并返回回执。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_undo(runtime, operation_id)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
