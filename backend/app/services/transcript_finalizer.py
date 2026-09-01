import asyncio
import json
import shutil
from pathlib import Path, PurePosixPath
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.models.document import ProcessingJob, RecordFile, Transcript
from app.models.record import Record
from app.schemas.document import ProcessingJobStatus, ProcessingJobType, RecordFileType
from app.schemas.record import RecordStatus

_FINALIZE_LOCK = asyncio.Lock()


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
    cache_root = (data_dir / "cache").resolve()
    for record_file in files:
        job = jobs_by_file.get(record_file.id)
        result_data = (
            cast(dict[str, object], json.loads(job.result_json))
            if job is not None and job.result_json
            else {}
        )
        raw_path = result_data.get("source_text_path")
        if not isinstance(raw_path, str):
            return False
        path = (data_dir / Path(*PurePosixPath(raw_path).parts)).resolve()
        if not path.is_relative_to(cache_root):
            return False
        try:
            text = (await asyncio.to_thread(path.read_text, encoding="utf-8")).strip()
        except OSError:
            return False
        if not text:
            return False
        texts.append(text)

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
            session.add(
                Transcript(
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
            )
        record.status = RecordStatus.SUMMARY_PENDING
        record.updated_at = now
        await session.flush()

    for cache_dir in (
        data_dir / "cache" / "audio" / record_id,
        data_dir / "cache" / "sources" / record_id,
    ):
        await asyncio.to_thread(shutil.rmtree, cache_dir, ignore_errors=True)
    from app.services.summary_service import SummaryService

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
        if ready:
            jobs_by_file: dict[str, ProcessingJob] = {}
            for job in jobs:
                input_data = cast(dict[str, object], json.loads(job.input_json))
                record_file_id = input_data.get("record_file_id")
                if not isinstance(record_file_id, str):
                    ready = False
                    break
                jobs_by_file[record_file_id] = job
            cache_root = (data_dir / "cache").resolve()
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
                raw_path = result_data.get("source_text_path")
                if not isinstance(raw_path, str):
                    ready = False
                    break
                path = (data_dir / Path(*PurePosixPath(raw_path).parts)).resolve()
                if not path.is_relative_to(cache_root):
                    ready = False
                    break
                try:
                    text = (await asyncio.to_thread(path.read_text, encoding="utf-8")).strip()
                except OSError:
                    ready = False
                    break
                if not text:
                    ready = False
                    break
                texts.append(text)

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
                session.add(
                    Transcript(
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
                )
                record.status = RecordStatus.SUMMARY_PENDING
                record.updated_at = now
                finalized = True
            await session.flush()
        if finalized:
            for cache_dir in (
                data_dir / "cache" / "audio" / record_id,
                data_dir / "cache" / "sources" / record_id,
            ):
                await asyncio.to_thread(shutil.rmtree, cache_dir, ignore_errors=True)
            from app.services.summary_service import SummaryService

            await SummaryService.enqueue_if_eligible(session_factory, data_dir, record_id)
        return True
