"""archive_course / restore_course 操作注册项（通用 Agent 第二阶段工单 03）。

课程归档写路径首次落地（历史推迟决策收口，spec 决策 14）：状态翻转走
CourseService.set_status_core（HTTP 路由与 Agent 应用器共用）；既有 ARCHIVED
三道读取闸门（summary / KP / quiz / todo 校验）零改动——归档只写状态＋
updated_at，不级联不删数据。快照读取器与目标定位复用 course_update 声明
（course.* 三动作共用同一形状）。载荷契约见 agent/schemas.py。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.course_update import (
    capture_course_state,
    resolve_course_target,
)
from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    parse_operation_payload,
    register_operation,
)
from app.modules.agent.schemas import (
    CourseArchivePayload,
    CourseArchiveResult,
)
from app.modules.course.service import CourseService
from app.modules.library.models import AgentProposal
from app.modules.library.schemas import ProposalType
from app.shared.errors import CodedHTTPException

# 工具名（langchain @tool 注册名 = 函数名）。
ARCHIVE_COURSE_ACTION = "archive_course"
RESTORE_COURSE_ACTION = "restore_course"


async def _apply_course_status(
    session: AsyncSession, proposal: AgentProposal, *, archived: bool
) -> CourseArchiveResult:
    """OP_COURSE_ARCHIVE / OP_COURSE_RESTORE 应用器（调用方事务内）。

    执行前重验已由注册表适配器统一完成；重复归档 / 重复恢复由领域核心
    幂等守卫拒绝（409 稳定错误码 → 提案 FAILED 可重试）。
    """
    payload = parse_operation_payload(proposal, CourseArchivePayload)
    course = await CourseService.get(session, payload.course_id)
    if course is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    await CourseService.set_status_core(session, course, archived=archived)
    return CourseArchiveResult(course_id=payload.course_id, status=course.status)


async def apply_course_archive(
    session: AsyncSession, proposal: AgentProposal
) -> CourseArchiveResult:
    return await _apply_course_status(session, proposal, archived=True)


async def apply_course_restore(
    session: AsyncSession, proposal: AgentProposal
) -> CourseArchiveResult:
    return await _apply_course_status(session, proposal, archived=False)


register_operation(
    OperationSpec(
        action=ARCHIVE_COURSE_ACTION,
        proposal_type=ProposalType.OP_COURSE_ARCHIVE,
        level=OperationLevel.L1,
        payload_schema=CourseArchivePayload,
        result_schema=CourseArchiveResult,
        applier=apply_course_archive,
        capture_state=capture_course_state,
        target_resolver=resolve_course_target,
    )
)
register_operation(
    OperationSpec(
        action=RESTORE_COURSE_ACTION,
        proposal_type=ProposalType.OP_COURSE_RESTORE,
        level=OperationLevel.L1,
        payload_schema=CourseArchivePayload,
        result_schema=CourseArchiveResult,
        applier=apply_course_restore,
        capture_state=capture_course_state,
        target_resolver=resolve_course_target,
    )
)
