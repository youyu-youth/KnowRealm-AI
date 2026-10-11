"""需要原后台结果才能继续回答时的框架等待入口。"""

import json
from typing import Literal

from langchain_core.tools import tool
from langgraph.types import interrupt

from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.turns.background import prepare_wait


@tool
async def wait_for_task(target_type: Literal["RUN", "JOB"], target_id: str) -> str:
    """等待本会话已提交的后台 Run 或 Job，取得真实结构化结果后继续回答。

    仅在后续回答必须消费后台结果时使用；只需告诉用户已创建任务时直接返回回执。
    target_id 必须来自真实工具回执。普通提案不使用此工具，也不自动批准或重投任务。
    失败、取消或部分完成会返回真实状态，不得宣称全部成功。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"})
    wait = await prepare_wait(runtime, target_type, target_id)
    if wait is None:
        return json.dumps({"ok": False, "error": "TASK_REFERENCE_UNAVAILABLE"})
    if wait.result_json is not None:
        return wait.result_json
    result = interrupt({"kind": "BACKGROUND_TASK", "wait_id": wait.id})
    return json.dumps(result, ensure_ascii=False)
