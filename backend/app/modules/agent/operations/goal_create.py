"""create_goal 操作注册项（通用 Agent 第三阶段工单 01）。

「为这门课定个目标：四周内学会 Agent 工程，每天一小时」→ 模型经
search_courses 消歧固化 course_id → 薄工具创建 OP_GOAL_CREATE 提案 →
确认卡预览目标参数 → 用户确认 → 应用器经领域核心落库（与 HTTP 路由共用
同一校验链）。

创建类动作携带执行前快照的原因：单空间单 ACTIVE 是状态依赖约束——快照
读取器在提交时即拒绝「课程不存在 / 已有进行中目标」（结构化错误零提案，
模型即时转述，spec 用户故事 3），确认前课程被改（如已有目标被归档）→
快照比对失效重新预览；领域核心的 ACTIVE 校验与部分唯一索引仍是存储层
兜底。目标范围来源固化 AI_INFERRED + scope_confirmed=True——确认卡即用户
确认（spec 用户故事 6：AI 推断范围必须经用户确认才生效）。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    register_operation,
)
from app.modules.agent.schemas import (
    GoalCreatePayload,
    GoalCreateResult,
    GoalCreateStateSnapshot,
)
from app.modules.course.service import CourseService
from app.modules.learning_plan.schemas import GoalCreateCore, GoalScopeSource
from app.modules.learning_plan.service import GoalService
from app.modules.library.schemas import ProposalType
from app.shared.errors import CodedHTTPException

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
CREATE_GOAL_ACTION = "create_goal"


async def capture_goal_create_state(
    session: AsyncSession, payload: GoalCreatePayload
) -> GoalCreateStateSnapshot:
    """创建前状态读取器：课程不可达或已有进行中目标 → 结构化拒绝（零提案）。"""
    course = await CourseService.get(session, payload.course_id)
    if course is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    await GoalService.require_no_active(session, course.id)
    return GoalCreateStateSnapshot(updated_at=course.updated_at, name=course.name)


def resolve_goal_create_target(payload: GoalCreatePayload) -> tuple[str, str]:
    return "course", payload.course_id


async def apply_goal_create(
    session: AsyncSession, payload: GoalCreatePayload, _execution_id: str
) -> GoalCreateResult:
    """OP_GOAL_CREATE 应用器（提案框架契约：调用方事务内、不得自行 begin）。

    执行前重验（课程可达 + 快照比对）已由注册表适配器完成；此处经领域核心
    落库。scope 固化 AI_INFERRED + scope_confirmed=True——默认档经确认卡
    （卡上确认即用户确认，spec 用户故事 6）；自动档直执行＝用户对该档位的
    预授权（ADR-0026，与其他写动作同口径），确认事实由 operation 行的
    authorization_json 承载。
    """
    course = await CourseService.get(session, payload.course_id)
    if course is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    goal = await GoalService.create_core(
        session,
        course,
        GoalCreateCore(
            goal_type=payload.goal_type,
            title=payload.title,
            target_date=payload.target_date,
            daily_minutes=payload.daily_minutes,
            target_score=payload.target_score,
            scope_source=GoalScopeSource.AI_INFERRED,
            scope_confirmed=True,
        ),
    )
    return GoalCreateResult(goal_id=goal.id, course_id=course.id)


register_operation(
    OperationSpec(
        action=CREATE_GOAL_ACTION,
        proposal_type=ProposalType.OP_GOAL_CREATE,
        level=OperationLevel.L1,
        payload_schema=GoalCreatePayload,
        result_schema=GoalCreateResult,
        applier=apply_goal_create,
        capture_state=capture_goal_create_state,
        target_resolver=resolve_goal_create_target,
        undo_reason="目标创建暂不在撤销范围，如需移除可直接在对话或课程中归档该目标",
    )
)
