"""library 域查询与派生服务：条目列表/详情/内容、联邦记录与资产、可用性派生。

可用性（PROCESSING/RETRIEVABLE/FAILED/EMPTY）从 processing_jobs 与 Segment
事实派生；分页后按批聚合（一组 IN 查询），避免逐条 N+1。
课程软删 → 其记录与资产不可见（对齐 RecordService.get 既有语义）。
"""

import json
from typing import Any, cast

from sqlalchemy import and_, bindparam, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.course.models import Course
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.knowledge_point.models import KnowledgePoint
from app.modules.knowledge_point.schemas import KnowledgePointGenerationStatus
from app.modules.library.models import LibraryItem, LibraryItemRecord
from app.modules.library.schemas import (
    BackfillStatusOut,
    DerivedRecordOut,
    LibraryAssetListQuery,
    LibraryAssetOut,
    LibraryAvailability,
    LibraryItemContentOut,
    LibraryItemDetailOut,
    LibraryItemListOut,
    LibraryItemListQuery,
    LibraryItemOut,
    LibraryRecordListQuery,
    LibraryRecordOut,
    LibrarySmartView,
)
from app.modules.record.models import Record
from app.modules.search.tokenizer import escape_like
from app.modules.transcript.models import Transcript
from app.shared.errors import CodedHTTPException

# 解析链任务类型：只有这些任务的终态影响「处理可用性」（Summary 等下游任务不影响）。
_PARSE_JOB_TYPES = (
    ProcessingJobType.ASR,
    ProcessingJobType.AUDIO_TRANSCODE,
    ProcessingJobType.DOCUMENT_PARSE,
    ProcessingJobType.WEB_FETCH,
)

# 页内条目的关联记录（批查询，避免逐条 N+1）。
_LINKED_RECORD_IDS_SQL = text(
    "SELECT lir.library_item_id, lir.record_id FROM library_item_records lir "
    "WHERE lir.library_item_id IN :ids"
).bindparams(bindparam("ids", expanding=True))

_SEGMENT_COUNT_SQL = text(
    "SELECT ts.record_id AS rid, count(*) AS n FROM transcript_segments ts "
    "WHERE ts.record_id IN :ids GROUP BY ts.record_id "
    "UNION ALL "
    "SELECT ds.record_id AS rid, count(*) AS n FROM document_segments ds "
    "WHERE ds.record_id IN :ids GROUP BY ds.record_id"
).bindparams(bindparam("ids", expanding=True))

_TRANSCRIPT_EXISTS_SQL = text(
    "SELECT DISTINCT t.record_id FROM transcripts t "
    "WHERE t.record_id IN :ids AND t.deleted_at IS NULL"
).bindparams(bindparam("ids", expanding=True))

_PARSE_JOB_SQL = text(
    "SELECT pj.record_id AS rid, pj.status AS st, count(*) AS n FROM processing_jobs pj "
    "WHERE pj.record_id IN :ids AND pj.status IN ('PENDING', 'RUNNING', 'FAILED') "
    "AND pj.job_type IN :types GROUP BY pj.record_id, pj.status"
).bindparams(bindparam("ids", expanding=True), bindparam("types", expanding=True))

_LINKED_COUNT_SUBQ = (
    select(func.count())
    .select_from(LibraryItemRecord)
    .where(LibraryItemRecord.record_id == Record.id)
    .scalar_subquery()
)

# 记录/资产联邦查询的「课程存活」条件：未归类直过，已归类须课程未软删。
_COURSE_ALIVE = or_(
    Record.course_id.is_(None),
    Course.id.is_not(None),
)


def _load_metadata(raw: str) -> dict[str, Any]:
    try:
        value: object = json.loads(raw)
    except ValueError:
        return {}
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _derive_availability(
    record_ids: list[str],
    segment_counts: dict[str, int],
    transcript_ids: set[str],
    job_states: dict[str, set[str]],
) -> LibraryAvailability:
    """条目可用性 = 关联记录聚合：解析中 > 解析失败 > 有分片/正文 > 空。"""
    if any(
        ProcessingJobStatus.PENDING in job_states.get(rid, ())
        or ProcessingJobStatus.RUNNING in job_states.get(rid, ())
        for rid in record_ids
    ):
        return LibraryAvailability.PROCESSING
    if any(ProcessingJobStatus.FAILED in job_states.get(rid, ()) for rid in record_ids):
        return LibraryAvailability.FAILED
    if any(segment_counts.get(rid, 0) > 0 for rid in record_ids):
        return LibraryAvailability.RETRIEVABLE
    if any(rid in transcript_ids for rid in record_ids):
        return LibraryAvailability.RETRIEVABLE
    return LibraryAvailability.EMPTY


class LibraryService:
    """资料条目只读 + 收藏写（重命名/归类/归档/删除随工单 05 生命周期端点）。"""

    @staticmethod
    async def _availability_by_item(
        session: AsyncSession, item_record_ids: dict[str, list[str]]
    ) -> dict[str, LibraryAvailability]:
        all_record_ids = sorted({rid for ids in item_record_ids.values() for rid in ids})
        if not all_record_ids:
            return {item_id: LibraryAvailability.EMPTY for item_id in item_record_ids}
        seg_rows = (await session.execute(_SEGMENT_COUNT_SQL, {"ids": all_record_ids})).all()
        segment_counts: dict[str, int] = {}
        for row in seg_rows:
            segment_counts[cast(str, row.rid)] = segment_counts.get(cast(str, row.rid), 0) + cast(
                int, row.n
            )
        transcript_ids = {
            cast(str, row[0])
            for row in (
                await session.execute(_TRANSCRIPT_EXISTS_SQL, {"ids": all_record_ids})
            ).all()
        }
        rows = (
            await session.execute(
                _PARSE_JOB_SQL, {"ids": all_record_ids, "types": list(_PARSE_JOB_TYPES)}
            )
        ).all()
        job_states: dict[str, set[str]] = {}
        for row in rows:
            job_states.setdefault(cast(str, row.rid), set()).add(cast(str, row.st))
        return {
            item_id: _derive_availability(ids, segment_counts, transcript_ids, job_states)
            for item_id, ids in item_record_ids.items()
        }

    @staticmethod
    async def _course_names(
        session: AsyncSession, course_ids: set[str | None]
    ) -> dict[str | None, str | None]:
        known = sorted(cid for cid in course_ids if cid is not None)
        if not known:
            return {}
        rows = await session.execute(select(Course.id, Course.name).where(Course.id.in_(known)))
        return {cast(str, cid): name for cid, name in rows.all()}

    @staticmethod
    async def _linked_record_ids(session: AsyncSession, item_id: str) -> list[str]:
        rows = (await session.execute(_LINKED_RECORD_IDS_SQL, {"ids": [item_id]})).all()
        return [cast(str, row.record_id) for row in rows]

    @staticmethod
    async def item_out(session: AsyncSession, item: LibraryItem) -> LibraryItemOut:
        record_ids = await LibraryService._linked_record_ids(session, item.id)
        availability = await LibraryService._availability_by_item(session, {item.id: record_ids})
        course_names = await LibraryService._course_names(session, {item.course_id})
        out = LibraryItemOut.model_validate(item)
        out.source_metadata = _load_metadata(item.metadata_json)
        out.course_name = course_names.get(item.course_id)
        out.availability = availability.get(item.id, LibraryAvailability.EMPTY)
        return out

    @staticmethod
    async def latest_backfill(session: AsyncSession) -> BackfillStatusOut | None:
        job = await session.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.job_type == ProcessingJobType.LIBRARY_BACKFILL)
            .order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc())
            .limit(1)
        )
        return None if job is None else BackfillStatusOut.model_validate(job)

    @staticmethod
    async def list_items(session: AsyncSession, query: LibraryItemListQuery) -> LibraryItemListOut:
        stmt = select(LibraryItem).where(LibraryItem.deleted_at.is_(None))
        if query.view == LibrarySmartView.FAVORITES:
            stmt = stmt.where(LibraryItem.favorite.is_(True))
        elif query.view == LibrarySmartView.NEEDS_REVIEW:
            stmt = stmt.where(LibraryItem.course_id.is_(None))
        if query.source_type is not None:
            stmt = stmt.where(LibraryItem.source_type == query.source_type.value)
        if query.unclassified:
            stmt = stmt.where(LibraryItem.course_id.is_(None))
        elif query.course_id is not None:
            stmt = stmt.where(LibraryItem.course_id == str(query.course_id))
        if query.q:
            needle = f"%{escape_like(query.q.strip())}%"
            stmt = stmt.where(
                or_(
                    LibraryItem.title.like(needle, escape="\\"),
                    LibraryItem.origin_uri.like(needle, escape="\\"),
                    LibraryItem.metadata_json.like(needle, escape="\\"),
                )
            )
        stmt = stmt.order_by(LibraryItem.updated_at.desc(), LibraryItem.id.desc())
        total = cast(int, await session.scalar(select(func.count()).select_from(stmt.subquery())))
        items = list(
            (await session.execute(stmt.offset(query.offset).limit(query.limit))).scalars().all()
        )
        link_rows = (
            await session.execute(_LINKED_RECORD_IDS_SQL, {"ids": [i.id for i in items]})
        ).all()
        item_record_ids: dict[str, list[str]] = {item.id: [] for item in items}
        for row in link_rows:
            item_record_ids.setdefault(cast(str, row.library_item_id), []).append(
                cast(str, row.record_id)
            )
        availability = await LibraryService._availability_by_item(session, item_record_ids)
        course_names = await LibraryService._course_names(
            session, {item.course_id for item in items}
        )
        outs = [LibraryService._compose_out(item, availability, course_names) for item in items]
        if query.availability is not None:
            # 可用性为派生值，无法进 WHERE：过滤后 total 改按结果行计数
            # （limit 默认 100 ≥ 桌面规模条目数，页内即全量）。
            outs = [out for out in outs if out.availability == query.availability]
            total = len(outs)
        return LibraryItemListOut(
            items=outs,
            total=total,
            backfill=await LibraryService.latest_backfill(session),
        )

    @staticmethod
    def _compose_out(
        item: LibraryItem,
        availability: dict[str, LibraryAvailability],
        course_names: dict[str | None, str | None],
    ) -> LibraryItemOut:
        out = LibraryItemOut.model_validate(item)
        out.source_metadata = _load_metadata(item.metadata_json)
        out.course_name = course_names.get(item.course_id)
        out.availability = availability.get(item.id, LibraryAvailability.EMPTY)
        return out

    @staticmethod
    async def get_item(session: AsyncSession, item_id: str) -> LibraryItemDetailOut:
        item = await LibraryService._active_item(session, item_id)
        detail = LibraryItemDetailOut.model_validate(item)
        detail.source_metadata = _load_metadata(item.metadata_json)
        record_ids = await LibraryService._linked_record_ids(session, item_id)
        availability = await LibraryService._availability_by_item(session, {item_id: record_ids})
        detail.availability = availability.get(item_id, LibraryAvailability.EMPTY)
        seg_rows = (
            await session.execute(_SEGMENT_COUNT_SQL, {"ids": record_ids or ["__none__"]})
        ).all()
        detail.segment_count = sum(cast(int, row.n) for row in seg_rows)
        if detail.availability == LibraryAvailability.FAILED and record_ids:
            # 失败原因透出（03）：解析链最新 FAILED 任务的稳定错误码，前端据此给降级引导。
            detail.failed_error_code = await session.scalar(
                select(ProcessingJob.error_code)
                .where(
                    ProcessingJob.record_id.in_(record_ids),
                    ProcessingJob.job_type.in_(_PARSE_JOB_TYPES),
                    ProcessingJob.status == ProcessingJobStatus.FAILED,
                )
                .order_by(ProcessingJob.updated_at.desc(), ProcessingJob.id.desc())
                .limit(1)
            )
        rows = (
            await session.execute(
                select(Record, LibraryItemRecord)
                .join(LibraryItemRecord, LibraryItemRecord.record_id == Record.id)
                .where(
                    LibraryItemRecord.library_item_id == item_id,
                    Record.deleted_at.is_(None),
                )
                .order_by(LibraryItemRecord.sequence_no, Record.created_at)
            )
        ).all()
        detail.derived_records = [
            DerivedRecordOut(
                record_id=record.id,
                title=record.title,
                status=record.status,  # type: ignore[arg-type]
                capture_type=record.capture_type,  # type: ignore[arg-type]
                role=link.role,
                sequence_no=link.sequence_no,
            )
            for record, link in rows
        ]
        course_names = await LibraryService._course_names(session, {item.course_id})
        detail.course_name = course_names.get(item.course_id)
        return detail

    @staticmethod
    async def patch_item(session: AsyncSession, item_id: str, favorite: bool) -> LibraryItemOut:
        async with session.begin():
            item = await LibraryService._active_item(session, item_id)
            item.favorite = favorite
            # 不 refresh：refresh 会丢弃未 flush 的属性修改；expire_on_commit=False
            # 使提交后属性仍可读。
        return await LibraryService.item_out(session, item)

    @staticmethod
    async def get_content(session: AsyncSession, item_id: str, limit: int) -> LibraryItemContentOut:
        await LibraryService._active_item(session, item_id)
        record_ids = await LibraryService._linked_record_ids(session, item_id)
        content = ""
        if record_ids:
            alive = list(
                (
                    await session.execute(
                        select(Record.id).where(
                            Record.id.in_(record_ids), Record.deleted_at.is_(None)
                        )
                    )
                ).scalars()
            )
            if alive:
                parts = (
                    (
                        await session.execute(
                            select(Transcript.content)
                            .where(
                                Transcript.record_id.in_(alive),
                                Transcript.deleted_at.is_(None),
                            )
                            .order_by(Transcript.created_at)
                        )
                    )
                    .scalars()
                    .all()
                )
                content = "\n\n".join(parts)
        return LibraryItemContentOut(content=content[:limit], truncated=len(content) > limit)

    @staticmethod
    async def list_records(
        session: AsyncSession, query: LibraryRecordListQuery
    ) -> list[LibraryRecordOut]:
        stmt = (
            select(Record, Course, _LINKED_COUNT_SUBQ)
            .outerjoin(Course, and_(Course.id == Record.course_id, Course.deleted_at.is_(None)))
            .where(Record.deleted_at.is_(None), _COURSE_ALIVE)
        )
        if query.unclassified:
            stmt = stmt.where(Record.course_id.is_(None))
        elif query.course_id is not None:
            stmt = stmt.where(Record.course_id == str(query.course_id))
        if query.q:
            stmt = stmt.where(Record.title.like(f"%{escape_like(query.q.strip())}%", escape="\\"))
        stmt = stmt.order_by(Record.updated_at.desc(), Record.id.desc())
        rows = (await session.execute(stmt)).all()
        record_ids = [record.id for record, _course, _linked in rows]
        link_rows = (
            await session.execute(
                text(
                    "SELECT lir.record_id, lir.library_item_id FROM library_item_records lir "
                    "WHERE lir.record_id IN :ids"
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": record_ids},
            )
        ).all()
        item_ids_by_record: dict[str, list[str]] = {}
        for link_row in link_rows:
            item_ids_by_record.setdefault(cast(str, link_row.record_id), []).append(
                cast(str, link_row.library_item_id)
            )
        return [
            LibraryRecordOut(
                id=record.id,
                course_id=record.course_id,
                course_name=course.name if course is not None else None,
                capture_type=record.capture_type,  # type: ignore[arg-type]
                title=record.title,
                status=record.status,  # type: ignore[arg-type]
                duration_ms=record.duration_ms,
                linked_item_count=cast(int, linked),
                library_item_ids=item_ids_by_record.get(record.id, []),
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            for record, course, linked in rows
        ]

    @staticmethod
    async def list_assets(
        session: AsyncSession, query: LibraryAssetListQuery
    ) -> list[LibraryAssetOut]:
        stmt = (
            select(KnowledgePoint, Record.title, Course.id, Course.name)
            .join(Record, Record.id == KnowledgePoint.record_id)
            .outerjoin(Course, and_(Course.id == Record.course_id, Course.deleted_at.is_(None)))
            .where(
                KnowledgePoint.deleted_at.is_(None),
                KnowledgePoint.generation_status == KnowledgePointGenerationStatus.ACTIVE,
                Record.deleted_at.is_(None),
                _COURSE_ALIVE,
            )
        )
        if query.course_id is not None:
            stmt = stmt.where(Record.course_id == str(query.course_id))
        if query.q:
            needle = f"%{escape_like(query.q.strip())}%"
            stmt = stmt.where(
                or_(
                    KnowledgePoint.name.like(needle, escape="\\"),
                    KnowledgePoint.detail.like(needle, escape="\\"),
                )
            )
        stmt = stmt.order_by(KnowledgePoint.updated_at.desc(), KnowledgePoint.id.desc())
        rows = (await session.execute(stmt)).all()
        return [
            LibraryAssetOut(
                id=kp.id,
                record_id=kp.record_id,
                record_title=cast("str | None", record_title),
                course_id=cast("str | None", course_id),
                course_name=cast("str | None", course_name),
                name=kp.name,
                detail=kp.detail,
                importance=kp.importance,
                generation_status=kp.generation_status,
                created_at=kp.created_at,
                updated_at=kp.updated_at,
            )
            for kp, record_title, course_id, course_name in rows
        ]

    @staticmethod
    async def _active_item(session: AsyncSession, item_id: str) -> LibraryItem:
        item = await session.get(LibraryItem, item_id)
        if item is None or item.deleted_at is not None:
            raise CodedHTTPException(
                code="LIBRARY_ITEM_NOT_FOUND", status_code=404, detail="资料条目不存在或已删除"
            )
        return item
