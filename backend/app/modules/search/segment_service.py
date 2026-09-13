"""分片级 FTS5 索引维护与检索服务（chat 检索工具数据地基，ADR-0016 纪律照搬）。

与全局 search_index 分表不复用：全局搜索三类资产语义不混入分片命中。
索引是可再生衍生数据：软删不触碰索引行，查询期 MATCH 命中后回分片业务表
取逐字原文（引用逐字校验的根基）并过滤挂载 record、transcript 与 record 软删；
分片物理删除（编辑重切）时由写路径同事务清理索引行。
"""

import asyncio
from typing import cast

from loguru import logger
from sqlalchemy import TextClause, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.search.schemas import SegmentEntityType, SegmentSearchHit
from app.modules.search.tokenizer import match_expression, tokenize

ENTITY_TRANSCRIPT_SEGMENT: SegmentEntityType = "transcript_segment"
ENTITY_DOCUMENT_SEGMENT: SegmentEntityType = "document_segment"

# 沿用全局索引的正文限长纪律：jieba 切词开销与正文长度线性，限长保证写路径时延有界。
_INDEX_BODY_LIMIT = 30_000

# 启动回填每块一个短事务（data-layer 写事务纪律），避免大事务长期占用写锁。
_BACKFILL_CHUNK = 200

_DELETE_SEGMENT_ROWS_SQL = text(
    "DELETE FROM segment_search_index WHERE entity_type = :entity_type AND entity_id IN :ids"
).bindparams(bindparam("ids", expanding=True))

_INSERT_SEGMENT_ROW_SQL = text(
    "INSERT INTO segment_search_index (body, entity_type, entity_id) "
    "VALUES (:body, :entity_type, :entity_id)"
)

_SEGMENT_SOURCE_SQL = {
    ENTITY_TRANSCRIPT_SEGMENT: text(
        "SELECT id, content FROM transcript_segments WHERE id IN :ids"
    ).bindparams(bindparam("ids", expanding=True)),
    ENTITY_DOCUMENT_SEGMENT: text(
        "SELECT id, content FROM document_segments WHERE id IN :ids"
    ).bindparams(bindparam("ids", expanding=True)),
}

_RECORD_TRANSCRIPT_SEGMENT_IDS_SQL = text(
    "SELECT id FROM transcript_segments WHERE record_id = :record_id"
)
_RECORD_DOCUMENT_SEGMENT_IDS_SQL = text(
    "SELECT id FROM document_segments WHERE record_id = :record_id"
)

# MATCH 命中后回表取逐字原文并过滤：限定挂载 record_id、transcript 未软删、
# record 未软删；文档分片按 record 挂靠路径（record_id 命中）过滤。
_SEARCH_TRANSCRIPT_SEGMENTS_SQL = text(
    "SELECT ts.id, ts.content, ts.sequence_no, ts.record_start_ms, ts.record_end_ms, "
    "bm25(segment_search_index) AS score "
    "FROM segment_search_index "
    "JOIN transcript_segments ts ON ts.id = segment_search_index.entity_id "
    "JOIN transcripts t ON t.id = ts.transcript_id AND t.deleted_at IS NULL "
    "JOIN records r ON r.id = ts.record_id AND r.deleted_at IS NULL "
    "WHERE segment_search_index MATCH :match "
    "AND segment_search_index.entity_type = 'transcript_segment' "
    "AND ts.record_id = :record_id "
    "ORDER BY score "
    "LIMIT :limit"
)
_SEARCH_DOCUMENT_SEGMENTS_SQL = text(
    "SELECT ds.id, ds.content, ds.sequence_no, ds.page_no, "
    "bm25(segment_search_index) AS score "
    "FROM segment_search_index "
    "JOIN document_segments ds ON ds.id = segment_search_index.entity_id "
    "JOIN records r ON r.id = ds.record_id AND r.deleted_at IS NULL "
    "WHERE segment_search_index MATCH :match "
    "AND segment_search_index.entity_type = 'document_segment' "
    "AND ds.record_id = :record_id "
    "ORDER BY score "
    "LIMIT :limit"
)

_MISSING_TRANSCRIPT_SEGMENTS_SQL = text(
    "SELECT ts.id FROM transcript_segments ts WHERE NOT EXISTS ("
    "SELECT 1 FROM segment_search_index si "
    "WHERE si.entity_type = 'transcript_segment' AND si.entity_id = ts.id)"
)
_MISSING_DOCUMENT_SEGMENTS_SQL = text(
    "SELECT ds.id FROM document_segments ds WHERE NOT EXISTS ("
    "SELECT 1 FROM segment_search_index si "
    "WHERE si.entity_type = 'document_segment' AND si.entity_id = ds.id)"
)

# 记录是否存在分片：chat 检索工具据此选择「FTS 无命中如实返回」或「无分片子串兜底」。
_RECORD_HAS_SEGMENTS_SQL = text(
    "SELECT EXISTS(SELECT 1 FROM transcript_segments WHERE record_id = :record_id) "
    "OR EXISTS(SELECT 1 FROM document_segments WHERE record_id = :record_id)"
)


async def _delete_segment_rows(
    session: AsyncSession, entity_type: str, segment_ids: list[str]
) -> None:
    await session.execute(
        _DELETE_SEGMENT_ROWS_SQL, {"entity_type": entity_type, "ids": segment_ids}
    )


async def _tokenize_bodies(contents: list[str]) -> list[str]:
    return await asyncio.to_thread(
        lambda: [tokenize(content[:_INDEX_BODY_LIMIT]) for content in contents]
    )


class SegmentSearchService:
    """分片索引唯一维护与检索入口：写路径挂点与 chat 检索工具（chat→search 单向）共用。"""

    @staticmethod
    async def upsert_segment_index(
        session: AsyncSession,
        entity_type: SegmentEntityType,
        segment_ids: list[str],
    ) -> None:
        """按分片 id 回表取 content 切词，先删后插同事务幂等；
        已不在业务表的 id 顺带清空残留索引行。"""
        if not segment_ids:
            return
        rows = (await session.execute(_SEGMENT_SOURCE_SQL[entity_type], {"ids": segment_ids})).all()
        await _delete_segment_rows(session, entity_type, segment_ids)
        if not rows:
            return
        bodies = await _tokenize_bodies([cast(str, row.content) for row in rows])
        await session.execute(
            _INSERT_SEGMENT_ROW_SQL,
            [
                {
                    "body": body,
                    "entity_type": entity_type,
                    "entity_id": cast(str, row.id),
                }
                for row, body in zip(rows, bodies, strict=True)
            ],
        )

    @staticmethod
    async def delete_segment_index(
        session: AsyncSession,
        entity_type: SegmentEntityType,
        segment_ids: list[str],
    ) -> None:
        """按分片 id 清理索引行（编辑重切物理删除行时的同事务挂钩）。"""
        if not segment_ids:
            return
        await _delete_segment_rows(session, entity_type, segment_ids)

    @staticmethod
    async def upsert_record_segments(session: AsyncSession, record_id: str) -> None:
        """记录级挂点：finalizer 建分片后的同事务维护（转写 + 文档两类）。"""
        transcript_ids = list(
            await session.scalars(_RECORD_TRANSCRIPT_SEGMENT_IDS_SQL, {"record_id": record_id})
        )
        await SegmentSearchService.upsert_segment_index(
            session, ENTITY_TRANSCRIPT_SEGMENT, transcript_ids
        )
        document_ids = list(
            await session.scalars(_RECORD_DOCUMENT_SEGMENT_IDS_SQL, {"record_id": record_id})
        )
        await SegmentSearchService.upsert_segment_index(
            session, ENTITY_DOCUMENT_SEGMENT, document_ids
        )

    @staticmethod
    async def search_segments(
        session: AsyncSession,
        record_id: str,
        query: str,
        limit: int,
    ) -> list[SegmentSearchHit]:
        """挂载记录内的分片检索：FTS MATCH → 回表逐字原文，BM25 跨两类合并排序。"""
        match = match_expression(query)
        if match is None:
            return []
        transcript_rows = (
            await session.execute(
                _SEARCH_TRANSCRIPT_SEGMENTS_SQL,
                {"match": match, "record_id": record_id, "limit": limit},
            )
        ).all()
        document_rows = (
            await session.execute(
                _SEARCH_DOCUMENT_SEGMENTS_SQL,
                {"match": match, "record_id": record_id, "limit": limit},
            )
        ).all()
        scored: list[tuple[float, SegmentSearchHit]] = [
            (
                cast(float, row.score),
                SegmentSearchHit(
                    entity_type=ENTITY_TRANSCRIPT_SEGMENT,
                    segment_id=cast(str, row.id),
                    content=cast(str, row.content),
                    sequence_no=cast(int, row.sequence_no),
                    record_start_ms=cast("int | None", row.record_start_ms),
                    record_end_ms=cast("int | None", row.record_end_ms),
                ),
            )
            for row in transcript_rows
        ] + [
            (
                cast(float, row.score),
                SegmentSearchHit(
                    entity_type=ENTITY_DOCUMENT_SEGMENT,
                    segment_id=cast(str, row.id),
                    content=cast(str, row.content),
                    sequence_no=cast(int, row.sequence_no),
                    page_no=cast("int | None", row.page_no),
                ),
            )
            for row in document_rows
        ]
        scored.sort(key=lambda item: item[0])
        return [hit for _score, hit in scored[:limit]]

    @staticmethod
    async def record_has_segments(session: AsyncSession, record_id: str) -> bool:
        """记录是否存在分片（含软删宿主；chat 检索工具据此选择兜底路径）。"""
        return bool(await session.scalar(_RECORD_HAS_SEGMENTS_SQL, {"record_id": record_id}))

    @staticmethod
    async def backfill_missing(session_factory: async_sessionmaker[AsyncSession]) -> None:
        """启动幂等回填：为索引缺行的分片补索引行（含软删宿主，查询期过滤）。

        NOT EXISTS 保证重复执行零副作用；按块开短事务（data-layer 写事务纪律）。
        """
        total = 0
        backfills: tuple[tuple[TextClause, SegmentEntityType], ...] = (
            (_MISSING_TRANSCRIPT_SEGMENTS_SQL, ENTITY_TRANSCRIPT_SEGMENT),
            (_MISSING_DOCUMENT_SEGMENTS_SQL, ENTITY_DOCUMENT_SEGMENT),
        )
        for missing_sql, entity_type in backfills:
            async with session_factory() as session:
                ids = list(await session.scalars(missing_sql))
            for start in range(0, len(ids), _BACKFILL_CHUNK):
                chunk = ids[start : start + _BACKFILL_CHUNK]
                async with session_factory() as session, session.begin():
                    await SegmentSearchService.upsert_segment_index(session, entity_type, chunk)
                total += len(chunk)
        if total:
            logger.info("segment_search_index_backfilled", rows=total)
