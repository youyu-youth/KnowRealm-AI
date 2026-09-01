import asyncio
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.capture.models import RecordFile
from app.modules.capture.schemas import (
    AudioImportAccepted,
    CaptureType,
    RecordFileSourceType,
    RecordFileType,
)
from app.modules.course import CourseService
from app.modules.course.schemas import CourseDetailOut, CourseStatus
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus

SUPPORTED_AUDIO = {
    ".mp3": "audio/mpeg",
    ".aac": "audio/aac",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
}
MAX_AUDIO_DURATION_MS = 5 * 60 * 60 * 1000
_DURATION = re.compile(rb"Duration: (\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)")


def copy_upload(source: BinaryIO, target: Path) -> tuple[int, str]:
    source.seek(0)
    size = 0
    digest = hashlib.sha256()
    with target.open("xb") as output:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
            output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    return size, digest.hexdigest()


def matches_audio_extension(path: Path, extension: str) -> bool:
    with path.open("rb") as source:
        head = source.read(16)
    if extension == ".wav":
        return len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    if extension == ".m4a":
        return len(head) >= 12 and head[4:8] == b"ftyp"
    if extension == ".mp3":
        return head.startswith(b"ID3") or (
            len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0
        )
    if extension == ".aac":
        return len(head) >= 2 and head[0] == 0xFF and head[1] & 0xF6 == 0xF0
    return False


async def probe_audio_duration_ms(ffmpeg_path: Path, path: Path) -> int:
    process = await asyncio.create_subprocess_exec(
        str(ffmpeg_path),
        "-hide_banner",
        "-nostdin",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-f",
        "null",
        "-",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    match = _DURATION.search(stderr)
    if process.returncode != 0 or match is None:
        raise HTTPException(status_code=400, detail="CORRUPT_AUDIO：音频已损坏")
    hours, minutes, seconds = match.groups()
    return round((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)


def _remove_file(path: Path) -> None:
    path.unlink(missing_ok=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass


class AudioImportService:
    @staticmethod
    async def create(
        session: AsyncSession,
        data_dir: Path,
        ffmpeg_path: Path,
        upload: UploadFile,
        course_id: str | None,
    ) -> AudioImportAccepted:
        original_name = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        extension = Path(original_name).suffix.lower()
        if not original_name or extension not in SUPPORTED_AUDIO:
            raise HTTPException(status_code=400, detail="UNSUPPORTED_AUDIO：不支持的音频格式")

        record_id, file_id, transcode_job_id, asr_job_id = (str(uuid4()) for _ in range(4))
        import_dir = data_dir / "cache" / "imports"
        import_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = import_dir / f"{file_id}.tmp"
        final_dir = data_dir / "files" / record_id
        final_path = final_dir / f"{file_id}{extension}"
        try:
            file_size, content_hash = await asyncio.to_thread(
                copy_upload, upload.file, temporary_path
            )
            if file_size == 0:
                raise HTTPException(status_code=400, detail="CORRUPT_AUDIO：音频不能为空")
            if not await asyncio.to_thread(matches_audio_extension, temporary_path, extension):
                raise HTTPException(status_code=400, detail="UNSUPPORTED_AUDIO：格式与内容不匹配")
            duration_ms = await probe_audio_duration_ms(ffmpeg_path, temporary_path)
            if duration_ms > MAX_AUDIO_DURATION_MS:
                raise HTTPException(status_code=400, detail="AUDIO_TOO_LONG：音频时长超过 5 小时")
            free_after_write = (await asyncio.to_thread(shutil.disk_usage, import_dir)).free
            if free_after_write < file_size * 2:
                raise HTTPException(status_code=507, detail="INSUFFICIENT_DISK：数据目录空间不足")
            final_dir.mkdir(parents=True)
            await asyncio.to_thread(os.replace, temporary_path, final_path)

            now = utcnow()
            hot_words: str | None = None
            async with session.begin():
                if course_id is not None:
                    course = await CourseService.get(session, course_id)
                    if course is None:
                        raise HTTPException(status_code=404, detail="课程不存在或已删除")
                    if course.status != CourseStatus.ACTIVE:
                        raise HTTPException(status_code=409, detail="已归档课程不能接受新音频")
                    words = CourseDetailOut.model_validate(course).hot_words
                    hot_words = ",".join(f"{word}|5" for word in words) or None
                session.add(
                    Record(
                        id=record_id,
                        course_id=course_id,
                        capture_type=CaptureType.AUDIO_IMPORT,
                        title=Path(original_name).stem,
                        status=RecordStatus.CONTENT_PROCESSING,
                        duration_ms=duration_ms,
                        summary_confirmed_at=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
                await session.flush()
                session.add_all(
                    [
                        RecordFile(
                            id=file_id,
                            record_id=record_id,
                            file_type=RecordFileType.AUDIO,
                            source_type=RecordFileSourceType.UPLOADED,
                            file_path=final_path.relative_to(data_dir).as_posix(),
                            original_name=original_name,
                            mime_type=SUPPORTED_AUDIO[extension],
                            file_size=file_size,
                            duration_ms=duration_ms,
                            sequence_no=0,
                            content_hash=content_hash,
                            created_at=now,
                            updated_at=now,
                        ),
                        ProcessingJob(
                            id=transcode_job_id,
                            record_id=record_id,
                            job_type=ProcessingJobType.AUDIO_TRANSCODE,
                            status=ProcessingJobStatus.PENDING,
                            progress=0,
                            attempts=0,
                            max_attempts=3,
                            input_json=json.dumps({"record_file_id": file_id}),
                            created_at=now,
                            updated_at=now,
                        ),
                        ProcessingJob(
                            id=asr_job_id,
                            record_id=record_id,
                            job_type=ProcessingJobType.ASR,
                            status=ProcessingJobStatus.PENDING,
                            progress=0,
                            attempts=0,
                            max_attempts=3,
                            input_json=json.dumps(
                                {
                                    "record_file_id": file_id,
                                    "depends_on_job_id": transcode_job_id,
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
                await session.flush()
        except BaseException:
            for path in (final_path, temporary_path):
                try:
                    await asyncio.to_thread(_remove_file, path)
                except OSError:
                    logger.error(
                        "audio_import_compensation_failed",
                        error_code="AUDIO_IMPORT_COMPENSATION_FAILED",
                        record_id=record_id,
                    )
            raise

        return AudioImportAccepted(
            record_id=record_id,
            transcode_job_id=transcode_job_id,
            asr_job_id=asr_job_id,
        )
