"""资料条目生命周期动作（工单 05）：重命名/归类/归档恢复/软删回收站/物理删除/
失败重试/重新抓取/索引重建，与回收站 30 天保留期清理。

语义定案：
- 软删不级联 Record——Record、其学习资产与索引原样保留（检索层 04 已按
  deleted_at 过滤，条目不再以资料身份召回）；恢复时校验快照完整性并幂等
  重建索引（索引是可再生衍生数据）。
- 物理删除的活动引用防线：存在未软删派生 Record 时 409；条目行删除后其
  链接、技术任务与直挂 document_segments 随 FK CASCADE 消亡（分片索引行
  先显式清理）。快照文件不在此删：files/ 目录生命周期跟随 Record 清理
  周期与孤儿清理（Record 已软删/不存在时其文件最终被既有周期收走）。
- 重新抓取 = 同 URL 新条目（allow_duplicate 强制放行），不覆盖旧快照、
  不建版本表；Course 归类只改条目 course_id，派生 Record 不静默跨 Course
  移动（COURSE 档可见范围按 li.course_id 查询期重算）。
"""

import asyncio
import json
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.capture.ingest import LibraryIngestService, valid_course
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.library.models import LibraryItem, LibraryItemRecord
from app.modules.library.schemas import (
    LibraryIngestAccepted,
    LibraryIngestRequest,
    LibraryIngestSource,
    LibraryItemOut,
    LibraryItemPatch,
    LibrarySourceType,
)
from app.modules.library.service import PARSE_JOB_TYPES, LibraryService
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus
from app.modules.search.segment_service import ENTITY_DOCUMENT_SEGMENT, SegmentSearchService
from app.modules.search.service import SearchService
from app.modules.transcript.models import DocumentSegment
from app.shared.errors import CodedHTTPException

TRASH_RETENTION_DAYS = 30


async def _trash_item(session: AsyncSession, item_id: str) -> LibraryItem:
    item = await session.get(LibraryItem, item_id)
    if item is None:
        raise CodedHTTPException(
            code="LIBRARY_ITEM_NOT_FOUND", status_code=404, detail="资料条目不存在"
        )
    if item.deleted_at is None:
        raise CodedHTTPException(
            code="LIBRARY_ITEM_NOT_IN_TRASH",
            status_code=409,
            detail="资料条目不在回收站中",
        )
    return item


async def _verify_snapshot(data_dir: Path, item: LibraryItem) -> None:
    """回收站恢复前的快照完整性校验：只在存在可验证哈希锚时执行。

    WEB 条目锚 = metadata.content_hash（正文哈希，03 定案：列上恒为 URL 哈希）；
    单文件 DOCUMENT 条目锚 = 列 content_hash；聚合哈希（多文件回填）与 TEXT
    （无文件）无可验证锚，跳过深检（文件缺失由使用路径自然暴露）。
    """
    if not item.local_path:
        return
    expected: str | None = None
    single_file_import = False
    try:
        loaded: object = json.loads(item.metadata_json)
    except ValueError:
        loaded = None
    if isinstance(loaded, dict):
        metadata = cast("dict[str, object]", loaded)
        raw_expected: object = metadata.get("content_hash")
        if isinstance(raw_expected, str):
            expected = raw_expected
        elif item.source_type == LibrarySourceType.DOCUMENT:
            files: object = metadata.get("files")
            if isinstance(files, list) and len(cast("list[object]", files)) == 1:
                single_file_import = True
    if expected is None and single_file_import:
        expected = item.content_hash
    if not isinstance(expected, str):
        return
    rel = PurePosixPath(item.local_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise CodedHTTPException(
            code="LIBRARY_ITEM_SNAPSHOT_INVALID", status_code=409, detail="快照路径异常，无法恢复"
        )
    path = data_dir / Path(*rel.parts)
    try:
        payload = await asyncio.to_thread(path.read_bytes)
    except OSError:
        raise CodedHTTPException(
            code="LIBRARY_ITEM_SNAPSHOT_INVALID",
            status_code=409,
            detail="快照文件缺失或不可读，无法恢复",
        ) from None
    if sha256(payload).hexdigest() != expected:
        raise CodedHTTPException(
            code="LIBRARY_ITEM_SNAPSHOT_INVALID",
            status_code=409,
            detail="快照内容与入库时不一致，无法恢复",
        )


class LibraryLifecycleService:
    @staticmethod
    async def patch_item(
        session: AsyncSession, item_id: str, body: LibraryItemPatch
    ) -> LibraryItemOut:
        """重命名 / 归类（null=取消归类）/ 收藏；字段缺省与显式 null 语义不同。"""
        async with session.begin():
            item = await LibraryService.active_item(session, item_id)
            await LibraryLifecycleService.patch_core(session, item, body)
        return await LibraryService.item_out(session, item)

    @staticmethod
    async def patch_core(
        session: AsyncSession, item: LibraryItem, body: LibraryItemPatch
    ) -> None:
        """重命名 / 归类 / 收藏事务内核心（工单 03）：调用方拥有事务边界，
        HTTP 路由与 Agent 应用器共用同一校验链；updated_at 统一维护
        （快照纪律显式不变量，spec 决策 12）。"""
        updates = body.model_dump(exclude_unset=True)
        if "title" in updates:
            title = (updates["title"] or "").strip()
            if not title:
                raise CodedHTTPException(
                    code="LIBRARY_PATCH_EMPTY", status_code=422, detail="标题不能为空"
                )
            item.title = title
        if "course_id" in updates:
            course_id = updates["course_id"]
            if course_id is None:
                item.course_id = None
            else:
                await valid_course(session, str(course_id))
                item.course_id = str(course_id)
        if "favorite" in updates:
            item.favorite = cast(bool, updates["favorite"])
        item.updated_at = utcnow()

    @staticmethod
    async def set_archived(session: AsyncSession, item_id: str, archived: bool) -> LibraryItemOut:
        async with session.begin():
            item = await LibraryService.active_item(session, item_id)
            await LibraryLifecycleService.set_archived_core(session, item, archived=archived)
        return await LibraryService.item_out(session, item)

    @staticmethod
    async def set_archived_core(
        session: AsyncSession, item: LibraryItem, *, archived: bool
    ) -> None:
        """条目归档 / 恢复事务内核心（工单 03）：HTTP 路由与 Agent 应用器共用。"""
        if archived and item.status == "ARCHIVED":
            raise CodedHTTPException(
                code="LIBRARY_ITEM_ALREADY_ARCHIVED", status_code=409, detail="资料条目已归档"
            )
        if not archived and item.status == "ACTIVE":
            raise CodedHTTPException(
                code="LIBRARY_ITEM_ALREADY_ACTIVE", status_code=409, detail="资料条目未归档"
            )
        item.status = "ARCHIVED" if archived else "ACTIVE"
        item.updated_at = utcnow()

    @staticmethod
    async def soft_delete(session: AsyncSession, item_id: str) -> LibraryItemOut:
        """软删入回收站（30 天）：不级联 Record 与学习资产、不动索引。"""
        async with session.begin():
            item = await LibraryService.active_item(session, item_id)
            now = utcnow()
            item.deleted_at = now
            item.updated_at = now
        return await LibraryService.item_out(session, item)

    @staticmethod
    async def restore(
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        item_id: str,
    ) -> LibraryItemOut:
        async with session_factory() as session, session.begin():
            item = await _trash_item(session, item_id)
            await _verify_snapshot(data_dir, item)
            item.deleted_at = None
            item.updated_at = utcnow()
            record_ids = await LibraryService.linked_record_ids(session, item_id)
            for record_id in record_ids:
                # 索引缺失幂等重建：软删期间索引行若意外丢失，恢复即补齐
                # （upsert 先删后插，同事务幂等）。
                await SearchService.upsert_record_index(session, record_id)
                await SegmentSearchService.upsert_record_segments(session, record_id)
        async with session_factory() as session:
            stored = await session.get(LibraryItem, item_id)
            assert stored is not None
            return await LibraryService.item_out(session, stored)

    @staticmethod
    async def purge_item(session_factory: async_sessionmaker[AsyncSession], item_id: str) -> None:
        """物理删除：活动派生 Record 防线 + 活动任务取消 + 直挂分片索引清理。"""
        now = utcnow()
        async with session_factory() as session, session.begin():
            item = await session.get(LibraryItem, item_id)
            if item is None:
                raise CodedHTTPException(
                    code="LIBRARY_ITEM_NOT_FOUND", status_code=404, detail="资料条目不存在"
                )
            alive_record = await session.scalar(
                select(Record.id)
                .join(LibraryItemRecord, LibraryItemRecord.record_id == Record.id)
                .where(
                    LibraryItemRecord.library_item_id == item_id,
                    Record.deleted_at.is_(None),
                )
                .limit(1)
            )
            if alive_record is not None:
                raise CodedHTTPException(
                    code="LIBRARY_ITEM_HAS_DERIVED_RECORDS",
                    status_code=409,
                    detail="存在未删除的派生学习记录，请先处理后再删除资料条目",
                )
            active_jobs = (
                await session.scalars(
                    select(ProcessingJob).where(
                        ProcessingJob.library_item_id == item_id,
                        ProcessingJob.status.in_(
                            (ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING)
                        ),
                    )
                )
            ).all()
            for job in active_jobs:
                job.status = ProcessingJobStatus.CANCELLED
                job.result_json = json.dumps({"reason": "library_item_deleted"})
                job.finished_at = now
                job.updated_at = now
            segment_ids = list(
                await session.scalars(
                    select(DocumentSegment.id).where(DocumentSegment.library_item_id == item_id)
                )
            )
            await SegmentSearchService.delete_segment_index(
                session, ENTITY_DOCUMENT_SEGMENT, segment_ids
            )
            await session.execute(delete(LibraryItem).where(LibraryItem.id == item_id))

    @staticmethod
    async def purge_expired_trash(
        session_factory: async_sessionmaker[AsyncSession],
        *,
        now: datetime | None = None,
    ) -> None:
        """回收站 30 天保留期清理：仅保留期届满且无活动引用的条目物理删除
        （启动期与 DocumentCleanupService 同容错级，失败仅记日志）。"""
        cutoff = (now or utcnow()) - timedelta(days=TRASH_RETENTION_DAYS)
        async with session_factory() as session:
            expired = list(
                (
                    await session.scalars(
                        select(LibraryItem.id).where(
                            LibraryItem.deleted_at.is_not(None), LibraryItem.deleted_at < cutoff
                        )
                    )
                ).all()
            )
        for item_id in expired:
            try:
                await LibraryLifecycleService.purge_item(session_factory, item_id)
            except CodedHTTPException as exc:
                if exc.code == "LIBRARY_ITEM_HAS_DERIVED_RECORDS":
                    continue  # 有活动引用：留给下次周期
                raise

    @staticmethod
    async def retry_failed(session: AsyncSession, item_id: str) -> LibraryItemOut:
        """失败重试：复用解析链最新 FAILED 任务（attempts 归零、错误清空），
        Record 状态回 CONTENT_PROCESSING 以重新满足 worker 领取条件。"""
        async with session.begin():
            item = await LibraryService.active_item(session, item_id)
            record_ids = await LibraryService.linked_record_ids(session, item_id)
            job = (
                await session.scalars(
                    select(ProcessingJob)
                    .where(
                        ProcessingJob.record_id.in_(record_ids or ["__none__"]),
                        ProcessingJob.job_type.in_(PARSE_JOB_TYPES),
                        ProcessingJob.status == ProcessingJobStatus.FAILED,
                    )
                    .order_by(ProcessingJob.updated_at.desc(), ProcessingJob.id.desc())
                    .limit(1)
                )
            ).one_or_none()
            if job is None:
                raise CodedHTTPException(
                    code="LIBRARY_RETRY_NOT_APPLICABLE",
                    status_code=422,
                    detail="该资料条目没有可重试的失败任务",
                )
            active = await session.scalar(
                select(ProcessingJob.id)
                .where(
                    ProcessingJob.record_id == job.record_id,
                    ProcessingJob.job_type == job.job_type,
                    ProcessingJob.status.in_(
                        (ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING)
                    ),
                )
                .limit(1)
            )
            if active is not None:
                raise CodedHTTPException(
                    code="LIBRARY_ITEM_JOB_ACTIVE",
                    status_code=409,
                    detail="该资料条目已有进行中的处理任务",
                )
            now = utcnow()
            job.status = ProcessingJobStatus.PENDING
            job.attempts = 0
            job.progress = 0
            job.next_run_at = None
            job.error_code = None
            job.error_message = None
            job.started_at = None
            job.finished_at = None
            job.updated_at = now
            record = await session.get(Record, job.record_id) if job.record_id else None
            if record is not None and record.deleted_at is None:
                record.status = RecordStatus.CONTENT_PROCESSING
                record.updated_at = now
            item.updated_at = now
        return await LibraryService.item_out(session, item)

    @staticmethod
    async def refetch(
        session_factory: async_sessionmaker[AsyncSession], item_id: str
    ) -> LibraryIngestAccepted:
        """同 URL 重新抓取 = 新条目（不覆盖旧快照、不建版本表）。

        归类继承原条目 course_id；判重锚是 URL 哈希，强制 allow_duplicate
        放行正是「内容变化生成新条目」语义；内容未变时得到的是重复条目，
        由用户在列表自行删除。
        """
        async with session_factory() as session:
            item = await LibraryService.active_item(session, item_id)
            if item.source_type != LibrarySourceType.WEB or not item.origin_uri:
                raise CodedHTTPException(
                    code="LIBRARY_REFETCH_UNSUPPORTED",
                    status_code=422,
                    detail="仅网页资料支持重新抓取",
                )
            url = item.origin_uri
            course_uuid = item.course_id
        return await LibraryIngestService.ingest_web(
            session_factory,
            LibraryIngestRequest(
                source=LibraryIngestSource.WEB,
                url=url,
                course_id=None if course_uuid is None else UUID(course_uuid),
                allow_duplicate=True,
            ),
        )

    @staticmethod
    async def enqueue_index_rebuild(
        session_factory: async_sessionmaker[AsyncSession], item_id: str
    ) -> ProcessingJob:
        """索引重建任务：条目存在即建 INDEX_REBUILD Job（one-active 唯一索引
        拦截并发重复，捕获后转 409 已在进行）。"""
        now = utcnow()
        try:
            async with session_factory() as session, session.begin():
                item = await LibraryService.active_item(session, item_id)
                job = ProcessingJob(
                    id=str(uuid4()),
                    record_id=None,
                    library_item_id=item.id,
                    job_type=ProcessingJobType.INDEX_REBUILD,
                    status=ProcessingJobStatus.PENDING,
                    progress=0,
                    attempts=0,
                    max_attempts=3,
                    input_json=json.dumps({"library_item_id": item.id}),
                    created_at=now,
                    updated_at=now,
                )
                session.add(job)
        except IntegrityError as exc:
            raise CodedHTTPException(
                code="LIBRARY_ITEM_JOB_ACTIVE",
                status_code=409,
                detail="该资料条目已有进行中的索引重建任务",
            ) from exc
        return job
