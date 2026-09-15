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

from app.modules.search.schemas import (
    LibrarySegmentSearchHit,
    SegmentEntityType,
    SegmentSearchHit,
)
from app.modules.search.tokenizer import match_expression, tokenize

ENTITY_TRANSCRIPT_SEGMENT: SegmentEntityType = "transcript_segment"
ENTITY_DOCUMENT_SEGMENT: SegmentEntityType = "document_segment"
# Course Brain（F4）：Concept 进同一多态索引表；只索引 CONFIRMED（Agent 可见面）。
ENTITY_CONCEPT: SegmentEntityType = "CONCEPT"

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
    # 正文 = 规范名 + 说明；仅 CONFIRMED 回表（归档 id 命中空行即顺带清索引）。
    ENTITY_CONCEPT: text(
        "SELECT id, canonical_name || ' ' || description AS content FROM concepts "
        "WHERE id IN :ids AND status = 'CONFIRMED'"
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

# 跨记录分片检索（B2 search_library）：去掉单记录过滤、JOIN records 取标题；
# course 条件可空（NULL = 全部未软删记录），软删过滤与单记录版一致。
_SEARCH_SCOPE_TRANSCRIPT_SEGMENTS_SQL = text(
    "SELECT ts.id, ts.record_id, r.title AS record_title, ts.content, "
    "ts.sequence_no, ts.record_start_ms, ts.record_end_ms, "
    "bm25(segment_search_index) AS score "
    "FROM segment_search_index "
    "JOIN transcript_segments ts ON ts.id = segment_search_index.entity_id "
    "JOIN transcripts t ON t.id = ts.transcript_id AND t.deleted_at IS NULL "
    "JOIN records r ON r.id = ts.record_id AND r.deleted_at IS NULL "
    "WHERE segment_search_index MATCH :match "
    "AND segment_search_index.entity_type = 'transcript_segment' "
    "AND (:course_id IS NULL OR r.course_id = :course_id) "
    "ORDER BY score "
    "LIMIT :limit"
)
_SEARCH_SCOPE_DOCUMENT_SEGMENTS_SQL = text(
    "SELECT ds.id, ds.record_id, r.title AS record_title, ds.content, "
    "ds.sequence_no, ds.page_no, "
    "bm25(segment_search_index) AS score "
    "FROM segment_search_index "
    "JOIN document_segments ds ON ds.id = segment_search_index.entity_id "
    "JOIN records r ON r.id = ds.record_id AND r.deleted_at IS NULL "
    "WHERE segment_search_index MATCH :match "
    "AND segment_search_index.entity_type = 'document_segment' "
    "AND (:course_id IS NULL OR r.course_id = :course_id) "
    "ORDER BY score "
    "LIMIT :limit"
)

# FTS5 无普通索引：NOT EXISTS 相关子查询会让外层每行全扫索引表
# （13356 分片 × 15296 索引行实测 40s），改两侧各扫一次、集合差集求缺行。
_INDEXED_SEGMENT_KEYS_SQL = text("SELECT entity_type, entity_id FROM segment_search_index")
_ALL_SEGMENT_IDS_SQL: dict[SegmentEntityType, TextClause] = {
    ENTITY_TRANSCRIPT_SEGMENT: text("SELECT id FROM transcript_segments"),
    ENTITY_DOCUMENT_SEGMENT: text("SELECT id FROM document_segments"),
    ENTITY_CONCEPT: text("SELECT id FROM concepts WHERE status = 'CONFIRMED'"),
}

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
    async def search_scope_segments(
        session: AsyncSession,
        course_id: str | None,
        query: str,
        limit: int,
    ) -> list[LibrarySegmentSearchHit]:
        """跨记录分片检索（课程 / 全部范围）：FTS MATCH → 回表逐字原文 + 归属记录标题，
        BM25 跨两类合并排序。course_id 为 None 时范围 = 全部未软删记录（含收件箱）。"""
        match = match_expression(query)
        if match is None:
            return []
        params = {"match": match, "course_id": course_id, "limit": limit}
        transcript_rows = (
            await session.execute(_SEARCH_SCOPE_TRANSCRIPT_SEGMENTS_SQL, params)
        ).all()
        document_rows = (await session.execute(_SEARCH_SCOPE_DOCUMENT_SEGMENTS_SQL, params)).all()
        scored: list[tuple[float, LibrarySegmentSearchHit]] = [
            (
                cast(float, row.score),
                LibrarySegmentSearchHit(
                    entity_type=ENTITY_TRANSCRIPT_SEGMENT,
                    segment_id=cast(str, row.id),
                    record_id=cast(str, row.record_id),
                    record_title=cast(str, row.record_title),
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
                LibrarySegmentSearchHit(
                    entity_type=ENTITY_DOCUMENT_SEGMENT,
                    segment_id=cast(str, row.id),
                    record_id=cast(str, row.record_id),
                    record_title=cast(str, row.record_title),
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
    async def backfill_missing(session_factory: async_sessionmaker[AsyncSession]) -> None:
        """启动幂等回填：为索引缺行的分片补索引行（含软删宿主，查询期过滤）。

        缺行检测见 _INDEXED_SEGMENT_KEYS_SQL 注释（集合差集）；
        按块开短事务（data-layer 写事务纪律）。
        """
        total = 0
        async with session_factory() as session:
            indexed = {
                (row.entity_type, row.entity_id)
                for row in (await session.execute(_INDEXED_SEGMENT_KEYS_SQL)).all()
            }
            missing_by_type: list[tuple[SegmentEntityType, list[str]]] = []
            for entity_type, ids_sql in _ALL_SEGMENT_IDS_SQL.items():
                ids = list(await session.scalars(ids_sql))
                missing_by_type.append(
                    (entity_type, [sid for sid in ids if (entity_type, sid) not in indexed])
                )
        for entity_type, missing in missing_by_type:
            for start in range(0, len(missing), _BACKFILL_CHUNK):
                chunk = missing[start : start + _BACKFILL_CHUNK]
                async with session_factory() as session, session.begin():
                    await SegmentSearchService.upsert_segment_index(session, entity_type, chunk)
                total += len(chunk)
        if total:
            logger.info("segment_search_index_backfilled", rows=total)
