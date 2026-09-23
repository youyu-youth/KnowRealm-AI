"""soft_delete_record 操作注册项（通用 Agent 第二阶段工单 04）：L3 删除动作。

「删掉这条记录」→ 模型经 search_library 消歧固化 record_id → 薄工具创建
OP_RECORD_SOFT_DELETE 提案（提交时同事务固化影响快照＝记录级资产计数）→
确认卡呈现目标与资产计数 → 用户逐项确认（L3：任何档位不自动执行）→ 应用器
先执行前重验（资产新增属实质差异 → 失效重新预览），再复用记录软删领域核心
（与 HTTP 路由共用同一级联语义），掌握度重算经 after_commit 挂钩提交后执行。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    parse_operation_payload,
    register_operation,
)
from app.modules.agent.schemas import (
    RecordDeleteSnapshot,
    RecordSoftDeletePayload,
    RecordSoftDeleteResult,
)
from app.modules.knowledge_point.models import KnowledgePoint
from app.modules.learning.service import MasteryService
from app.modules.library.models import AgentProposal
from app.modules.library.schemas import ProposalType
from app.modules.quiz.models import Quiz
from app.modules.record.service import RecordService
from app.modules.review_material.models import ReviewMaterial
from app.modules.summary.models import AiSummary
from app.modules.todo.models import TodoItem
from app.shared.errors import CodedHTTPException

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
SOFT_DELETE_RECORD_ACTION = "soft_delete_record"

# 记录级资产表共形集合（均有 record_id + deleted_at 列），供计数收窄类型。
_RecordScopedModel = type[KnowledgePoint] | type[Quiz] | type[TodoItem] | type[
    ReviewMaterial
] | type[AiSummary]


async def _alive_count(
    session: AsyncSession, model: _RecordScopedModel, record_id: str
) -> int:
    """该记录名下未软删的资产行数（各资产表均有 record_id + deleted_at 列）。"""
    return int(
        await session.scalar(
            select(func.count()).select_from(model).where(
                model.record_id == record_id,
                model.deleted_at.is_(None),
            )
        )
        or 0
    )


async def capture_record_delete_state(
    session: AsyncSession, payload: RecordSoftDeletePayload
) -> RecordDeleteSnapshot:
    """执行前快照读取器：不存在/已删 → 结构化拒绝（零提案）。"""
    record = await RecordService.get(session, payload.record_id)
    if record is None:
        raise CodedHTTPException(
            code="RECORD_NOT_FOUND", status_code=404, detail="学习记录不存在或已删除"
        )
    return RecordDeleteSnapshot(
        updated_at=record.updated_at,
        title=record.title,
        status=record.status,
        course_id=record.course_id,
        knowledge_point_count=await _alive_count(session, KnowledgePoint, payload.record_id),
        quiz_count=await _alive_count(session, Quiz, payload.record_id),
        todo_count=await _alive_count(session, TodoItem, payload.record_id),
        review_material_count=await _alive_count(session, ReviewMaterial, payload.record_id),
        has_summary=await _alive_count(session, AiSummary, payload.record_id) > 0,
    )


def resolve_record_target(payload: RecordSoftDeletePayload) -> tuple[str, str]:
    return "record", payload.record_id


async def apply_record_soft_delete(
    session: AsyncSession, proposal: AgentProposal
) -> RecordSoftDeleteResult:
    """OP_RECORD_SOFT_DELETE 应用器（调用方事务内、不得自行 begin）：执行前
    重验已由注册表适配器完成；复用记录软删领域核心（级联语义与 HTTP 路由
    同源），掌握度重算登记为提交后动作（回滚不触发）。"""
    payload = parse_operation_payload(proposal, RecordSoftDeletePayload)
    record = await RecordService.get(session, payload.record_id)
    if record is None:
        raise CodedHTTPException(
            code="RECORD_NOT_FOUND", status_code=404, detail="学习记录不存在或已删除"
        )
    title = record.title
    affected_concepts = await RecordService.soft_delete_core(session, record)
    MasteryService.schedule_recompute_after_commit(session, affected_concepts)
    return RecordSoftDeleteResult(record_id=payload.record_id, title=title)


register_operation(
    OperationSpec(
        action=SOFT_DELETE_RECORD_ACTION,
        proposal_type=ProposalType.OP_RECORD_SOFT_DELETE,
        level=OperationLevel.L3,
        payload_schema=RecordSoftDeletePayload,
        result_schema=RecordSoftDeleteResult,
        applier=apply_record_soft_delete,
        capture_state=capture_record_delete_state,
        target_resolver=resolve_record_target,
    )
)
