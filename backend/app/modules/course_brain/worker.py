"""课程大脑构建执行体描述（F4 CB-04；任务循环骨架见 job_runner.py，ADR-0012）。

课程级任务（record_id=NULL，course_id 存 input_json，job_type=CONCEPT_EXTRACTION）：
多来源收集（ACTIVE KP / Transcript 分片 / Document 分片 / 对话转 KP 的 Chat 锚点）→
按记录分块（转写 ≤30k 全文，超长降级已确认摘要 + KP 清单；块总预算 40k）→
LLM 结构化抽取 → 确定性归一化（同 CONFIRMED 名自动挂接）→ 候选 / KP 桥 / 锚点 /
关系候选 → 单事务原子发布。失败回滚不破坏上一版图谱；不写 learning_events
（AI 推断不是学习证据，ADR-0022）。
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from loguru import logger
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.course.models import Course
from app.modules.course.schemas import CourseStatus
from app.modules.course_brain.models import Concept, ConceptRelation, RecordConcept
from app.modules.course_brain.schemas import (
    ConceptSource,
    ConceptStatus,
    CourseBrainExtractionBatch,
)
from app.modules.course_brain.service import (
    compute_source_fingerprint,
    normalize_concept_name,
)
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.runner import (
    CancelClaim,
    ClaimCheck,
    ClaimedJob,
    LoopFailure,
    Ready,
    RunnerContext,
    WorkerSpec,
    mark_failed,
    recover_running_to_failed,
)
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.llm.service import (
    CourseBrainModel,
    StructuredGenerationError,
    call_course_brain_model,
)
from app.modules.record.models import Record
from app.modules.settings.config import (
    LlmProviderConfig,
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
)
from app.modules.source_anchor.models import SourceAnchor, SourceAnchorLink
from app.modules.source_anchor.schemas import SourceAnchorType
from app.modules.source_anchor.service import SourceAnchorService
from app.modules.summary.derivation import summary_content
from app.modules.summary.models import AiSummary
from app.modules.summary.schemas import AiSummaryStatus, SummaryContent
from app.shared.events import RecordInvalidationNotifier
from app.shared.prompts import CONTENT_LANGUAGE_INSTRUCTION

PROMPT_VERSION = "course_brain_v1"
PREREQUISITE_CHANGED = "PREREQUISITE_CHANGED"
TRANSCRIPT_LIMIT = 30_000  # 复用 KP worker 的转写预算惯例
BLOCK_CHAR_BUDGET = 40_000

_RECORDS_SQL = text(
    "SELECT id, title FROM records "
    "WHERE course_id = :course_id AND deleted_at IS NULL "
    "ORDER BY created_at, id"
)
_TRANSCRIPT_SEGMENTS_SQL = text(
    "SELECT ts.id AS segment_id, ts.record_id, ts.content, ts.sequence_no, "
    "ts.record_start_ms, ts.record_end_ms "
    "FROM transcript_segments ts "
    "JOIN transcripts t ON t.id = ts.transcript_id AND t.deleted_at IS NULL "
    "JOIN records r ON r.id = ts.record_id AND r.deleted_at IS NULL "
    "WHERE r.course_id = :course_id "
    "ORDER BY ts.record_id, ts.sequence_no"
)
_DOCUMENT_SEGMENTS_SQL = text(
    "SELECT ds.id AS segment_id, ds.record_id, ds.content, ds.sequence_no, ds.page_no "
    "FROM document_segments ds "
    "JOIN records r ON r.id = ds.record_id AND r.deleted_at IS NULL "
    "WHERE r.course_id = :course_id "
    "ORDER BY ds.record_id, ds.sequence_no"
)
_KP_ROWS_SQL = text(
    "SELECT kp.id AS kp_id, kp.record_id, kp.name, kp.detail "
    "FROM knowledge_points kp "
    "JOIN records r ON r.id = kp.record_id AND r.deleted_at IS NULL "
    "WHERE r.course_id = :course_id AND kp.deleted_at IS NULL "
    "AND kp.generation_status = 'ACTIVE' "
    "ORDER BY kp.record_id, kp.created_at"
)
_KP_CHAT_ANCHOR_SQL = text(
    "SELECT l.resource_id AS kp_id, a.id AS anchor_id "
    "FROM source_anchor_links l "
    "JOIN source_anchors a ON a.id = l.source_anchor_id "
    "JOIN knowledge_points kp ON kp.id = l.resource_id AND kp.deleted_at IS NULL "
    "JOIN records r ON r.id = kp.record_id AND r.deleted_at IS NULL "
    "WHERE l.resource_type = 'KNOWLEDGE_POINT' AND a.source_type = 'CHAT_MESSAGE' "
    "AND r.course_id = :course_id"
)


@dataclass(frozen=True)
class _SourceSegment:
    source_type: SourceAnchorType
    segment_id: str
    record_id: str
    content: str
    sequence_no: int
    start_ms: int | None
    end_ms: int | None
    page_no: int | None


@dataclass(frozen=True)
class _RecordBlock:
    record_id: str
    prompt_text: str
    segments: tuple[_SourceSegment, ...]
    kp_id_by_normalized: dict[str, str]


@dataclass(frozen=True)
class _RecordExtraction:
    block: _RecordBlock
    content: CourseBrainExtractionBatch


@dataclass(frozen=True)
class _BrainExtraction:
    records: tuple[_RecordExtraction, ...]
    fingerprint: dict[str, object]


@dataclass
class _Occurrence:
    """一条记录内某概念的出现累积（构造期可变，发布期只读）。"""

    relevance: float
    evidence_count: int = 0
    first_start_ms: int | None = None
    knowledge_point_id: str | None = None


@dataclass(frozen=True)
class _PublishPlan:
    touched_count: int
    created_concept_count: int
    skipped_evidence_count: int
    occurrences: dict[tuple[str, str], _Occurrence]
    located: dict[tuple[str, str], _SourceSegment]
    relation_candidates: dict[tuple[str, str, str], float]


@dataclass(frozen=True)
class _ClaimedBrainJob(ClaimedJob):
    """课程级任务：record_id 坐标位承载 course_id（构建任务无 record 主体）。"""

    course_id: str
    course_name: str
    learning_context: str
    education_stage: str | None
    depth: str | None
    provider: LlmProviderConfig


def build_brain_prompt(ctx: _ClaimedBrainJob, block: _RecordBlock) -> str:
    return (
        "请从以下课程内容中抽取概念（Concept）以及概念之间的关系。"
        "严格返回指定结构，不添加结构外字段；没有把握的内容不要输出。\n"
        f"课程名称：{ctx.course_name}\n"
        f"学习场景：{ctx.learning_context}\n"
        f"教育阶段：{ctx.education_stage or '未设置'}\n"
        f"内容深度：{ctx.depth or '未设置'}\n"
        "抽取要求：\n"
        "- name：概念规范名，尽量使用课程中出现的规范术语，跨记录保持一致\n"
        "- description：一句话说明概念含义\n"
        "- concept_type：从 TERM/PROCESS/PRINCIPLE/METHOD/TOOL 中选择\n"
        "- importance：1~5 的整数\n"
        "- evidence.quote：必须逐字摘自下方原文（不超过 120 字），不得改写或概括\n"
        "- relations 的 source/target：必须是本次返回概念中的 name\n"
        "- relation_type：从 PREREQUISITE/PART_OF/RELATED_TO/COMPARE_WITH/"
        "CAUSES/APPLIES_TO 中选择\n"
        f"{CONTENT_LANGUAGE_INSTRUCTION}\n"
        "课程内容：\n"
        f"{block.prompt_text}"
    )


def _summary_text(content: SummaryContent) -> str:
    sections = "\n".join(
        f"{section.heading}：" + "；".join(section.points) for section in content.sections
    )
    return "\n".join(part for part in (content.topic, content.abstract, sections) if part)


def _build_block(
    *,
    record_id: str,
    title: str,
    segments: list[_SourceSegment],
    kp_rows: list[tuple[str, str, str]],
    summary_text: str | None,
) -> _RecordBlock:
    transcript_text = "\n".join(
        segment.content
        for segment in segments
        if segment.source_type == SourceAnchorType.AUDIO_SEGMENT
    )
    document_text = "\n".join(
        f"第 {segment.page_no} 页：{segment.content}"
        if segment.page_no is not None
        else segment.content
        for segment in segments
        if segment.source_type == SourceAnchorType.DOCUMENT_SEGMENT
    )
    parts = [f"记录：{title}"]
    if kp_rows:
        parts.append(
            "已确认知识点：\n"
            + "\n".join(f"- {name}：{detail}" for _kp_id, name, detail in kp_rows)
        )
    if len(transcript_text) > TRANSCRIPT_LIMIT:
        parts.append("已确认总结：\n" + (summary_text or "（无）"))
    elif transcript_text:
        parts.append("转写：\n" + transcript_text[:TRANSCRIPT_LIMIT])
    if document_text:
        parts.append("文档：\n" + document_text)
    return _RecordBlock(
        record_id=record_id,
        prompt_text="\n".join(parts)[:BLOCK_CHAR_BUDGET],
        segments=tuple(segments),
        kp_id_by_normalized={
            normalize_concept_name(name): kp_id for kp_id, name, _detail in kp_rows
        },
    )


async def _collect_blocks(session: AsyncSession, course_id: str) -> list[_RecordBlock]:
    params = {"course_id": course_id}
    records = (await session.execute(_RECORDS_SQL, params)).all()
    segments_by_record: dict[str, list[_SourceSegment]] = {}
    for row in (await session.execute(_TRANSCRIPT_SEGMENTS_SQL, params)).all():
        segments_by_record.setdefault(cast(str, row.record_id), []).append(
            _SourceSegment(
                source_type=SourceAnchorType.AUDIO_SEGMENT,
                segment_id=cast(str, row.segment_id),
                record_id=cast(str, row.record_id),
                content=cast(str, row.content),
                sequence_no=int(row.sequence_no),
                start_ms=cast("int | None", row.record_start_ms),
                end_ms=cast("int | None", row.record_end_ms),
                page_no=None,
            )
        )
    for row in (await session.execute(_DOCUMENT_SEGMENTS_SQL, params)).all():
        segments_by_record.setdefault(cast(str, row.record_id), []).append(
            _SourceSegment(
                source_type=SourceAnchorType.DOCUMENT_SEGMENT,
                segment_id=cast(str, row.segment_id),
                record_id=cast(str, row.record_id),
                content=cast(str, row.content),
                sequence_no=int(row.sequence_no),
                start_ms=None,
                end_ms=None,
                page_no=cast("int | None", row.page_no),
            )
        )
    kp_rows_by_record: dict[str, list[tuple[str, str, str]]] = {}
    for row in (await session.execute(_KP_ROWS_SQL, params)).all():
        kp_rows_by_record.setdefault(cast(str, row.record_id), []).append(
            (cast(str, row.kp_id), cast(str, row.name), cast(str, row.detail))
        )
    summary_by_record: dict[str, str] = {}
    summaries = (
        await session.scalars(
            select(AiSummary)
            .join(Record, Record.id == AiSummary.record_id)
            .where(
                Record.course_id == course_id,
                Record.deleted_at.is_(None),
                AiSummary.status == AiSummaryStatus.CONFIRMED,
                AiSummary.deleted_at.is_(None),
            )
            .order_by(AiSummary.version_no.desc())
        )
    ).all()
    for summary in summaries:
        summary_by_record.setdefault(summary.record_id, _summary_text(summary_content(summary)))

    blocks: list[_RecordBlock] = []
    for record in records:
        record_id = cast(str, record.id)
        segments = segments_by_record.get(record_id, [])
        kp_rows = kp_rows_by_record.get(record_id, [])
        if not segments and not kp_rows:
            continue
        block = _build_block(
            record_id=record_id,
            title=cast(str, record.title),
            segments=segments,
            kp_rows=kp_rows,
            summary_text=summary_by_record.get(record_id),
        )
        if block.prompt_text.strip():
            blocks.append(block)
    return blocks


def _locate_quote(segments: tuple[_SourceSegment, ...], quote: str) -> _SourceSegment | None:
    normalized = quote.strip()
    if not normalized:
        return None
    for segment in segments:
        if normalized in segment.content:
            return segment
    return None


async def _chat_anchors_by_kp(session: AsyncSession, course_id: str) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for row in (await session.execute(_KP_CHAT_ANCHOR_SQL, {"course_id": course_id})).all():
        mapping.setdefault(cast(str, row.kp_id), []).append(cast(str, row.anchor_id))
    return mapping


async def preflight(data_dir: Path) -> LlmProviderConfig | None:
    provider = await asyncio.to_thread(load_llm_provider, data_dir)
    consent_at, consent_current = await asyncio.to_thread(llm_consent, data_dir)
    if provider is None or not provider.api_key or not consent_current or consent_at is None:
        return None
    return provider


async def find_candidate(session: AsyncSession, now: datetime) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.job_type == ProcessingJobType.CONCEPT_EXTRACTION,
                ProcessingJob.status == ProcessingJobStatus.PENDING,
            )
            .order_by(ProcessingJob.created_at)
            .limit(1)
        )
    ).one_or_none()


async def validate_claim(
    session: AsyncSession,
    job: ProcessingJob,
    _record_id: str,
    provider: LlmProviderConfig | None,
) -> ClaimCheck[_ClaimedBrainJob]:
    """领取闸门：课程存活 / 非 ARCHIVED / 供应商指纹任一失效即静默取消。"""
    current_provider = cast(LlmProviderConfig, provider)  # preflight 通过时必非 None
    input_data = cast(dict[str, object], json.loads(job.input_json))
    course_id = input_data.get("course_id")
    course = await session.get(Course, course_id) if isinstance(course_id, str) else None
    if (
        course is None
        or course.deleted_at is not None
        or course.status != CourseStatus.ACTIVE
        or input_data.get("provider_fingerprint") != llm_provider_fingerprint(current_provider)
    ):
        return CancelClaim(PREREQUISITE_CHANGED)
    return Ready(
        _ClaimedBrainJob(
            job_id=job.id,
            record_id=course.id,
            course_id=course.id,
            course_name=course.name,
            learning_context=course.learning_context,
            education_stage=course.education_stage,
            depth=course.depth,
            provider=current_provider,
        )
    )


async def execute(
    ctx: _ClaimedBrainJob,
    _runtime: RunnerContext,
    session_factory: async_sessionmaker[AsyncSession],
    model: CourseBrainModel,
) -> _BrainExtraction:
    """只读收集 + LLM 抽取（零业务写入；发布全部落在 writeback 单事务）。"""
    async with session_factory() as session:
        blocks = await _collect_blocks(session, ctx.course_id)
    extractions: list[_RecordExtraction] = []
    for block in blocks:
        call = await call_course_brain_model(
            session_factory=session_factory,
            course_brain_model=model,
            provider=ctx.provider,
            prompt=build_brain_prompt(ctx, block),
            prompt_version=PROMPT_VERSION,
        )
        extractions.append(_RecordExtraction(block=block, content=call.content))
    async with session_factory() as session:
        fingerprint = await compute_source_fingerprint(session, ctx.course_id)
    return _BrainExtraction(records=tuple(extractions), fingerprint=fingerprint)


async def writeback(
    ctx: _ClaimedBrainJob,
    extraction: _BrainExtraction,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    """原子发布：候选 + record_concepts + 锚点 + 关系候选同事务；失败整体回滚。"""
    now = utcnow()
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, ctx.job_id)
        if job is None or job.status != ProcessingJobStatus.RUNNING:
            return False
        course = await session.get(Course, ctx.course_id)
        if course is None or course.deleted_at is not None or course.status != CourseStatus.ACTIVE:
            job.status = ProcessingJobStatus.CANCELLED
            job.result_json = json.dumps({"reason": PREREQUISITE_CHANGED}, separators=(",", ":"))
            job.finished_at = now
            job.updated_at = now
            return False

        plan = await _build_publish_plan(session, ctx.course_id, extraction)
        await _publish_occurrences(session, ctx.course_id, plan, now)
        await _publish_anchors(session, ctx.course_id, plan)
        await _publish_relation_candidates(session, ctx.course_id, plan, now)

        job.status = ProcessingJobStatus.SUCCEEDED
        job.progress = 1
        job.result_json = json.dumps(
            {
                "fingerprint": extraction.fingerprint,
                "concept_count": plan.touched_count,
                "candidate_count": plan.created_concept_count,
                "skipped_evidence_count": plan.skipped_evidence_count,
                # 本次抽取到的关系三元组（CB-06）：查询侧据此派生 CONFIRMED 关系的过期徽章。
                "supported_relations": [
                    [source_id, target_id, relation_type]
                    for source_id, target_id, relation_type in plan.relation_candidates
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        job.error_code = None
        job.error_message = None
        job.finished_at = now
        job.updated_at = now
    if plan.skipped_evidence_count:
        logger.warning(
            "course_brain_evidence_unlocated",
            course_id=ctx.course_id,
            count=plan.skipped_evidence_count,
        )
    return True


async def _build_publish_plan(
    session: AsyncSession, course_id: str, extraction: _BrainExtraction
) -> _PublishPlan:
    """归一化抽取结果：复用/新建概念、累计出现、逐字定位证据、汇总关系候选。"""
    concepts = list(
        (
            await session.scalars(
                select(Concept)
                .where(
                    Concept.course_id == course_id,
                    # ARCHIVED 不参与复用：用户已忽略的同名概念重新抽取须再走 CANDIDATE 审核。
                    Concept.status.in_(
                        (ConceptStatus.CONFIRMED.value, ConceptStatus.CANDIDATE.value)
                    ),
                )
                .order_by(Concept.created_at, Concept.id)
            )
        ).all()
    )
    # 同 normalized_name 优先复用 CONFIRMED，其次早建候选（不重正式节点）。
    concept_by_norm: dict[str, Concept] = {}
    for concept in concepts:
        current = concept_by_norm.get(concept.normalized_name)
        if current is None or (
            concept.status == ConceptStatus.CONFIRMED.value
            and current.status != ConceptStatus.CONFIRMED.value
        ):
            concept_by_norm[concept.normalized_name] = concept

    created_concepts: list[Concept] = []
    touched_ids: set[str] = set()
    occurrences: dict[tuple[str, str], _Occurrence] = {}
    located: dict[tuple[str, str], _SourceSegment] = {}
    relation_candidates: dict[tuple[str, str, str], float] = {}
    skipped_evidence_count = 0
    evidenced_concept_ids: set[str] = set()

    for record_extraction in extraction.records:
        block = record_extraction.block
        for raw in record_extraction.content.concepts:
            normalized = normalize_concept_name(raw.name)
            if not normalized:
                continue
            concept = concept_by_norm.get(normalized)
            if concept is None:
                concept = Concept(
                    course_id=course_id,
                    canonical_name=raw.name.strip(),
                    normalized_name=normalized,
                    description=raw.description.strip(),
                    concept_type=raw.concept_type.strip() or "TERM",
                    importance=raw.importance,
                    status=ConceptStatus.CANDIDATE.value,
                    source=ConceptSource.AI_EXTRACTED.value,
                )
                session.add(concept)
                await session.flush()
                concept_by_norm[normalized] = concept
                created_concepts.append(concept)
            touched_ids.add(concept.id)

            occurrence = occurrences.setdefault(
                (block.record_id, concept.id),
                _Occurrence(
                    relevance=raw.importance / 5.0,
                    knowledge_point_id=block.kp_id_by_normalized.get(normalized),
                ),
            )
            if occurrence.knowledge_point_id is None:
                occurrence.knowledge_point_id = block.kp_id_by_normalized.get(normalized)
            for evidence in raw.evidence:
                segment = _locate_quote(block.segments, evidence.quote)
                if segment is None:
                    # 逐字定位失败：跳过该条证据并计数（不污染出现次数）。
                    skipped_evidence_count += 1
                    continue
                occurrence.evidence_count += 1
                evidenced_concept_ids.add(concept.id)
                located.setdefault((concept.id, segment.segment_id), segment)
                if (
                    segment.source_type == SourceAnchorType.AUDIO_SEGMENT
                    and segment.start_ms is not None
                ):
                    if (
                        occurrence.first_start_ms is None
                        or segment.start_ms < occurrence.first_start_ms
                    ):
                        occurrence.first_start_ms = segment.start_ms

        for relation in record_extraction.content.relations:
            source = concept_by_norm.get(normalize_concept_name(relation.source))
            target = concept_by_norm.get(normalize_concept_name(relation.target))
            if source is None or target is None or source.id == target.id:
                continue
            key = (source.id, target.id, relation.relation_type.value)
            # 同一三元组重复出现取最高置信度（Last-write 会让顺序影响结果）。
            relation_candidates[key] = max(relation_candidates.get(key, 0.0), relation.confidence)

    # 零证据闸门：本次新建但一条证据都未定位成功的概念不进审核（连同关系候选、
    # 出现计数一并剔除）；零证据出现映射一律不写（无逐字证据的挂靠不算出现）。
    # 复用中的既有候选/正式概念不动历史数据，由确认闸门（service._apply_confirm）兜底。
    kept_created: list[Concept] = []
    dropped_ids: set[str] = set()
    for concept in created_concepts:
        if concept.id in evidenced_concept_ids:
            kept_created.append(concept)
        else:
            dropped_ids.add(concept.id)
            touched_ids.discard(concept.id)
            await session.delete(concept)
    created_concepts = kept_created
    occurrences = {
        key: occurrence for key, occurrence in occurrences.items() if occurrence.evidence_count > 0
    }
    if dropped_ids:
        relation_candidates = {
            key: confidence
            for key, confidence in relation_candidates.items()
            if key[0] not in dropped_ids and key[1] not in dropped_ids
        }

    return _PublishPlan(
        touched_count=len(touched_ids),
        created_concept_count=len(created_concepts),
        skipped_evidence_count=skipped_evidence_count,
        occurrences=occurrences,
        located=located,
        relation_candidates=relation_candidates,
    )


async def _publish_occurrences(
    session: AsyncSession, course_id: str, plan: _PublishPlan, now: datetime
) -> None:
    """课程内出现映射整体替换（重复构建不累加）。"""
    await session.execute(
        delete(RecordConcept).where(
            RecordConcept.record_id.in_(select(Record.id).where(Record.course_id == course_id))
        )
    )
    for (record_id, concept_id), occurrence in plan.occurrences.items():
        session.add(
            RecordConcept(
                record_id=record_id,
                concept_id=concept_id,
                knowledge_point_id=occurrence.knowledge_point_id,
                relevance=occurrence.relevance,
                evidence_count=occurrence.evidence_count,
                first_start_ms=occurrence.first_start_ms,
                created_at=now,
                updated_at=now,
            )
        )


async def _publish_anchors(session: AsyncSession, course_id: str, plan: _PublishPlan) -> None:
    """撤旧 CONCEPT 链接（仅服务概念的 AUDIO/DOCUMENT 锚点一并回收）后按本次定位重建；
    KP 桥命中的对话来源挂到同一 CHAT_MESSAGE 锚点（不复制锚点行）。"""
    concept_ids_select = select(Concept.id).where(Concept.course_id == course_id)
    existing_anchor_ids = list(
        await session.scalars(
            select(SourceAnchorLink.source_anchor_id).where(
                SourceAnchorLink.resource_type == "CONCEPT",
                SourceAnchorLink.resource_id.in_(concept_ids_select),
            )
        )
    )
    if existing_anchor_ids:
        await session.execute(
            delete(SourceAnchor).where(
                SourceAnchor.id.in_(existing_anchor_ids),
                SourceAnchor.source_type.in_(
                    (SourceAnchorType.AUDIO_SEGMENT, SourceAnchorType.DOCUMENT_SEGMENT)
                ),
            )
        )
        await session.execute(
            delete(SourceAnchorLink).where(
                SourceAnchorLink.resource_type == "CONCEPT",
                SourceAnchorLink.resource_id.in_(concept_ids_select),
            )
        )
    for (concept_id, _segment_id), segment in plan.located.items():
        anchor = SourceAnchor(
            course_id=course_id,
            source_type=segment.source_type,
            source_id=segment.segment_id,
            record_id=segment.record_id,
            transcript_segment_id=(
                segment.segment_id
                if segment.source_type == SourceAnchorType.AUDIO_SEGMENT
                else None
            ),
            document_segment_id=(
                segment.segment_id
                if segment.source_type == SourceAnchorType.DOCUMENT_SEGMENT
                else None
            ),
            page_no=segment.page_no,
        )
        session.add(anchor)
        await session.flush()
        await SourceAnchorService.link_resource(
            session,
            resource_type="CONCEPT",
            resource_id=concept_id,
            source_anchor_id=anchor.id,
            relation_type="SUPPORTS",
        )
    chat_anchors = await _chat_anchors_by_kp(session, course_id)
    for (_record_id, concept_id), occurrence in plan.occurrences.items():
        if occurrence.knowledge_point_id is None:
            continue
        for anchor_id in chat_anchors.get(occurrence.knowledge_point_id, []):
            await SourceAnchorService.link_resource(
                session,
                resource_type="CONCEPT",
                resource_id=concept_id,
                source_anchor_id=anchor_id,
                relation_type="REFERENCES",
            )


async def _publish_relation_candidates(
    session: AsyncSession, course_id: str, plan: _PublishPlan, now: datetime
) -> None:
    """关系候选只补缺：既有人工结论（含 DISMISSED）不被重建复活或覆盖。"""
    existing = {
        (str(row[0]), str(row[1]), str(row[2]))
        for row in (
            await session.execute(
                select(
                    ConceptRelation.source_concept_id,
                    ConceptRelation.target_concept_id,
                    ConceptRelation.relation_type,
                ).where(ConceptRelation.course_id == course_id)
            )
        ).all()
    }
    for (source_id, target_id, relation_type), confidence in plan.relation_candidates.items():
        if (source_id, target_id, relation_type) in existing:
            continue
        session.add(
            ConceptRelation(
                course_id=course_id,
                source_concept_id=source_id,
                target_concept_id=target_id,
                relation_type=relation_type,
                confidence=confidence,
                evidence_count=0,
                status="CANDIDATE",
                created_at=now,
                updated_at=now,
            )
        )
        existing.add((source_id, target_id, relation_type))


def failure_code(ctx: _ClaimedBrainJob, exc: Exception) -> str | None:
    del ctx
    if isinstance(exc, StructuredGenerationError):
        return exc.code
    return "INTERNAL_ERROR"


async def apply_failure(
    ctx: _ClaimedBrainJob,
    session: AsyncSession,
    job: ProcessingJob,
    record: Record | None,
    error_code: str,
    now: datetime,
) -> bool:
    del ctx, session, record  # 课程大脑失败不触碰记录/课程状态
    mark_failed(job, code=error_code, message="课程大脑构建失败，请检查 Provider 后重试", now=now)
    return True


def course_brain_spec(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    model: CourseBrainModel,
    record_notifier: RecordInvalidationNotifier,
) -> WorkerSpec[LlmProviderConfig, _ClaimedBrainJob, _BrainExtraction]:
    async def recover() -> None:
        await recover_running_to_failed(
            session_factory,
            record_notifier,
            ProcessingJobType.CONCEPT_EXTRACTION,
            "课程大脑构建被意外中断",
        )

    def classify(_exc: Exception) -> LoopFailure:
        return LoopFailure(event="course_brain_worker_unexpected_failure")

    return WorkerSpec(
        name="course_brain_worker",
        job_type=ProcessingJobType.CONCEPT_EXTRACTION,
        poll_interval=0.25,
        find_candidate=find_candidate,
        validate_claim=validate_claim,
        execute=lambda ctx, runtime: execute(ctx, runtime, session_factory, model),
        writeback=lambda ctx, extraction: writeback(ctx, extraction, session_factory),
        failure_code=failure_code,
        apply_failure=apply_failure,
        recover_interrupted=recover,
        classify_loop_error=classify,
        preflight=lambda: preflight(data_dir),
    )
