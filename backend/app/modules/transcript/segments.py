"""纯文本建分片 service（票 04）：启动幂等回填与编辑增量对齐重切共用同一对齐器。

分片是 transcripts.content 的派生定位层。对齐规则 = 逐句 content_hash 命中
保留原分片行（id 与 file/record 时间轴一并保留），未命中句以无时间戳形态
新入——时间戳 NULL = 全库唯一退化态。未命中句的 file 归属：继承左侧最近
命中句，前缀无命中回退右侧最近命中，全程无命中回退首个记录文件。
"""

from collections import deque
from dataclasses import dataclass

from loguru import logger
from sqlalchemy import delete, exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.capture.models import RecordFile
from app.modules.record.models import Record
from app.modules.search.segment_service import (
    ENTITY_DOCUMENT_SEGMENT,
    ENTITY_TRANSCRIPT_SEGMENT,
    SegmentSearchService,
)
from app.modules.transcript.models import (
    DocumentSegment,
    Transcript,
    TranscriptSegment,
)
from app.modules.transcript.sentences import (
    Sentence,
    content_hash,
    sentences_from_plain_text,
)


@dataclass(frozen=True)
class SegmentPlanRow:
    segment_id: str | None  # 命中的既有分片 id；None = 新建行
    content: str
    content_hash: str
    file_id: str


def plan_alignment(
    sentences: list[Sentence],
    old_segments: list[TranscriptSegment],
    fallback_file_id: str,
) -> list[SegmentPlanRow]:
    """逐句哈希对齐产出重切计划：同哈希按队列顺序消费（顺序稳定、重复句各归各）。"""
    by_hash: dict[str, deque[TranscriptSegment]] = {}
    for segment in old_segments:
        by_hash.setdefault(segment.content_hash, deque()).append(segment)

    matches: list[TranscriptSegment | None] = []
    for sentence in sentences:
        queue = by_hash.get(content_hash(sentence.text))
        matches.append(queue.popleft() if queue else None)

    files: list[str | None] = []
    carry: str | None = None
    for match in matches:
        if match is not None:
            carry = match.file_id
        files.append(carry)
    following: str | None = None
    for index in reversed(range(len(files))):
        if files[index] is None:
            files[index] = following
        else:
            following = files[index]

    return [
        SegmentPlanRow(
            segment_id=match.id if match is not None else None,
            content=sentence.text,
            content_hash=content_hash(sentence.text),
            file_id=file_id or fallback_file_id,
        )
        for sentence, match, file_id in zip(sentences, matches, files, strict=True)
    ]


class SegmentService:
    """分片派生层写入者之一：finalizer 走解析缓存建分片（02/03），本 service 走纯文本。"""

    @staticmethod
    async def realign_for_edit(
        session: AsyncSession,
        transcript_id: str,
        record_id: str,
        content: str,
    ) -> None:
        """编辑保存同事务内的增量对齐重切：命中句仅重排 sequence_no，未命中删除重建。"""
        # 编辑后 content 已变，文档块的块界与 offset 全部失效，同事务清零
        # （前端时间轴随之回落到本次重切产出的行级 transcript_segments）；
        # 物理删除的行在删除前先取 id，同事务清理其索引行。
        document_segment_ids = list(
            (
                await session.scalars(
                    select(DocumentSegment.id).where(DocumentSegment.record_id == record_id)
                )
            ).all()
        )
        await session.execute(delete(DocumentSegment).where(DocumentSegment.record_id == record_id))
        file_ids = list(
            (
                await session.scalars(
                    select(RecordFile.id)
                    .where(
                        RecordFile.record_id == record_id,
                        RecordFile.deleted_at.is_(None),
                    )
                    .order_by(RecordFile.sequence_no)
                )
            ).all()
        )
        old_segments = list(
            (
                await session.scalars(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.transcript_id == transcript_id)
                    .order_by(TranscriptSegment.sequence_no)
                )
            ).all()
        )
        if not file_ids:
            # 粘贴/速记（无文件）不建分片；文件全删后的残留分片一并清零。
            if old_segments:
                await session.execute(
                    delete(TranscriptSegment).where(
                        TranscriptSegment.transcript_id == transcript_id
                    )
                )
                await SegmentSearchService.delete_segment_index(
                    session,
                    ENTITY_TRANSCRIPT_SEGMENT,
                    [segment.id for segment in old_segments],
                )
            await SegmentSearchService.delete_segment_index(
                session, ENTITY_DOCUMENT_SEGMENT, document_segment_ids
            )
            return
        rows = plan_alignment(sentences_from_plain_text(content), old_segments, file_ids[0])
        keep_ids = [row.segment_id for row in rows if row.segment_id is not None]
        keep_id_set = set(keep_ids)
        removed_ids = [segment.id for segment in old_segments if segment.id not in keep_id_set]
        if old_segments:
            await session.execute(
                delete(TranscriptSegment).where(
                    TranscriptSegment.transcript_id == transcript_id,
                    TranscriptSegment.id.not_in(keep_ids),
                )
            )
        old_by_id = {segment.id: segment for segment in old_segments}
        new_segments: list[TranscriptSegment] = []
        for sequence_no, row in enumerate(rows):
            if row.segment_id is not None:
                if old_by_id[row.segment_id].sequence_no != sequence_no:
                    await session.execute(
                        update(TranscriptSegment)
                        .where(TranscriptSegment.id == row.segment_id)
                        .values(sequence_no=sequence_no)
                    )
            else:
                segment = TranscriptSegment(
                    transcript_id=transcript_id,
                    record_id=record_id,
                    file_id=row.file_id,
                    sequence_no=sequence_no,
                    content=row.content,
                    content_hash=row.content_hash,
                )
                session.add(segment)
                new_segments.append(segment)
        # 物理删除行同事务清索引行；新建分片落库后回表补索引（保留句 content
        # 未变，索引行原样复用）。
        await session.flush()
        await SegmentSearchService.delete_segment_index(
            session, ENTITY_TRANSCRIPT_SEGMENT, removed_ids
        )
        await SegmentSearchService.upsert_segment_index(
            session,
            ENTITY_TRANSCRIPT_SEGMENT,
            [segment.id for segment in new_segments],
        )
        await SegmentSearchService.delete_segment_index(
            session, ENTITY_DOCUMENT_SEGMENT, document_segment_ids
        )

    @staticmethod
    async def backfill_missing(session_factory: async_sessionmaker[AsyncSession]) -> None:
        """启动幂等回填：为无分片的存量转写按 content 行拆建无时间戳分片。

        NOT EXISTS 保证重复启动零副作用；粘贴/速记（无文件）不建。每转写一个
        短事务（对齐搜索索引回填写事务纪律，main.py 同容错级包裹）。
        """
        async with session_factory() as session:
            transcript_ids = list(
                (
                    await session.scalars(
                        select(Transcript.id)
                        .join(Record, Transcript.record_id == Record.id)
                        .where(
                            Transcript.deleted_at.is_(None),
                            Record.deleted_at.is_(None),
                            ~exists(
                                select(TranscriptSegment.id).where(
                                    TranscriptSegment.transcript_id == Transcript.id
                                )
                            ),
                        )
                        .order_by(Transcript.created_at)
                    )
                ).all()
            )
        total = 0
        for transcript_id in transcript_ids:
            async with session_factory() as session, session.begin():
                transcript = await session.get(Transcript, transcript_id)
                record = (
                    None if transcript is None else await session.get(Record, transcript.record_id)
                )
                if (
                    transcript is None
                    or transcript.deleted_at is not None
                    or record is None
                    or record.deleted_at is not None
                ):
                    continue
                already = (
                    await session.scalars(
                        select(TranscriptSegment.id)
                        .where(TranscriptSegment.transcript_id == transcript_id)
                        .limit(1)
                    )
                ).first()
                if already is not None:
                    continue
                file_id = (
                    await session.scalars(
                        select(RecordFile.id)
                        .where(
                            RecordFile.record_id == transcript.record_id,
                            RecordFile.deleted_at.is_(None),
                        )
                        .order_by(RecordFile.sequence_no)
                        .limit(1)
                    )
                ).first()
                if file_id is None:
                    continue
                rows = plan_alignment(sentences_from_plain_text(transcript.content), [], file_id)
                segments = [
                    TranscriptSegment(
                        transcript_id=transcript_id,
                        record_id=transcript.record_id,
                        file_id=file_id,
                        sequence_no=sequence_no,
                        content=row.content,
                        content_hash=row.content_hash,
                    )
                    for sequence_no, row in enumerate(rows)
                ]
                session.add_all(segments)
                await session.flush()
                await SegmentSearchService.upsert_segment_index(
                    session,
                    ENTITY_TRANSCRIPT_SEGMENT,
                    [segment.id for segment in segments],
                )
                total += len(rows)
        if total:
            logger.info("transcript_segments_backfilled", rows=total)
