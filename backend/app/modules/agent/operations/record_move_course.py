"""move_record_course 操作注册项（通用 Agent 第二阶段工单 04）：L2 迁移动作。

「把这条记录移到课程 B」→ 模型经 search_library / search_courses 消歧固化
record_id 与 target_course_id → 薄工具创建 OP_RECORD_MOVE_COURSE 提案（提交时
同事务固化执行前快照，原 course_id 即 06 票 Undo 反向迁移的补偿数据）→ 确认卡
呈现记录与 before/after 课程 → 用户确认 → 应用器先执行前重验，再经跨课迁移
领域核心（与 HTTP 共用，spec 决策 17）落库。记录级资产随记录天然随走；历史
归属（quiz 存量绑定 / quiz_test_items / learning_events / learning_evidence /
record_concepts）零触碰（spec 决策 18）。

工单 06：Undo＝反向迁移过全部校验（spec 决策 19：迁移快照存原 course_id）。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    UndoOperationResult,
    assert_undo_state,
    parse_operation_payload,
    parse_undo_basis,
    register_operation,
)
from app.modules.agent.runs.models import AgentOperation
from app.modules.agent.schemas import (
    RecordMoveCoursePayload,
    RecordMoveCourseResult,
    RecordStateSnapshot,
)
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus
from app.modules.library.models import AgentProposal
from app.modules.library.schemas import ProposalType
from app.modules.record.move import RecordMoveService
from app.modules.record.service import RecordService
from app.modules.search.service import SearchService
from app.shared.errors import CodedHTTPException

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
MOVE_RECORD_COURSE_ACTION = "move_record_course"


async def capture_record_state(
    session: AsyncSession, payload: RecordMoveCoursePayload
) -> RecordStateSnapshot:
    """执行前快照读取器（record.* 动作共用形状）：不存在/已删 → 结构化拒绝。"""
    record = await RecordService.get(session, payload.record_id)
    if record is None:
        raise CodedHTTPException(
            code="RECORD_NOT_FOUND", status_code=404, detail="学习记录不存在或已删除"
        )
    return RecordStateSnapshot(
        updated_at=record.updated_at,
        title=record.title,
        status=record.status,
        course_id=record.course_id,
    )


def resolve_record_target(payload: RecordMoveCoursePayload) -> tuple[str, str]:
    return "record", payload.record_id


async def apply_record_move_course(
    session: AsyncSession, proposal: AgentProposal
) -> RecordMoveCourseResult:
    """OP_RECORD_MOVE_COURSE 应用器（调用方事务内、不得自行 begin）：执行前
    重验已由注册表适配器完成；经跨课迁移领域核心落库（目标课程校验、进行中
    任务拒绝、搜索索引同事务重建），返回 before/after 课程对照。"""
    payload = parse_operation_payload(proposal, RecordMoveCoursePayload)
    record = await RecordService.get(session, payload.record_id)
    if record is None:
        raise CodedHTTPException(
            code="RECORD_NOT_FOUND", status_code=404, detail="学习记录不存在或已删除"
        )
    before_course_id = record.course_id
    await RecordMoveService.move_cross_course_core(session, record, payload.target_course_id)
    return RecordMoveCourseResult(
        record_id=payload.record_id,
        before_course_id=before_course_id,
        after_course_id=record.course_id,
    )


async def undo_move_record_course(
    session: AsyncSession, original: AgentOperation
) -> UndoOperationResult:
    """move_record_course 补偿器（工单 06，spec 决策 19）：反向迁移过全部校验。

    撤销前重验：记录当前课程必须是原操作的目标课程（payload.target_course_id）。
    恢复＝迁移回快照的原 course_id（经 move_cross_course_core 完整校验链：目标
    课程存在且 ACTIVE、无进行中任务）；原课程为收件箱（course_id 空）时轻量
    恢复为未归类（无目标课程校验可过，维护 updated_at＋索引重建同口径）。"""
    payload, snapshot = parse_undo_basis(original, RecordMoveCoursePayload, RecordStateSnapshot)
    record = await RecordService.get(session, payload.record_id)
    if record is None:
        raise CodedHTTPException(
            code="OPERATION_UNDO_CONFLICT",
            status_code=409,
            detail="学习记录已不存在或已删除，无法撤销",
        )
    assert_undo_state({"course_id": payload.target_course_id}, {"course_id": record.course_id})
    if snapshot.course_id is None:
        # 恢复到收件箱（无目标课程可校验）：仍过「无进行中任务」守卫
        # （与正向迁移同口径，决策 17），再轻量恢复＋索引重建。
        active_job = await session.scalar(
            select(ProcessingJob.id).where(
                ProcessingJob.record_id == record.id,
                ProcessingJob.status.in_(
                    (ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING)
                ),
            )
        )
        if active_job is not None:
            raise CodedHTTPException(
                code="RECORD_MOVE_JOB_IN_PROGRESS",
                status_code=409,
                detail="记录有正在进行的处理任务，请等待处理完成后再迁移",
            )
        record.course_id = None
        record.updated_at = utcnow()
        await session.flush()
        await SearchService.upsert_record_index(session, record.id)
    else:
        await RecordMoveService.move_cross_course_core(session, record, snapshot.course_id)
    return UndoOperationResult(restored={"course_id": snapshot.course_id})


register_operation(
    OperationSpec(
        action=MOVE_RECORD_COURSE_ACTION,
        proposal_type=ProposalType.OP_RECORD_MOVE_COURSE,
        level=OperationLevel.L2,
        payload_schema=RecordMoveCoursePayload,
        result_schema=RecordMoveCourseResult,
        applier=apply_record_move_course,
        capture_state=capture_record_state,
        target_resolver=resolve_record_target,
        undoer=undo_move_record_course,
    )
)
