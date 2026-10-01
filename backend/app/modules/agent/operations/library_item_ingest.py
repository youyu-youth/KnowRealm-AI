"""ingest_library_item 操作注册项（通用 Agent 第三阶段工单 06，M2 执行闭环）。

计划内步骤动作（无独立薄工具，不经单步提案——07 多资料建课 Run 在此地基上
编排四类来源）：应用器复用 WEB 入库的事务内核心 ``create_web_ingest_rows``
（Record + 条目 + WEB_FETCH 任务同事务落库，确认前不发起任何网络请求），
result 携带 awaited_job_id——推进 worker 据此把 Run 转 WAITING_JOB，等待
抓取终态后自动续跑或失败分流（工单 06 机制）。创建类动作：无目标快照、
不在撤销范围。

重试边界（07 收口）：抓取失败后资料条目已在库（同 URL 内容指纹），本动作
重试会命中重复内容拒绝——失败条目的正确处置走资料库既有重试 / 手动粘贴
通道；「失败步骤可单独重试」对导入类步骤的幂等语义随 07 多资料票收口。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    parse_operation_payload,
    register_operation,
)
from app.modules.agent.schemas import LibraryItemIngestPayload, LibraryItemIngestResult
from app.modules.capture.ingest import create_web_ingest_rows
from app.modules.library.models import AgentProposal
from app.modules.library.schemas import ProposalType

# 动作标识（= 注册表 action；计划项动作枚举 INGEST_LIBRARY_ITEM 的映射值）。
INGEST_LIBRARY_ITEM_ACTION = "ingest_library_item"


async def apply_library_item_ingest(
    session: AsyncSession, proposal: AgentProposal
) -> LibraryItemIngestResult:
    """OP_LIBRARY_ITEM_INGEST 应用器（调用方事务内、不得自行 begin）：经
    WEB 入库核心建行并提交 WEB_FETCH 任务，返回等待核对对象（job_id）。"""
    payload = parse_operation_payload(proposal, LibraryItemIngestPayload)
    record_id, item_id, job_id = await create_web_ingest_rows(
        session,
        payload.url,
        payload.course_id,
        allow_duplicate=False,
        title=payload.title,
    )
    return LibraryItemIngestResult(
        library_item_id=item_id, record_id=record_id, awaited_job_id=job_id
    )


register_operation(
    OperationSpec(
        action=INGEST_LIBRARY_ITEM_ACTION,
        proposal_type=ProposalType.OP_LIBRARY_ITEM_INGEST,
        level=OperationLevel.L1,
        payload_schema=LibraryItemIngestPayload,
        result_schema=LibraryItemIngestResult,
        applier=apply_library_item_ingest,
        undo_reason="资料导入产生条目与后台抓取任务，如需移除请在资料库手动删除",
        waits_for_job=True,
    )
)
