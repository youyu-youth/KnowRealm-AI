"""WEB_FETCH 执行体：网页剪藏的抓取与净化产物落库（工单 03）。

写回单事务完成：Job SUCCEEDED + Record 状态推进 + Transcript（净化正文）
+ DocumentSegments（library_item 直挂，0026 XOR 另一分支的首个写入者）
+ LibraryItem 快照元数据更新 + 全局/分片搜索索引。净化快照先落 cache/
临时文件再 os.replace 进 files/（该目录只接收完整文件，随全量导出走）。
失败一次性终态（登录墙/不可达不重试轰炸），用户侧经「重新导入 / 降级
手动粘贴」闭环（通用 retry 端点属工单 05）；进程中断经重启恢复在
attempts 预算内自动重投（对齐 DOCUMENT_PARSE 恢复形态，工单 08）。
"""

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Protocol, cast

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.capture.web_clip import ClipContent, WebClipError
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.runner import (
    ClaimCheck,
    ClaimedJob,
    LoopFailure,
    Ready,
    RunnerContext,
    WorkerSpec,
    mark_failed,
)
from app.modules.jobs.schemas import ProcessingJobErrorCode, ProcessingJobStatus, ProcessingJobType
from app.modules.library.models import LibraryItem
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus
from app.modules.search.segment_service import SegmentSearchService
from app.modules.search.service import SearchService
from app.modules.transcript.document_parser import DocumentBlock, blocks_from_plain_text
from app.modules.transcript.models import DocumentSegment, Transcript
from app.modules.transcript.sentences import content_hash
from app.shared.events import RecordInvalidationNotifier

ERROR_MESSAGES = {
    ProcessingJobErrorCode.WEB_FETCH_BLOCKED_URL: "目标地址属于受限网络范围",
    ProcessingJobErrorCode.WEB_FETCH_CONTENT_TOO_LARGE: "页面内容超过大小上限",
    ProcessingJobErrorCode.WEB_FETCH_UNSUPPORTED_CONTENT_TYPE: "页面类型不受支持",
    ProcessingJobErrorCode.WEB_FETCH_UNREACHABLE: "目标站点无法访问",
    ProcessingJobErrorCode.WEB_FETCH_EXTRACT_FAILED: "正文提取失败，可改用手动粘贴",
    ProcessingJobErrorCode.WORKER_INTERRUPTED: "网页抓取被意外中断",
    ProcessingJobErrorCode.INTERNAL_ERROR: "网页抓取失败",
}


class ClipFetcher(Protocol):
    """抓取+提取最小契约：生产 WebClipAdapter 与测试 fake 共同满足。"""

    async def fetch_and_extract(self, url: str) -> ClipContent: ...


@dataclass(frozen=True)
class ClaimedWebFetch(ClaimedJob):
    url: str
    library_item_id: str


async def find_candidate(session: AsyncSession, now: datetime) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .join(Record, ProcessingJob.record_id == Record.id)
            .where(
                ProcessingJob.job_type == ProcessingJobType.WEB_FETCH,
                ProcessingJob.status == ProcessingJobStatus.PENDING,
                Record.deleted_at.is_(None),
                Record.status == RecordStatus.CONTENT_PROCESSING,
                (ProcessingJob.next_run_at.is_(None) | (ProcessingJob.next_run_at <= now)),
            )
            .order_by(ProcessingJob.created_at)
            .limit(1)
        )
    ).one_or_none()


async def validate_claim(
    session: AsyncSession,
    job: ProcessingJob,
    record_id: str,
    _payload: None,
) -> ClaimCheck[ClaimedWebFetch]:
    input_data: object = json.loads(job.input_json)
    url = ""
    if isinstance(input_data, dict):
        raw_url = cast(dict[str, object], input_data).get("url")
        if isinstance(raw_url, str):
            url = raw_url
    return Ready(
        ClaimedWebFetch(
            job_id=job.id, record_id=record_id, url=url, library_item_id=job.library_item_id or ""
        )
    )


async def execute(
    ctx: ClaimedWebFetch,
    _runtime: RunnerContext,
    session_factory: async_sessionmaker[AsyncSession],
    adapter: ClipFetcher,
) -> ClipContent | None:
    """领取后二次确认仍 RUNNING 且记录未删，才发起抓取（删除竞态防线）。"""
    async with session_factory() as session:
        active_job = (
            await session.execute(
                select(ProcessingJob.id)
                .join(Record, ProcessingJob.record_id == Record.id)
                .where(
                    ProcessingJob.id == ctx.job_id,
                    ProcessingJob.status == ProcessingJobStatus.RUNNING,
                    Record.id == ctx.record_id,
                    Record.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
    if active_job is None:
        return None
    return await adapter.fetch_and_extract(ctx.url)


def _build_web_segments(
    record: Record, library_item_id: str, blocks: list[DocumentBlock]
) -> list[DocumentSegment]:
    segments: list[DocumentSegment] = []
    for block in blocks:
        segments.append(
            DocumentSegment(
                course_id=record.course_id,
                record_id=record.id,
                record_file_id=None,
                library_item_id=library_item_id,
                sequence_no=len(segments),
                page_no=block.page_no,
                section_title=None,
                content=block.content,
                start_offset=block.start_offset,
                end_offset=block.end_offset,
                content_hash=content_hash(block.content),
            )
        )
    return segments


async def writeback(
    ctx: ClaimedWebFetch,
    clip: ClipContent,
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
) -> bool:
    # 净化快照：cache 临时写 → fsync → replace 进 files/（导出与备份语义同 record 文件）。
    cache_dir = data_dir / "cache" / "webclips"
    cache_dir.mkdir(parents=True, exist_ok=True)
    temporary_path = cache_dir / f"{ctx.job_id}.tmp"
    payload = clip.text.encode("utf-8")
    await asyncio.to_thread(_write_temp, temporary_path, payload)
    snapshot_rel = f"files/{ctx.record_id}/{ctx.job_id}.md"
    final_path = data_dir / "files" / ctx.record_id / f"{ctx.job_id}.md"
    final_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(os.replace, temporary_path, final_path)

    now = utcnow()
    async with session_factory() as session, session.begin():
        record = await session.get(Record, ctx.record_id)
        job = await session.get(ProcessingJob, ctx.job_id)
        if (
            record is None
            or record.deleted_at is not None
            or job is None
            or job.status != ProcessingJobStatus.RUNNING
        ):
            await asyncio.to_thread(final_path.unlink, True)
            return False
        item = (
            await session.scalars(select(LibraryItem).where(LibraryItem.id == ctx.library_item_id))
        ).one_or_none()
        job.status = ProcessingJobStatus.SUCCEEDED
        job.progress = 1
        job.next_run_at = None
        job.result_json = json.dumps(
            {"snapshot_path": snapshot_rel, "title": clip.title}, ensure_ascii=False
        )
        job.error_code = None
        job.error_message = None
        job.finished_at = now
        job.updated_at = now
        if item is not None:
            if clip.title:
                item.title = clip.title
                record.title = clip.title
            # content_hash 保持 ingest 时的 URL 哈希（同 URL 重复导入的判重锚），
            # 正文哈希记入 metadata——REFETCH（同 URL 内容变化=新条目）属工单 05。
            item.fetched_at = now
            item.local_path = snapshot_rel
            item.mime_type = "text/markdown"
            item.file_size = len(payload)
            item.metadata_json = json.dumps(
                {**clip.metadata, "content_hash": sha256(payload).hexdigest()},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            item.updated_at = now
        existing_transcript = (
            await session.scalars(select(Transcript).where(Transcript.record_id == record.id))
        ).one_or_none()
        if existing_transcript is None:
            session.add(
                Transcript(
                    record_id=record.id,
                    language="und",
                    content=clip.text,
                    source_version=1,
                    edited_by_user=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add_all(
                _build_web_segments(record, ctx.library_item_id, blocks_from_plain_text(clip.text))
            )
        record.status = (
            RecordStatus.SUMMARY_PENDING if record.course_id is not None else RecordStatus.NOTE
        )
        record.updated_at = now
        has_course = record.course_id is not None
        await session.flush()
        await SearchService.upsert_record_index(session, record.id)
        await SegmentSearchService.upsert_record_segments(session, record.id)

    if has_course:
        from app.modules.summary.service import SummaryService

        await SummaryService.enqueue_if_eligible_best_effort(
            session_factory,
            data_dir,
            record.id,
            log_event="web_clip_summary_enqueue_failed",
            error_code="WEB_CLIP_SUMMARY_ENQUEUE_FAILED",
        )
    return True


def _write_temp(path: Path, payload: bytes) -> None:
    # 覆盖写而非排他创建：中断重投会撞上次「写到一半 / 未 replace」的同名
    # 残留 tmp（进程中断窗口，该目录无启动清理），排他创建会让重投连续失败
    # 耗尽恢复预算；tmp 是纯草稿（唯一消费方是紧随的 os.replace，领取原语
    # 保证同 job 唯一领取者），覆盖无语义损失（工单 08）。
    with path.open("wb") as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())


def failure_code(_ctx: ClaimedWebFetch, exc: Exception) -> str | None:
    if isinstance(exc, WebClipError):
        return exc.code
    # loguru sink 不渲染 kwargs：错误码内联进消息；exception 附完整堆栈
    logger.exception(f"web_fetch_failed error_code={ProcessingJobErrorCode.INTERNAL_ERROR}")
    return ProcessingJobErrorCode.INTERNAL_ERROR


async def apply_failure(
    _ctx: ClaimedWebFetch,
    _session: AsyncSession,
    job: ProcessingJob,
    record: Record | None,
    error_code: str,
    now: datetime,
) -> bool:
    if record is None or record.deleted_at is not None:
        return False
    code = ProcessingJobErrorCode(error_code)
    mark_failed(job, code=code.value, message=ERROR_MESSAGES.get(code, "网页抓取失败"), now=now)
    record.status = RecordStatus.FAILED
    record.updated_at = now
    return True


async def recover_running(
    session_factory: async_sessionmaker[AsyncSession],
    record_notifier: RecordInvalidationNotifier,
    code: ProcessingJobErrorCode,
) -> None:
    now = utcnow()
    record_ids: set[str] = set()
    async with session_factory() as session, session.begin():
        jobs = (
            await session.scalars(
                select(ProcessingJob)
                .join(Record, ProcessingJob.record_id == Record.id)
                .where(
                    ProcessingJob.job_type == ProcessingJobType.WEB_FETCH,
                    ProcessingJob.status == ProcessingJobStatus.RUNNING,
                    Record.deleted_at.is_(None),
                )
            )
        ).all()
        for job in jobs:
            if job.record_id is not None:
                record_ids.add(job.record_id)
            message = ERROR_MESSAGES.get(code, "网页抓取失败")
            if job.attempts < job.max_attempts:
                # 进程中断 ≠ 业务失败：预算内回 PENDING 自动重投（对齐
                # document_worker.recover_running 形态），Record 维持
                # CONTENT_PROCESSING 供 find_candidate 照常命中，等待中的
                # Run 经领取核对自动接续（spec US32 自动续跑）。
                job.status = ProcessingJobStatus.PENDING
                job.next_run_at = now + timedelta(seconds=2 ** max(job.attempts, 0))
            else:
                mark_failed(job, code=code.value, message=message, now=now)
                if job.record_id is not None:
                    record = await session.get(Record, job.record_id)
                    if record is not None:
                        record.status = RecordStatus.FAILED
                        record.updated_at = now
            job.error_code = code.value
            job.error_message = message
            job.updated_at = now
        await session.flush()
    for record_id in record_ids:
        await record_notifier.notify(record_id)


def classify_loop_error(_exc: Exception) -> LoopFailure:
    return LoopFailure(
        event="web_fetch_worker_unexpected_failure",
        error_code=ProcessingJobErrorCode.INTERNAL_ERROR,
        pause=False,
    )


def web_fetch_spec(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    record_notifier: RecordInvalidationNotifier,
    adapter: ClipFetcher | None = None,
) -> WorkerSpec[None, ClaimedWebFetch, ClipContent]:
    from app.modules.capture.web_clip import WebClipAdapter

    clip_adapter = adapter if adapter is not None else WebClipAdapter()

    def classify(exc: Exception) -> LoopFailure:
        return classify_loop_error(exc)

    async def recover() -> None:
        await recover_running(
            session_factory, record_notifier, ProcessingJobErrorCode.WORKER_INTERRUPTED
        )

    return WorkerSpec[None, ClaimedWebFetch, ClipContent](
        name="web_fetch_worker",
        job_type=ProcessingJobType.WEB_FETCH,
        poll_interval=1,
        find_candidate=find_candidate,
        validate_claim=validate_claim,
        execute=lambda ctx, runtime: execute(ctx, runtime, session_factory, clip_adapter),
        writeback=lambda ctx, result: writeback(ctx, result, session_factory, data_dir),
        failure_code=failure_code,
        apply_failure=apply_failure,
        recover_interrupted=recover,
        classify_loop_error=classify,
        clock=utcnow,
    )
