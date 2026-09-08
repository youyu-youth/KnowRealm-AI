import asyncio
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import uuid4

from fastapi import UploadFile
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.capture.audio_import import (
    MAX_AUDIO_DURATION_MS,
    SUPPORTED_AUDIO,
    copy_upload,
    matches_audio_extension,
    probe_audio_duration_ms,
)
from app.modules.capture.document_import import SUPPORTED_DOCUMENTS
from app.modules.capture.models import RecordFile, RecordingSession
from app.modules.capture.schemas import (
    CaptureBatchAccepted,
    CaptureType,
    RecordFileSourceType,
    RecordFileType,
    RecordingSessionState,
)
from app.modules.course.schemas import CourseDetailOut, CourseStatus
from app.modules.course.service import CourseService
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus
from app.modules.search.service import SearchService
from app.shared.errors import CodedHTTPException


@dataclass(frozen=True)
class PreparedSource:
    file_id: str
    name: str
    extension: str
    temporary_path: Path
    size: int
    content_hash: str
    duration_ms: int | None

    @property
    def is_audio(self) -> bool:
        return self.extension in SUPPORTED_AUDIO


_RECORDING_FINALIZE_LOCK = asyncio.Lock()


class CaptureBatchService:
    @staticmethod
    async def create_recording(
        session: AsyncSession,
        data_dir: Path,
        ffmpeg_path: Path,
        recording_session_id: str,
    ) -> CaptureBatchAccepted:
        # ponytail: one sidecar writer; replace with a DB claim if writers become multi-process.
        async with _RECORDING_FINALIZE_LOCK:
            return await CaptureBatchService._create_recording(
                session, data_dir, ffmpeg_path, recording_session_id
            )

    @staticmethod
    async def _create_recording(
        session: AsyncSession,
        data_dir: Path,
        ffmpeg_path: Path,
        recording_session_id: str,
    ) -> CaptureBatchAccepted:
        recording = await session.get(RecordingSession, recording_session_id)
        if recording is None:
            raise CodedHTTPException(
                code="RECORDING_NOT_FOUND",
                status_code=404,
                detail="RECORDING_NOT_FOUND：录音会话不存在",
            )
        if recording.state != RecordingSessionState.FINALIZING:
            raise CodedHTTPException(
                code="RECORDING_NOT_SEALED",
                status_code=409,
                detail="RECORDING_NOT_SEALED：录音清单尚未封口",
            )
        raw_paths: object = json.loads(recording.chunk_paths)
        if not isinstance(raw_paths, list) or not raw_paths:
            raise CodedHTTPException(
                code="EMPTY_RECORDING",
                status_code=400,
                detail="EMPTY_RECORDING：录音没有可处理分片",
            )
        cache_root = (data_dir / "cache").resolve()
        staging_root = (data_dir / "cache" / "staging").resolve()
        chunk_paths: list[Path] = []
        for raw in cast(list[object], raw_paths):
            if not isinstance(raw, str):
                raise CodedHTTPException(
                    code="INVALID_RECORDING_STAGING",
                    status_code=400,
                    detail="INVALID_RECORDING_STAGING：分片清单无效",
                )
            pure = PurePosixPath(raw)
            path = (data_dir / Path(*pure.parts)).resolve()
            if (
                pure.is_absolute()
                or ".." in pure.parts
                or not path.is_relative_to(staging_root)
                or not path.is_file()
            ):
                raise CodedHTTPException(
                    code="INVALID_RECORDING_STAGING",
                    status_code=400,
                    detail="INVALID_RECORDING_STAGING：录音分片不安全或不存在",
                )
            chunk_paths.append(path)
        course_id = recording.course_id
        title = (recording.title or "录音").strip() or "录音"
        await session.rollback()

        file_id, transcode_id, asr_id = (str(uuid4()) for _ in range(3))
        work_dir = (data_dir / "cache" / "imports" / recording_session_id).resolve()
        if not work_dir.is_relative_to(cache_root):
            raise CodedHTTPException(
                code="INVALID_RECORDING_STAGING",
                status_code=400,
                detail="INVALID_RECORDING_STAGING：缓存路径无效",
            )
        final_dir = data_dir / "files" / recording_session_id
        final_path = final_dir / f"{file_id}.ogg"
        work_dir.mkdir(parents=True, exist_ok=True)
        manifest = work_dir / "chunks.txt"
        manifest_lines = [
            f"file '{str(path).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n"
            for path in chunk_paths
        ]
        manifest.write_text("".join(manifest_lines), encoding="utf-8")
        try:
            total_size = sum(path.stat().st_size for path in chunk_paths)
            free = (await asyncio.to_thread(shutil.disk_usage, work_dir)).free
            if free < total_size * 2:
                raise CodedHTTPException(
                    code="INSUFFICIENT_DISK",
                    status_code=507,
                    detail="INSUFFICIENT_DISK：数据目录空间不足",
                )
            final_dir.mkdir(parents=True, exist_ok=True)
            process = await asyncio.create_subprocess_exec(
                str(ffmpeg_path),
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(manifest),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "libopus",
                "-b:a",
                "24k",
                str(final_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            if await process.wait() != 0:
                raise CodedHTTPException(
                    code="CORRUPT_AUDIO", status_code=400, detail="CORRUPT_AUDIO：录音分片无法合并"
                )
            duration_ms = await probe_audio_duration_ms(ffmpeg_path, final_path)
            if duration_ms > 3 * 60 * 60 * 1000:
                raise CodedHTTPException(
                    code="RECORDING_TOO_LONG",
                    status_code=400,
                    detail="RECORDING_TOO_LONG：录音超过 3 小时",
                )
            content = await asyncio.to_thread(final_path.read_bytes)
            now = utcnow()
            async with session.begin():
                current = await session.get(RecordingSession, recording_session_id)
                if current is None or current.state != RecordingSessionState.FINALIZING:
                    raise CodedHTTPException(
                        code="RECORDING_NOT_SEALED",
                        status_code=409,
                        detail="RECORDING_NOT_SEALED：录音交接状态已改变",
                    )
                course = await CourseService.get(session, course_id) if course_id else None
                if course_id and course is None:
                    course_id = None
                hot_words = (
                    ",".join(
                        f"{word}|5" for word in CourseDetailOut.model_validate(course).hot_words
                    )
                    if course is not None
                    else ""
                ) or None
                session.add(
                    Record(
                        id=recording_session_id,
                        course_id=course_id,
                        capture_type=CaptureType.RECORDING,
                        title=title,
                        status=RecordStatus.CONTENT_PROCESSING,
                        duration_ms=duration_ms,
                        summary_confirmed_at=None,
                        created_at=current.started_at,
                        updated_at=now,
                    )
                )
                await session.flush()
                session.add_all(
                    [
                        RecordFile(
                            id=file_id,
                            record_id=recording_session_id,
                            file_type=RecordFileType.AUDIO,
                            source_type=RecordFileSourceType.RECORDED,
                            file_path=final_path.relative_to(data_dir).as_posix(),
                            original_name=f"{title}.ogg",
                            mime_type="audio/ogg",
                            file_size=len(content),
                            duration_ms=duration_ms,
                            sequence_no=0,
                            content_hash=hashlib.sha256(content).hexdigest(),
                            created_at=now,
                            updated_at=now,
                        ),
                        ProcessingJob(
                            id=transcode_id,
                            record_id=recording_session_id,
                            job_type=ProcessingJobType.AUDIO_TRANSCODE,
                            status=ProcessingJobStatus.PENDING,
                            progress=0,
                            attempts=0,
                            max_attempts=3,
                            input_json=json.dumps(
                                {
                                    "record_file_id": file_id,
                                    "sequence_no": 0,
                                    "source_name": f"{title}.ogg",
                                }
                            ),
                            created_at=now,
                            updated_at=now,
                        ),
                        ProcessingJob(
                            id=asr_id,
                            record_id=recording_session_id,
                            job_type=ProcessingJobType.ASR,
                            status=ProcessingJobStatus.PENDING,
                            progress=0,
                            attempts=0,
                            max_attempts=3,
                            input_json=json.dumps(
                                {
                                    "record_file_id": file_id,
                                    "sequence_no": 0,
                                    "source_name": f"{title}.ogg",
                                    "depends_on_job_id": transcode_id,
                                    "chunks": [],
                                    "engine_model_type": "16k_zh",
                                    "channel_num": 1,
                                    "res_text_format": 3,
                                    "hot_words": hot_words,
                                }
                            ),
                            created_at=now,
                            updated_at=now,
                        ),
                    ]
                )
                current.state = RecordingSessionState.DONE
                current.updated_at = now
                await session.flush()
                await SearchService.upsert_record_index(session, recording_session_id)
        except BaseException:
            await asyncio.to_thread(final_path.unlink, missing_ok=True)
            try:
                await asyncio.to_thread(final_dir.rmdir)
            except OSError:
                pass
            raise
        else:
            for path in chunk_paths:
                await asyncio.to_thread(path.unlink, missing_ok=True)
            for directory in {path.parent for path in chunk_paths}:
                try:
                    await asyncio.to_thread(directory.rmdir)
                except OSError:
                    pass
            return CaptureBatchAccepted(
                record_id=recording_session_id,
                job_ids=[transcode_id, asr_id],
            )
        finally:
            await asyncio.to_thread(shutil.rmtree, work_dir, ignore_errors=True)

    @staticmethod
    async def create(
        session: AsyncSession,
        data_dir: Path,
        ffmpeg_path: Path | None,
        uploads: list[UploadFile],
        course_id: str | None,
    ) -> CaptureBatchAccepted:
        if not uploads:
            raise CodedHTTPException(
                code="EMPTY_BATCH", status_code=400, detail="EMPTY_BATCH：至少选择一个来源"
            )

        record_id = str(uuid4())
        temporary_dir = data_dir / "cache" / "imports" / record_id
        final_dir = data_dir / "files" / record_id
        temporary_dir.mkdir(parents=True)
        prepared: list[PreparedSource] = []
        try:
            for upload in uploads:
                name = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
                extension = Path(name).suffix.lower()
                if not name or extension not in SUPPORTED_AUDIO | SUPPORTED_DOCUMENTS:
                    raise CodedHTTPException(
                        code="UNSUPPORTED_SOURCE",
                        status_code=400,
                        detail="UNSUPPORTED_SOURCE：不支持的来源格式",
                    )
                file_id = str(uuid4())
                temporary_path = temporary_dir / f"{file_id}.tmp"
                size, content_hash = await asyncio.to_thread(
                    copy_upload, upload.file, temporary_path
                )
                if size == 0:
                    raise CodedHTTPException(
                        code="EMPTY_SOURCE", status_code=400, detail="EMPTY_SOURCE：来源不能为空"
                    )
                duration_ms: int | None = None
                if extension in SUPPORTED_AUDIO:
                    if ffmpeg_path is None:
                        raise CodedHTTPException(
                            code="FFMPEG_UNAVAILABLE",
                            status_code=503,
                            detail="FFMPEG_UNAVAILABLE：音频处理组件不可用",
                        )
                    if not await asyncio.to_thread(
                        matches_audio_extension, temporary_path, extension
                    ):
                        raise CodedHTTPException(
                            code="UNSUPPORTED_AUDIO",
                            status_code=400,
                            detail="UNSUPPORTED_AUDIO：格式与内容不匹配",
                        )
                    duration_ms = await probe_audio_duration_ms(ffmpeg_path, temporary_path)
                prepared.append(
                    PreparedSource(
                        file_id,
                        name,
                        extension,
                        temporary_path,
                        size,
                        content_hash,
                        duration_ms,
                    )
                )

            course = await CourseService.get(session, course_id) if course_id is not None else None
            if course_id is not None and course is None:
                raise CodedHTTPException(
                    code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
                )
            if course is not None and course.status != CourseStatus.ACTIVE:
                raise CodedHTTPException(
                    code="COURSE_ARCHIVED", status_code=409, detail="已归档课程不能接受新资料"
                )
            hot_words = (
                ",".join(f"{word}|5" for word in CourseDetailOut.model_validate(course).hot_words)
                if course is not None
                else ""
            ) or None
            await session.rollback()

            total_audio_ms = sum(source.duration_ms or 0 for source in prepared)
            if total_audio_ms > MAX_AUDIO_DURATION_MS:
                raise CodedHTTPException(
                    code="AUDIO_TOO_LONG",
                    status_code=400,
                    detail="AUDIO_TOO_LONG：批次音频超过 5 小时",
                )
            total_size = sum(source.size for source in prepared)
            free_after_write = (await asyncio.to_thread(shutil.disk_usage, temporary_dir)).free
            if free_after_write < total_size * 2:
                raise CodedHTTPException(
                    code="INSUFFICIENT_DISK",
                    status_code=507,
                    detail="INSUFFICIENT_DISK：数据目录空间不足",
                )

            final_dir.mkdir(parents=True)
            for source in prepared:
                await asyncio.to_thread(
                    os.replace,
                    source.temporary_path,
                    final_dir / f"{source.file_id}{source.extension}",
                )

            now = utcnow()
            job_ids: list[str] = []
            async with session.begin():
                source_kinds = {source.is_audio for source in prepared}
                capture_type = (
                    CaptureType.MULTI_SOURCE
                    if len(source_kinds) > 1
                    else CaptureType.AUDIO_IMPORT
                    if prepared[0].is_audio
                    else CaptureType.DOCUMENT_IMPORT
                )
                session.add(
                    Record(
                        id=record_id,
                        course_id=course_id,
                        capture_type=capture_type,
                        title=(
                            Path(prepared[0].name).stem
                            if len(prepared) == 1
                            else f"{Path(prepared[0].name).stem} 等 {len(prepared)} 个文件"
                        ),
                        status=RecordStatus.CONTENT_PROCESSING,
                        duration_ms=total_audio_ms,
                        summary_confirmed_at=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
                await session.flush()
                for sequence_no, source in enumerate(prepared):
                    final_path = final_dir / f"{source.file_id}{source.extension}"
                    session.add(
                        RecordFile(
                            id=source.file_id,
                            record_id=record_id,
                            file_type=(
                                RecordFileType.AUDIO if source.is_audio else RecordFileType.DOCUMENT
                            ),
                            source_type=RecordFileSourceType.UPLOADED,
                            file_path=final_path.relative_to(data_dir).as_posix(),
                            original_name=source.name,
                            mime_type=(SUPPORTED_AUDIO | SUPPORTED_DOCUMENTS)[source.extension],
                            file_size=source.size,
                            duration_ms=source.duration_ms,
                            sequence_no=sequence_no,
                            content_hash=source.content_hash,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    if source.is_audio:
                        transcode_id, asr_id = str(uuid4()), str(uuid4())
                        job_ids.extend((transcode_id, asr_id))
                        session.add_all(
                            [
                                ProcessingJob(
                                    id=transcode_id,
                                    record_id=record_id,
                                    job_type=ProcessingJobType.AUDIO_TRANSCODE,
                                    status=ProcessingJobStatus.PENDING,
                                    progress=0,
                                    attempts=0,
                                    max_attempts=3,
                                    input_json=json.dumps(
                                        {
                                            "record_file_id": source.file_id,
                                            "sequence_no": sequence_no,
                                            "source_name": source.name,
                                        }
                                    ),
                                    created_at=now,
                                    updated_at=now,
                                ),
                                ProcessingJob(
                                    id=asr_id,
                                    record_id=record_id,
                                    job_type=ProcessingJobType.ASR,
                                    status=ProcessingJobStatus.PENDING,
                                    progress=0,
                                    attempts=0,
                                    max_attempts=3,
                                    input_json=json.dumps(
                                        {
                                            "record_file_id": source.file_id,
                                            "sequence_no": sequence_no,
                                            "source_name": source.name,
                                            "depends_on_job_id": transcode_id,
                                            "chunks": [],
                                            "engine_model_type": "16k_zh",
                                            "channel_num": 1,
                                            "res_text_format": 3,
                                            "hot_words": hot_words,
                                        }
                                    ),
                                    created_at=now,
                                    updated_at=now,
                                ),
                            ]
                        )
                    else:
                        job_id = str(uuid4())
                        job_ids.append(job_id)
                        session.add(
                            ProcessingJob(
                                id=job_id,
                                record_id=record_id,
                                job_type=ProcessingJobType.DOCUMENT_PARSE,
                                status=ProcessingJobStatus.PENDING,
                                progress=0,
                                attempts=0,
                                max_attempts=3,
                                input_json=json.dumps(
                                    {
                                        "record_file_id": source.file_id,
                                        "sequence_no": sequence_no,
                                        "source_name": source.name,
                                    }
                                ),
                                created_at=now,
                                updated_at=now,
                            )
                        )
                await session.flush()
                await SearchService.upsert_record_index(session, record_id)
        except BaseException:
            try:
                await asyncio.to_thread(shutil.rmtree, final_dir, ignore_errors=True)
                await asyncio.to_thread(shutil.rmtree, temporary_dir, ignore_errors=True)
            except OSError:
                logger.error(
                    "capture_batch_compensation_failed",
                    error_code="CAPTURE_BATCH_COMPENSATION_FAILED",
                    record_id=record_id,
                )
            raise
        await asyncio.to_thread(shutil.rmtree, temporary_dir, ignore_errors=True)
        return CaptureBatchAccepted(record_id=record_id, job_ids=job_ids)
