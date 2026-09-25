from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.capture.models import RecordFile
from app.modules.course.service import CourseService
from app.modules.jobs.lifecycle import cancel_nonterminal_jobs
from app.modules.jobs.models import ProcessingJob
from app.modules.learning.service import MasteryService
from app.modules.record.models import LearningEvent, Record
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
    async def list_inbox(
        session: AsyncSession,
    ) -> list[tuple[Record, int | None, int | None]]:
        """返回 (记录, 文件大小之和字节, 正文字符数)。

        元信息用相关标量子查询取值，避免 files × transcript join 相乘导致 SUM 重复计数。
        """
        file_size_sq = (
            select(func.sum(RecordFile.file_size))
            .where(
                RecordFile.record_id == Record.id,
                RecordFile.deleted_at.is_(None),
            )
            .correlate(Record)
            .scalar_subquery()
        )
        content_chars_sq = (
            select(func.length(Transcript.content))
            .where(
                Transcript.record_id == Record.id,
                Transcript.deleted_at.is_(None),
            )
            .correlate(Record)
            .scalar_subquery()
        )
        statement = (
            select(Record, file_size_sq, content_chars_sq)
            .where(
                Record.course_id.is_(None),
                Record.deleted_at.is_(None),
            )
            .order_by(Record.created_at.desc(), Record.id.desc())
        )
        rows = (await session.execute(statement)).all()
        return [(record, file_size, content_chars) for record, file_size, content_chars in rows]

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
    async def soft_delete_core(session: AsyncSession, record: Record) -> set[str]:
        """记录软删事务内核心（工单 04，不得自行 begin）：软删记录＋取消非终态
        任务＋复习资料与 Todo 级联软删；返回受影响 Concept 集合（调用方触发
        Mastery 重算）。历史 Event/Evidence 原样保留审计价值。"""
        affected_concepts = {
            concept_id
            for concept_id in (
                await session.scalars(
                    select(LearningEvent.concept_id).where(
                        LearningEvent.record_id == record.id,
                        LearningEvent.concept_id.is_not(None),
                    )
                )
            ).all()
            if concept_id is not None
        }
        deleted_at = utcnow()
        record.deleted_at = deleted_at
        record.updated_at = deleted_at
        await cancel_nonterminal_jobs(
            session,
            record_filter=ProcessingJob.record_id == record.id,
            now=deleted_at,
        )
        await session.execute(
            update(ReviewMaterial)
            .where(
                ReviewMaterial.record_id == record.id,
                ReviewMaterial.deleted_at.is_(None),
            )
            .values(deleted_at=deleted_at, updated_at=deleted_at)
        )
        await session.execute(
            update(TodoItem)
            .where(
                TodoItem.record_id == record.id,
                TodoItem.deleted_at.is_(None),
            )
            .values(deleted_at=deleted_at, updated_at=deleted_at)
        )
        await session.flush()
        await MasteryService.mark_snapshots_stale(session, affected_concepts)
        return affected_concepts

    @staticmethod
    async def soft_delete(session: AsyncSession, record_id: str) -> set[str] | None:
        """软删除并返回受影响的 Concept 集合（None = 记录不存在）。

        受影响概念由调用方触发 Mastery 全量重算（删除事务先行提交，重算失败
        不回滚删除）。
        """
        async with session.begin():
            record = await RecordService.get(session, record_id)
            if record is None:
                return None
            return await RecordService.soft_delete_core(session, record)

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
