"""音频转码 + ASR 双流水线执行体描述（任务循环骨架见 job_runner.py，ADR-0012）。

单任务内领取依序双试：先 AUDIO_TRANSCODE，无候选再 ASR（waiting 三态门控）。
ASR 的中途事件（checkpoint / 转写失败）经 RunnerContext.notifier 在域内发送。
"""

import asyncio
import hashlib
import json
import shutil
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import cast

import httpx
from loguru import logger
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.models.document import RecordFile
from app.models.record import Record
from app.modules.jobs import (
    ClaimCheck,
    ClaimedJob,
    LoopFailure,
    Ready,
    RunnerContext,
    WaitingClaim,
    WorkerSpec,
    mark_failed,
    mark_retry_fixed,
)
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import (
    ProcessingJobErrorCode,
    ProcessingJobStatus,
    ProcessingJobType,
    ProcessingJobWaitingReason,
)
from app.modules.settings import (
    external_processing_consent_at,
    load_tencent_asr_config,
)
from app.schemas.document import AsrChunkStatus
from app.schemas.record import RecordStatus
from app.services.record_invalidation import RecordInvalidationNotifier
from app.services.tencent_asr_client import (
    TencentAsrApiError,
    TencentAsrClient,
    TencentAsrCredentials,
    TencentAsrTaskStatus,
)
from app.services.transcript_finalizer import complete_source_job, finalize_record_if_ready

MAX_CHUNK_BYTES = 5 * 1024 * 1024
CHUNK_DURATION_MS = 5 * 60 * 1000


@dataclass(frozen=True)
class ClaimedTranscode(ClaimedJob):
    record_file_id: str
    source_path: Path
    duration_ms: int


@dataclass(frozen=True)
class ClaimedAsr(ClaimedJob):
    input_data: dict[str, object]
    checkpoint: dict[str, object]
    region: str
    secret_id: str
    secret_key: str


def _asr_api_failure(code: str) -> tuple[ProcessingJobErrorCode, str]:
    if code.startswith("AuthFailure") or code == "FailedOperation.CheckAuthInfoFailed":
        return ProcessingJobErrorCode.ASR_AUTH_FAILED, "腾讯云凭据无效"
    if code in {
        "FailedOperation.ServiceIsolate",
        "FailedOperation.UserHasNoAmount",
        "FailedOperation.UserHasNoFreeAmount",
    }:
        return ProcessingJobErrorCode.ASR_QUOTA_EXHAUSTED, "腾讯云识别额度不足"
    if code in {
        "FailedOperation.NoSuchTask",
        "FailedOperation.TaskNotExist",
        "InvalidParameterValue.TaskId",
        "ResourceNotFound.Task",
    }:
        return ProcessingJobErrorCode.ASR_TASK_EXPIRED, "腾讯云识别任务已失效"
    if code.startswith(("InternalError", "RequestLimitExceeded", "ResourceUnavailable")):
        return ProcessingJobErrorCode.ASR_TEMPORARY_UNAVAILABLE, "腾讯云识别暂时不可用"
    return ProcessingJobErrorCode.ASR_RECOGNITION_FAILED, "腾讯云识别请求失败"


async def find_candidate(session: AsyncSession, now: datetime) -> ProcessingJob | None:
    """转码优先；无候选再扫 ASR（chunks 就绪且依赖转码已成功）。"""
    transcode = (
        await session.scalars(
            select(ProcessingJob)
            .join(Record, ProcessingJob.record_id == Record.id)
            .where(
                ProcessingJob.job_type == ProcessingJobType.AUDIO_TRANSCODE,
                ProcessingJob.status == ProcessingJobStatus.PENDING,
                Record.deleted_at.is_(None),
                Record.status == RecordStatus.CONTENT_PROCESSING,
                or_(ProcessingJob.next_run_at.is_(None), ProcessingJob.next_run_at <= now),
            )
            .order_by(ProcessingJob.created_at, ProcessingJob.id)
            .limit(1)
        )
    ).one_or_none()
    if transcode is not None:
        return transcode
    jobs = (
        await session.scalars(
            select(ProcessingJob)
            .join(Record, ProcessingJob.record_id == Record.id)
            .where(
                ProcessingJob.job_type == ProcessingJobType.ASR,
                ProcessingJob.status == ProcessingJobStatus.PENDING,
                Record.deleted_at.is_(None),
                Record.status == RecordStatus.CONTENT_PROCESSING,
                or_(ProcessingJob.next_run_at.is_(None), ProcessingJob.next_run_at <= now),
            )
            .order_by(ProcessingJob.created_at, ProcessingJob.id)
        )
    ).all()
    for job in jobs:
        if job.record_id is None:
            continue
        input_data: object = json.loads(job.input_json)
        if not isinstance(input_data, dict):
            continue
        parsed_input = cast(dict[str, object], input_data)
        if not parsed_input.get("chunks"):
            continue
        dependency_id = parsed_input.get("depends_on_job_id")
        dependency = (
            await session.get(ProcessingJob, dependency_id)
            if isinstance(dependency_id, str)
            else None
        )
        if dependency is not None and dependency.status == ProcessingJobStatus.SUCCEEDED:
            return job
    return None


async def validate_claim(
    session: AsyncSession,
    job: ProcessingJob,
    record_id: str,
    data_dir: Path,
    asr_client: TencentAsrClient,
) -> ClaimCheck[ClaimedJob]:
    """ASR 前置三重门控（不抢占不耗 attempts）；转码直接可领（路径异常仍抢占）。"""
    if job.job_type == ProcessingJobType.ASR:
        consent = await asyncio.to_thread(external_processing_consent_at, data_dir)
        if consent is None:
            return WaitingClaim(ProcessingJobWaitingReason.CONSENT_REQUIRED)
        provider = await asyncio.to_thread(load_tencent_asr_config, data_dir)
        if provider is None:
            return WaitingClaim(ProcessingJobWaitingReason.ASR_KEY_REQUIRED)
        if not await asr_client.is_online():
            return WaitingClaim(ProcessingJobWaitingReason.OFFLINE)
        input_data: object = json.loads(job.input_json)
        if not isinstance(input_data, dict):
            input_data = {}
        checkpoint: object = json.loads(job.result_json) if job.result_json else {}
        return Ready(
            ClaimedAsr(
                job_id=job.id,
                record_id=record_id,
                input_data=cast(dict[str, object], input_data),
                checkpoint=cast(dict[str, object], checkpoint)
                if isinstance(checkpoint, dict)
                else {},
                region=provider.region,
                secret_id=provider.secret_id,
                secret_key=provider.secret_key,
            )
        )
    record_file_id = ""
    source_path = Path()
    duration_ms = 0
    input_data = json.loads(job.input_json)
    if isinstance(input_data, dict):
        raw_file_id = cast(dict[str, object], input_data).get("record_file_id")
        if isinstance(raw_file_id, str):
            record_file_id = raw_file_id
            record_file = (
                await session.scalars(
                    select(RecordFile).where(
                        RecordFile.id == record_file_id,
                        RecordFile.record_id == record_id,
                        RecordFile.deleted_at.is_(None),
                    )
                )
            ).one_or_none()
            if record_file is not None and record_file.duration_ms is not None:
                duration_ms = record_file.duration_ms
                candidate = (data_dir / Path(*PurePosixPath(record_file.file_path).parts)).resolve()
                files_root = (data_dir / "files").resolve()
                if candidate.is_relative_to(files_root):
                    source_path = candidate
    return Ready(
        ClaimedTranscode(
            job_id=job.id,
            record_id=record_id,
            record_file_id=record_file_id,
            source_path=source_path,
            duration_ms=duration_ms,
        )
    )


async def on_preempted(
    session: AsyncSession,
    job: ProcessingJob,
    ctx: ClaimedJob,
    now: datetime,
) -> ClaimedJob:
    """ASR 抢占成功后补写 region（幂等）并定型输入。"""
    del session, now  # job 事务由抢占原语管理
    if not isinstance(ctx, ClaimedAsr):
        return ctx
    input_data = dict(ctx.input_data)
    input_data.setdefault("region", ctx.region)
    job.input_json = json.dumps(input_data, separators=(",", ":"))
    return replace(ctx, input_data=input_data)


async def transcode_audio(
    data_dir: Path,
    ffmpeg_path: Path,
    record_id: str,
    record_file_id: str,
    source_path: Path,
    duration_ms: int,
) -> list[dict[str, object]]:
    """ffmpeg 归一化 + 300s 切片，产出 ASR 分片清单（测试挂闸点）。"""
    cache_dir = (data_dir / "cache" / "audio" / record_id / record_file_id).resolve()
    cache_root = (data_dir / "cache").resolve()
    if not cache_dir.is_relative_to(cache_root):
        raise ValueError("unsafe audio cache path")
    await asyncio.to_thread(shutil.rmtree, cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True)
    normalized_path = cache_dir / "normalized.ogg"
    normalize = await asyncio.create_subprocess_exec(
        str(ffmpeg_path),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "libopus",
        "-b:a",
        "24k",
        str(normalized_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    if await normalize.wait() != 0:
        raise RuntimeError("ffmpeg normalization failed")
    chunks_dir = cache_dir / "chunks"
    chunks_dir.mkdir()
    split = await asyncio.create_subprocess_exec(
        str(ffmpeg_path),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(normalized_path),
        "-map",
        "0:a:0",
        "-c",
        "copy",
        "-f",
        "segment",
        "-segment_time",
        "300",
        "-reset_timestamps",
        "1",
        str(chunks_dir / "chunk-%05d.ogg"),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    if await split.wait() != 0:
        raise RuntimeError("ffmpeg chunking failed")
    chunks = sorted(chunks_dir.glob("chunk-*.ogg"))
    if not chunks or any(path.stat().st_size >= MAX_CHUNK_BYTES for path in chunks):
        raise RuntimeError("invalid ASR chunks")
    manifest: list[dict[str, object]] = []
    for index, path in enumerate(chunks):
        content = await asyncio.to_thread(path.read_bytes)
        start_ms = index * CHUNK_DURATION_MS
        manifest.append(
            {
                "index": index,
                "start_ms": start_ms,
                "end_ms": min(duration_ms, start_ms + CHUNK_DURATION_MS),
                "cache_path": path.relative_to(data_dir).as_posix(),
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        )
    return manifest


async def execute(
    ctx: ClaimedJob,
    runtime: RunnerContext,
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    ffmpeg_path: Path,
    asr_client: TencentAsrClient,
) -> list[dict[str, object]] | None:
    if isinstance(ctx, ClaimedTranscode):
        return await transcode_audio(
            data_dir,
            ffmpeg_path,
            ctx.record_id,
            ctx.record_file_id,
            ctx.source_path,
            ctx.duration_ms,
        )
    if isinstance(ctx, ClaimedAsr):
        await _execute_asr(asr_client, session_factory, runtime, data_dir, ctx)
    return None  # ASR 写回在域内完成（checkpoint / finalize 自持）


async def writeback(
    ctx: ClaimedJob,
    manifest: list[dict[str, object]],
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
) -> bool:
    """仅转码流水线抵达：注入 ASR 分片并置等待用户同意。"""
    accepted = await _complete_transcode(session_factory, ctx.job_id, ctx.record_id, manifest)
    if not accepted:
        cache_dir = data_dir / "cache" / "audio" / ctx.record_id
        await asyncio.to_thread(shutil.rmtree, cache_dir, ignore_errors=True)
    return True


def failure_code(ctx: ClaimedJob, exc: Exception) -> str | None:
    del exc
    if isinstance(ctx, ClaimedAsr):
        return None  # ASR 中途失败由域内 checkpoint + _fail_asr 自结
    logger.error(
        "audio_transcode_failed",
        record_id=ctx.record_id,
        job_id=ctx.job_id,
        error_code=ProcessingJobErrorCode.AUDIO_TRANSCODE_FAILED,
    )
    return ProcessingJobErrorCode.AUDIO_TRANSCODE_FAILED


async def apply_failure(
    ctx: ClaimedJob,
    session: AsyncSession,
    job: ProcessingJob,
    record: Record | None,
    error_code: str,
    now: datetime,
) -> bool:
    del session, error_code  # 仅转码流水线可达，错误码固定
    if not isinstance(ctx, ClaimedTranscode) or record is None:
        return False
    mark_failed(
        job,
        code=ProcessingJobErrorCode.AUDIO_TRANSCODE_FAILED,
        message="音频转码失败",
        now=now,
    )
    record.status = RecordStatus.FAILED
    record.updated_at = now
    return True


async def finalize_cycle(
    ctx: ClaimedJob,
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
) -> None:
    if await _record_is_deleted(session_factory, ctx.record_id):
        cache_dir = data_dir / "cache" / "audio" / ctx.record_id
        await asyncio.to_thread(shutil.rmtree, cache_dir, ignore_errors=True)


async def _complete_transcode(
    session_factory: async_sessionmaker[AsyncSession],
    job_id: str,
    record_id: str,
    manifest: list[dict[str, object]],
) -> bool:
    now = utcnow()
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, job_id)
        record = await session.get(Record, record_id)
        if (
            job is None
            or record is None
            or record.deleted_at is not None
            or job.status != ProcessingJobStatus.RUNNING
        ):
            return False
        asr_job = (
            await session.scalars(
                select(ProcessingJob).where(
                    ProcessingJob.record_id == record_id,
                    ProcessingJob.job_type == ProcessingJobType.ASR,
                    ProcessingJob.status == ProcessingJobStatus.PENDING,
                    func.json_extract(ProcessingJob.input_json, "$.depends_on_job_id") == job_id,
                )
            )
        ).one_or_none()
        if asr_job is None:
            return False
        input_data = cast(dict[str, object], json.loads(asr_job.input_json))
        input_data["chunks"] = manifest
        asr_job.input_json = json.dumps(input_data, separators=(",", ":"))
        asr_job.waiting_reason = ProcessingJobWaitingReason.CONSENT_REQUIRED
        asr_job.updated_at = now
        job.status = ProcessingJobStatus.SUCCEEDED
        job.progress = 1
        job.result_json = json.dumps({"chunk_count": len(manifest)})
        job.error_code = None
        job.error_message = None
        job.finished_at = now
        job.updated_at = now
        await session.flush()
    return True


async def _execute_asr(
    asr_client: TencentAsrClient,
    session_factory: async_sessionmaker[AsyncSession],
    runtime: RunnerContext,
    data_dir: Path,
    ctx: ClaimedAsr,
) -> None:
    notifier = runtime.record_notifier
    credentials = TencentAsrCredentials(
        secret_id=ctx.secret_id,
        secret_key=ctx.secret_key,
        region=cast(str, ctx.input_data["region"]),
    )
    job_id = ctx.job_id
    record_id = ctx.record_id
    chunks = cast(list[dict[str, object]], ctx.input_data["chunks"])
    states_raw = ctx.checkpoint.get("chunks")
    states = cast(list[dict[str, object]], states_raw) if isinstance(states_raw, list) else []
    by_index = {
        cast(int, state["index"]): state for state in states if isinstance(state.get("index"), int)
    }
    for chunk in chunks:
        if not await _asr_can_continue(session_factory, job_id, record_id):
            return
        index = cast(int, chunk["index"])
        state = by_index.setdefault(index, {"index": index, "status": AsrChunkStatus.PENDING})
        if state.get("status") == AsrChunkStatus.SUCCEEDED:
            continue
        path = _cache_path(data_dir, cast(str, chunk["cache_path"]))
        task_id = state.get("task_id")
        if not isinstance(task_id, str):
            try:
                task_id = await asr_client.submit(path, credentials, ctx.input_data)
            except (httpx.RequestError, httpx.HTTPStatusError):
                state.update(
                    {
                        "status": AsrChunkStatus.FAILED,
                        "error_code": ProcessingJobErrorCode.ASR_SUBMIT_UNKNOWN,
                    }
                )
                await _save_checkpoint(
                    session_factory, notifier, job_id, record_id, by_index, index, len(chunks)
                )
                await _fail_asr(
                    session_factory,
                    notifier,
                    job_id,
                    record_id,
                    ProcessingJobErrorCode.ASR_SUBMIT_UNKNOWN,
                    "ASR 提交状态未知，请人工确认后重试",
                )
                return
            except TencentAsrApiError as exc:
                stable, message = _asr_api_failure(exc.code)
                state.update(
                    {
                        "status": AsrChunkStatus.FAILED,
                        "error_code": stable,
                        "provider_error_code": exc.code,
                    }
                )
                await _save_checkpoint(
                    session_factory, notifier, job_id, record_id, by_index, index, len(chunks)
                )
                await _fail_asr(session_factory, notifier, job_id, record_id, stable, message)
                return
            state.update({"task_id": task_id, "status": AsrChunkStatus.SUBMITTED})
            await _save_checkpoint(
                session_factory, notifier, job_id, record_id, by_index, index, len(chunks)
            )

        while not runtime.stopped.is_set():
            if not await _asr_can_continue(session_factory, job_id, record_id):
                return
            try:
                task = await asr_client.poll(task_id, credentials)
            except (httpx.RequestError, httpx.HTTPStatusError):
                state["error_code"] = ProcessingJobErrorCode.ASR_TEMPORARY_UNAVAILABLE
                await _save_checkpoint(
                    session_factory, notifier, job_id, record_id, by_index, index, len(chunks)
                )
                await _fail_asr(
                    session_factory,
                    notifier,
                    job_id,
                    record_id,
                    ProcessingJobErrorCode.ASR_TEMPORARY_UNAVAILABLE,
                    "腾讯云识别暂时不可用",
                )
                return
            except TencentAsrApiError as exc:
                stable, message = _asr_api_failure(exc.code)
                if stable == ProcessingJobErrorCode.ASR_TASK_EXPIRED:
                    state["status"] = AsrChunkStatus.EXPIRED
                state.update(
                    {
                        "error_code": stable,
                        "provider_error_code": exc.code,
                    }
                )
                await _save_checkpoint(
                    session_factory, notifier, job_id, record_id, by_index, index, len(chunks)
                )
                await _fail_asr(session_factory, notifier, job_id, record_id, stable, message)
                return
            if not await _asr_can_continue(session_factory, job_id, record_id):
                return
            if task.status == TencentAsrTaskStatus.PENDING:
                await asyncio.sleep(1)
                continue
            if task.status == TencentAsrTaskStatus.FAILED:
                state.update(
                    {
                        "status": AsrChunkStatus.FAILED,
                        "error_code": ProcessingJobErrorCode.ASR_RECOGNITION_FAILED,
                        "provider_error_code": task.error_code or "ASR_FAILED",
                    }
                )
                await _save_checkpoint(
                    session_factory, notifier, job_id, record_id, by_index, index, len(chunks)
                )
                await _fail_asr(
                    session_factory,
                    notifier,
                    job_id,
                    record_id,
                    ProcessingJobErrorCode.ASR_RECOGNITION_FAILED,
                    "腾讯云识别失败",
                )
                return
            text_path = path.parent.parent / "texts" / f"chunk-{index:05d}.txt"
            try:
                text_path.parent.mkdir(exist_ok=True)
                await asyncio.to_thread(text_path.write_text, task.text, encoding="utf-8")
            except OSError:
                if not await _asr_can_continue(session_factory, job_id, record_id):
                    return
                raise
            state.update(
                {
                    "status": AsrChunkStatus.SUCCEEDED,
                    "text_path": text_path.relative_to(data_dir).as_posix(),
                }
            )
            await _save_checkpoint(
                session_factory, notifier, job_id, record_id, by_index, index + 1, len(chunks)
            )
            break
    await _finalize_asr(session_factory, notifier, data_dir, job_id, record_id, by_index)


def _cache_path(data_dir: Path, raw: str) -> Path:
    path = (data_dir / Path(*PurePosixPath(raw).parts)).resolve()
    cache_root = (data_dir / "cache").resolve()
    if not path.is_relative_to(cache_root):
        raise ValueError("unsafe ASR cache path")
    return path


async def _asr_can_continue(
    session_factory: async_sessionmaker[AsyncSession], job_id: str, record_id: str
) -> bool:
    async with session_factory() as session:
        active = (
            await session.execute(
                select(ProcessingJob.id)
                .join(Record, ProcessingJob.record_id == Record.id)
                .where(
                    ProcessingJob.id == job_id,
                    ProcessingJob.status == ProcessingJobStatus.RUNNING,
                    Record.id == record_id,
                    Record.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
    return active is not None


async def _record_is_deleted(
    session_factory: async_sessionmaker[AsyncSession], record_id: str
) -> bool:
    async with session_factory() as session:
        deleted_at = await session.scalar(select(Record.deleted_at).where(Record.id == record_id))
    return deleted_at is not None


async def _save_checkpoint(
    session_factory: async_sessionmaker[AsyncSession],
    notifier: RecordInvalidationNotifier,
    job_id: str,
    record_id: str,
    by_index: dict[int, dict[str, object]],
    cursor: int,
    total: int,
) -> None:
    now = utcnow()
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, job_id)
        if job is None or job.status != ProcessingJobStatus.RUNNING:
            return
        job.result_json = json.dumps(
            {"cursor": cursor, "chunks": [by_index[index] for index in sorted(by_index)]},
            separators=(",", ":"),
        )
        job.progress = cursor / total
        job.updated_at = now
        await session.flush()
    await notifier.notify(record_id)


async def _finalize_asr(
    session_factory: async_sessionmaker[AsyncSession],
    notifier: RecordInvalidationNotifier,
    data_dir: Path,
    job_id: str,
    record_id: str,
    by_index: dict[int, dict[str, object]],
) -> None:
    texts: list[str] = []
    for index in sorted(by_index):
        raw_path = by_index[index].get("text_path")
        if not isinstance(raw_path, str):
            return
        texts.append(
            (
                await asyncio.to_thread(_cache_path(data_dir, raw_path).read_text, encoding="utf-8")
            ).strip()
        )
    content = "\n".join(text for text in texts if text).strip()
    if not content:
        await _fail_asr(
            session_factory,
            notifier,
            job_id,
            record_id,
            ProcessingJobErrorCode.NO_SPEECH_DETECTED,
            "没有检测到可识别语音",
        )
        return
    source_dir = (data_dir / "cache" / "sources" / record_id).resolve()
    cache_root = (data_dir / "cache").resolve()
    if not source_dir.is_relative_to(cache_root):
        return
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / f"{job_id}.txt"
    await asyncio.to_thread(source_path.write_text, content, encoding="utf-8")
    accepted = await complete_source_job(
        session_factory,
        data_dir,
        record_id,
        job_id,
        json.dumps(
            {
                "cursor": len(by_index),
                "chunks": [
                    {
                        "index": index,
                        "task_id": by_index[index].get("task_id"),
                        "status": AsrChunkStatus.SUCCEEDED,
                    }
                    for index in sorted(by_index)
                ],
                "source_text_path": source_path.relative_to(data_dir).as_posix(),
            },
            separators=(",", ":"),
        ),
    )
    if not accepted:
        await asyncio.to_thread(shutil.rmtree, source_dir, ignore_errors=True)
    await notifier.notify(record_id)


async def _fail_asr(
    session_factory: async_sessionmaker[AsyncSession],
    notifier: RecordInvalidationNotifier,
    job_id: str,
    record_id: str,
    code: ProcessingJobErrorCode,
    message: str,
) -> None:
    now = utcnow()
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, job_id)
        record = await session.get(Record, record_id)
        if job is None or record is None or job.status != ProcessingJobStatus.RUNNING:
            return
        retry_automatically = (
            code == ProcessingJobErrorCode.ASR_TEMPORARY_UNAVAILABLE
            and job.attempts < job.max_attempts
        )
        if retry_automatically:
            mark_retry_fixed(job, code=code, message=message, now=now)
            record.status = RecordStatus.CONTENT_PROCESSING
        else:
            mark_failed(job, code=code, message=message, now=now, clear_next_run=True)
            record.status = RecordStatus.FAILED
        record.updated_at = now
        await session.flush()
    await notifier.notify(record_id)


async def recover_audio(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
) -> None:
    now = utcnow()
    async with session_factory() as session, session.begin():
        await session.execute(
            update(ProcessingJob)
            .where(
                ProcessingJob.job_type.in_(
                    (ProcessingJobType.AUDIO_TRANSCODE, ProcessingJobType.ASR)
                ),
                ProcessingJob.status == ProcessingJobStatus.RUNNING,
            )
            .values(
                status=ProcessingJobStatus.PENDING,
                next_run_at=None,
                updated_at=now,
            )
        )
    async with session_factory() as session:
        record_ids = list(
            (
                await session.scalars(
                    select(ProcessingJob.record_id)
                    .where(
                        ProcessingJob.job_type == ProcessingJobType.ASR,
                        ProcessingJob.status == ProcessingJobStatus.SUCCEEDED,
                        ProcessingJob.record_id.is_not(None),
                    )
                    .distinct()
                )
            ).all()
        )
    for record_id in record_ids:
        if record_id is not None:
            await finalize_record_if_ready(session_factory, data_dir, record_id)


def classify_loop_error(_exc: Exception) -> LoopFailure:
    return LoopFailure(
        event="audio_worker_unexpected_failure",
        error_code=ProcessingJobErrorCode.INTERNAL_ERROR,
    )


def audio_spec(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    ffmpeg_path: Path,
    asr_client: TencentAsrClient,
    record_notifier: RecordInvalidationNotifier,
) -> WorkerSpec[None, ClaimedJob, list[dict[str, object]]]:
    async def recover() -> None:
        await recover_audio(session_factory, data_dir)

    return WorkerSpec(
        name="audio_worker",
        job_type=ProcessingJobType.ASR,
        poll_interval=1,
        find_candidate=find_candidate,
        validate_claim=lambda session, job, record_id, _payload: validate_claim(
            session, job, record_id, data_dir, asr_client
        ),
        on_preempted=on_preempted,
        execute=lambda ctx, runtime: execute(
            ctx, runtime, session_factory, data_dir, ffmpeg_path, asr_client
        ),
        writeback=lambda ctx, manifest: writeback(ctx, manifest, session_factory, data_dir),
        failure_code=failure_code,
        apply_failure=apply_failure,
        recover_interrupted=recover,
        classify_loop_error=classify_loop_error,
        finalize_cycle=lambda ctx: finalize_cycle(ctx, session_factory, data_dir),
        clear_waiting_on_claim=True,
    )
