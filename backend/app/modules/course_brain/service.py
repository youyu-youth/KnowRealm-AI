"""Course Brain 查询服务（F4 CB-03）：快照六态、概念查询、来源回溯与 B2 检索底座。

零 LLM：手动创建的 CONFIRMED Concept 即可被统一查询模块读取；六态在查询时
派生（零后台任务），STALE 由「来源表 (count, max_updated_at) 聚合指纹」与最近
一次成功构建的 result_json.fingerprint 比对得出（ADR-0022）。
"""

import json
import re
import unicodedata
from datetime import datetime
from typing import cast

from sqlalchemy import bindparam, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.course.models import Course
from app.modules.course.schemas import CourseStatus
from app.modules.course_brain.models import Concept
from app.modules.course_brain.schemas import (
    BrainConceptCreate,
    BrainConceptDetailOut,
    BrainConceptListQuery,
    BrainConceptOut,
    BrainSearchConceptOut,
    BrainSearchOccurrenceOut,
    BrainSearchRelationOut,
    BrainSnapshotOut,
    BrainStatus,
    ConceptAnchorSourceOut,
    ConceptKpSourceOut,
    ConceptSource,
    ConceptSourcesOut,
    ConceptStatus,
    CourseBrainSearchOut,
)
from app.modules.search.schemas import LibrarySegmentSearchHit
from app.modules.search.segment_service import ENTITY_CONCEPT, SegmentSearchService
from app.modules.search.tokenizer import match_expression
from app.modules.source_anchor.schemas import SourceAnchorType
from app.shared.errors import CodedHTTPException

_ACTIVE_JOB_STATUSES = ("PENDING", "RUNNING")
_CONCEPT_MATCH_LIMIT = 4
_OCCURRENCE_PER_TERM = 8
_OCCURRENCE_QUOTE_LIMIT = 500

# 来源指纹：各来源表 (count, max_updated_at) 聚合；只统计未软删记录（含其宿主）。
_FINGERPRINT_SQL = {
    "transcript_segments": text(
        "SELECT count(*), max(t.updated_at) "
        "FROM transcript_segments ts "
        "JOIN transcripts t ON t.id = ts.transcript_id AND t.deleted_at IS NULL "
        "JOIN records r ON r.id = ts.record_id AND r.deleted_at IS NULL "
        "WHERE r.course_id = :course_id"
    ),
    "document_segments": text(
        "SELECT count(*), max(rf.updated_at) "
        "FROM document_segments ds "
        "JOIN records r ON r.id = ds.record_id AND r.deleted_at IS NULL "
        "LEFT JOIN record_files rf ON rf.id = ds.record_file_id "
        "WHERE r.course_id = :course_id"
    ),
    "knowledge_points": text(
        "SELECT count(*), max(kp.updated_at) "
        "FROM knowledge_points kp "
        "JOIN records r ON r.id = kp.record_id AND r.deleted_at IS NULL "
        "WHERE r.course_id = :course_id AND kp.deleted_at IS NULL "
        "AND kp.generation_status = 'ACTIVE'"
    ),
}

# 课程级构建任务：record_id 恒 NULL，course_id 存 input_json（CB-04 写入约定）。
_COURSE_JOBS_SQL = text(
    "SELECT id, status, result_json, finished_at FROM processing_jobs "
    "WHERE record_id IS NULL AND job_type = 'CONCEPT_EXTRACTION' "
    "AND json_extract(input_json, '$.course_id') = :course_id "
    "ORDER BY created_at DESC, id DESC"
)

# 出现统计：只计未软删且仍在课程内的记录（跨课程/软删不泄漏）。
_RECORD_CONCEPT_STATS_SQL = text(
    "SELECT rc.concept_id AS concept_id, count(*) AS record_count, "
    "coalesce(sum(rc.evidence_count), 0) AS occurrence_count "
    "FROM record_concepts rc "
    "JOIN records r ON r.id = rc.record_id AND r.deleted_at IS NULL "
    "WHERE rc.concept_id IN :ids AND r.course_id = :course_id "
    "GROUP BY rc.concept_id"
).bindparams(bindparam("ids", expanding=True))

_CONCEPT_ANCHOR_COUNT_SQL = text(
    "SELECT count(*) FROM source_anchor_links l "
    "JOIN source_anchors a ON a.id = l.source_anchor_id "
    "WHERE l.resource_type = 'CONCEPT' AND l.resource_id = :concept_id "
    "AND a.course_id = :course_id"
)

# Concept 命中：CONFIRMED-only（Agent 只读边界，ADR-0022）。
_CONCEPT_MATCH_SQL = text(
    "SELECT c.id AS concept_id, c.canonical_name, c.description "
    "FROM segment_search_index "
    "JOIN concepts c ON c.id = segment_search_index.entity_id "
    "WHERE segment_search_index MATCH :match "
    "AND segment_search_index.entity_type = 'CONCEPT' "
    "AND c.course_id = :course_id AND c.status = 'CONFIRMED' "
    "ORDER BY bm25(segment_search_index) "
    "LIMIT :limit"
)

_RELATED_OUTGOING_SQL = text(
    "SELECT c.id AS concept_id, c.canonical_name, cr.relation_type "
    "FROM concept_relations cr "
    "JOIN concepts c ON c.id = cr.target_concept_id "
    "WHERE cr.course_id = :course_id AND cr.status = 'CONFIRMED' "
    "AND cr.source_concept_id IN :ids "
    "ORDER BY cr.confidence DESC, c.canonical_name"
).bindparams(bindparam("ids", expanding=True))
_RELATED_INCOMING_SQL = text(
    "SELECT c.id AS concept_id, c.canonical_name, cr.relation_type "
    "FROM concept_relations cr "
    "JOIN concepts c ON c.id = cr.source_concept_id "
    "WHERE cr.course_id = :course_id AND cr.status = 'CONFIRMED' "
    "AND cr.target_concept_id IN :ids "
    "ORDER BY cr.confidence DESC, c.canonical_name"
).bindparams(bindparam("ids", expanding=True))

# 来源锚点：AUDIO/DOCUMENT 取分片逐字原文与时间/页码；CHAT 回溯会话 id。
_CONCEPT_ANCHORS_SQL = text(
    "SELECT l.relation_type, a.id AS anchor_id, a.source_type, a.record_id, "
    "r.title AS record_title, "
    "ts.content AS transcript_content, ts.record_start_ms, ts.record_end_ms, "
    "ds.content AS document_content, ds.page_no, "
    "cm.content AS chat_content, cm.session_id AS chat_session_id "
    "FROM source_anchor_links l "
    "JOIN source_anchors a ON a.id = l.source_anchor_id "
    "LEFT JOIN records r ON r.id = a.record_id AND r.deleted_at IS NULL "
    "LEFT JOIN transcript_segments ts ON ts.id = a.transcript_segment_id "
    "LEFT JOIN document_segments ds ON ds.id = a.document_segment_id "
    "LEFT JOIN chat_messages cm ON cm.id = a.source_id AND a.source_type = 'CHAT_MESSAGE' "
    "WHERE l.resource_type = 'CONCEPT' AND l.resource_id = :concept_id "
    "AND a.course_id = :course_id "
    "AND (a.record_id IS NULL OR r.id IS NOT NULL) "
    "ORDER BY a.id"
)

# KP 桥来源：record_concepts 中携带 knowledge_point_id 的行（KP→Concept Resolution）。
_CONCEPT_KP_SOURCES_SQL = text(
    "SELECT rc.record_id, r.title AS record_title, rc.knowledge_point_id, "
    "kp.name AS knowledge_point_name, rc.relevance, rc.evidence_count "
    "FROM record_concepts rc "
    "JOIN records r ON r.id = rc.record_id AND r.deleted_at IS NULL "
    "JOIN knowledge_points kp ON kp.id = rc.knowledge_point_id AND kp.deleted_at IS NULL "
    "WHERE rc.concept_id = :concept_id AND r.course_id = :course_id "
    "ORDER BY r.updated_at DESC, rc.id"
)


def normalize_concept_name(name: str) -> str:
    """规范名归一化（spec 数据合同）：strip → 空白折叠 → 全角转半角 → casefold。"""
    collapsed = re.sub(r"\s+", " ", name.strip())
    return unicodedata.normalize("NFKC", collapsed).casefold()


async def _get_active_course(session: AsyncSession, course_id: str) -> Course:
    course = (
        await session.scalars(
            select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
        )
    ).one_or_none()
    if course is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    if course.status != CourseStatus.ACTIVE:
        raise CodedHTTPException(
            code="COURSE_ARCHIVED", status_code=409, detail="归档课程不能使用课程大脑"
        )
    return course


async def _require_concept(session: AsyncSession, course_id: str, concept_id: str) -> Concept:
    concept = (
        await session.scalars(
            select(Concept).where(Concept.id == concept_id, Concept.course_id == course_id)
        )
    ).one_or_none()
    if concept is None:
        raise CodedHTTPException(
            code="COURSE_BRAIN_CONCEPT_NOT_FOUND", status_code=404, detail="概念不存在"
        )
    return concept


async def compute_source_fingerprint(session: AsyncSession, course_id: str) -> dict[str, object]:
    """来源指纹（查询时派生）：供快照 STALE 比对与 CB-04 构建结果落盘共用。"""
    fingerprint: dict[str, object] = {}
    for key, statement in _FINGERPRINT_SQL.items():
        row = (await session.execute(statement, {"course_id": course_id})).one()
        fingerprint[key] = [int(row[0]), row[1]]
    return fingerprint


def _stored_fingerprint(result_json: str | None) -> dict[str, object] | None:
    if not result_json:
        return None
    try:
        payload: object = json.loads(result_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    fingerprint = cast("dict[str, object]", payload).get("fingerprint")
    return cast("dict[str, object]", fingerprint) if isinstance(fingerprint, dict) else None


async def _concept_stats(
    session: AsyncSession, course_id: str, concept_ids: list[str]
) -> dict[str, tuple[int, int]]:
    if not concept_ids:
        return {}
    rows = (
        await session.execute(
            _RECORD_CONCEPT_STATS_SQL, {"ids": concept_ids, "course_id": course_id}
        )
    ).all()
    return {
        cast(str, row.concept_id): (int(row.record_count), int(row.occurrence_count))
        for row in rows
    }


def _concept_out(concept: Concept, stats: tuple[int, int] | None) -> BrainConceptOut:
    record_count, occurrence_count = stats if stats is not None else (0, 0)
    return BrainConceptOut(
        id=concept.id,
        course_id=concept.course_id,
        canonical_name=concept.canonical_name,
        description=concept.description,
        concept_type=concept.concept_type,
        importance=concept.importance,
        status=ConceptStatus(concept.status),
        source=ConceptSource(concept.source),
        created_at=concept.created_at,
        updated_at=concept.updated_at,
        record_count=record_count,
        occurrence_count=occurrence_count,
    )


def _occurrence_out(hit: LibrarySegmentSearchHit) -> BrainSearchOccurrenceOut:
    return BrainSearchOccurrenceOut(
        record_id=hit.record_id,
        record_title=hit.record_title,
        source_type=hit.entity_type,
        segment_id=hit.segment_id,
        quote=hit.content[:_OCCURRENCE_QUOTE_LIMIT],
        position=hit.sequence_no,
        start_ms=hit.record_start_ms,
        end_ms=hit.record_end_ms,
        page_no=hit.page_no,
    )


class CourseBrainService:
    """Course Brain 统一查询入口：UI 与 B2 `search_library` 共用（Agent 只读）。"""

    @staticmethod
    async def get_snapshot(session: AsyncSession, course_id: str) -> BrainSnapshotOut:
        """六态查询时派生：BUILDING → REVIEW → STALE → FAILED → READY（EMPTY 兜底）。"""
        await _get_active_course(session, course_id)
        jobs = (await session.execute(_COURSE_JOBS_SQL, {"course_id": course_id})).all()
        active_job = next(
            (job for job in jobs if cast(str, job.status) in _ACTIVE_JOB_STATUSES), None
        )
        last_job = jobs[0] if jobs else None
        last_succeeded = next(
            (job for job in jobs if job.status == "SUCCEEDED" and job.result_json), None
        )
        status_rows = (
            await session.execute(
                select(Concept.status, func.count())
                .where(Concept.course_id == course_id)
                .group_by(Concept.status)
            )
        ).all()
        counts = {cast(str, row[0]): int(row[1]) for row in status_rows}
        confirmed = counts.get("CONFIRMED", 0)
        candidates = counts.get("CANDIDATE", 0)
        total = sum(counts.values())

        stale = False
        if last_succeeded is not None:
            stored = _stored_fingerprint(cast("str | None", last_succeeded.result_json))
            if stored is not None:
                stale = stored != await compute_source_fingerprint(session, course_id)

        if active_job is not None:
            status = BrainStatus.BUILDING
        elif total == 0 and not jobs:
            status = BrainStatus.EMPTY
        elif candidates > 0:
            status = BrainStatus.REVIEW
        elif stale:
            status = BrainStatus.STALE
        elif last_job is not None and last_job.status == "FAILED" and confirmed == 0:
            status = BrainStatus.FAILED
        else:
            status = BrainStatus.READY

        return BrainSnapshotOut(
            course_id=course_id,
            status=status,
            concept_count=confirmed,
            candidate_count=candidates,
            stale=stale,
            active_job_id=cast("str | None", active_job.id) if active_job is not None else None,
            last_built_at=(
                cast("datetime | None", last_succeeded.finished_at)
                if last_succeeded is not None
                else None
            ),
        )

    @staticmethod
    async def list_concepts(
        session: AsyncSession, course_id: str, query: BrainConceptListQuery
    ) -> list[BrainConceptOut]:
        await _get_active_course(session, course_id)
        concepts = list(
            (
                await session.scalars(
                    select(Concept)
                    .where(Concept.course_id == course_id, Concept.status == query.status.value)
                    .order_by(Concept.importance.desc(), Concept.canonical_name, Concept.id)
                    .limit(query.limit)
                    .offset(query.offset)
                )
            ).all()
        )
        stats = await _concept_stats(session, course_id, [concept.id for concept in concepts])
        return [_concept_out(concept, stats.get(concept.id)) for concept in concepts]

    @staticmethod
    async def get_concept(
        session: AsyncSession, course_id: str, concept_id: str
    ) -> BrainConceptDetailOut:
        await _get_active_course(session, course_id)
        concept = await _require_concept(session, course_id, concept_id)
        stats = await _concept_stats(session, course_id, [concept.id])
        anchor_count = int(
            await session.scalar(
                _CONCEPT_ANCHOR_COUNT_SQL, {"concept_id": concept.id, "course_id": course_id}
            )
            or 0
        )
        base = _concept_out(concept, stats.get(concept.id))
        return BrainConceptDetailOut(**base.model_dump(), anchor_count=anchor_count)

    @staticmethod
    async def get_concept_sources(
        session: AsyncSession, course_id: str, concept_id: str
    ) -> ConceptSourcesOut:
        await _get_active_course(session, course_id)
        concept = await _require_concept(session, course_id, concept_id)
        anchor_rows = (
            await session.execute(
                _CONCEPT_ANCHORS_SQL, {"concept_id": concept.id, "course_id": course_id}
            )
        ).all()
        anchors: list[ConceptAnchorSourceOut] = []
        for row in anchor_rows:
            source_type = cast(str, row.source_type)
            if source_type == "AUDIO_SEGMENT":
                quote = cast("str | None", row.transcript_content)
            elif source_type == "DOCUMENT_SEGMENT":
                quote = cast("str | None", row.document_content)
            elif source_type == "CHAT_MESSAGE":
                quote = cast("str | None", row.chat_content)
            else:
                quote = None
            anchors.append(
                ConceptAnchorSourceOut(
                    anchor_id=cast(str, row.anchor_id),
                    source_type=cast(SourceAnchorType, row.source_type),
                    relation_type=cast(str, row.relation_type),
                    record_id=cast("str | None", row.record_id),
                    record_title=cast("str | None", row.record_title),
                    quote=quote[:_OCCURRENCE_QUOTE_LIMIT] if quote is not None else None,
                    start_ms=cast("int | None", row.record_start_ms),
                    end_ms=cast("int | None", row.record_end_ms),
                    page_no=cast("int | None", row.page_no),
                    chat_session_id=cast("str | None", row.chat_session_id),
                )
            )
        kp_rows = (
            await session.execute(
                _CONCEPT_KP_SOURCES_SQL, {"concept_id": concept.id, "course_id": course_id}
            )
        ).all()
        knowledge_points = [
            ConceptKpSourceOut(
                record_id=cast(str, row.record_id),
                record_title=cast(str, row.record_title),
                knowledge_point_id=cast(str, row.knowledge_point_id),
                knowledge_point_name=cast(str, row.knowledge_point_name),
                relevance=float(row.relevance),
                evidence_count=int(row.evidence_count),
            )
            for row in kp_rows
        ]
        return ConceptSourcesOut(
            concept_id=concept.id, anchors=anchors, knowledge_points=knowledge_points
        )

    @staticmethod
    async def create_concept(
        session: AsyncSession, course_id: str, body: BrainConceptCreate
    ) -> BrainConceptOut:
        try:
            async with session.begin():
                await _get_active_course(session, course_id)
                normalized = normalize_concept_name(body.name)
                existing = await session.scalar(
                    select(Concept.id).where(
                        Concept.course_id == course_id,
                        Concept.normalized_name == normalized,
                        Concept.status == ConceptStatus.CONFIRMED.value,
                    )
                )
                if existing is not None:
                    raise CodedHTTPException(
                        code="COURSE_BRAIN_CONCEPT_EXISTS",
                        status_code=409,
                        detail="已存在同名概念",
                    )
                concept = Concept(
                    course_id=course_id,
                    canonical_name=body.name,
                    normalized_name=normalized,
                    description=body.description,
                    concept_type=body.concept_type,
                    importance=body.importance,
                    status=ConceptStatus.CONFIRMED.value,
                    source=ConceptSource.USER_CONFIRMED.value,
                )
                session.add(concept)
                await session.flush()
                await SegmentSearchService.upsert_segment_index(
                    session, ENTITY_CONCEPT, [concept.id]
                )
        except IntegrityError:
            # 部分唯一索引兜底（并发同名额）。
            raise CodedHTTPException(
                code="COURSE_BRAIN_CONCEPT_EXISTS", status_code=409, detail="已存在同名概念"
            ) from None
        return _concept_out(concept, None)

    @staticmethod
    async def search(
        session: AsyncSession, course_id: str, query: str, limit: int = 8
    ) -> CourseBrainSearchOut:
        """概念命中 → 检索词扩展（原查询 + 各 canonical_name 并跑）→ 合并去重。"""
        await _get_active_course(session, course_id)
        match = match_expression(query)
        if match is None:
            return CourseBrainSearchOut(matched_concepts=[], related_concepts=[], occurrences=[])
        concept_rows = (
            await session.execute(
                _CONCEPT_MATCH_SQL,
                {
                    "match": match,
                    "course_id": course_id,
                    "limit": min(limit, _CONCEPT_MATCH_LIMIT),
                },
            )
        ).all()
        matched_ids = [cast(str, row.concept_id) for row in concept_rows]
        stats = await _concept_stats(session, course_id, matched_ids)
        matched_concepts = [
            BrainSearchConceptOut(
                concept_id=cast(str, row.concept_id),
                canonical_name=cast(str, row.canonical_name),
                description=cast(str, row.description),
                record_count=stats.get(cast(str, row.concept_id), (0, 0))[0],
                occurrence_count=stats.get(cast(str, row.concept_id), (0, 0))[1],
            )
            for row in concept_rows
        ]

        occurrences: list[BrainSearchOccurrenceOut] = []
        seen: set[tuple[str, str]] = set()
        expansion_terms = [query] + [cast(str, row.canonical_name) for row in concept_rows]
        for term in expansion_terms:
            hits = await SegmentSearchService.search_scope_segments(
                session, course_id, term, _OCCURRENCE_PER_TERM
            )
            for hit in hits:
                key = (hit.record_id, hit.content)
                if key in seen:
                    continue
                seen.add(key)
                occurrences.append(_occurrence_out(hit))
                if len(occurrences) >= limit:
                    break
            if len(occurrences) >= limit:
                break

        related = (
            await _related_concepts(session, course_id, matched_ids, limit) if matched_ids else []
        )
        return CourseBrainSearchOut(
            matched_concepts=matched_concepts,
            related_concepts=related,
            occurrences=occurrences,
        )


async def _related_concepts(
    session: AsyncSession, course_id: str, concept_ids: list[str], limit: int
) -> list[BrainSearchRelationOut]:
    params = {"course_id": course_id, "ids": concept_ids}
    outgoing = (await session.execute(_RELATED_OUTGOING_SQL, params)).all()
    incoming = (await session.execute(_RELATED_INCOMING_SQL, params)).all()
    results: list[BrainSearchRelationOut] = []
    seen: set[str] = set(concept_ids)
    for row in [*outgoing, *incoming]:
        concept_id = cast(str, row.concept_id)
        if concept_id in seen:
            continue
        seen.add(concept_id)
        results.append(
            BrainSearchRelationOut(
                concept_id=concept_id,
                canonical_name=cast(str, row.canonical_name),
                relation_type=cast(str, row.relation_type),
            )
        )
        if len(results) >= limit:
            break
    return results
