"""create_course 操作注册项（通用 Agent 第一阶段工单 02）：操作注册表首个接入动作。

「帮我创建课程」→ 模型经薄工具创建 COURSE_CREATE 提案 → 用户确认卡确认 →
应用器在确认事务内经课程创建核心建课（业务写入 + 搜索索引 + APPLIED +
result_json 原子提交）。导入即注册（先例：library/organize、learner/routes）。
载荷契约（CourseCreatePayload / CourseCreateResult）见 agent/schemas.py。
"""

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    operation_payload_dict,
    register_operation,
)
from app.modules.agent.schemas import CourseCreatePayload, CourseCreateResult
from app.modules.course.schemas import CourseCreate
from app.modules.course.service import CourseService
from app.modules.library.models import AgentProposal
from app.modules.library.schemas import ProposalType
from app.shared.errors import CodedHTTPException

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
CREATE_COURSE_ACTION = "create_course"


async def apply_course_create(session: AsyncSession, proposal: AgentProposal) -> CourseCreateResult:
    """COURSE_CREATE 应用器（提案框架契约：调用方事务内、不得自行 begin）。

    经课程创建事务内核心建课（与 HTTP 路由共用，校验零双份漂移）；返回类型化
    结果投影，经注册表适配器校验后在确认事务内写进 result_json（操作回执）。
    """
    try:
        payload = CourseCreate.model_validate(operation_payload_dict(proposal))
    except ValidationError as exc:
        raise CodedHTTPException(
            code="PROPOSAL_PAYLOAD_INVALID",
            status_code=422,
            detail="提案载荷不符合该类型的结构要求",
        ) from exc
    course = await CourseService.create_core(session, payload)
    return CourseCreateResult(course_id=course.id)


register_operation(
    OperationSpec(
        action=CREATE_COURSE_ACTION,
        proposal_type=ProposalType.COURSE_CREATE,
        level=OperationLevel.L1,
        payload_schema=CourseCreatePayload,
        result_schema=CourseCreateResult,
        applier=apply_course_create,
        undo_reason="创建类动作不在首批撤销范围，如需移除请在知识空间手动删除",
    )
)
