"""学习计划草案生成工具（通用 Agent 第三阶段工单 02，只读零落库）。

「基于这门课的资料生成四周学习计划」→ 本工具聚合课程资料（标题 + 已确认
总结 + 复用既有检索的逐字引文）交给 LLM 产出结构化草案，再由确定性排期器
铺排日期（不超期限、每日总量与每日投入相容——脚本优先、LLM 次之）。返回
的草案**未保存**：模型须如实向用户复述草案，再经 confirm_plan 提交确认，
用户在确认卡确认后计划才落库（spec 用户故事 9/11）。纯目标起点（课程无
资料）返回建议学习内容与资料缺口清单，引导补充资料（用户故事 8）。
"""

import json

from langchain_core.tools import tool
from loguru import logger

from app.modules.agent.runtime import MAX_TOOL_CALLS_PER_TURN, current_agent_runtime
from app.modules.agent.tools.time_utils import local_today
from app.modules.learning_plan.generation import (
    PlanGenerationService,
    draft_summary,
)
from app.modules.learning_plan.scheduling import ScheduleInfeasible
from app.modules.learning_plan.service import GoalService, PlanService
from app.modules.llm.service import StructuredGenerationError
from app.shared.errors import CodedHTTPException

GENERATE_PLAN_TOOL_NAME = "generate_learning_plan"


@tool
async def generate_learning_plan(goal_id: str) -> str:
    """为目标生成学习计划草案（不落库）：用户说「帮我生成学习计划 / 制定四周计划」时使用。

    必须传 goal_id（先用 list_goals 确认，目标要先存在）。基于课程已有资料
    生成阶段划分、逐项内容、时长与理由，日期由系统按顺序与每日预算铺排；
    课程还没有资料时返回建议学习内容与资料缺口清单。草案未保存——拿到草案
    后先用简洁的中文列表向用户复述（每行：日期、内容、时长、理由，按阶段
    分组），用户认可后把草案原样（逐字段不加改动）传给 confirm_plan 的参数
    提交确认卡。**草案 JSON 只进 confirm_plan 的工具参数，严禁把 JSON 或
    代码块原文输出到回复正文**——正文里用户只需要可读的中文复述；用户想
    调整就按新要求重新生成。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"}, ensure_ascii=False)
    if runtime.budget.calls_used >= MAX_TOOL_CALLS_PER_TURN:
        return json.dumps(
            {
                "ok": False,
                "error": "TOOL_CALL_LIMIT",
                "message": "本轮工具调用已达上限，请基于已获得的结果回答。",
            },
            ensure_ascii=False,
        )
    runtime.budget.calls_used += 1
    if runtime.llm_provider is None or not runtime.llm_provider.api_key:
        return json.dumps({"ok": False, "error": "LLM_PROVIDER_UNCONFIGURED"}, ensure_ascii=False)
    try:
        async with runtime.session_factory() as session:
            goal = await GoalService.get(session, goal_id)
            if goal is None:
                return _not_found()
            if goal.status != "ACTIVE":
                return json.dumps(
                    {
                        "ok": False,
                        "error": "GOAL_NOT_ACTIVE",
                        "message": "目标已完结或归档，只有进行中的目标可以生成计划。",
                    },
                    ensure_ascii=False,
                )
            await PlanService.require_no_active(session, goal.id)
            materials = await PlanGenerationService.gather_materials(session, goal.course_id)
            evidence = await PlanGenerationService.retrieve_evidence(
                session, goal.course_id, goal.title
            )
        # LLM 调用期间不占 DB 连接（资料上下文已提取完毕）。
        outcome = await PlanGenerationService.generate(
            session_factory=runtime.session_factory,
            goal=goal,
            provider=runtime.llm_provider,
            today=local_today(),
            materials=materials,
            evidence=evidence,
        )
    except StructuredGenerationError as exc:
        return json.dumps({"ok": False, "error": exc.code}, ensure_ascii=False)
    except CodedHTTPException as exc:
        # 提交时状态依赖拒绝（已有进行中计划等）零草案转述，模型如实转述错误码语义。
        return json.dumps({"ok": False, "error": exc.code}, ensure_ascii=False)
    except ScheduleInfeasible as exc:
        return json.dumps(
            {
                "ok": False,
                "error": "PLAN_SCHEDULE_INFEASIBLE",
                "message": (
                    f"{exc}。请修正草案（精简总量 / 拆分超预算单项），"
                    "或建议用户延长期限、提高每日投入。"
                ),
            },
            ensure_ascii=False,
        )
    except Exception:
        logger.warning("generate_learning_plan_failed", error_code="PLAN_GENERATION_FAILED")
        return json.dumps({"ok": False, "error": "PLAN_GENERATION_FAILED"}, ensure_ascii=False)
    if outcome.kind == "SUGGESTIONS":
        assert outcome.suggestions is not None
        body: dict[str, object] = {
            "ok": True,
            "suggestions": outcome.suggestions.model_dump(mode="json"),
            "message": (
                "课程还没有资料，无法生成正式计划。请向用户转述建议学习内容与"
                "资料缺口，引导先补充资料（导入文档 / 网页剪藏 / 粘贴文本 / 录音），"
                "资料就绪后再生成正式计划。"
            ),
        }
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        runtime.budget.chars_fed += len(payload)
        return payload
    assert outcome.plan is not None and outcome.constraints is not None
    body = {
        "ok": True,
        "plan": outcome.plan.model_dump(mode="json"),
        "total_estimated_minutes": outcome.total_minutes,
        "materials_used": outcome.materials_used,
        "message": (
            f"{draft_summary(outcome.plan)}。请用简洁的中文列表向用户复述草案"
            "（每行：日期、内容、时长、理由，按阶段分组），用户认可后把草案"
            "原样传给 confirm_plan 的参数提交确认——草案 JSON 只进工具参数，"
            "不要在回复正文输出 JSON 或代码块；草案关闭即弃、不会自动保存。"
        ),
    }
    payload = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    runtime.budget.chars_fed += len(payload)
    return payload


def _not_found() -> str:
    return json.dumps(
        {
            "ok": False,
            "error": "GOAL_NOT_FOUND",
            "message": "目标不存在或所属课程已删除；请先用 list_goals 确认目标 id，不要猜测。",
        },
        ensure_ascii=False,
    )
