"""LIBRARY_BACKFILL 幂等回填 Worker（工单 02，ExistingCaptureAdapter 的存量映射）。

不重跑已成功处理链：回填只「建条目 + 建关联」，不触发解析/转写/总结——
那些链路要么早已成功（其产物直接复用），要么仍在自己的 Job 里跑。
扫描对象 = 未软删且尚无 library_item_records 链接的记录（LEFT JOIN 差集），
按 records.rowid 稳定游标分块；每块一个短事务并把游标/统计检查点写回
result_json，崩溃后重试从检查点续跑。扫描一轮发现仍有未链接记录（运行期
新捕获）则游标归零再扫，直到一轮扫空才 SUCCEEDED；并发新捕获由 capture
流程同事务调用 ensure_backfill_enqueued 兜底入队新任务。
「索引补建」无需本任务承担：segment_search_index / search_index 的启动幂等
回填（backfill_missing）已覆盖存量行。文件行读取走原生 SQL（不用
capture.models 的 RecordFile）：保持 library 不反向依赖 capture（fastapi.md
法定方向 capture → 下游域）。
"""

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, cast

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.capture.schemas import CaptureType
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.runner import (
    ClaimCheck,
    ClaimedJob,
    LoopFailure,
    Ready,
    RunnerContext,
    WorkerSpec,
    mark_failed,
    recover_running_to_failed,
)
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.library.models import LibraryItem, LibraryItemRecord
from app.modules.library.schemas import LibrarySourceType
from app.modules.record.models import Record
from app.modules.transcript.models import Transcript
from app.shared.events import RecordInvalidationNotifier

BACKFILL_JOB_TYPE = ProcessingJobType.LIBRARY_BACKFILL

_CHUNK = 200
# 安全阀：单次执行最多块数（200×5000=百万级记录），防御异常并发写入下的死循环。
_MAX_CHUNKS_PER_RUN = 5000

_UNLINKED_RECORD_IDS_SQL = text(
    "SELECT r.id, r.rowid AS rid FROM records r "
    "LEFT JOIN library_item_records lir ON lir.record_id = r.id "
    "WHERE r.rowid > :cursor AND r.deleted_at IS NULL AND lir.record_id IS NULL "
    "ORDER BY r.rowid LIMIT :limit"
)

_REMAINING_UNLINKED_SQL = text(
    "SELECT count(*) FROM records r "
    "LEFT JOIN library_item_records lir ON lir.record_id = r.id "
    "WHERE r.deleted_at IS NULL AND lir.record_id IS NULL"
)

_FILE_META_KEYS = ("id", "original_name", "mime_type", "file_size")

_RECORD_FILES_SQL = text(
    "SELECT id, file_type, file_path, original_name, mime_type, file_size, "
    "sequence_no, content_hash FROM record_files "
    "WHERE record_id = :rid AND deleted_at IS NULL ORDER BY sequence_no"
)


@dataclass(frozen=True)
class _FileRow:
    id: str
    file_type: str
    file_path: str
    original_name: str
    mime_type: str
    file_size: int
    sequence_no: int
    content_hash: str


async def ensure_backfill_enqueued(session: AsyncSession) -> bool:
    """同事务入队钩子：无活动（PENDING/RUNNING）回填任务时新建一个。

    capture 流程在创建 Record 的同一事务内调用（回滚时任务随之消失，
    不产生孤儿任务）；启动 lifespan 与本 Worker 写回兜底同样调用。
    """
    active = await session.scalar(
        select(ProcessingJob.id)
        .where(
            ProcessingJob.job_type == BACKFILL_JOB_TYPE,
            ProcessingJob.status.in_((ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING)),
        )
        .limit(1)
    )
    if active is not None:
        return False
    session.add(
        ProcessingJob(
            job_type=BACKFILL_JOB_TYPE,
            status=ProcessingJobStatus.PENDING,
            input_json="{}",
        )
    )
    return True


def _load_state(raw: str | None) -> dict[str, Any]:
    """检查点状态：四个计数值 + pass_base / finished_reason / skipped_unlinked。"""
    defaults: dict[str, Any] = {
        "cursor": 0,
        "scanned": 0,
        "created_items": 0,
        "linked_records": 0,
        "pass_base": 0,
    }
    if not raw:
        return defaults
    try:
        state = cast(dict[str, Any], json.loads(raw))
    except ValueError:
        state = {}
    merged = dict(defaults)
    for key in defaults:
        merged[key] = int(state.get(key, defaults[key]))
    for key in ("finished_reason", "skipped_unlinked"):
        if key in state:
            merged[key] = state[key]
    return merged


def _files_meta(files: list[_FileRow]) -> list[dict[str, Any]]:
    return [{key: getattr(f, key) for key in _FILE_META_KEYS} for f in files]


async def _link_record(session: AsyncSession, record_id: str, now: datetime) -> int:
    """为单条未链接记录建条目与关联（幂等前提：调用方已按无链接过滤）。

    返回新建条目数；无正文且无文件、或记录已软删时返回 0（下一轮扫描
    仍会视其为未链接，待其内容产生后再补——与「不重跑已成功链」不冲突）。
    """
    record = await session.get(Record, record_id)
    if record is None or record.deleted_at is not None:
        return 0
    file_rows = (await session.execute(_RECORD_FILES_SQL, {"rid": record_id})).all()
    files = [
        _FileRow(
            id=cast(str, row[0]),
            file_type=cast(str, row[1]),
            file_path=cast(str, row[2]),
            original_name=cast(str, row[3]),
            mime_type=cast(str, row[4]),
            file_size=cast(int, row[5]),
            sequence_no=cast(int, row[6]),
            content_hash=cast(str, row[7]),
        )
        for row in file_rows
    ]

    async def _add(
        *,
        source_type: LibrarySourceType,
        content_hash: str,
        local_path: str | None,
        mime_type: str | None,
        file_size: int | None,
        metadata: dict[str, Any],
        sequence_no: int,
    ) -> None:
        item = LibraryItem(
            course_id=record.course_id,
            source_type=source_type,
            title=record.title,
            local_path=local_path,
            mime_type=mime_type,
            file_size=file_size,
            content_hash=content_hash,
            metadata_json=json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
            created_at=now,
            updated_at=now,
        )
        session.add(item)
        await session.flush()
        session.add(
            LibraryItemRecord(
                library_item_id=item.id,
                record_id=record_id,
                role="PRIMARY",
                sequence_no=sequence_no,
                created_at=now,
            )
        )

    if record.capture_type in (CaptureType.PASTE, CaptureType.QUICK_NOTE):
        content = await session.scalar(
            select(Transcript.content)
            .where(Transcript.record_id == record_id, Transcript.deleted_at.is_(None))
            .order_by(Transcript.created_at)
            .limit(1)
        )
        if content is None:
            return 0
        size = len(content.encode("utf-8"))
        await _add(
            source_type=LibrarySourceType.TEXT,
            content_hash=sha256(content.encode("utf-8")).hexdigest(),
            local_path=None,
            mime_type="text/plain",
            file_size=size,
            metadata={"kind": record.capture_type, "char_count": len(content)},
            sequence_no=0,
        )
        return 1

    if not files:
        return 0
    if record.capture_type == CaptureType.MULTI_SOURCE:
        # 多来源 Record：逐文件一来源条目（M:N 的「多来源」方向）。
        for record_file in files:
            await _add(
                source_type=LibrarySourceType.AUDIO
                if record_file.file_type == "AUDIO"
                else LibrarySourceType.DOCUMENT,
                content_hash=record_file.content_hash,
                local_path=record_file.file_path,
                mime_type=record_file.mime_type,
                file_size=record_file.file_size,
                metadata={
                    "kind": record.capture_type,
                    "sequence_no": record_file.sequence_no,
                    "files": _files_meta([record_file]),
                },
                sequence_no=record_file.sequence_no,
            )
        return len(files)
    # 单来源类型：一条 Record 一个条目；hash = 有序文件哈希拼接（确定性、幂等）。
    if record.capture_type in (CaptureType.RECORDING, CaptureType.AUDIO_IMPORT):
        source_type = LibrarySourceType.AUDIO
    elif record.capture_type == CaptureType.DOCUMENT_IMPORT:
        source_type = LibrarySourceType.DOCUMENT
    else:  # CLIP（剪藏记录随工单 03 产生，此处按 WEB 防御性映射）
        source_type = LibrarySourceType.WEB
    aggregate_hash = sha256("|".join(f.content_hash for f in files).encode()).hexdigest()
    await _add(
        source_type=source_type,
        content_hash=aggregate_hash,
        local_path=files[0].file_path,
        mime_type=files[0].mime_type,
        file_size=sum(f.file_size for f in files),
        metadata={"kind": record.capture_type, "files": _files_meta(files)},
        sequence_no=0,
    )
    return 1


async def process_chunk(
    session_factory: async_sessionmaker[AsyncSession], job_id: str, chunk: int
) -> bool:
    """一块一事务（建条目/关联 + 游标检查点）；返回该任务是否已到终局。"""
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, job_id)
        if job is None or job.status != ProcessingJobStatus.RUNNING:
            return True
        state = _load_state(job.result_json)
        rows = (
            await session.execute(
                _UNLINKED_RECORD_IDS_SQL, {"cursor": state["cursor"], "limit": chunk}
            )
        ).all()
        now = utcnow()
        max_rowid = state["cursor"]
        for row in rows:
            max_rowid = max(max_rowid, cast(int, row.rid))
            state["scanned"] += 1
            created = await _link_record(session, cast(str, row.id), now)
            state["created_items"] += created
            if created > 0:
                state["linked_records"] += 1
        # 原生 text() 不触发 autoflush：计数前必须显式落盘本块新建的链接行。
        await session.flush()
        remaining = cast(int, await session.scalar(_REMAINING_UNLINKED_SQL))
        if len(rows) < chunk:
            # 一轮扫完：全链接 → 完结；本轮零新建且仍有未链接（不可映射记录，
            # 如既无文件又无正文）→ 停滞终止记 skipped，防止任务自旋。
            if remaining == 0:
                state["finished_reason"] = "complete"
                job.result_json = json.dumps(state, separators=(",", ":"))
                return True
            if state["created_items"] == state.get("pass_base", 0):
                state["finished_reason"] = "stalled"
                state["skipped_unlinked"] = remaining
                logger.warning("library_backfill_stalled", skipped_unlinked=remaining)
                job.result_json = json.dumps(state, separators=(",", ":"))
                return True
            # 并发新增未链接记录：游标归零重扫（pass_base 重置以便下轮再测停滞）。
            state["cursor"] = 0
            state["pass_base"] = state["created_items"]
        else:
            state["cursor"] = max_rowid
        job.result_json = json.dumps(state, separators=(",", ":"))
        job.progress = min(0.99, state["scanned"] / max(state["scanned"] + remaining, 1))
        return False


@dataclass(frozen=True)
class BackfillJobCtx(ClaimedJob):
    """全局单例任务上下文：无 record 坐标（record_id 传空串，runner 协议点）。"""


async def find_candidate(session: AsyncSession, _now: datetime) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.job_type == BACKFILL_JOB_TYPE,
                ProcessingJob.status == ProcessingJobStatus.PENDING,
            )
            .order_by(ProcessingJob.created_at)
            .limit(1)
        )
    ).one_or_none()


async def validate_claim(
    _session: AsyncSession,
    job: ProcessingJob,
    _record_id: str,
    _preflight: None,
) -> ClaimCheck[BackfillJobCtx]:
    # 全局单例任务：无外部前置条件，恒可领取。
    return Ready(BackfillJobCtx(job_id=job.id, record_id=""))


async def execute(
    ctx: BackfillJobCtx,
    _runtime: RunnerContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    """返回是否自然终局（全部块扫空）；预算耗尽返回 False 由 writeback 记可重试失败。"""
    for _ in range(_MAX_CHUNKS_PER_RUN):
        if await process_chunk(session_factory, ctx.job_id, _CHUNK):
            return True
    logger.warning("library_backfill_chunk_budget_exhausted", job_id=ctx.job_id)
    return False


async def writeback(
    ctx: BackfillJobCtx,
    finished: bool,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, ctx.job_id)
        if job is None or job.status != ProcessingJobStatus.RUNNING:
            return False
        if not finished:
            # 块预算耗尽 = 异常规模：如实记 FAILED（可重试，从检查点续跑），
            # 不制造假 SUCCEEDED。
            mark_failed(
                job,
                code="LIBRARY_BACKFILL_FAILED",
                message="资料库回填超出单次块预算，稍后将自动续跑",
                now=utcnow(),
            )
            return True
        job.status = ProcessingJobStatus.SUCCEEDED
        job.progress = 1
        completed_at = utcnow()
        job.finished_at = completed_at
        job.updated_at = completed_at
        # 写回兜底：正常完结且仍有未链接记录（执行期并发新捕获）才补后续任务——
        # 无条件入队会让「成功→新任务→空扫成功」无限自旋；stalled（不可映射
        # 记录）同样不补，待重启或下次捕获钩子再试。
        stats = _load_state(job.result_json)
        if stats.get("finished_reason") == "complete" or "finished_reason" not in stats:
            remaining = cast(int, await session.scalar(_REMAINING_UNLINKED_SQL))
            if remaining > 0:
                await ensure_backfill_enqueued(session)
        logger.info(
            "library_backfill_finished",
            created_items=stats["created_items"],
            linked_records=stats["linked_records"],
        )
    return True


def failure_code(_ctx: BackfillJobCtx, _exc: Exception) -> str | None:
    return "LIBRARY_BACKFILL_FAILED"


async def apply_failure(
    _ctx: BackfillJobCtx,
    _session: AsyncSession,
    job: ProcessingJob,
    _record: Record | None,
    error_code: str,
    now: datetime,
) -> bool:
    mark_failed(job, code=error_code, message="资料库回填失败，稍后将自动重试", now=now)
    return True


def backfill_spec(
    session_factory: async_sessionmaker[AsyncSession],
    record_notifier: RecordInvalidationNotifier,
) -> WorkerSpec[None, BackfillJobCtx, bool]:
    def classify(_exc: Exception) -> LoopFailure:
        return LoopFailure(event="library_backfill_worker_unexpected_failure")

    async def recover() -> None:
        # 回填可从 result_json 检查点续跑：中断按 FAILED 记账后由重试机制接续。
        await recover_running_to_failed(
            session_factory,
            record_notifier,
            BACKFILL_JOB_TYPE,
            "资料库回填被意外中断",
        )

    return WorkerSpec(
        name="library_backfill_worker",
        job_type=BACKFILL_JOB_TYPE,
        poll_interval=2.0,
        find_candidate=find_candidate,
        validate_claim=validate_claim,
        execute=lambda ctx, runtime: execute(ctx, runtime, session_factory),
        writeback=lambda ctx, result: writeback(ctx, result, session_factory),
        failure_code=failure_code,
        apply_failure=apply_failure,
        recover_interrupted=recover,
        classify_loop_error=classify,
    )
