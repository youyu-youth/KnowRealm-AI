"""统一入库入口（工单 03）：网页剪藏 / 本地文件 / 纯文本三路适配。

服务落在 capture 域（capture → 下游域法定方向；library 域不反向依赖 capture 的
ORM 模型），路由挂 /api/library/ingest。三类来源各自复用既有管线：
TEXT 复用 text_capture 校验与 Transcript 落库；FILE 复用 document_import 的
扩展名校验、临时落盘与 DOCUMENT_PARSE 任务（解析/分片/finalize 全由现有
document_worker 承接，本模块零新解析逻辑）；WEB 建 WEB_FETCH 任务由
web_fetch_worker 异步抓取净化。三路同事务创建 LibraryItem + library_item_records
链接——LIBRARY_BACKFILL 扫描「无链接记录」差集，天然不重复建条目。
"""

import asyncio
import json
import os
import shutil
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.capture.document_import import (
    SUPPORTED_DOCUMENTS,
    copy_upload,
    remove_import_file,
    valid_course,
)
from app.modules.capture.models import RecordFile
from app.modules.capture.schemas import (
    CaptureType,
    RecordFileSourceType,
    RecordFileType,
)
from app.modules.capture.web_clip import WebClipError, validate_public_http_url
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.library.models import LibraryItem, LibraryItemRecord
from app.modules.library.schemas import (
    LibraryIngestAccepted,
    LibraryIngestRequest,
    LibrarySourceType,
)
from app.modules.library.service import LibraryService
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus
from app.modules.search.service import SearchService
from app.modules.transcript.models import Transcript
from app.shared.errors import CodedHTTPException

MAX_TEXT_BYTES = 1024 * 1024


async def _duplicate_item_id(session: AsyncSession, content_hash: str) -> str | None:
    row = (
        await session.execute(
            select(LibraryItem.id)
            .where(LibraryItem.content_hash == content_hash, LibraryItem.deleted_at.is_(None))
            .limit(1)
        )
    ).scalar_one_or_none()
    return row


def _raise_duplicate(existing_item_id: str) -> None:
    raise CodedHTTPException(
        code="LIBRARY_ITEM_DUPLICATE_CONTENT",
        status_code=409,
        detail="已存在相同内容的资料条目",
        params={"existing_item_id": existing_item_id},
    )


def _item_metadata(kind: str, extra: dict[str, object] | None = None) -> str:
    payload: dict[str, object] = {"kind": kind}
    if extra:
        payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


async def create_web_ingest_rows(
    session: AsyncSession,
    url: str,
    course_id: str | None,
    *,
    allow_duplicate: bool,
    title: str | None = None,
) -> tuple[str, str, str]:
    """WEB 入库的事务内核心（ingest_web 与 RESEARCH_INGEST 提案应用器共用，
    工单 05）：在调用者事务内写入 Record + LibraryItem + WEB_FETCH 任务 +
    关联 + 搜索索引，返回 (record_id, item_id, job_id)。title 为提案携带的
    展示标题（抓取成功后由 web_fetch_worker 用页面真标题覆盖）；真实抓取
    由 web_fetch_worker 异步完成——确认前不发起任何网络请求。"""
    try:
        validate_public_http_url(url)
    except WebClipError as exc:
        raise CodedHTTPException(code=exc.code, status_code=422, detail=exc.detail) from exc
    host = urlsplit(url).hostname or url
    display_title = (title or "").strip() or host
    content_hash = sha256(f"web:{url}".encode()).hexdigest()
    record_id, item_id, job_id = (str(uuid4()) for _ in range(3))
    now = utcnow()
    await valid_course(session, course_id)
    duplicate = await _duplicate_item_id(session, content_hash)
    if duplicate is not None and not allow_duplicate:
        _raise_duplicate(duplicate)
    session.add(
        Record(
            id=record_id,
            course_id=course_id,
            capture_type=CaptureType.CLIP,
            title=display_title,
            status=RecordStatus.CONTENT_PROCESSING,
            duration_ms=0,
            summary_confirmed_at=None,
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()
    session.add(
        LibraryItem(
            id=item_id,
            course_id=course_id,
            source_type=LibrarySourceType.WEB,
            title=display_title,
            origin_uri=url,
            local_path=None,
            mime_type=None,
            file_size=None,
            content_hash=content_hash,
            metadata_json=_item_metadata("web", {"url": url, "pending": True}),
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()
    session.add(
        ProcessingJob(
            id=job_id,
            record_id=record_id,
            library_item_id=item_id,
            job_type=ProcessingJobType.WEB_FETCH,
            status=ProcessingJobStatus.PENDING,
            progress=0,
            attempts=0,
            # 业务失败仍一次性终态（worker apply_failure 不看预算）；3 次预算
            # 只被重启恢复消费（进程中断自动重投，工单 08）。
            max_attempts=3,
            input_json=json.dumps({"url": url, "library_item_id": item_id}),
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        LibraryItemRecord(
            library_item_id=item_id,
            record_id=record_id,
            role="PRIMARY",
            sequence_no=0,
            created_at=now,
        )
    )
    await session.flush()
    await SearchService.upsert_record_index(session, record_id)
    return record_id, item_id, job_id


class LibraryIngestService:
    @staticmethod
    async def ingest_text(
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        body: LibraryIngestRequest,
    ) -> LibraryIngestAccepted:
        from app.modules.capture.text_capture import content_title, normalize_content

        content = normalize_content(body.content or "")
        if not content.strip():
            raise CodedHTTPException(
                code="LIBRARY_INGEST_INVALID_REQUEST", status_code=422, detail="正文不能为空"
            )
        if len(content.encode("utf-8")) > MAX_TEXT_BYTES:
            raise CodedHTTPException(
                code="LIBRARY_ITEM_LIMIT_EXCEEDED",
                status_code=422,
                detail="正文超过 1 MiB 上限",
            )
        title = (body.title or "").strip() or content_title(content)
        content_hash = sha256(content.encode("utf-8")).hexdigest()

        record_id, item_id = (str(uuid4()) for _ in range(2))
        now = utcnow()
        course_id = str(body.course_id) if body.course_id is not None else None
        async with session_factory() as session, session.begin():
            await valid_course(session, course_id)
            duplicate = await _duplicate_item_id(session, content_hash)
            if duplicate is not None and not body.allow_duplicate:
                _raise_duplicate(duplicate)
            session.add(
                Record(
                    id=record_id,
                    course_id=course_id,
                    capture_type=CaptureType.PASTE,
                    title=title or "未命名文本",
                    status=(RecordStatus.SUMMARY_PENDING if course_id else RecordStatus.NOTE),
                    duration_ms=0,
                    summary_confirmed_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.flush()
            session.add(
                Transcript(
                    record_id=record_id,
                    language="und",
                    content=content,
                    source_version=1,
                    edited_by_user=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            item = LibraryItem(
                id=item_id,
                course_id=course_id,
                source_type=LibrarySourceType.TEXT,
                title=title or "未命名文本",
                origin_uri=body.origin_uri,
                local_path=None,
                mime_type="text/plain",
                file_size=len(content.encode("utf-8")),
                content_hash=content_hash,
                metadata_json=_item_metadata("PASTE", {"char_count": len(content)}),
                created_at=now,
                updated_at=now,
            )
            session.add(item)
            await session.flush()
            session.add(
                LibraryItemRecord(
                    library_item_id=item_id,
                    record_id=record_id,
                    role="PRIMARY",
                    sequence_no=0,
                    created_at=now,
                )
            )
            await session.flush()
            await SearchService.upsert_record_index(session, record_id)

        if course_id:
            from app.modules.summary.service import SummaryService

            await SummaryService.enqueue_if_eligible_best_effort(
                session_factory,
                data_dir,
                record_id,
                log_event="library_ingest_summary_enqueue_failed",
                error_code="LIBRARY_INGEST_SUMMARY_ENQUEUE_FAILED",
            )
        async with session_factory() as session:
            stored = await session.get(LibraryItem, item_id)
            assert stored is not None
            out = await LibraryService.item_out(session, stored)
        return LibraryIngestAccepted(item=out, job=None)

    @staticmethod
    async def ingest_web(
        session_factory: async_sessionmaker[AsyncSession],
        body: LibraryIngestRequest,
    ) -> LibraryIngestAccepted:
        url = (body.url or "").strip()
        course_id = str(body.course_id) if body.course_id is not None else None
        async with session_factory() as session, session.begin():
            _record_id, item_id, job_id = await create_web_ingest_rows(
                session, url, course_id, allow_duplicate=body.allow_duplicate
            )

        async with session_factory() as session:
            from app.modules.jobs.service import ProcessingJobService

            stored_item = await session.get(LibraryItem, item_id)
            stored_job = await session.get(ProcessingJob, job_id)
            assert stored_item is not None and stored_job is not None
            out = await LibraryService.item_out(session, stored_item)
            job_out = ProcessingJobService.to_out(stored_job)
        return LibraryIngestAccepted(item=out, job=job_out)

    @staticmethod
    async def ingest_file(
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        upload: UploadFile,
        course_id: str | None,
        allow_duplicate: bool,
    ) -> LibraryIngestAccepted:
        original_name = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
        extension = Path(original_name).suffix.lower()
        if not original_name or extension not in SUPPORTED_DOCUMENTS:
            raise CodedHTTPException(
                code="DOCUMENT_FORMAT_UNSUPPORTED",
                status_code=400,
                detail="仅支持 TXT、MD、PDF 或 DOCX 文件",
            )

        record_id, file_id, item_id, job_id = (str(uuid4()) for _ in range(4))
        target_dir = data_dir / "files" / record_id
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
            await asyncio.to_thread(target_dir.mkdir, parents=True, exist_ok=True)
            free_after_write = (await asyncio.to_thread(shutil.disk_usage, target_dir)).free
            if free_after_write + file_size < file_size * 2:
                raise CodedHTTPException(
                    code="INSUFFICIENT_DISK", status_code=507, detail="数据目录可用空间不足"
                )
            async with session_factory() as session:
                await valid_course(session, course_id)
                duplicate = await _duplicate_item_id(session, content_hash)
            if duplicate is not None and not allow_duplicate:
                _raise_duplicate(duplicate)
            await asyncio.to_thread(os.replace, temporary_path, final_path)

            title = Path(original_name).stem
            now = utcnow()
            async with session_factory() as session, session.begin():
                session.add(
                    Record(
                        id=record_id,
                        course_id=course_id,
                        capture_type=CaptureType.DOCUMENT_IMPORT,
                        title=title,
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
                        LibraryItem(
                            id=item_id,
                            course_id=course_id,
                            source_type=LibrarySourceType.DOCUMENT,
                            title=title,
                            origin_uri=None,
                            local_path=final_path.relative_to(data_dir).as_posix(),
                            mime_type=SUPPORTED_DOCUMENTS[extension],
                            file_size=file_size,
                            content_hash=content_hash,
                            metadata_json=_item_metadata(
                                "DOCUMENT_IMPORT",
                                {
                                    "files": [
                                        {
                                            "id": file_id,
                                            "original_name": original_name,
                                            "mime_type": SUPPORTED_DOCUMENTS[extension],
                                            "file_size": file_size,
                                        }
                                    ]
                                },
                            ),
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
                        LibraryItemRecord(
                            library_item_id=item_id,
                            record_id=record_id,
                            role="PRIMARY",
                            sequence_no=0,
                            created_at=now,
                        ),
                    ]
                )
                await session.flush()
                await SearchService.upsert_record_index(session, record_id)
        except BaseException:
            for path in (final_path, temporary_path):
                try:
                    await asyncio.to_thread(remove_import_file, path)
                except OSError:
                    pass
            raise

        async with session_factory() as session:
            from app.modules.jobs.service import ProcessingJobService

            stored_item = await session.get(LibraryItem, item_id)
            stored_job = await session.get(ProcessingJob, job_id)
            assert stored_item is not None and stored_job is not None
            out = await LibraryService.item_out(session, stored_item)
            job_out = ProcessingJobService.to_out(stored_job)
        return LibraryIngestAccepted(item=out, job=job_out)
