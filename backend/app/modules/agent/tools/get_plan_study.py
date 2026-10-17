"""资料学习只读状态及准确站内入口；实际阅读由用户完成。"""

import json

from langchain_core.tools import tool
from loguru import logger

from app.modules.agent.budget.service import budgeted, mark_output
from app.modules.agent.runtime import current_agent_runtime
from app.modules.learning_plan.study import state
from app.shared.errors import CodedHTTPException


@tool
@budgeted(lambda: json.dumps({"ok": False, "error": "TOOL_CALL_LIMIT"}))
async def get_plan_study(item_id: str, q: str = "") -> str:
    """查询资料计划项的关联、明确启动事实、上次页签及站内学习入口，可按标题筛选资料候选。

    item_id 先从 get_plan 获取；仅返回课程归属或当前有效共享资料，不扩大访问范围。
    缺关联或来源失效时用 update_plan_item(record_id=候选身份) 提出人工确认的关联变更，
    多个候选先向用户消歧。entry_path 可让用户明确启动学习；查询不会记录阅读，
    启动不是读完，完成仍需用户明确表达意图后用 complete_plan_item，不改变掌握度。
    历史版本、完结目标和已跳过项只查询既有结果，不声称模型代替用户阅读。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"})
    try:
        async with runtime.session_factory() as session:
            result = await state(session, item_id, q=q)
    except CodedHTTPException as exc:
        return json.dumps({"ok": False, "error": exc.code})
    except Exception:
        logger.warning("get_plan_study_failed", error_code="PLAN_QUERY_FAILED")
        return json.dumps({"ok": False, "error": "PLAN_QUERY_FAILED"})
    output = json.dumps({"ok": True, "study": result.model_dump(mode="json")}, ensure_ascii=False)
    mark_output(output)
    return output
