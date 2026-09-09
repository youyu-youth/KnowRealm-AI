from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.course.service import CourseService
from app.modules.jobs.lifecycle import cancel_nonterminal_jobs
from app.modules.jobs.models import ProcessingJob
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus
from app.modules.review_material.models import ReviewMaterial
from app.modules.search.service import SearchService
from app.modules.summary.models import AiSummary
from app.modules.summary.schemas import AiSummaryStatus
from app.modules.todo.models import TodoItem
from app.modules.transcript.models import DocumentSegment, Transcript, TranscriptSegment
from app.modules.transcript.schemas import TranscriptUpdateRequest
from app.modules.transcript.segments import SegmentService
from app.shared.errors import CodedHTTPException


class RecordService:
    @staticmethod
    async def get(session: AsyncSession, record_id: str) -> Record | None:
        statement = select(Record).where(
            Record.id == record_id,
            Record.deleted_at.is_(None),
        )
        record = (await session.scalars(statement)).one_or_none()
        if record is None:
            return None
        if (
            record.course_id is not None
            and await CourseService.get(session, record.course_id) is None
        ):
            return None
        return record

    @staticmethod
    async def list_for_course(
        session: AsyncSession,
        course_id: str,
    ) -> list[Record] | None:
        if await CourseService.get(session, course_id) is None:
            return None
        statement = (
            select(Record)
            .where(
                Record.course_id == course_id,
                Record.deleted_at.is_(None),
            )
            .order_by(Record.created_at.desc())
        )
        return list((await session.scalars(statement)).all())

    @staticmethod
    async def list_inbox(session: AsyncSession) -> list[Record]:
        statement = (
            select(Record)
            .where(
                Record.course_id.is_(None),
                Record.deleted_at.is_(None),
            )
            .order_by(Record.created_at.desc(), Record.id.desc())
        )
        return list((await session.scalars(statement)).all())

    @staticmethod
    async def get_transcript(session: AsyncSession, record_id: str) -> Transcript | None:
        statement = select(Transcript).where(
            Transcript.record_id == record_id,
            Transcript.deleted_at.is_(None),
        )
        return (await session.scalars(statement)).one_or_none()

    @staticmethod
    async def get_transcript_segments(
        session: AsyncSession, record_id: str
    ) -> list[TranscriptSegment]:
        """当前生效转写（未软删）的分片；转写不存在或已删时返回空。"""
        transcript = await RecordService.get_transcript(session, record_id)
        if transcript is None:
            return []
        return list(
            (
                await session.scalars(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.record_id == record_id)
                    .order_by(TranscriptSegment.sequence_no)
                )
            ).all()
        )

    @staticmethod
    async def get_document_segments(session: AsyncSession, record_id: str) -> list[DocumentSegment]:
        """该记录文档分片（sequence_no 全局有序）；记录级软删过滤由端点前置校验承担。"""
        return list(
            (
                await session.scalars(
                    select(DocumentSegment)
                    .where(DocumentSegment.record_id == record_id)
                    .order_by(DocumentSegment.sequence_no)
                )
            ).all()
        )

    @staticmethod
    async def soft_delete(session: AsyncSession, record_id: str) -> bool:
        async with session.begin():
            record = await RecordService.get(session, record_id)
            if record is None:
                return False
            deleted_at = utcnow()
            record.deleted_at = deleted_at
            record.updated_at = deleted_at
            await cancel_nonterminal_jobs(
                session,
                record_filter=ProcessingJob.record_id == record_id,
                now=deleted_at,
            )
            await session.execute(
                update(ReviewMaterial)
                .where(
                    ReviewMaterial.record_id == record_id,
                    ReviewMaterial.deleted_at.is_(None),
                )
                .values(deleted_at=deleted_at, updated_at=deleted_at)
            )
            await session.execute(
                update(TodoItem)
                .where(
                    TodoItem.record_id == record_id,
                    TodoItem.deleted_at.is_(None),
                )
                .values(deleted_at=deleted_at, updated_at=deleted_at)
            )
            await session.flush()
        return True

    @staticmethod
    async def update_transcript(
        session: AsyncSession,
        record_id: str,
        body: TranscriptUpdateRequest,
    ) -> Transcript:
        if not body.content.strip():
            raise CodedHTTPException(
                code="TRANSCRIPT_EMPTY", status_code=422, detail="Transcript 正文不能为空"
            )
        now = utcnow()
        async with session.begin():
            record = await RecordService.get(session, record_id)
            if record is None:
                raise CodedHTTPException(
                    code="RECORD_NOT_FOUND", status_code=404, detail="学习记录不存在或已删除"
                )
            if record.status in (
                RecordStatus.CONTENT_PROCESSING,
                RecordStatus.SUMMARY_PROCESSING,
            ):
                raise CodedHTTPException(
                    code="TRANSCRIPT_NOT_EDITABLE",
                    status_code=409,
                    detail="当前状态不允许编辑 Transcript",
                )
            transcript = (
                await session.scalars(
                    update(Transcript)
                    .where(
                        Transcript.record_id == record_id,
                        Transcript.deleted_at.is_(None),
                        Transcript.source_version == body.expected_source_version,
                    )
                    .values(
                        content=body.content,
                        source_version=Transcript.source_version + 1,
                        edited_by_user=True,
                        updated_at=now,
                    )
                    .returning(Transcript)
                )
            ).one_or_none()
            if transcript is None:
                current = await RecordService.get_transcript(session, record_id)
                if current is None:
                    raise CodedHTTPException(
                        code="TRANSCRIPT_NOT_READY", status_code=404, detail="Transcript 尚未生成"
                    )
                raise CodedHTTPException(
                    code="TRANSCRIPT_VERSION_CONFLICT",
                    status_code=409,
                    detail="Transcript 已被其他操作更新",
                )
            await session.execute(
                update(AiSummary)
                .where(
                    AiSummary.record_id == record_id,
                    AiSummary.deleted_at.is_(None),
                    AiSummary.status.in_((AiSummaryStatus.GENERATED, AiSummaryStatus.CONFIRMED)),
                )
                .values(status=AiSummaryStatus.SUPERSEDED, updated_at=now)
            )
            # NOTE 是纯本地文本：编辑只更新 Transcript，保持 NOTE、不推进到总结流程。
            if record.status != RecordStatus.NOTE:
                record.status = RecordStatus.SUMMARY_PENDING
                record.updated_at = now
            await SegmentService.realign_for_edit(session, transcript.id, record_id, body.content)
            await session.flush()
            await SearchService.upsert_record_index(session, record_id)
        return transcript
