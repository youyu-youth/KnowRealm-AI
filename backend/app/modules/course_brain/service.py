"""Course Brain 查询服务（F4 CB-03）：快照六态、概念查询、来源回溯与 B2 检索底座。

零 LLM：手动创建的 CONFIRMED Concept 即可被统一查询模块读取；六态在查询时
派生（零后台任务），STALE 由「来源表 (count, max_updated_at) 聚合指纹」与最近
一次成功构建的 result_json.fingerprint 比对得出（ADR-0022）。
"""

import asyncio
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from loguru import logger
from sqlalchemy import bindparam, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.course.models import Course
from app.modules.course.schemas import CourseStatus
from app.modules.course_brain.models import Concept, ConceptRelation, RecordConcept
from app.modules.course_brain.schemas import (
    ApplyReviewRequest,
    BrainConceptCreate,
    BrainConceptDetailOut,
    BrainConceptListQuery,
    BrainConceptOut,
    BrainGraphEdgeOut,
    BrainGraphNodeOut,
    BrainGraphOut,
    BrainRelationListQuery,
    BrainRelationOut,
    BrainRelationStatus,
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
    ConfirmDecision,
    ConfirmRelationDecision,
    CourseBrainSearchOut,
    DismissDecision,
    DismissRelationDecision,
    MergeDecision,
    ReviewDecisionType,
)
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.search.schemas import LibrarySegmentSearchHit
from app.modules.search.segment_service import ENTITY_CONCEPT, SegmentSearchService
from app.modules.search.tokenizer import match_expression
from app.modules.settings.config import (
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
)
from app.modules.source_anchor.models import SourceAnchorLink
from app.modules.source_anchor.schemas import SourceAnchorType
from app.shared.errors import CodedHTTPException

_ACTIVE_JOB_STATUSES = ("PENDING", "RUNNING")
_CONCEPT_MATCH_LIMIT = 4
_OCCURRENCE_PER_TERM = 8
_OCCURRENCE_QUOTE_LIMIT = 500

# 合并建议阈值（CB-05）：确定性相似度量，超阈值只标注建议，不自动合并。
_MERGE_EDIT_SIMILARITY = 0.8
_MERGE_TOKEN_OVERLAP = 0.5

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

# 重复触发闸门：课程级构建任务在 PENDING/RUNNING 即视为进行中。
_ACTIVE_BUILD_JOB_SQL = text(
    "SELECT id FROM processing_jobs "
    "WHERE record_id IS NULL AND job_type = 'CONCEPT_EXTRACTION' "
    "AND status IN ('PENDING', 'RUNNING') "
    "AND json_extract(input_json, '$.course_id') = :course_id "
    "LIMIT 1"
)

# 出现统计：只计未软删记录；course_id 为 None 时统计全部课程（Agent ALL 范围）。
_RECORD_CONCEPT_STATS_SQL = text(
    "SELECT rc.concept_id AS concept_id, count(*) AS record_count, "
    "coalesce(sum(rc.evidence_count), 0) AS occurrence_count "
    "FROM record_concepts rc "
    "JOIN records r ON r.id = rc.record_id AND r.deleted_at IS NULL "
    "WHERE rc.concept_id IN :ids AND (:course_id IS NULL OR r.course_id = :course_id) "
    "GROUP BY rc.concept_id"
).bindparams(bindparam("ids", expanding=True))

_CONCEPT_ANCHOR_COUNT_SQL = text(
    "SELECT count(*) FROM source_anchor_links l "
    "JOIN source_anchors a ON a.id = l.source_anchor_id "
    "LEFT JOIN records r ON r.id = a.record_id AND r.deleted_at IS NULL "
    "WHERE l.resource_type = 'CONCEPT' AND l.resource_id = :concept_id "
    "AND a.course_id = :course_id "
    "AND (a.record_id IS NULL OR r.id IS NOT NULL)"
)

# Concept 命中：CONFIRMED-only（Agent 只读边界，ADR-0022）；course_id 为 None
# 时匹配全部课程（Agent ALL 范围），扩展由调用方按概念归属课程执行。
_CONCEPT_MATCH_SQL = text(
    "SELECT c.id AS concept_id, c.canonical_name, c.description, c.course_id AS course_id "
    "FROM segment_search_index "
    "JOIN concepts c ON c.id = segment_search_index.entity_id "
    "WHERE segment_search_index MATCH :match "
    "AND segment_search_index.entity_type = 'CONCEPT' "
    "AND c.status = 'CONFIRMED' "
    "AND (:course_id IS NULL OR c.course_id = :course_id) "
    "ORDER BY bm25(segment_search_index) "
    "LIMIT :limit"
)

# 关联概念同样守 CONFIRMED-only + 同课程（Agent 只读边界；跨课程异常行不泄漏）。
_RELATED_OUTGOING_SQL = text(
    "SELECT c.id AS concept_id, c.canonical_name, cr.relation_type "
    "FROM concept_relations cr "
    "JOIN concepts c ON c.id = cr.target_concept_id "
    "AND c.status = 'CONFIRMED' AND c.course_id = :course_id "
    "WHERE cr.course_id = :course_id AND cr.status = 'CONFIRMED' "
    "AND cr.source_concept_id IN :ids "
    "ORDER BY cr.confidence DESC, c.canonical_name"
).bindparams(bindparam("ids", expanding=True))
_RELATED_INCOMING_SQL = text(
    "SELECT c.id AS concept_id, c.canonical_name, cr.relation_type "
    "FROM concept_relations cr "
    "JOIN concepts c ON c.id = cr.source_concept_id "
    "AND c.status = 'CONFIRMED' AND c.course_id = :course_id "
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

# KP 桥来源：record_concepts 中携带 knowledge_point_id 的行（KP→Concept Resolution）；
# 只露 ACTIVE（收集/指纹口径一致，DRAFT/SUPERSEDED 不进来源面）。
_CONCEPT_KP_SOURCES_SQL = text(
    "SELECT rc.record_id, r.title AS record_title, rc.knowledge_point_id, "
    "kp.name AS knowledge_point_name, rc.relevance, rc.evidence_count "
    "FROM record_concepts rc "
    "JOIN records r ON r.id = rc.record_id AND r.deleted_at IS NULL "
    "JOIN knowledge_points kp ON kp.id = rc.knowledge_point_id "
    "AND kp.deleted_at IS NULL AND kp.generation_status = 'ACTIVE' "
    "WHERE rc.concept_id = :concept_id AND r.course_id = :course_id "
    "ORDER BY r.updated_at DESC, rc.id"
)


# 待归档派生（CB-05）：有出现映射且全部挂失效记录（软删/缺失）→ stale_archivable；
# 查询时派生不落库，零映射（如手动创建）不算待归档。
_STALE_ARCHIVABLE_SQL = text(
    "SELECT rc.concept_id AS concept_id, count(*) AS total_rows, "
    "sum(CASE WHEN r.id IS NULL OR r.deleted_at IS NOT NULL THEN 1 ELSE 0 END) AS dead_rows "
    "FROM record_concepts rc "
    "LEFT JOIN records r ON r.id = rc.record_id "
    "WHERE rc.concept_id IN :ids "
    "GROUP BY rc.concept_id"
).bindparams(bindparam("ids", expanding=True))

# 关系列表（CB-06）：JOIN 两端概念取规范名，供候选审核与正式关系管理。
_RELATIONS_LIST_SQL = text(
    "SELECT cr.id, cr.source_concept_id, "
    "sc.canonical_name AS source_name, sc.status AS source_status, "
    "cr.target_concept_id, "
    "tc.canonical_name AS target_name, tc.status AS target_status, "
    "cr.relation_type, cr.confidence, cr.evidence_count, cr.status, cr.created_at, cr.updated_at "
    "FROM concept_relations cr "
    "JOIN concepts sc ON sc.id = cr.source_concept_id "
    "JOIN concepts tc ON tc.id = cr.target_concept_id "
    "WHERE cr.course_id = :course_id AND cr.status = :status "
    "ORDER BY cr.confidence DESC, cr.created_at, cr.id "
    "LIMIT :limit OFFSET :offset"
)

# 图谱边（CB-06）：CONFIRMED 关系且两端概念均 CONFIRMED（跨课程异常行不泄漏）。
_GRAPH_EDGES_SQL = text(
    "SELECT cr.source_concept_id, cr.target_concept_id, cr.relation_type, "
    "cr.confidence, cr.evidence_count "
    "FROM concept_relations cr "
    "JOIN concepts sc ON sc.id = cr.source_concept_id "
    "AND sc.status = 'CONFIRMED' AND sc.course_id = :course_id "
    "JOIN concepts tc ON tc.id = cr.target_concept_id "
    "AND tc.status = 'CONFIRMED' AND tc.course_id = :course_id "
    "WHERE cr.course_id = :course_id AND cr.status = 'CONFIRMED' "
    "ORDER BY cr.confidence DESC, cr.id"
)

# 最近一次成功构建的产物（关系过期判定依据）；无产物返回 None（不标过期）。
_LATEST_BUILD_RESULT_SQL = text(
    "SELECT result_json FROM processing_jobs "
    "WHERE record_id IS NULL AND job_type = 'CONCEPT_EXTRACTION' "
    "AND status = 'SUCCEEDED' AND result_json IS NOT NULL "
    "AND json_extract(input_json, '$.course_id') = :course_id "
    "ORDER BY created_at DESC, id DESC LIMIT 1"
)


def normalize_concept_name(name: str) -> str:
    """规范名归一化（spec 数据合同）：strip → 空白折叠 → 全角转半角 → casefold。"""
    collapsed = re.sub(r"\s+", " ", name.strip())
    return unicodedata.normalize("NFKC", collapsed).casefold()


def _levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        for j, right_char in enumerate(right, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def _token_overlap(left: str, right: str) -> float:
    left_tokens = set(left.split(" "))
    right_tokens = set(right.split(" "))
    smaller = min(len(left_tokens), len(right_tokens))
    if smaller == 0:
        return 0.0
    return len(left_tokens & right_tokens) / smaller


def _suggest_merge_target(normalized_name: str, confirmed: list[Concept]) -> Concept | None:
    """确定性合并建议（CB-05）：编辑距离相似度或 token 重叠率超阈值的最高分正式概念。

    不自动合并；平分时保持传入顺序（调用方按 canonical_name, id 定序保证确定性）。
    """
    best: Concept | None = None
    best_score = 0.0
    for concept in confirmed:
        longer = max(len(normalized_name), len(concept.normalized_name))
        edit_similarity = (
            1.0 - _levenshtein_distance(normalized_name, concept.normalized_name) / longer
            if longer
            else 1.0
        )
        overlap = _token_overlap(normalized_name, concept.normalized_name)
        if edit_similarity < _MERGE_EDIT_SIMILARITY and overlap < _MERGE_TOKEN_OVERLAP:
            continue
        score = max(edit_similarity, overlap)
        if best is None or score > best_score:
            best = concept
            best_score = score
    return best


async def _confirmed_concepts(session: AsyncSession, course_id: str) -> list[Concept]:
    """课程内全部正式概念（合并建议的候选目标池）。"""
    return list(
        (
            await session.scalars(
                select(Concept)
                .where(
                    Concept.course_id == course_id,
                    Concept.status == ConceptStatus.CONFIRMED.value,
                )
                .order_by(Concept.canonical_name, Concept.id)
            )
        ).all()
    )


async def _stale_archivable_map(session: AsyncSession, concept_ids: list[str]) -> dict[str, bool]:
    """出现映射全部失效的正式概念 → 待归档徽章（查询时派生，不自动改状态）。"""
    if not concept_ids:
        return {}
    rows = (await session.execute(_STALE_ARCHIVABLE_SQL, {"ids": concept_ids})).all()
    return {
        cast(str, row.concept_id): int(row.total_rows) > 0
        and int(row.total_rows) == int(row.dead_rows)
        for row in rows
    }


async def _concept_badges(
    session: AsyncSession, course_id: str, concepts: list[Concept]
) -> tuple[dict[str, Concept | None], dict[str, bool]]:
    """按状态装配派生字段：候选 → 合并建议；正式概念 → 待归档徽章。"""
    suggestions: dict[str, Concept | None] = {}
    stale_map: dict[str, bool] = {}
    if any(concept.status == ConceptStatus.CANDIDATE.value for concept in concepts):
        confirmed = await _confirmed_concepts(session, course_id)
        suggestions = {
            concept.id: _suggest_merge_target(concept.normalized_name, confirmed)
            for concept in concepts
            if concept.status == ConceptStatus.CANDIDATE.value
        }
    confirmed_ids = [
        concept.id for concept in concepts if concept.status == ConceptStatus.CONFIRMED.value
    ]
    if confirmed_ids:
        stale_map = await _stale_archivable_map(session, confirmed_ids)
    return suggestions, stale_map


def _supported_relation_keys(result_json: str | None) -> set[tuple[str, str, str]] | None:
    """最近一次成功构建的关系支撑集（CB-06 worker 落盘）；无产物或旧格式为 None（不标过期）。"""
    if not result_json:
        return None
    try:
        payload: object = json.loads(result_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    supported = cast("dict[str, object]", payload).get("supported_relations")
    if not isinstance(supported, list):
        return None
    keys: set[tuple[str, str, str]] = set()
    for raw in cast("list[object]", supported):
        if not isinstance(raw, list):
            continue
        parts = cast("list[object]", raw)
        if len(parts) != 3:
            continue
        source_id, target_id, relation_type = parts
        if (
            isinstance(source_id, str)
            and isinstance(target_id, str)
            and isinstance(relation_type, str)
        ):
            keys.add((source_id, target_id, relation_type))
    return keys


def _relation_stale(key: tuple[str, str, str], supported: set[tuple[str, str, str]] | None) -> bool:
    """CONFIRMED 关系过期判定：有构建产物且本次抽取未覆盖该三元组；无产物不诬报。"""
    return supported is not None and key not in supported


async def _latest_supported_relations(
    session: AsyncSession, course_id: str
) -> set[tuple[str, str, str]] | None:
    row = cast(
        "str | None", await session.scalar(_LATEST_BUILD_RESULT_SQL, {"course_id": course_id})
    )
    return _supported_relation_keys(row)


async def _course_graph(
    session: AsyncSession, course_id: str, supported: set[tuple[str, str, str]] | None
) -> BrainGraphOut:
    """正式图谱视图（CB-06）：节点 = CONFIRMED 概念，边 = 两端均 CONFIRMED 的正式关系。

    supported 为 None（无成功构建产物）时不判过期，避免无依据的过期告警。
    """
    concepts = list(
        (
            await session.scalars(
                select(Concept)
                .where(
                    Concept.course_id == course_id,
                    Concept.status == ConceptStatus.CONFIRMED.value,
                )
                .order_by(Concept.canonical_name, Concept.id)
            )
        ).all()
    )
    stats = await _concept_stats(session, course_id, [concept.id for concept in concepts])
    nodes = [
        BrainGraphNodeOut(
            id=concept.id,
            canonical_name=concept.canonical_name,
            concept_type=concept.concept_type,
            importance=concept.importance,
            record_count=stats.get(concept.id, (0, 0))[0],
            occurrence_count=stats.get(concept.id, (0, 0))[1],
        )
        for concept in concepts
    ]
    edge_rows = (await session.execute(_GRAPH_EDGES_SQL, {"course_id": course_id})).all()
    edges = [
        BrainGraphEdgeOut(
            source_concept_id=cast(str, row.source_concept_id),
            target_concept_id=cast(str, row.target_concept_id),
            relation_type=cast(str, row.relation_type),
            confidence=float(row.confidence),
            evidence_count=int(row.evidence_count),
            stale=_relation_stale(
                (
                    cast(str, row.source_concept_id),
                    cast(str, row.target_concept_id),
                    cast(str, row.relation_type),
                ),
                supported,
            ),
        )
        for row in edge_rows
    ]
    return BrainGraphOut(nodes=nodes, edges=edges)


async def _set_concept_status(
    session: AsyncSession, concept: Concept, status: ConceptStatus
) -> None:
    """状态迁移同事务收尾：updated_at 落盘 + FTS 索引同步。

    归档 id 回表无 CONFIRMED 行，upsert 即顺带清理残留索引；确认/重命名则重建索引。
    """
    concept.status = status.value
    concept.updated_at = utcnow()
    await session.flush()
    await SegmentSearchService.upsert_segment_index(session, ENTITY_CONCEPT, [concept.id])


async def _set_relation_status(
    session: AsyncSession, relation: ConceptRelation, status: BrainRelationStatus
) -> None:
    """关系状态迁移同事务收尾：relation 不进 FTS，仅落 updated_at。"""
    relation.status = status.value
    relation.updated_at = utcnow()
    await session.flush()


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


async def _require_relation(
    session: AsyncSession, course_id: str, relation_id: str
) -> ConceptRelation:
    relation = (
        await session.scalars(
            select(ConceptRelation).where(
                ConceptRelation.id == relation_id, ConceptRelation.course_id == course_id
            )
        )
    ).one_or_none()
    if relation is None:
        raise CodedHTTPException(
            code="COURSE_BRAIN_RELATION_NOT_FOUND", status_code=404, detail="概念关系不存在"
        )
    return relation


async def _active_build_job(session: AsyncSession, course_id: str) -> str | None:
    return cast(
        "str | None",
        await session.scalar(_ACTIVE_BUILD_JOB_SQL, {"course_id": course_id}),
    )


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
    session: AsyncSession, course_id: str | None, concept_ids: list[str]
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


def _concept_out(
    concept: Concept,
    stats: tuple[int, int] | None,
    *,
    suggested_target: Concept | None = None,
    stale_archivable: bool = False,
) -> BrainConceptOut:
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
        suggested_target_id=suggested_target.id if suggested_target is not None else None,
        suggested_target_name=(
            suggested_target.canonical_name if suggested_target is not None else None
        ),
        stale_archivable=stale_archivable,
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
        # 关系过期判定依据：最近一次成功构建抽取到的关系三元组集合（CB-06）。
        supported = (
            _supported_relation_keys(cast("str | None", last_succeeded.result_json))
            if last_succeeded is not None
            else None
        )

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
            graph=await _course_graph(session, course_id, supported),
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
        # 派生徽章按状态装配：候选带合并建议，正式概念带待归档徽章（均查询时派生）。
        suggestions, stale_map = await _concept_badges(session, course_id, concepts)
        return [
            _concept_out(
                concept,
                stats.get(concept.id),
                suggested_target=suggestions.get(concept.id),
                stale_archivable=stale_map.get(concept.id, False),
            )
            for concept in concepts
        ]

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
        suggestions, stale_map = await _concept_badges(session, course_id, [concept])
        base = _concept_out(
            concept,
            stats.get(concept.id),
            suggested_target=suggestions.get(concept.id),
            stale_archivable=stale_map.get(concept.id, False),
        )
        return BrainConceptDetailOut(**base.model_dump(), anchor_count=anchor_count)

    @staticmethod
    async def list_relations(
        session: AsyncSession, course_id: str, query: BrainRelationListQuery
    ) -> list[BrainRelationOut]:
        """关系列表（CB-06）：按状态筛选；CONFIRMED 关系附过期徽章。"""
        await _get_active_course(session, course_id)
        supported: set[tuple[str, str, str]] | None = None
        if query.status == BrainRelationStatus.CONFIRMED:
            supported = await _latest_supported_relations(session, course_id)
        rows = (
            await session.execute(
                _RELATIONS_LIST_SQL,
                {
                    "course_id": course_id,
                    "status": query.status.value,
                    "limit": query.limit,
                    "offset": query.offset,
                },
            )
        ).all()
        relations: list[BrainRelationOut] = []
        for row in rows:
            source_id = cast(str, row.source_concept_id)
            target_id = cast(str, row.target_concept_id)
            relation_type = cast(str, row.relation_type)
            relations.append(
                BrainRelationOut(
                    id=cast(str, row.id),
                    course_id=course_id,
                    source_concept_id=source_id,
                    source_name=cast(str, row.source_name),
                    target_concept_id=target_id,
                    target_name=cast(str, row.target_name),
                    relation_type=relation_type,
                    confidence=float(row.confidence),
                    evidence_count=int(row.evidence_count),
                    status=BrainRelationStatus(cast(str, row.status)),
                    stale=(
                        cast(str, row.source_status) == ConceptStatus.CONFIRMED.value
                        and cast(str, row.target_status) == ConceptStatus.CONFIRMED.value
                        and _relation_stale((source_id, target_id, relation_type), supported)
                    ),
                    created_at=cast(datetime, row.created_at),
                    updated_at=cast(datetime, row.updated_at),
                )
            )
        return relations

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
    async def request_build(session: AsyncSession, data_dir: Path, course_id: str) -> str:
        """触发课程级构建任务（CB-04）：Provider/同意前置 → 课程守卫 → 重复触发闸门。"""
        provider, consent = await asyncio.gather(
            asyncio.to_thread(load_llm_provider, data_dir),
            asyncio.to_thread(llm_consent, data_dir),
        )
        if provider is None or not provider.api_key:
            raise CodedHTTPException(
                code="LLM_PROVIDER_UNCONFIGURED", status_code=409, detail="请先配置 LLM Provider"
            )
        if not consent[1]:
            raise CodedHTTPException(
                code="AI_CONSENT_REQUIRED", status_code=409, detail="请先同意外部 AI 处理"
            )
        async with session.begin():
            await _get_active_course(session, course_id)
            if await _active_build_job(session, course_id) is not None:
                raise CodedHTTPException(
                    code="COURSE_BRAIN_BUILD_IN_PROGRESS",
                    status_code=409,
                    detail="已有进行中的课程大脑构建任务",
                )
            now = utcnow()
            job = ProcessingJob(
                id=str(uuid4()),
                record_id=None,
                job_type=ProcessingJobType.CONCEPT_EXTRACTION,
                status=ProcessingJobStatus.PENDING,
                progress=0,
                attempts=0,
                max_attempts=1,
                next_run_at=None,
                waiting_reason=None,
                input_json=json.dumps(
                    {
                        "course_id": course_id,
                        "provider_fingerprint": llm_provider_fingerprint(provider),
                        "source_fingerprint": await compute_source_fingerprint(session, course_id),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                result_json=None,
                error_code=None,
                error_message=None,
                started_at=None,
                finished_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(job)
            await session.flush()
            return job.id

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
    async def apply_review(
        session: AsyncSession, course_id: str, body: ApplyReviewRequest
    ) -> BrainSnapshotOut:
        """审核闭环（CB-05 概念 / CB-06 关系）：决策列表单事务原子应用，任一决策失败整体回滚。"""
        try:
            async with session.begin():
                await _get_active_course(session, course_id)
                for decision in body.decisions:
                    if isinstance(decision, ConfirmDecision):
                        await _apply_confirm(session, course_id, decision)
                    elif isinstance(decision, MergeDecision):
                        await _apply_merge(session, course_id, decision)
                    elif isinstance(decision, DismissDecision):
                        await _apply_dismiss(session, course_id, decision)
                    elif isinstance(decision, ConfirmRelationDecision):
                        await _apply_confirm_relation(session, course_id, decision)
                    else:
                        # discriminated union 已穷尽五种决策，此处必为 DismissRelationDecision。
                        await _apply_dismiss_relation(session, course_id, decision)
        except IntegrityError:
            # 部分唯一索引兜底（确认/重命名撞已有正式名额）。
            raise CodedHTTPException(
                code="COURSE_BRAIN_CONCEPT_EXISTS", status_code=409, detail="已存在同名概念"
            ) from None
        # 审计日志（CB-08）：只记课程与决策计数，不落概念名/正文。
        counts = Counter(decision.decision_type for decision in body.decisions)
        logger.info(
            "course_brain_review_applied",
            course_id=course_id,
            confirm=counts.get(ReviewDecisionType.CONFIRM, 0),
            merge=counts.get(ReviewDecisionType.MERGE, 0),
            dismiss=counts.get(ReviewDecisionType.DISMISS, 0),
            confirm_relation=counts.get(ReviewDecisionType.CONFIRM_RELATION, 0),
            dismiss_relation=counts.get(ReviewDecisionType.DISMISS_RELATION, 0),
        )
        return await CourseBrainService.get_snapshot(session, course_id)

    @staticmethod
    async def archive_concept(
        session: AsyncSession, course_id: str, concept_id: str
    ) -> BrainConceptOut:
        """正式概念归档（CONFIRMED→ARCHIVED）：界面二次确认后的受控退役路径。"""
        async with session.begin():
            await _get_active_course(session, course_id)
            concept = await _require_concept(session, course_id, concept_id)
            if concept.status != ConceptStatus.CONFIRMED.value:
                raise CodedHTTPException(
                    code="COURSE_BRAIN_CONCEPT_STATE_INVALID",
                    status_code=409,
                    detail="仅正式概念可归档",
                )
            await _set_concept_status(session, concept, ConceptStatus.ARCHIVED)
            stats = await _concept_stats(session, course_id, [concept.id])
        return _concept_out(concept, stats.get(concept.id))

    @staticmethod
    async def match_concepts(
        session: AsyncSession,
        course_id: str | None,
        query: str,
        limit: int = _CONCEPT_MATCH_LIMIT,
    ) -> list[BrainSearchConceptOut]:
        """概念 FTS 命中（CONFIRMED-only，BM25 序）：course_id 为 None 时匹配全部课程。"""
        match = match_expression(query)
        if match is None:
            return []
        rows = (
            await session.execute(
                _CONCEPT_MATCH_SQL, {"match": match, "course_id": course_id, "limit": limit}
            )
        ).all()
        stats = await _concept_stats(
            session, course_id, [cast(str, row.concept_id) for row in rows]
        )
        return [
            BrainSearchConceptOut(
                concept_id=cast(str, row.concept_id),
                canonical_name=cast(str, row.canonical_name),
                description=cast(str, row.description),
                course_id=cast(str, row.course_id),
                record_count=stats.get(cast(str, row.concept_id), (0, 0))[0],
                occurrence_count=stats.get(cast(str, row.concept_id), (0, 0))[1],
            )
            for row in rows
        ]

    @staticmethod
    async def search(
        session: AsyncSession, course_id: str, query: str, limit: int = 8
    ) -> CourseBrainSearchOut:
        """概念命中 → 检索词扩展（原查询 + 各 canonical_name 并跑）→ 合并去重。"""
        await _get_active_course(session, course_id)
        matched_concepts = await CourseBrainService.match_concepts(
            session, course_id, query, min(limit, _CONCEPT_MATCH_LIMIT)
        )
        matched_ids = [concept.concept_id for concept in matched_concepts]

        occurrences: list[BrainSearchOccurrenceOut] = []
        seen: set[tuple[str, str]] = set()
        expansion_terms = [query] + [concept.canonical_name for concept in matched_concepts]
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


async def _apply_confirm(session: AsyncSession, course_id: str, decision: ConfirmDecision) -> None:
    """候选确认：可选重命名（归一化撞正式名额即 409）；确认后进 FTS 供检索。"""
    concept = await _require_concept(session, course_id, decision.concept_id)
    if concept.status != ConceptStatus.CANDIDATE.value:
        raise CodedHTTPException(
            code="COURSE_BRAIN_CONCEPT_STATE_INVALID",
            status_code=409,
            detail="仅待审核候选可确认",
        )
    if decision.new_name:
        normalized = normalize_concept_name(decision.new_name)
        existing = await session.scalar(
            select(Concept.id).where(
                Concept.course_id == course_id,
                Concept.normalized_name == normalized,
                Concept.status == ConceptStatus.CONFIRMED.value,
            )
        )
        if existing is not None:
            raise CodedHTTPException(
                code="COURSE_BRAIN_CONCEPT_EXISTS", status_code=409, detail="已存在同名概念"
            )
        concept.canonical_name = decision.new_name
        concept.normalized_name = normalized
    await _set_concept_status(session, concept, ConceptStatus.CONFIRMED)


async def _apply_merge(session: AsyncSession, course_id: str, decision: MergeDecision) -> None:
    """候选并入正式概念：出现映射计数合并、锚点链接改挂去重，候选退役。"""
    concept = await _require_concept(session, course_id, decision.concept_id)
    target = await _require_concept(session, course_id, decision.target_concept_id)
    if concept.id == target.id:
        raise CodedHTTPException(
            code="COURSE_BRAIN_CONCEPT_STATE_INVALID",
            status_code=409,
            detail="合并目标不能是候选自身",
        )
    if concept.status != ConceptStatus.CANDIDATE.value:
        raise CodedHTTPException(
            code="COURSE_BRAIN_CONCEPT_STATE_INVALID",
            status_code=409,
            detail="仅待审核候选可合并",
        )
    if target.status != ConceptStatus.CONFIRMED.value:
        raise CodedHTTPException(
            code="COURSE_BRAIN_CONCEPT_STATE_INVALID",
            status_code=409,
            detail="合并目标必须是正式概念",
        )
    now = utcnow()

    # 出现映射迁移：目标已有同记录行 → 计数合并后退役候选侧行；否则整体改挂。
    candidate_rows = list(
        (
            await session.scalars(
                select(RecordConcept).where(RecordConcept.concept_id == concept.id)
            )
        ).all()
    )
    if candidate_rows:
        target_rows = {
            row.record_id: row
            for row in (
                await session.scalars(
                    select(RecordConcept).where(
                        RecordConcept.concept_id == target.id,
                        RecordConcept.record_id.in_([row.record_id for row in candidate_rows]),
                    )
                )
            ).all()
        }
        for row in candidate_rows:
            merged = target_rows.get(row.record_id)
            if merged is None:
                row.concept_id = target.id
                row.updated_at = now
                continue
            merged.evidence_count += row.evidence_count
            merged.relevance = max(merged.relevance, row.relevance)
            if row.first_start_ms is not None and (
                merged.first_start_ms is None or row.first_start_ms < merged.first_start_ms
            ):
                merged.first_start_ms = row.first_start_ms
            if merged.knowledge_point_id is None:
                merged.knowledge_point_id = row.knowledge_point_id
            merged.updated_at = now
            await session.delete(row)
        await session.flush()

    # 锚点链接迁移：目标已有同锚点同关系类型的链接则去重删除，否则改挂 resource_id。
    candidate_links = list(
        (
            await session.scalars(
                select(SourceAnchorLink).where(
                    SourceAnchorLink.resource_type == "CONCEPT",
                    SourceAnchorLink.resource_id == concept.id,
                )
            )
        ).all()
    )
    if candidate_links:
        target_link_keys = {
            (row.source_anchor_id, row.relation_type)
            for row in (
                await session.scalars(
                    select(SourceAnchorLink).where(
                        SourceAnchorLink.resource_type == "CONCEPT",
                        SourceAnchorLink.resource_id == target.id,
                        SourceAnchorLink.source_anchor_id.in_(
                            [link.source_anchor_id for link in candidate_links]
                        ),
                    )
                )
            ).all()
        }
        for link in candidate_links:
            key = (link.source_anchor_id, link.relation_type)
            if key in target_link_keys:
                await session.delete(link)
            else:
                link.resource_id = target.id
        await session.flush()

    await _set_concept_status(session, concept, ConceptStatus.ARCHIVED)


async def _apply_dismiss(session: AsyncSession, course_id: str, decision: DismissDecision) -> None:
    """候选忽略：CANDIDATE→ARCHIVED；重建时同名概念会重新进入审核。"""
    concept = await _require_concept(session, course_id, decision.concept_id)
    if concept.status != ConceptStatus.CANDIDATE.value:
        raise CodedHTTPException(
            code="COURSE_BRAIN_CONCEPT_STATE_INVALID",
            status_code=409,
            detail="仅待审核候选可忽略",
        )
    await _set_concept_status(session, concept, ConceptStatus.ARCHIVED)


async def _apply_confirm_relation(
    session: AsyncSession, course_id: str, decision: ConfirmRelationDecision
) -> None:
    """关系候选确认：CANDIDATE→CONFIRMED，进入正式图谱与检索扩展。"""
    relation = await _require_relation(session, course_id, decision.relation_id)
    if relation.status != BrainRelationStatus.CANDIDATE.value:
        raise CodedHTTPException(
            code="COURSE_BRAIN_RELATION_STATE_INVALID",
            status_code=409,
            detail="仅待审核关系候选可确认",
        )
    await _set_relation_status(session, relation, BrainRelationStatus.CONFIRMED)


async def _apply_dismiss_relation(
    session: AsyncSession, course_id: str, decision: DismissRelationDecision
) -> None:
    """关系候选忽略：CANDIDATE→DISMISSED；重建同三元组被跳过，不会复活。"""
    relation = await _require_relation(session, course_id, decision.relation_id)
    if relation.status != BrainRelationStatus.CANDIDATE.value:
        raise CodedHTTPException(
            code="COURSE_BRAIN_RELATION_STATE_INVALID",
            status_code=409,
            detail="仅待审核关系候选可忽略",
        )
    await _set_relation_status(session, relation, BrainRelationStatus.DISMISSED)


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
