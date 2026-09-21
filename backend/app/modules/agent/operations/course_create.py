"""create_course 操作注册项（通用 Agent 第一阶段工单 02）：操作注册表首个接入动作。

「帮我创建课程」→ 模型经薄工具创建 COURSE_CREATE 提案 → 用户确认卡确认 →
应用器在确认事务内经课程创建核心建课（业务写入 + 搜索索引 + APPLIED +
result_json 原子提交）。导入即注册（先例：library/organize、learner/routes）。
"""

from typing import Any

from pydantic import ConfigDict, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.registry import (
    OperationSpec,
    operation_payload_dict,
    register_operation,
)
from app.modules.course.schemas import CourseCreate
from app.modules.course.service import CourseService
from app.modules.library.models import AgentProposal
from app.modules.library.schemas import ProposalType
from app.shared.errors import CodedHTTPException

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
CREATE_COURSE_ACTION = "create_course"


class CourseCreatePayload(CourseCreate):
    """COURSE_CREATE 提案判别载荷：字段与校验复用 HTTP 创建契约 CourseCreate
    （同源零漂移），仅收紧未知键拒绝（extra=forbid，ADR-0024 载荷纪律）。"""

    model_config = ConfigDict(extra="forbid")


async def apply_course_create(session: AsyncSession, proposal: AgentProposal) -> dict[str, Any]:
    """COURSE_CREATE 应用器（提案框架契约：调用方事务内、不得自行 begin）。

    经课程创建事务内核心建课（与 HTTP 路由共用，校验零双份漂移）；返回结果
    投影 {course_id}，由提案框架在确认事务内写进 result_json（操作回执）。
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
    return {"course_id": course.id}


register_operation(
    OperationSpec(
        action=CREATE_COURSE_ACTION,
        proposal_type=ProposalType.COURSE_CREATE,
        payload_schema=CourseCreatePayload,
        applier=apply_course_create,
    )
)
