import asyncio
import json
import shutil
from pathlib import Path, PurePosixPath
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.capture.models import RecordFile
from app.modules.capture.schemas import RecordFileType
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus
from app.modules.search.service import SearchService
from app.modules.transcript.document_parser import (
    DocumentBlock,
    blocks_from_plain_text,
    read_blocks_jsonl,
)
from app.modules.transcript.models import DocumentSegment, Transcript, TranscriptSegment
from app.modules.transcript.sentences import (
    Sentence,
    content_hash,
    read_sentences_jsonl,
    sentences_from_plain_text,
)

_FINALIZE_LOCK = asyncio.Lock()


async def _read_source(
    data_dir: Path,
    result_data: dict[str, object],
    *,
    is_audio: bool,
) -> tuple[str, list[Sentence], list[DocumentBlock]] | None:
    """读单文件 source 中转，返回 (全文, 句子流, 文档内容块)；不可用返回 None。

    句子流两来源：jsonl（本票起）、旧 txt 行拆降级（音频 in-flight，无时间戳）；
    内容块两来源：blocks jsonl（票 03 起）、旧缓存纯文本切段降级（文档
    in-flight，无页码）。
    """
    cache_root = (data_dir / "cache").resolve()
    raw_path = result_data.get("source_text_path")
    if not isinstance(raw_path, str):
        return None
    path = (data_dir / Path(*PurePosixPath(raw_path).parts)).resolve()
    if not path.is_relative_to(cache_root):
        return None
    try:
        text = (await asyncio.to_thread(path.read_text, encoding="utf-8")).strip()
    except OSError:
        return None
    if not text:
        return None
    sentences: list[Sentence]
    raw_sentences_path = result_data.get("source_sentences_path")
    if isinstance(raw_sentences_path, str):
        sentences_path = (
            data_dir / Path(*PurePosixPath(raw_sentences_path).parts)
        ).resolve()
        if not sentences_path.is_relative_to(cache_root):
            return None
        try:
            sentences = await asyncio.to_thread(read_sentences_jsonl, sentences_path)
        except OSError:
            return None
    else:
        sentences = sentences_from_plain_text(text) if is_audio else []
    blocks: list[DocumentBlock] = []
    if not is_audio:
        raw_blocks_path = result_data.get("source_blocks_path")
        if isinstance(raw_blocks_path, str):
            blocks_path = (data_dir / Path(*PurePosixPath(raw_blocks_path).parts)).resolve()
            if not blocks_path.is_relative_to(cache_root):
                return None
            try:
                blocks = await asyncio.to_thread(read_blocks_jsonl, blocks_path)
            except OSError:
                return None
        else:
            blocks = blocks_from_plain_text(text)
    return text, sentences, blocks


def _build_segments(
    transcript_id: str,
    record_id: str,
    files_sentences: list[tuple[RecordFile, list[Sentence]]],
) -> list[TranscriptSegment]:
    """按文件 sequence_no 顺序建全记录连续分片；record_start_ms 为课堂拼接
    时间轴（前序文件 duration_ms 累加，非真实墙钟）；无时间戳句子四列全 NULL。"""
    segments: list[TranscriptSegment] = []
    record_offset_ms = 0
    for record_file, sentences in files_sentences:
        for sentence in sentences:
            if not sentence.text.strip():
                continue
            has_timeline = sentence.start_ms is not None and sentence.end_ms is not None
            file_start = sentence.start_ms if has_timeline else None
            file_end = sentence.end_ms if has_timeline else None
            segments.append(
                TranscriptSegment(
                    transcript_id=transcript_id,
                    record_id=record_id,
                    file_id=record_file.id,
                    sequence_no=len(segments),
                    record_start_ms=record_offset_ms + file_start
                    if file_start is not None
                    else None,
                    record_end_ms=record_offset_ms + file_end if file_end is not None else None,
                    file_start_ms=file_start,
                    file_end_ms=file_end,
                    content=sentence.text,
                    content_hash=content_hash(sentence.text),
                )
            )
        record_offset_ms += record_file.duration_ms or 0
    return segments


def _build_document_segments(
    record: Record,
    files_blocks: list[tuple[RecordFile, list[DocumentBlock]]],
) -> list[DocumentSegment]:
    """文档分片：逐块挂 record_file，sequence_no 记录内全局连续（跨文件递增）；
    course_id 随记录（收件箱记录为 NULL），course_material 路径本期恒 NULL。"""
    segments: list[DocumentSegment] = []
    for record_file, blocks in files_blocks:
        for block in blocks:
            segments.append(
                DocumentSegment(
                    course_id=record.course_id,
                    record_id=record.id,
                    record_file_id=record_file.id,
                    course_material_id=None,
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


async def finalize_record_if_ready(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    record_id: str,
) -> bool:
    # ponytail: process-local lock; move to a DB claim only if multiple writer processes are added.
    async with _FINALIZE_LOCK:
        return await _finalize_record_if_ready(session_factory, data_dir, record_id)


async def _finalize_record_if_ready(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    record_id: str,
) -> bool:
    async with session_factory() as session:
        record = await session.get(Record, record_id)
        if record is None or record.deleted_at is not None:
            return False
        existing_transcript = (
            await session.scalars(select(Transcript).where(Transcript.record_id == record_id))
        ).one_or_none()
        if existing_transcript is not None:
            return True
        files = list(
            (
                await session.scalars(
                    select(RecordFile)
                    .where(
                        RecordFile.record_id == record_id,
                        RecordFile.deleted_at.is_(None),
                    )
                    .order_by(RecordFile.sequence_no)
                )
            ).all()
        )
        jobs = list(
            (
                await session.scalars(
                    select(ProcessingJob).where(
                        ProcessingJob.record_id == record_id,
                        ProcessingJob.job_type.in_(
                            (ProcessingJobType.DOCUMENT_PARSE, ProcessingJobType.ASR)
                        ),
                    )
                )
            ).all()
        )
    if (
        not files
        or len(jobs) != len(files)
        or any(job.status != ProcessingJobStatus.SUCCEEDED for job in jobs)
    ):
        return False

    jobs_by_file: dict[str, ProcessingJob] = {}
    for job in jobs:
        input_data = cast(dict[str, object], json.loads(job.input_json))
        record_file_id = input_data.get("record_file_id")
        if not isinstance(record_file_id, str):
            return False
        jobs_by_file[record_file_id] = job

    texts: list[str] = []
    files_sentences: list[tuple[RecordFile, list[Sentence]]] = []
    files_blocks: list[tuple[RecordFile, list[DocumentBlock]]] = []
    for record_file in files:
        job = jobs_by_file.get(record_file.id)
        result_data = (
            cast(dict[str, object], json.loads(job.result_json))
            if job is not None and job.result_json
            else {}
        )
        source = await _read_source(
            data_dir,
            result_data,
            is_audio=record_file.file_type == RecordFileType.AUDIO,
        )
        if source is None:
            return False
        texts.append(source[0])
        files_sentences.append((record_file, source[1]))
        files_blocks.append((record_file, source[2]))

    now = utcnow()
    async with session_factory() as session, session.begin():
        record = await session.get(Record, record_id)
        if record is None or record.deleted_at is not None:
            return False
        current_jobs = list(
            (
                await session.scalars(
                    select(ProcessingJob).where(
                        ProcessingJob.record_id == record_id,
                        ProcessingJob.job_type.in_(
                            (ProcessingJobType.DOCUMENT_PARSE, ProcessingJobType.ASR)
                        ),
                    )
                )
            ).all()
        )
        if len(current_jobs) != len(files) or any(
            job.status != ProcessingJobStatus.SUCCEEDED for job in current_jobs
        ):
            return False
        transcript = (
            await session.scalars(select(Transcript).where(Transcript.record_id == record_id))
        ).one_or_none()
        if transcript is None:
            new_transcript = Transcript(
                record_id=record_id,
                language=(
                    "und"
                    if any(file.file_type == RecordFileType.DOCUMENT for file in files)
                    else "zh-CN"
                ),
                content="\n\n".join(texts),
                source_version=1,
                edited_by_user=False,
                created_at=now,
                updated_at=now,
            )
            session.add(new_transcript)
            await session.flush()
            session.add_all(
                _build_segments(new_transcript.id, record_id, files_sentences)
            )
            session.add_all(_build_document_segments(record, files_blocks))
        record.status = RecordStatus.SUMMARY_PENDING
        record.updated_at = now
        await session.flush()
        await SearchService.upsert_record_index(session, record_id)

    for cache_dir in (
        data_dir / "cache" / "audio" / record_id,
        data_dir / "cache" / "sources" / record_id,
    ):
        await asyncio.to_thread(shutil.rmtree, cache_dir, ignore_errors=True)
    from app.modules.summary.service import SummaryService

    await SummaryService.enqueue_if_eligible(session_factory, data_dir, record_id)
    return True


async def complete_source_job(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    record_id: str,
    job_id: str,
    result_json: str,
) -> bool:
    async with _FINALIZE_LOCK:
        async with session_factory() as session:
            files = list(
                (
                    await session.scalars(
                        select(RecordFile)
                        .where(
                            RecordFile.record_id == record_id,
                            RecordFile.deleted_at.is_(None),
                        )
                        .order_by(RecordFile.sequence_no)
                    )
                ).all()
            )
            jobs = list(
                (
                    await session.scalars(
                        select(ProcessingJob).where(
                            ProcessingJob.record_id == record_id,
                            ProcessingJob.job_type.in_(
                                (ProcessingJobType.DOCUMENT_PARSE, ProcessingJobType.ASR)
                            ),
                        )
                    )
                ).all()
            )

        ready = len(files) == len(jobs) and all(
            job.id == job_id or job.status == ProcessingJobStatus.SUCCEEDED for job in jobs
        )
        texts: list[str] = []
        files_sentences: list[tuple[RecordFile, list[Sentence]]] = []
        files_blocks: list[tuple[RecordFile, list[DocumentBlock]]] = []
        if ready:
            jobs_by_file: dict[str, ProcessingJob] = {}
            for job in jobs:
                input_data = cast(dict[str, object], json.loads(job.input_json))
                record_file_id = input_data.get("record_file_id")
                if not isinstance(record_file_id, str):
                    ready = False
                    break
                jobs_by_file[record_file_id] = job
            for record_file in files if ready else ():
                job = jobs_by_file.get(record_file.id)
                raw_result = (
                    result_json
                    if job is not None and job.id == job_id
                    else job.result_json
                    if job
                    else None
                )
                result_data = cast(dict[str, object], json.loads(raw_result)) if raw_result else {}
                source = await _read_source(
                    data_dir,
                    result_data,
                    is_audio=record_file.file_type == RecordFileType.AUDIO,
                )
                if source is None:
                    ready = False
                    break
                texts.append(source[0])
                files_sentences.append((record_file, source[1]))
                files_blocks.append((record_file, source[2]))

        now = utcnow()
        finalized = False
        async with session_factory() as session, session.begin():
            record = await session.get(Record, record_id)
            job = await session.get(ProcessingJob, job_id)
            if (
                record is None
                or record.deleted_at is not None
                or job is None
                or job.status != ProcessingJobStatus.RUNNING
            ):
                return False
            job.status = ProcessingJobStatus.SUCCEEDED
            job.progress = 1
            job.next_run_at = None
            job.result_json = result_json
            job.error_code = None
            job.error_message = None
            job.finished_at = now
            job.updated_at = now
            if ready:
                new_transcript = Transcript(
                    record_id=record_id,
                    language=(
                        "und"
                        if any(file.file_type == RecordFileType.DOCUMENT for file in files)
                        else "zh-CN"
                    ),
                    content="\n\n".join(texts),
                    source_version=1,
                    edited_by_user=False,
                    created_at=now,
                    updated_at=now,
                )
                session.add(new_transcript)
                await session.flush()
                session.add_all(_build_segments(new_transcript.id, record_id, files_sentences))
                session.add_all(_build_document_segments(record, files_blocks))
                record.status = RecordStatus.SUMMARY_PENDING
                record.updated_at = now
                finalized = True
            await session.flush()
            await SearchService.upsert_record_index(session, record_id)
        if finalized:
            for cache_dir in (
                data_dir / "cache" / "audio" / record_id,
                data_dir / "cache" / "sources" / record_id,
            ):
                await asyncio.to_thread(shutil.rmtree, cache_dir, ignore_errors=True)
            from app.modules.summary.service import SummaryService

            await SummaryService.enqueue_if_eligible(session_factory, data_dir, record_id)
        return True
