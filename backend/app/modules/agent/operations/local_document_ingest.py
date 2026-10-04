"""ingest_local_document 操作注册项（通用 Agent 第三阶段工单 07，M2 执行闭环）。

计划内步骤动作（无独立薄工具，不经单步提案——多资料建课 Run 的本地文档
来源）：应用器复用 document import 的导入核心 ``create_document_ingest_rows``
（Record + 文件行 + DOCUMENT_PARSE 任务同事务落库，路径由用户在对话中明确
提供），result 携带 awaited_job_id——推进 worker 据此把 Run 转 WAITING_JOB，
解析完成后自动接续（工单 06 机制）。创建类动作：无目标快照、不在撤销范围。

重试幂等（工单 07 收口）：同课程同内容指纹的既有导入直接复用——上次解析
失败时新投解析任务继续等待，已成功则不再等待直接落定（大 PDF 仍按整本
一条记录处理，按章拆分属书籍拆章波次，不引入临时解析路径）。
"""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.data_dir import bound_data_dir
from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    parse_operation_payload,
    register_operation,
)
from app.modules.agent.schemas import (
    LocalDocumentIngestPayload,
    LocalDocumentIngestResult,
)
from app.modules.capture.document_import import create_document_ingest_rows
from app.modules.library.models import AgentProposal
from app.modules.library.schemas import ProposalType
from app.shared.errors import CodedHTTPException

# 动作标识（= 注册表 action；计划项动作枚举 INGEST_LOCAL_DOCUMENT 的映射值）。
INGEST_LOCAL_DOCUMENT_ACTION = "ingest_local_document"


async def apply_local_document_ingest(
    session: AsyncSession, proposal: AgentProposal
) -> LocalDocumentIngestResult:
    """OP_LOCAL_DOCUMENT_INGEST 应用器（调用方事务内、不得自行 begin）：经
    document import 核心建行并提交解析任务，返回等待核对对象（job_id）。"""
    payload = parse_operation_payload(proposal, LocalDocumentIngestPayload)
    data_dir = bound_data_dir()
    if data_dir is None:
        raise CodedHTTPException(
            code="DATA_DIR_UNBOUND",
            status_code=500,
            detail="数据目录未初始化，无法导入本地文档",
        )
    record_id, file_id, job_id = await create_document_ingest_rows(
        session,
        data_dir,
        payload.course_id,
        Path(payload.path),
        title=payload.title,
    )
    return LocalDocumentIngestResult(record_id=record_id, file_id=file_id, awaited_job_id=job_id)


register_operation(
    OperationSpec(
        action=INGEST_LOCAL_DOCUMENT_ACTION,
        proposal_type=ProposalType.OP_LOCAL_DOCUMENT_INGEST,
        level=OperationLevel.L1,
        payload_schema=LocalDocumentIngestPayload,
        result_schema=LocalDocumentIngestResult,
        applier=apply_local_document_ingest,
        undo_reason="文档导入产生记录与后台解析任务，如需移除请在记录页手动删除",
        waits_for_job=True,
    )
)
