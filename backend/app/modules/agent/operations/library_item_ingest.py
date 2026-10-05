"""ingest_library_item 操作注册项（通用 Agent 第三阶段工单 06，M2 执行闭环）。

计划内步骤动作（无独立薄工具，不经单步提案——07 多资料建课 Run 在此地基上
编排四类来源）：应用器复用 WEB 入库的事务内核心 ``create_web_ingest_rows``
（Record + 条目 + WEB_FETCH 任务同事务落库，确认前不发起任何网络请求），
result 携带 awaited_job_id——推进 worker 据此把 Run 转 WAITING_JOB，等待
抓取终态后自动续跑或失败分流（工单 06 机制）。创建类动作：无目标快照、
不在撤销范围。

重试幂等（07 收口）：抓取失败后条目已在库（同 URL 内容指纹），步骤重试
预查命中即复用既有条目、不重复入库——上次抓取失败的 WEB_FETCH 任务原地
重置回 PENDING 继续等待重新抓取（对齐资料库 retry_failed 通道语义；
「失败步骤可单独重试」＝重新尝试取得内容，Run 如实呈现，07 review 二轮）。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    parse_operation_payload,
    register_operation,
)
from app.modules.agent.schemas import LibraryItemIngestPayload, LibraryItemIngestResult
from app.modules.capture.ingest import create_web_ingest_rows
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.library.models import AgentProposal, LibraryItem, LibraryItemRecord
from app.modules.library.schemas import ProposalType
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus

# 动作标识（= 注册表 action；计划项动作枚举 INGEST_LIBRARY_ITEM 的映射值）。
INGEST_LIBRARY_ITEM_ACTION = "ingest_library_item"


async def _reused_ingest(
    session: AsyncSession, url: str, course_id: str | None
) -> LibraryItemIngestResult | None:
    """重试幂等预查：同 URL 且**同归类**的在库存活条目（上次执行建的、抓取
    失败）——复用其坐标，不重复入库。活动抓取任务仍等待之；上次抓取失败则
    原地重置 WEB_FETCH 任务回 PENDING 并等待重新抓取（字段集对齐资料库
    retry_failed 通道；Record 状态回 CONTENT_PROCESSING——web fetch worker
    的候选查询按该状态过滤，不重置则任务永不被领取；不新投，任务数不变）；
    已成功或无任务不再等待。归类与存活（未软删、未归档）不匹配则不复用，
    交由 create_web_ingest_rows 的重复拒绝如实失败（模型可改用
    update_library_item / add_shared_ref 处置既有条目——与本地文档侧
    _reusable_document_import 同口径，工单 07 review）。"""
    from hashlib import sha256

    content_hash = sha256(f"web:{url}".encode()).hexdigest()
    item_id = (
        await session.execute(
            select(LibraryItem.id)
            .where(
                LibraryItem.content_hash == content_hash,
                LibraryItem.course_id.is_(course_id),
                LibraryItem.deleted_at.is_(None),
                LibraryItem.status == "ACTIVE",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if item_id is None:
        return None
    record_id = (
        await session.execute(
            select(LibraryItemRecord.record_id)
            .where(LibraryItemRecord.library_item_id == item_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if record_id is None:
        return LibraryItemIngestResult(
            library_item_id=item_id, record_id=item_id, awaited_job_id=None
        )
    job = (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.record_id == record_id,
                ProcessingJob.job_type == ProcessingJobType.WEB_FETCH,
            )
            .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
            .limit(1)
        )
    ).one_or_none()
    awaited: str | None = None
    if job is not None:
        if job.status in (
            ProcessingJobStatus.PENDING.value,
            ProcessingJobStatus.RUNNING.value,
        ):
            awaited = job.id
        elif job.status == ProcessingJobStatus.FAILED.value:
            # 上次抓取失败：原地重置重跑（不新投）。宣布成功会让 Run 呈现
            # 完成而内容未取得——违反 spec「最终如实呈现部分成功」。
            now = utcnow()
            job.status = ProcessingJobStatus.PENDING
            job.attempts = 0
            job.progress = 0
            job.next_run_at = None
            job.error_code = None
            job.error_message = None
            job.started_at = None
            job.finished_at = None
            job.updated_at = now
            record = await session.get(Record, record_id)
            if record is not None and record.deleted_at is None:
                record.status = RecordStatus.CONTENT_PROCESSING
                record.updated_at = now
            item = await session.get(LibraryItem, item_id)
            if item is not None:
                item.updated_at = now
            await session.flush()
            awaited = job.id
    return LibraryItemIngestResult(
        library_item_id=item_id,
        record_id=record_id,
        awaited_job_id=awaited,
    )


async def apply_library_item_ingest(
    session: AsyncSession, proposal: AgentProposal
) -> LibraryItemIngestResult:
    """OP_LIBRARY_ITEM_INGEST 应用器（调用方事务内、不得自行 begin）：经
    WEB 入库核心建行并提交 WEB_FETCH 任务，返回等待核对对象（job_id）。"""
    payload = parse_operation_payload(proposal, LibraryItemIngestPayload)
    reused = await _reused_ingest(session, payload.url, payload.course_id)
    if reused is not None:
        return reused
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
