import asyncio
import hashlib
import json
import shutil
from datetime import timedelta
from pathlib import Path, PurePosixPath
from typing import cast

import httpx
from loguru import logger
from sqlalchemy import or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.base import utcnow
from app.models.document import ProcessingJob, RecordFile, Transcript
from app.models.record import Record
from app.schemas.document import (
    AsrChunkStatus,
    ProcessingJobErrorCode,
    ProcessingJobStatus,
    ProcessingJobType,
    ProcessingJobWaitingReason,
)
from app.schemas.record import RecordStatus
from app.services.local_config import (
    external_processing_consent_at,
    load_tencent_asr_config,
)
from app.services.record_invalidation import RecordInvalidationNotifier
from app.services.tencent_asr_client import (
    TencentAsrApiError,
    TencentAsrClient,
    TencentAsrCredentials,
    TencentAsrTaskStatus,
)

MAX_CHUNK_BYTES = 5 * 1024 * 1024
CHUNK_DURATION_MS = 5 * 60 * 1000


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


class AudioWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        ffmpeg_path: Path,
        asr_client: TencentAsrClient,
        record_notifier: RecordInvalidationNotifier,
    ) -> None:
        self._session_factory = session_factory
        self._data_dir = data_dir
        self._ffmpeg_path = ffmpeg_path
        self._asr_client = asr_client
        self._record_notifier = record_notifier
        self._stopped = asyncio.Event()

    def stop(self) -> None:
        self._stopped.set()

    async def recover_interrupted(self) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
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

    async def run(self) -> None:
        while not self._stopped.is_set():
            if await self._process_transcode():
                continue
            if await self._process_asr():
                continue
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=0.05)
            except TimeoutError:
                pass

    async def _process_transcode(self) -> bool:
        claimed = await self._claim_transcode()
        if claimed is None:
            return False
        job_id, record_id, record_file_id, source_path, duration_ms = claimed
        await self._record_notifier.notify(record_id)
        try:
            manifest = await self._transcode(record_id, record_file_id, source_path, duration_ms)
        except Exception:
            logger.error(
                "audio_transcode_failed",
                record_id=record_id,
                job_id=job_id,
                error_code=ProcessingJobErrorCode.AUDIO_TRANSCODE_FAILED,
            )
            await self._fail_transcode(job_id, record_id)
        else:
            if not await self._complete_transcode(job_id, record_id, manifest):
                cache_dir = self._data_dir / "cache" / "audio" / record_id
                await asyncio.to_thread(shutil.rmtree, cache_dir, ignore_errors=True)
        finally:
            if await self._record_is_deleted(record_id):
                cache_dir = self._data_dir / "cache" / "audio" / record_id
                await asyncio.to_thread(shutil.rmtree, cache_dir, ignore_errors=True)
        await self._record_notifier.notify(record_id)
        return True

    async def _claim_transcode(self) -> tuple[str, str, str, Path, int] | None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = (
                await session.scalars(
                    select(ProcessingJob)
                    .join(Record, ProcessingJob.record_id == Record.id)
                    .where(
                        ProcessingJob.job_type == ProcessingJobType.AUDIO_TRANSCODE,
                        ProcessingJob.status == ProcessingJobStatus.PENDING,
                        Record.deleted_at.is_(None),
                        or_(ProcessingJob.next_run_at.is_(None), ProcessingJob.next_run_at <= now),
                    )
                    .order_by(ProcessingJob.created_at, ProcessingJob.id)
                    .limit(1)
                )
            ).one_or_none()
            if job is None or job.record_id is None:
                return None
            result = cast(
                CursorResult[tuple[()]],
                await session.execute(
                    update(ProcessingJob)
                    .where(
                        ProcessingJob.id == job.id,
                        ProcessingJob.status == ProcessingJobStatus.PENDING,
                    )
                    .values(
                        status=ProcessingJobStatus.RUNNING,
                        attempts=ProcessingJob.attempts + 1,
                        waiting_reason=None,
                        started_at=now,
                        updated_at=now,
                    )
                ),
            )
            if result.rowcount != 1:
                return None
            input_data: object = json.loads(job.input_json)
            if not isinstance(input_data, dict):
                return job.id, job.record_id, "", Path(), 0
            record_file_id = cast(dict[str, object], input_data).get("record_file_id")
            if not isinstance(record_file_id, str):
                return job.id, job.record_id, "", Path(), 0
            record_file = (
                await session.scalars(
                    select(RecordFile).where(
                        RecordFile.id == record_file_id,
                        RecordFile.record_id == job.record_id,
                        RecordFile.deleted_at.is_(None),
                    )
                )
            ).one_or_none()
            if record_file is None or record_file.duration_ms is None:
                return job.id, job.record_id, record_file_id, Path(), 0
            source_path = (
                self._data_dir / Path(*PurePosixPath(record_file.file_path).parts)
            ).resolve()
            files_root = (self._data_dir / "files").resolve()
            if not source_path.is_relative_to(files_root):
                return job.id, job.record_id, record_file_id, Path(), 0
            return job.id, job.record_id, record_file_id, source_path, record_file.duration_ms

    async def _transcode(
        self,
        record_id: str,
        record_file_id: str,
        source_path: Path,
        duration_ms: int,
    ) -> list[dict[str, object]]:
        cache_dir = (self._data_dir / "cache" / "audio" / record_id / record_file_id).resolve()
        cache_root = (self._data_dir / "cache").resolve()
        if not cache_dir.is_relative_to(cache_root):
            raise ValueError("unsafe audio cache path")
        await asyncio.to_thread(shutil.rmtree, cache_dir, ignore_errors=True)
        cache_dir.mkdir(parents=True)
        normalized_path = cache_dir / "normalized.ogg"
        normalize = await asyncio.create_subprocess_exec(
            str(self._ffmpeg_path),
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
            str(self._ffmpeg_path),
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
                    "cache_path": path.relative_to(self._data_dir).as_posix(),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                }
            )
        return manifest

    async def _complete_transcode(
        self,
        job_id: str,
        record_id: str,
        manifest: list[dict[str, object]],
    ) -> bool:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
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

    async def _fail_transcode(self, job_id: str, record_id: str) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, job_id)
            record = await session.get(Record, record_id)
            if job is None or record is None or job.status != ProcessingJobStatus.RUNNING:
                return
            job.status = ProcessingJobStatus.FAILED
            job.error_code = ProcessingJobErrorCode.AUDIO_TRANSCODE_FAILED
            job.error_message = "音频转码失败"
            job.finished_at = now
            job.updated_at = now
            record.status = RecordStatus.FAILED
            record.updated_at = now
            await session.flush()
        await self._record_notifier.notify(record_id)

    async def _process_asr(self) -> bool:
        candidate = await self._pending_asr()
        if candidate is None:
            return False
        job_id, record_id = candidate
        consent = await asyncio.to_thread(external_processing_consent_at, self._data_dir)
        if consent is None:
            await self._set_waiting(job_id, record_id, ProcessingJobWaitingReason.CONSENT_REQUIRED)
            return False
        provider = await asyncio.to_thread(load_tencent_asr_config, self._data_dir)
        if provider is None:
            await self._set_waiting(job_id, record_id, ProcessingJobWaitingReason.ASR_KEY_REQUIRED)
            return False
        if not await self._asr_client.is_online():
            await self._set_waiting(job_id, record_id, ProcessingJobWaitingReason.OFFLINE)
            return False
        claimed = await self._claim_asr(job_id, provider.region)
        if claimed is None:
            return True
        input_data, checkpoint = claimed
        await self._record_notifier.notify(record_id)
        credentials = TencentAsrCredentials(
            secret_id=provider.secret_id,
            secret_key=provider.secret_key,
            region=cast(str, input_data["region"]),
        )
        await self._execute_asr(job_id, record_id, input_data, checkpoint, credentials)
        if await self._record_is_deleted(record_id):
            cache_dir = self._data_dir / "cache" / "audio" / record_id
            await asyncio.to_thread(shutil.rmtree, cache_dir, ignore_errors=True)
        return True

    async def _pending_asr(self) -> tuple[str, str] | None:
        now = utcnow()
        async with self._session_factory() as session:
            jobs = (
                await session.scalars(
                    select(ProcessingJob)
                    .join(Record, ProcessingJob.record_id == Record.id)
                    .where(
                        ProcessingJob.job_type == ProcessingJobType.ASR,
                        ProcessingJob.status == ProcessingJobStatus.PENDING,
                        Record.deleted_at.is_(None),
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
                    return job.id, job.record_id
        return None

    async def _set_waiting(
        self,
        job_id: str,
        record_id: str,
        reason: ProcessingJobWaitingReason,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            result = cast(
                CursorResult[tuple[()]],
                await session.execute(
                    update(ProcessingJob)
                    .where(
                        ProcessingJob.id == job_id,
                        ProcessingJob.status == ProcessingJobStatus.PENDING,
                        or_(
                            ProcessingJob.waiting_reason.is_(None),
                            ProcessingJob.waiting_reason != reason,
                        ),
                    )
                    .values(waiting_reason=reason, updated_at=utcnow())
                ),
            )
        if result.rowcount == 1:
            await self._record_notifier.notify(record_id)

    async def _claim_asr(
        self,
        job_id: str,
        region: str,
    ) -> tuple[dict[str, object], dict[str, object]] | None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, job_id)
            if job is None or job.status != ProcessingJobStatus.PENDING:
                return None
            input_data = cast(dict[str, object], json.loads(job.input_json))
            input_data.setdefault("region", region)
            job.input_json = json.dumps(input_data, separators=(",", ":"))
            job.status = ProcessingJobStatus.RUNNING
            job.attempts += 1
            job.waiting_reason = None
            job.started_at = now
            job.updated_at = now
            checkpoint: object = json.loads(job.result_json) if job.result_json else {}
            await session.flush()
            return input_data, cast(dict[str, object], checkpoint)

    async def _execute_asr(
        self,
        job_id: str,
        record_id: str,
        input_data: dict[str, object],
        checkpoint: dict[str, object],
        credentials: TencentAsrCredentials,
    ) -> None:
        chunks = cast(list[dict[str, object]], input_data["chunks"])
        states_raw = checkpoint.get("chunks")
        states = cast(list[dict[str, object]], states_raw) if isinstance(states_raw, list) else []
        by_index = {
            cast(int, state["index"]): state
            for state in states
            if isinstance(state.get("index"), int)
        }
        for chunk in chunks:
            if not await self._asr_can_continue(job_id, record_id):
                return
            index = cast(int, chunk["index"])
            state = by_index.setdefault(index, {"index": index, "status": AsrChunkStatus.PENDING})
            if state.get("status") == AsrChunkStatus.SUCCEEDED:
                continue
            path = self._cache_path(cast(str, chunk["cache_path"]))
            task_id = state.get("task_id")
            if not isinstance(task_id, str):
                try:
                    task_id = await self._asr_client.submit(path, credentials, input_data)
                except (httpx.RequestError, httpx.HTTPStatusError):
                    state.update(
                        {
                            "status": AsrChunkStatus.FAILED,
                            "error_code": ProcessingJobErrorCode.ASR_SUBMIT_UNKNOWN,
                        }
                    )
                    await self._save_checkpoint(job_id, record_id, by_index, index, len(chunks))
                    await self._fail_asr(
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
                    await self._save_checkpoint(job_id, record_id, by_index, index, len(chunks))
                    await self._fail_asr(job_id, record_id, stable, message)
                    return
                state.update({"task_id": task_id, "status": AsrChunkStatus.SUBMITTED})
                await self._save_checkpoint(job_id, record_id, by_index, index, len(chunks))

            while not self._stopped.is_set():
                if not await self._asr_can_continue(job_id, record_id):
                    return
                try:
                    task = await self._asr_client.poll(task_id, credentials)
                except (httpx.RequestError, httpx.HTTPStatusError):
                    state["error_code"] = ProcessingJobErrorCode.ASR_TEMPORARY_UNAVAILABLE
                    await self._save_checkpoint(job_id, record_id, by_index, index, len(chunks))
                    await self._fail_asr(
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
                    await self._save_checkpoint(job_id, record_id, by_index, index, len(chunks))
                    await self._fail_asr(job_id, record_id, stable, message)
                    return
                if not await self._asr_can_continue(job_id, record_id):
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
                    await self._save_checkpoint(job_id, record_id, by_index, index, len(chunks))
                    await self._fail_asr(
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
                    if not await self._asr_can_continue(job_id, record_id):
                        return
                    raise
                state.update(
                    {
                        "status": AsrChunkStatus.SUCCEEDED,
                        "text_path": text_path.relative_to(self._data_dir).as_posix(),
                    }
                )
                await self._save_checkpoint(job_id, record_id, by_index, index + 1, len(chunks))
                break
        await self._finalize_asr(job_id, record_id, by_index)

    def _cache_path(self, raw: str) -> Path:
        path = (self._data_dir / Path(*PurePosixPath(raw).parts)).resolve()
        cache_root = (self._data_dir / "cache").resolve()
        if not path.is_relative_to(cache_root):
            raise ValueError("unsafe ASR cache path")
        return path

    async def _asr_can_continue(self, job_id: str, record_id: str) -> bool:
        async with self._session_factory() as session:
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

    async def _record_is_deleted(self, record_id: str) -> bool:
        async with self._session_factory() as session:
            deleted_at = await session.scalar(
                select(Record.deleted_at).where(Record.id == record_id)
            )
        return deleted_at is not None

    async def _save_checkpoint(
        self,
        job_id: str,
        record_id: str,
        by_index: dict[int, dict[str, object]],
        cursor: int,
        total: int,
    ) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
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
        await self._record_notifier.notify(record_id)

    async def _finalize_asr(
        self,
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
                    await asyncio.to_thread(self._cache_path(raw_path).read_text, encoding="utf-8")
                ).strip()
            )
        content = "\n".join(text for text in texts if text).strip()
        if not content:
            await self._fail_asr(
                job_id,
                record_id,
                ProcessingJobErrorCode.NO_SPEECH_DETECTED,
                "没有检测到可识别语音",
            )
            return
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, job_id)
            record = await session.get(Record, record_id)
            if (
                job is None
                or record is None
                or record.deleted_at is not None
                or job.status != ProcessingJobStatus.RUNNING
            ):
                return
            transcript = (
                await session.scalars(select(Transcript).where(Transcript.record_id == record_id))
            ).one_or_none()
            if transcript is None:
                session.add(
                    Transcript(
                        record_id=record_id,
                        language="zh-CN",
                        content=content,
                        source_version=1,
                        edited_by_user=False,
                        created_at=now,
                        updated_at=now,
                    )
                )
            job.status = ProcessingJobStatus.SUCCEEDED
            job.progress = 1
            job.result_json = json.dumps(
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
                },
                separators=(",", ":"),
            )
            job.error_code = None
            job.error_message = None
            job.finished_at = now
            job.updated_at = now
            record.status = RecordStatus.SUMMARY_PENDING
            record.updated_at = now
            await session.flush()
        cache_dir = self._data_dir / "cache" / "audio" / record_id
        await asyncio.to_thread(shutil.rmtree, cache_dir, ignore_errors=True)
        await self._record_notifier.notify(record_id)

    async def _fail_asr(
        self,
        job_id: str,
        record_id: str,
        code: ProcessingJobErrorCode,
        message: str,
    ) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, job_id)
            record = await session.get(Record, record_id)
            if job is None or record is None or job.status != ProcessingJobStatus.RUNNING:
                return
            retry_automatically = (
                code == ProcessingJobErrorCode.ASR_TEMPORARY_UNAVAILABLE
                and job.attempts < job.max_attempts
            )
            job.status = (
                ProcessingJobStatus.PENDING if retry_automatically else ProcessingJobStatus.FAILED
            )
            job.error_code = code
            job.error_message = message
            job.next_run_at = now + timedelta(seconds=1) if retry_automatically else None
            job.finished_at = None if retry_automatically else now
            job.updated_at = now
            record.status = (
                RecordStatus.CONTENT_PROCESSING if retry_automatically else RecordStatus.FAILED
            )
            record.updated_at = now
            await session.flush()
        await self._record_notifier.notify(record_id)
