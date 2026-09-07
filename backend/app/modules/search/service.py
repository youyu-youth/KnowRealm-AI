"""FTS5 统一索引维护与检索服务（ADR-0016）。

索引是可再生衍生数据：软删/归档不触碰索引行，查询期 MATCH 命中后回业务
真表取显示数据并过滤 `deleted_at` 与 ARCHIVED 课程（含其记录与知识点）。
实体映射：记录（title=标题、body=转写正文）、知识点（title=名称、body=详情、
keywords=tags）、课程（title=课程名、keywords=hot_words）。
索引正文只取前 30,000 字符（`_INDEX_BODY_LIMIT`）：切词开销与正文长度线性，
限长保证写路径同步索引的时延有界。
"""

import asyncio
import json
from datetime import datetime
from typing import cast

from loguru import logger
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.search.schemas import (
    SearchCourseItem,
    SearchKnowledgePointItem,
    SearchOut,
    SearchRecordItem,
)
from app.modules.search.tokenizer import match_expression, tokenize

ENTITY_COURSE = "course"
ENTITY_RECORD = "record"
ENTITY_KNOWLEDGE_POINT = "knowledge_point"

# 索引正文限长（对齐 LLM 侧 TRANSCRIPT_LIMIT 量级）：jieba 是纯 Python CPU 密集，
# 4 MiB 文档全文切词约 9 秒且同步阻塞事件循环；限长 + 线程池保证写路径毫秒级抖动。
_INDEX_BODY_LIMIT = 30_000

# bm25 列权重（title/body/keywords）：标题命中显著优先于正文命中。
_FTS_MATCH_SQL = text(
    "SELECT entity_id, snippet(search_index, 1, '', '', '…', 16) AS body_snippet, "
    "snippet(search_index, 0, '', '', '…', 16) AS title_snippet "
    "FROM search_index "
    "WHERE search_index MATCH :match AND entity_type = :entity_type "
    "ORDER BY bm25(search_index, 10.0, 1.0, 1.0) "
    "LIMIT :limit"
)

_RECORD_CONTEXT_SQL = text(
    "SELECT r.id, r.title, r.updated_at, c.name AS course_name "
    "FROM records r "
    "LEFT JOIN courses c ON c.id = r.course_id "
    "WHERE r.deleted_at IS NULL "
    "AND (c.id IS NULL OR (c.deleted_at IS NULL AND c.status != 'ARCHIVED')) "
    "AND r.id IN :ids"
).bindparams(bindparam("ids", expanding=True))

_KNOWLEDGE_POINT_CONTEXT_SQL = text(
    "SELECT kp.id, kp.name AS title, kp.updated_at, kp.record_id, c.name AS course_name "
    "FROM knowledge_points kp "
    "JOIN records r ON r.id = kp.record_id "
    "LEFT JOIN courses c ON c.id = r.course_id "
    "WHERE kp.deleted_at IS NULL "
    "AND kp.generation_status IN ('DRAFT', 'ACTIVE') "
    "AND r.deleted_at IS NULL "
    "AND (c.id IS NULL OR (c.deleted_at IS NULL AND c.status != 'ARCHIVED')) "
    "AND kp.id IN :ids"
).bindparams(bindparam("ids", expanding=True))

_COURSE_CONTEXT_SQL = text(
    "SELECT c.id, c.name AS title, c.updated_at "
    "FROM courses c "
    "WHERE c.deleted_at IS NULL AND c.status = 'ACTIVE' "
    "AND c.id IN :ids"
).bindparams(bindparam("ids", expanding=True))

_RECORD_SOURCE_SQL = text(
    "SELECT r.title, t.content "
    "FROM records r "
    "LEFT JOIN transcripts t ON t.record_id = r.id AND t.deleted_at IS NULL "
    "WHERE r.id = :record_id"
)
_KNOWLEDGE_POINT_SOURCE_SQL = text(
    "SELECT kp.name, kp.detail, kp.tags FROM knowledge_points kp WHERE kp.id = :knowledge_point_id"
)
_COURSE_SOURCE_SQL = text("SELECT c.name, c.hot_words FROM courses c WHERE c.id = :course_id")

_MISSING_RECORDS_SQL = text(
    "SELECT r.id FROM records r WHERE NOT EXISTS ("
    "SELECT 1 FROM search_index si "
    "WHERE si.entity_type = 'record' AND si.entity_id = r.id)"
)
_MISSING_KNOWLEDGE_POINTS_SQL = text(
    "SELECT kp.id FROM knowledge_points kp WHERE NOT EXISTS ("
    "SELECT 1 FROM search_index si "
    "WHERE si.entity_type = 'knowledge_point' AND si.entity_id = kp.id)"
)
_MISSING_COURSES_SQL = text(
    "SELECT c.id FROM courses c WHERE NOT EXISTS ("
    "SELECT 1 FROM search_index si "
    "WHERE si.entity_type = 'course' AND si.entity_id = c.id)"
)


async def _delete_index_row(session: AsyncSession, entity_type: str, entity_id: str) -> None:
    await session.execute(
        text(
            "DELETE FROM search_index WHERE entity_type = :entity_type AND entity_id = :entity_id"
        ),
        {"entity_type": entity_type, "entity_id": entity_id},
    )


async def _upsert_index_row(
    session: AsyncSession,
    entity_type: str,
    entity_id: str,
    *,
    title: str,
    body: str,
    keywords: str,
) -> None:
    # FTS5 无 UNIQUE 约束：先删旧行再插新行，同事务内幂等。
    await _delete_index_row(session, entity_type, entity_id)
    await session.execute(
        text(
            "INSERT INTO search_index (title, body, keywords, entity_type, entity_id) "
            "VALUES (:title, :body, :keywords, :entity_type, :entity_id)"
        ),
        {
            "title": title,
            "body": body,
            "keywords": keywords,
            "entity_type": entity_type,
            "entity_id": entity_id,
        },
    )


def _json_words(raw: str | None) -> str:
    if raw is None:
        return ""
    words = json.loads(raw)
    return tokenize(" ".join(cast("list[str]", words)))


async def _tokenize_body(text: str) -> str:
    return await asyncio.to_thread(tokenize, text[:_INDEX_BODY_LIMIT])


class SearchService:
    """唯一搜索入口：HTTP 路由与未来 AI 对话检索工具共用。"""

    @staticmethod
    async def search(session: AsyncSession, q: str, limit: int) -> SearchOut:
        match = match_expression(q)
        if match is None:
            return SearchOut(courses=[], records=[], knowledge_points=[])
        records = await _search_records(session, match, limit)
        knowledge_points = await _search_knowledge_points(session, match, limit)
        courses = await _search_courses(session, match, limit)
        return SearchOut(courses=courses, records=records, knowledge_points=knowledge_points)

    @staticmethod
    async def upsert_record_index(session: AsyncSession, record_id: str) -> None:
        """学习记录索引行（title=标题、body=转写正文）；实体已物理删除时清空索引行。"""
        row = (await session.execute(_RECORD_SOURCE_SQL, {"record_id": record_id})).first()
        if row is None:
            await _delete_index_row(session, ENTITY_RECORD, record_id)
            return
        await _upsert_index_row(
            session,
            ENTITY_RECORD,
            record_id,
            title=tokenize(cast(str, row.title)),
            body=await _tokenize_body(cast("str | None", row.content) or ""),
            keywords="",
        )

    @staticmethod
    async def upsert_knowledge_point_index(session: AsyncSession, knowledge_point_id: str) -> None:
        """知识点索引行（title=名称、body=详情、keywords=tags）。"""
        row = (
            await session.execute(
                _KNOWLEDGE_POINT_SOURCE_SQL, {"knowledge_point_id": knowledge_point_id}
            )
        ).first()
        if row is None:
            await _delete_index_row(session, ENTITY_KNOWLEDGE_POINT, knowledge_point_id)
            return
        await _upsert_index_row(
            session,
            ENTITY_KNOWLEDGE_POINT,
            knowledge_point_id,
            title=tokenize(cast(str, row.name)),
            body=await _tokenize_body(cast(str, row.detail)),
            keywords=_json_words(cast(str, row.tags)),
        )

    @staticmethod
    async def upsert_course_index(session: AsyncSession, course_id: str) -> None:
        """课程索引行（title=课程名、keywords=hot_words）。"""
        row = (await session.execute(_COURSE_SOURCE_SQL, {"course_id": course_id})).first()
        if row is None:
            await _delete_index_row(session, ENTITY_COURSE, course_id)
            return
        await _upsert_index_row(
            session,
            ENTITY_COURSE,
            course_id,
            title=tokenize(cast(str, row.name)),
            body="",
            keywords=_json_words(cast("str | None", row.hot_words)),
        )

    @staticmethod
    async def backfill_missing(session_factory: async_sessionmaker[AsyncSession]) -> None:
        """启动幂等回填：为索引缺行的三类实体补索引行（含软删/归档，查询期过滤）。"""
        total = 0
        # 每类一个短事务（data-layer 写事务纪律）；NOT EXISTS 保证重复执行不重复。
        for missing_sql, upsert in (
            (_MISSING_RECORDS_SQL, SearchService.upsert_record_index),
            (
                _MISSING_KNOWLEDGE_POINTS_SQL,
                SearchService.upsert_knowledge_point_index,
            ),
            (_MISSING_COURSES_SQL, SearchService.upsert_course_index),
        ):
            async with session_factory() as session:
                ids = list(await session.scalars(missing_sql))
                if not ids:
                    continue
                for entity_id in ids:
                    await upsert(session, entity_id)
                await session.commit()
                total += len(ids)
        if total:
            logger.info("search_index_backfilled", rows=total)


async def _match_ids(
    session: AsyncSession, match: str, entity_type: str, limit: int
) -> list[tuple[str, str]]:
    """FTS 命中行：entity_id 与摘录（body 列优先，无正文回退 title 列）。"""
    rows = (
        await session.execute(
            _FTS_MATCH_SQL,
            {"match": match, "entity_type": entity_type, "limit": limit},
        )
    ).all()
    return [
        (
            cast(str, row.entity_id),
            cast(str, row.body_snippet or row.title_snippet or ""),
        )
        for row in rows
    ]


async def _search_records(session: AsyncSession, match: str, limit: int) -> list[SearchRecordItem]:
    matched = await _match_ids(session, match, ENTITY_RECORD, limit)
    if not matched:
        return []
    rows = (
        await session.execute(_RECORD_CONTEXT_SQL, {"ids": [entity_id for entity_id, _ in matched]})
    ).all()
    context = {cast(str, row.id): row for row in rows}
    items: list[SearchRecordItem] = []
    for entity_id, snippet in matched:
        row = context.get(entity_id)
        if row is None:
            continue
        items.append(
            SearchRecordItem(
                id=entity_id,
                title=cast(str, row.title),
                snippet=snippet,
                course_name=cast("str | None", row.course_name),
                updated_at=datetime.fromisoformat(cast(str, row.updated_at)),
            )
        )
    return items


async def _search_knowledge_points(
    session: AsyncSession, match: str, limit: int
) -> list[SearchKnowledgePointItem]:
    matched = await _match_ids(session, match, ENTITY_KNOWLEDGE_POINT, limit)
    if not matched:
        return []
    rows = (
        await session.execute(_KNOWLEDGE_POINT_CONTEXT_SQL, {"ids": [e for e, _ in matched]})
    ).all()
    context = {cast(str, row.id): row for row in rows}
    items: list[SearchKnowledgePointItem] = []
    for entity_id, snippet in matched:
        row = context.get(entity_id)
        if row is None:
            continue
        items.append(
            SearchKnowledgePointItem(
                id=entity_id,
                title=cast(str, row.title),
                snippet=snippet,
                course_name=cast("str | None", row.course_name),
                record_id=cast(str, row.record_id),
                updated_at=datetime.fromisoformat(cast(str, row.updated_at)),
            )
        )
    return items


async def _search_courses(session: AsyncSession, match: str, limit: int) -> list[SearchCourseItem]:
    matched = await _match_ids(session, match, ENTITY_COURSE, limit)
    if not matched:
        return []
    rows = (await session.execute(_COURSE_CONTEXT_SQL, {"ids": [e for e, _ in matched]})).all()
    context = {cast(str, row.id): row for row in rows}
    items: list[SearchCourseItem] = []
    for entity_id, snippet in matched:
        row = context.get(entity_id)
        if row is None:
            continue
        items.append(
            SearchCourseItem(
                id=entity_id,
                title=cast(str, row.title),
                snippet=snippet,
                updated_at=datetime.fromisoformat(cast(str, row.updated_at)),
            )
        )
    return items
