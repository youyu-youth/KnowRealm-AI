import asyncio
import hashlib
import json
import os
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
    CaptureType,
    DocumentImportAccepted,
    RecordFileSourceType,
    RecordFileType,
)
from app.modules.course.models import Course
from app.modules.course.schemas import CourseStatus
from app.modules.course.service import CourseService
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus
from app.modules.search.service import SearchService

SUPPORTED_DOCUMENTS = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _copy_upload(source: BinaryIO, target: Path) -> tuple[int, str]:
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


def _remove_import_file(path: Path) -> None:
    path.unlink(missing_ok=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass


class DocumentImportService:
    @staticmethod
    async def create(
        session: AsyncSession,
        data_dir: Path,
        course_id: str | None,
        upload: UploadFile,
    ) -> DocumentImportAccepted:
        original_name = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        extension = Path(original_name).suffix.lower()
        if not original_name or extension not in SUPPORTED_DOCUMENTS:
            raise HTTPException(status_code=400, detail="仅支持 TXT、MD、PDF 或 DOCX 文件")

        record_id, file_id, job_id = (str(uuid4()) for _ in range(3))
        target_dir = data_dir / "files" / record_id
        target_dir.mkdir(parents=True)
        # 临时文件落 cache/（与音频导入同约定）：files/ 只接收 os.replace 的完整文件，
        # 全量导出遍历 files/ 时无部分写入竞态。
        temporary_path = data_dir / "cache" / "imports" / f"{file_id}.tmp"
        temporary_path.parent.mkdir(parents=True, exist_ok=True)
        final_path = target_dir / f"{file_id}{extension}"
        try:
            file_size, content_hash = await asyncio.to_thread(
                _copy_upload, upload.file, temporary_path
            )
            if file_size == 0:
                raise HTTPException(status_code=400, detail="文件不能为空")
            free_after_write = (await asyncio.to_thread(shutil.disk_usage, target_dir)).free
            if free_after_write + file_size < file_size * 2:
                raise HTTPException(status_code=507, detail="数据目录可用空间不足")
            await asyncio.to_thread(os.replace, temporary_path, final_path)

            now = utcnow()
            async with session.begin():
                if course_id is not None:
                    course: Course | None = await CourseService.get(session, course_id)
                    if course is None:
                        raise HTTPException(status_code=404, detail="课程不存在或已删除")
                    if course.status != CourseStatus.ACTIVE:
                        raise HTTPException(status_code=409, detail="已归档课程不能接受新文档")
                session.add(
                    Record(
                        id=record_id,
                        course_id=course_id,
                        capture_type=CaptureType.DOCUMENT_IMPORT,
                        title=Path(original_name).stem,
                        status=RecordStatus.CONTENT_PROCESSING,
                        duration_ms=0,
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
                            file_type=RecordFileType.DOCUMENT,
                            source_type=RecordFileSourceType.UPLOADED,
                            file_path=final_path.relative_to(data_dir).as_posix(),
                            original_name=original_name,
                            mime_type=SUPPORTED_DOCUMENTS[extension],
                            file_size=file_size,
                            sequence_no=0,
                            content_hash=content_hash,
                            created_at=now,
                            updated_at=now,
                        ),
                        ProcessingJob(
                            id=job_id,
                            record_id=record_id,
                            job_type=ProcessingJobType.DOCUMENT_PARSE,
                            status=ProcessingJobStatus.PENDING,
                            progress=0,
                            attempts=0,
                            max_attempts=3,
                            input_json=json.dumps({"record_file_id": file_id}),
                            created_at=now,
                            updated_at=now,
                        ),
                    ]
                )
                await session.flush()
                await SearchService.upsert_record_index(session, record_id)
        except BaseException:
            for path in (final_path, temporary_path):
                try:
                    await asyncio.to_thread(_remove_import_file, path)
                except OSError:
                    logger.error(
                        "document_import_compensation_failed",
                        error_code="DOCUMENT_IMPORT_COMPENSATION_FAILED",
                        record_id=record_id,
                    )
            raise

        return DocumentImportAccepted(record_id=record_id, job_id=job_id)
