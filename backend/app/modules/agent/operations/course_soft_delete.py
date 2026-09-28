"""delete_course 操作注册项（通用 Agent 第二阶段工单 04）：L3 删除动作。

「删掉这门课」→ 模型经 search_courses 消歧固化 course_id → 薄工具创建
OP_COURSE_SOFT_DELETE 提案（提交时同事务固化影响清单＝当前记录清单与计数）→
确认卡完整呈现级联影响 → 用户逐项确认（L3：任何档位不自动执行）→ 应用器先
执行前重验（批准后新增记录 → 清单差异 → 失效重新预览，新增记录不被悄悄纳入
删除），再走课程删除领域应用函数（级联软删＋掌握度重算＋consumer 重试一体，
spec 决策 15 收拢，与 HTTP 路由共用）。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    parse_operation_payload,
    register_operation,
)
from app.modules.agent.schemas import (
    CourseDeleteSnapshot,
    CourseDeleteSnapshotRecord,
    CourseSoftDeletePayload,
    CourseSoftDeleteResult,
)
from app.modules.course.service import CourseService
from app.modules.library.models import AgentProposal
from app.modules.library.schemas import ProposalType
from app.modules.record.models import Record
from app.shared.errors import CodedHTTPException

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
DELETE_COURSE_ACTION = "delete_course"


async def capture_course_delete_state(
    session: AsyncSession, payload: CourseSoftDeletePayload
) -> CourseDeleteSnapshot:
    """执行前快照读取器：级联影响清单＝当前记录（id+标题，id 排序保证序列化
    稳定，重验比对即「批准后新增记录 → 失效」的 Q8 语义）。"""
    course = await CourseService.get(session, payload.course_id)
    if course is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    rows = (
        await session.execute(
            select(Record.id, Record.title)
            .where(
                Record.course_id == payload.course_id,
                Record.deleted_at.is_(None),
            )
            .order_by(Record.id)
        )
    ).all()
    return CourseDeleteSnapshot(
        updated_at=course.updated_at,
        name=course.name,
        status=course.status,
        records=[
            CourseDeleteSnapshotRecord(record_id=record_id, title=title)
            for record_id, title in rows
        ],
        record_count=len(rows),
    )


def resolve_course_delete_target(payload: CourseSoftDeletePayload) -> tuple[str, str]:
    return "course", payload.course_id


async def apply_course_soft_delete(
    session: AsyncSession, proposal: AgentProposal
) -> CourseSoftDeleteResult:
    """OP_COURSE_SOFT_DELETE 应用器（调用方事务内、不得自行 begin）：执行前
    重验已由注册表适配器完成；课程删除编排（级联软删＋重算＋consumer 重试）
    经领域应用函数 apply_soft_delete 与 HTTP 路由同源（spec 决策 15）。"""
    payload = parse_operation_payload(proposal, CourseSoftDeletePayload)
    course = await CourseService.get(session, payload.course_id)
    if course is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    record_count, _ = await CourseService.apply_soft_delete(session, course)
    return CourseSoftDeleteResult(course_id=payload.course_id, record_count=record_count)


register_operation(
    OperationSpec(
        action=DELETE_COURSE_ACTION,
        proposal_type=ProposalType.OP_COURSE_SOFT_DELETE,
        level=OperationLevel.L3,
        payload_schema=CourseSoftDeletePayload,
        result_schema=CourseSoftDeleteResult,
        applier=apply_course_soft_delete,
        capture_state=capture_course_delete_state,
        target_resolver=resolve_course_delete_target,
        undo_reason="课程删除（含级联删除记录）不可撤销：影响面大且暂无恢复入口",
    )
)
