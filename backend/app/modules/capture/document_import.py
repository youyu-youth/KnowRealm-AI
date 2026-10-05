import asyncio
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from fastapi import UploadFile
from loguru import logger
from sqlalchemy import select
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
from app.modules.library.backfill import ensure_backfill_enqueued
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus
from app.modules.search.service import SearchService
from app.shared.errors import CodedHTTPException

SUPPORTED_DOCUMENTS = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


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


def remove_import_file(path: Path) -> None:
    path.unlink(missing_ok=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass


def _hash_file(path: Path) -> tuple[int, str]:
    """只读计算文件大小与内容指纹（幂等预查用，不复制）。"""
    size = 0
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


async def create_document_ingest_rows(
    session: AsyncSession,
    data_dir: Path,
    course_id: str | None,
    source_path: Path,
    *,
    title: str | None = None,
) -> tuple[str, str, str | None]:
    """本地文档导入的事务内核心（第三阶段工单 07）：HTTP 上传与 Agent 计划
    步骤共用，调用方拥有事务边界。

    与 :meth:`DocumentImportService.create` 的差异：source 是磁盘上既有的
    用户文件（路径由用户在对话中明确提供），先只读算指纹做幂等预查——
    同课程同内容指纹的既有导入（步骤重试场景）直接复用，解析任务按其终态
    决定是否新投；新导入则复制进 files/ 并建行（Record + RecordFile +
    DOCUMENT_PARSE 任务 + 索引 + 回填，与 HTTP 路径同一套行构造）。
    返回 (record_id, file_id, awaited_job_id | None)。
    """
    source = Path(source_path)
    extension = source.suffix.lower()
    if not source.is_file() or extension not in SUPPORTED_DOCUMENTS:
        raise CodedHTTPException(
            code="DOCUMENT_FILE_UNREADABLE",
            status_code=400,
            detail="本地文档不存在或不支持（仅支持 TXT、MD、PDF、DOCX）",
        )
    try:
        file_size, content_hash = await asyncio.to_thread(_hash_file, source)
    except OSError as exc:
        # 源文件被占用（Windows 锁，如正被编辑的 DOCX）等读取失败：步骤级
        # 结构化失败可重试，不升级为 Run 级系统性故障。
        raise CodedHTTPException(
            code="DOCUMENT_FILE_UNREADABLE",
            status_code=400,
            detail="本地文档暂时无法读取（可能正被其他程序占用），请关闭后重试",
        ) from exc
    if file_size == 0:
        raise CodedHTTPException(code="DOCUMENT_EMPTY", status_code=400, detail="文件不能为空")
    reused = await _reusable_document_import(session, course_id, content_hash)
    if reused is not None:
        record_id, file_id = reused
        job_id = await _reschedule_failed_parse(session, record_id, file_id)
        return record_id, file_id, job_id
    original_name = source.name
    record_id, file_id, job_id = (str(uuid4()) for _ in range(3))
    target_dir = data_dir / "files" / record_id
    target_dir.mkdir(parents=True)
    temporary_path = data_dir / "cache" / "imports" / f"{file_id}.tmp"
    temporary_path.parent.mkdir(parents=True, exist_ok=True)
    final_path = target_dir / f"{file_id}{extension}"
    try:
        try:
            await asyncio.to_thread(shutil.copyfile, source, temporary_path)
        except OSError as exc:
            raise CodedHTTPException(
                code="DOCUMENT_FILE_UNREADABLE",
                status_code=400,
                detail="本地文档暂时无法读取（可能正被其他程序占用），请关闭后重试",
            ) from exc
        free_after_write = (await asyncio.to_thread(shutil.disk_usage, target_dir)).free
        if free_after_write + file_size < file_size * 2:
            raise CodedHTTPException(
                code="INSUFFICIENT_DISK", status_code=507, detail="数据目录可用空间不足"
            )
        await asyncio.to_thread(os.replace, temporary_path, final_path)
        await _ingest_document_rows(
            session,
            data_dir,
            course_id,
            final_path=final_path,
            original_name=original_name,
            extension=extension,
            file_size=file_size,
            content_hash=content_hash,
            record_id=record_id,
            file_id=file_id,
            job_id=job_id,
            title=title,
        )
    except BaseException:
        for path in (final_path, temporary_path):
            try:
                await asyncio.to_thread(remove_import_file, path)
            except OSError:
                logger.error(
                    "document_import_compensation_failed",
                    error_code="DOCUMENT_IMPORT_COMPENSATION_FAILED",
                    record_id=record_id,
                )
        raise
    return record_id, file_id, job_id


async def _reusable_document_import(
    session: AsyncSession, course_id: str | None, content_hash: str
) -> tuple[str, str] | None:
    """同课程同内容指纹的既有导入（步骤重试幂等）：返回 (record_id, file_id)。
    归类口径含未归类（course_id 双侧 NULL）。"""
    row = (
        await session.execute(
            select(RecordFile.id, RecordFile.record_id)
            .join(Record, RecordFile.record_id == Record.id)
            .where(
                RecordFile.content_hash == content_hash,
                Record.course_id.is_(course_id),
                Record.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).first()
    return (row.record_id, row.id) if row is not None else None


async def _reschedule_failed_parse(
    session: AsyncSession, record_id: str, file_id: str
) -> str | None:
    """复用导入的解析任务口径：活动任务等待之；上次失败原地重置回 PENDING
    （对齐 jobs 重试通道 ProcessingJobService.retry 的语义，不新投——新投会使
    记录的解析任务数超过文件数，finalizer 的等数判定 len(files)==len(jobs)
    永不成立，任务成功后记录仍卡 CONTENT_PROCESSING、无 Transcript）；
    Record 状态重置回 CONTENT_PROCESSING——document worker 的候选查询按该
    状态过滤，不重置则任务永不被领取、Run 永久等待；已成功不再投；
    无任务（异常数据）新建兜底（任务数 0→1 不破坏等数判定）。"""
    job = (
        await session.execute(
            select(ProcessingJob)
            .where(
                ProcessingJob.record_id == record_id,
                ProcessingJob.job_type == ProcessingJobType.DOCUMENT_PARSE,
            )
            .order_by(ProcessingJob.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if job is not None:
        if job.status in (
            ProcessingJobStatus.PENDING.value,
            ProcessingJobStatus.RUNNING.value,
        ):
            return job.id
        if job.status == ProcessingJobStatus.SUCCEEDED.value:
            return None
    now = utcnow()
    awaited_job_id: str
    if job is None:
        awaited_job_id = str(uuid4())
        session.add(
            ProcessingJob(
                id=awaited_job_id,
                record_id=record_id,
                job_type=ProcessingJobType.DOCUMENT_PARSE,
                status=ProcessingJobStatus.PENDING,
                progress=0,
                attempts=0,
                max_attempts=3,
                input_json=json.dumps({"record_file_id": file_id}),
                created_at=now,
                updated_at=now,
            )
        )
    else:
        # FAILED / CANCELLED：原地重置（字段集对齐 ProcessingJobService.retry
        # 的非 ASR 分支）。
        awaited_job_id = job.id
        job.status = ProcessingJobStatus.PENDING
        job.progress = 0
        job.attempts = 0
        job.next_run_at = None
        job.waiting_reason = None
        job.error_code = None
        job.error_message = None
        job.started_at = None
        job.finished_at = None
        job.result_json = None
        job.updated_at = now
    record = await session.get(Record, record_id)
    if record is not None:
        record.status = RecordStatus.CONTENT_PROCESSING
        record.updated_at = now
    await session.flush()
    return awaited_job_id


async def _ingest_document_rows(
    session: AsyncSession,
    data_dir: Path,
    course_id: str | None,
    *,
    final_path: Path,
    original_name: str,
    extension: str,
    file_size: int,
    content_hash: str,
    record_id: str,
    file_id: str,
    job_id: str,
    title: str | None = None,
) -> None:
    """导入行构造（调用方事务内）：Record + RecordFile + DOCUMENT_PARSE 任务 +
    搜索索引 + 资料库回填。title 是 Agent 计划步骤携带的展示标题（缺省用
    文件名去扩展名）。"""
    await valid_course(session, course_id)
    now = utcnow()
    session.add(
        Record(
            id=record_id,
            course_id=course_id,
            capture_type=CaptureType.DOCUMENT_IMPORT,
            title=(title or "").strip() or Path(original_name).stem,
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
    await ensure_backfill_enqueued(session)


async def valid_course(session: AsyncSession, course_id: str | None) -> None:
    """课程可达性与归档校验（HTTP / Agent 计划步骤 / web ingest 与生命周期
    归类共用，跨模块公开正本——detail 与 ingest 侧既有文案统一）。"""
    if course_id is not None:
        course: Course | None = await CourseService.get(session, course_id)
        if course is None:
            raise CodedHTTPException(
                code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
            )
        if course.status != CourseStatus.ACTIVE:
            raise CodedHTTPException(
                code="COURSE_ARCHIVED",
                status_code=409,
                detail="已归档课程不能接受新资料",
            )


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
            raise CodedHTTPException(
                code="DOCUMENT_FORMAT_UNSUPPORTED",
                status_code=400,
                detail="仅支持 TXT、MD、PDF 或 DOCX 文件",
            )

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
                copy_upload, upload.file, temporary_path
            )
            if file_size == 0:
                raise CodedHTTPException(
                    code="DOCUMENT_EMPTY", status_code=400, detail="文件不能为空"
                )
            free_after_write = (await asyncio.to_thread(shutil.disk_usage, target_dir)).free
            if free_after_write + file_size < file_size * 2:
                raise CodedHTTPException(
                    code="INSUFFICIENT_DISK", status_code=507, detail="数据目录可用空间不足"
                )
            await asyncio.to_thread(os.replace, temporary_path, final_path)

            # HTTP 路径自持事务边界（Agent 计划步骤路径由应用器调用方拥有事务，
            # 复用 _ingest_document_rows 时零内嵌 begin）。
            async with session.begin():
                await _ingest_document_rows(
                    session,
                    data_dir,
                    course_id,
                    final_path=final_path,
                    original_name=original_name,
                    extension=extension,
                    file_size=file_size,
                    content_hash=content_hash,
                    record_id=record_id,
                    file_id=file_id,
                    job_id=job_id,
                )
        except BaseException:
            for path in (final_path, temporary_path):
                try:
                    await asyncio.to_thread(remove_import_file, path)
                except OSError:
                    logger.error(
                        "document_import_compensation_failed",
                        error_code="DOCUMENT_IMPORT_COMPENSATION_FAILED",
                        record_id=record_id,
                    )
            raise

        return DocumentImportAccepted(record_id=record_id, job_id=job_id)
