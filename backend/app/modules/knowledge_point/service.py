import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.agent.models import ChatMessage
from app.modules.course.models import Course
from app.modules.course.schemas import CourseStatus
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.knowledge_point.models import KnowledgePoint
from app.modules.knowledge_point.schemas import (
    KnowledgePointAction,
    KnowledgePointBlockedReason,
    KnowledgePointChatSourceOut,
    KnowledgePointGenerationStatus,
    KnowledgePointInputMode,
    KnowledgePointOut,
    KnowledgePointReadOut,
    KnowledgePointWriteRequest,
)
from app.modules.learning.events import write_learning_event
from app.modules.library.shared_refs import assert_asset_generation_allowed
from app.modules.record.models import LearningEvent, Record
from app.modules.search.service import SearchService
from app.modules.settings.config import (
    LlmProviderConfig,
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
)
from app.modules.source_anchor.models import SourceAnchor, SourceAnchorLink
from app.modules.source_anchor.service import SourceAnchorService
from app.modules.summary.models import AiSummary
from app.modules.summary.schemas import AiSummaryStatus
from app.modules.transcript.models import Transcript
from app.shared.errors import CodedHTTPException

TRANSCRIPT_LIMIT = 30_000


def _knowledge_point_out(
    item: KnowledgePoint,
    *,
    chat_source: KnowledgePointChatSourceOut | None = None,
) -> KnowledgePointOut:
    raw_tags = cast(object, json.loads(item.tags))
    tag_items = cast(list[object], raw_tags) if isinstance(raw_tags, list) else []
    tags = [value for value in tag_items if isinstance(value, str)]
    return KnowledgePointOut(
        id=item.id,
        record_id=item.record_id,
        batch_id=item.batch_id,
        name=item.name,
        detail=item.detail,
        tags=tags,
        importance=int(item.importance),
        generated_from_summary_id=item.generated_from_summary_id,
        generation_status=KnowledgePointGenerationStatus(item.generation_status),
        chat_source=chat_source,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def _provider_state(data_dir: Path) -> tuple[LlmProviderConfig | None, bool]:
    provider, consent = await asyncio.gather(
        asyncio.to_thread(load_llm_provider, data_dir),
        asyncio.to_thread(llm_consent, data_dir),
    )
    return provider, consent[1]


async def _get_record(session: AsyncSession, record_id: str) -> Record:
    record = (
        await session.scalars(
            select(Record).where(Record.id == record_id, Record.deleted_at.is_(None))
        )
    ).one_or_none()
    if record is None:
        raise CodedHTTPException(
            code="RECORD_NOT_FOUND", status_code=404, detail="学习记录不存在或已删除"
        )
    return record


async def _confirmed_summary(session: AsyncSession, record_id: str) -> AiSummary | None:
    return (
        await session.scalars(
            select(AiSummary)
            .where(
                AiSummary.record_id == record_id,
                AiSummary.status == AiSummaryStatus.CONFIRMED,
                AiSummary.deleted_at.is_(None),
            )
            .order_by(AiSummary.version_no.desc())
            .limit(1)
        )
    ).one_or_none()


async def _superseded_summary_exists(session: AsyncSession, record_id: str) -> bool:
    return (
        await session.scalars(
            select(AiSummary.id)
            .where(
                AiSummary.record_id == record_id,
                AiSummary.status == AiSummaryStatus.SUPERSEDED,
                AiSummary.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).first() is not None


async def _active_job(session: AsyncSession, record_id: str) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.record_id == record_id,
                ProcessingJob.job_type == ProcessingJobType.KNOWLEDGE_EXTRACTION,
                ProcessingJob.status.in_(
                    (ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING)
                ),
            )
            .order_by(ProcessingJob.created_at.desc())
            .limit(1)
        )
    ).one_or_none()


async def _failed_job(session: AsyncSession, record_id: str) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.record_id == record_id,
                ProcessingJob.job_type == ProcessingJobType.KNOWLEDGE_EXTRACTION,
                ProcessingJob.status == ProcessingJobStatus.FAILED,
            )
            .order_by(ProcessingJob.created_at.desc())
            .limit(1)
        )
    ).one_or_none()


async def _visible_items(
    session: AsyncSession,
    record_id: str,
    *,
    include_superseded: bool = False,
) -> list[KnowledgePoint]:
    statuses: tuple[KnowledgePointGenerationStatus, ...] = (
        (
            KnowledgePointGenerationStatus.DRAFT,
            KnowledgePointGenerationStatus.ACTIVE,
            KnowledgePointGenerationStatus.SUPERSEDED,
        )
        if include_superseded
        else (
            KnowledgePointGenerationStatus.DRAFT,
            KnowledgePointGenerationStatus.ACTIVE,
        )
    )
    return list(
        (
            await session.scalars(
                select(KnowledgePoint)
                .where(
                    KnowledgePoint.record_id == record_id,
                    KnowledgePoint.deleted_at.is_(None),
                    KnowledgePoint.generation_status.in_(statuses),
                )
                .order_by(KnowledgePoint.importance.desc(), KnowledgePoint.created_at)
            )
        ).all()
    )


async def _chat_source_sessions(session: AsyncSession, record_id: str) -> dict[str, str]:
    """记录下知识点的对话来源映射（kp_id → chat_session_id）。

    经 KNOWLEDGE_POINT 链接 × CHAT_MESSAGE 锚点派生；不回查会话软删——
    徽章表达「来自 AI 对话」的历史事实，跳转后由会话页自然处理失效态。
    """
    rows = (
        await session.execute(
            select(SourceAnchorLink.resource_id, ChatMessage.session_id)
            .join(SourceAnchor, SourceAnchor.id == SourceAnchorLink.source_anchor_id)
            .join(ChatMessage, ChatMessage.id == SourceAnchor.source_id)
            .where(
                SourceAnchorLink.resource_type == "KNOWLEDGE_POINT",
                SourceAnchor.source_type == "CHAT_MESSAGE",
                SourceAnchor.record_id == record_id,
            )
        )
    ).all()
    return {resource_id: chat_session_id for resource_id, chat_session_id in rows}


def _job_input_mode(job: ProcessingJob) -> KnowledgePointInputMode | None:
    raw = cast(dict[str, object], json.loads(job.input_json))
    value = raw.get("input_mode")
    return KnowledgePointInputMode(value) if isinstance(value, str) else None


class KnowledgePointService:
    @staticmethod
    async def read(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
        *,
        include_superseded: bool = False,
    ) -> KnowledgePointReadOut:
        record = await _get_record(session, record_id)
        items = await _visible_items(session, record_id, include_superseded=include_superseded)
        chat_sources = await _chat_source_sessions(session, record_id)
        output = [
            _knowledge_point_out(
                item,
                chat_source=(
                    KnowledgePointChatSourceOut(chat_session_id=session_id)
                    if (session_id := chat_sources.get(item.id)) is not None
                    else None
                ),
            )
            for item in items
        ]
        active = await _active_job(session, record_id)
        if active is not None:
            return KnowledgePointReadOut(
                items=output,
                action_required=KnowledgePointAction.NONE,
                active_job_id=active.id,
                input_mode=_job_input_mode(active),
            )

        course = await session.get(Course, record.course_id) if record.course_id else None
        if course is None or course.deleted_at is not None or course.status != CourseStatus.ACTIVE:
            return KnowledgePointReadOut(
                items=output,
                action_required=KnowledgePointAction.NONE,
                blocked_reason=KnowledgePointBlockedReason.COURSE_ARCHIVED,
            )
        summary = await _confirmed_summary(session, record_id)
        if summary is None:
            blocked = (
                KnowledgePointBlockedReason.SUMMARY_SUPERSEDED
                if await _superseded_summary_exists(session, record_id)
                else KnowledgePointBlockedReason.SUMMARY_NOT_CONFIRMED
            )
            return KnowledgePointReadOut(
                items=output,
                action_required=KnowledgePointAction.NONE,
                blocked_reason=blocked,
            )
        transcript = (
            await session.scalars(
                select(Transcript).where(
                    Transcript.record_id == record_id,
                    Transcript.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if transcript is None:
            return KnowledgePointReadOut(
                items=output,
                action_required=KnowledgePointAction.NONE,
                blocked_reason=KnowledgePointBlockedReason.TRANSCRIPT_NOT_READY,
            )
        draft = next(
            (
                item
                for item in items
                if item.generation_status == KnowledgePointGenerationStatus.DRAFT
            ),
            None,
        )
        if draft is not None and draft.batch_id is not None:
            if draft.generated_from_summary_id != summary.id:
                # 候选绑定的总结已被换代（转写编辑后确认了新总结），确认必被 409 拒绝，
                # 读端点直接给出换代原因，引导丢弃后基于新总结重新生成。
                return KnowledgePointReadOut(
                    items=output,
                    action_required=KnowledgePointAction.NONE,
                    blocked_reason=KnowledgePointBlockedReason.SUMMARY_SUPERSEDED,
                )
            job = await session.get(ProcessingJob, draft.batch_id)
            return KnowledgePointReadOut(
                items=output,
                action_required=KnowledgePointAction.CONFIRM,
                input_mode=_job_input_mode(job) if job is not None else None,
            )
        provider, consent_current = await _provider_state(data_dir)
        if provider is None or not provider.api_key:
            return KnowledgePointReadOut(
                items=output,
                action_required=KnowledgePointAction.NONE,
                blocked_reason=KnowledgePointBlockedReason.PROVIDER_NOT_CONFIGURED,
            )
        if not consent_current:
            return KnowledgePointReadOut(
                items=output,
                action_required=KnowledgePointAction.NONE,
                blocked_reason=KnowledgePointBlockedReason.CONSENT_REQUIRED,
            )
        failed = await _failed_job(session, record_id)
        return KnowledgePointReadOut(
            items=output,
            action_required=(
                KnowledgePointAction.RETRY if failed is not None else KnowledgePointAction.GENERATE
            ),
        )

    @staticmethod
    async def submit(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
        request_course_id: str | None = None,
    ) -> str:
        """生成入口；request_course_id（工单 05）＝请求方知识空间上下文，共享
        引用资料只读（SHARED_REF_ASSET_READ_ONLY），缺省＝原空间视角放行。"""
        provider, consent_current = await _provider_state(data_dir)
        if provider is None or not provider.api_key:
            raise CodedHTTPException(
                code="LLM_PROVIDER_UNCONFIGURED", status_code=409, detail="请先配置 LLM Provider"
            )
        if not consent_current:
            raise CodedHTTPException(
                code="AI_CONSENT_REQUIRED", status_code=409, detail="请先同意外部 AI 处理"
            )
        try:
            async with session.begin():
                record = await _get_record(session, record_id)
                await assert_asset_generation_allowed(session, record, request_course_id)
                course = await session.get(Course, record.course_id) if record.course_id else None
                if (
                    course is None
                    or course.deleted_at is not None
                    or course.status != CourseStatus.ACTIVE
                ):
                    raise CodedHTTPException(
                        code="COURSE_ARCHIVED", status_code=409, detail="归档课程不能生成知识点"
                    )
                summary = await _confirmed_summary(session, record_id)
                if summary is None:
                    raise CodedHTTPException(
                        code="SUMMARY_NOT_CONFIRMED", status_code=409, detail="请先确认当前总结"
                    )
                transcript = (
                    await session.scalars(
                        select(Transcript).where(
                            Transcript.record_id == record_id,
                            Transcript.deleted_at.is_(None),
                        )
                    )
                ).one_or_none()
                if transcript is None:
                    raise CodedHTTPException(
                        code="TRANSCRIPT_NOT_READY", status_code=409, detail="Transcript 尚未生成"
                    )
                if await _active_job(session, record_id) is not None:
                    raise CodedHTTPException(
                        code="GENERATION_IN_PROGRESS",
                        status_code=409,
                        detail="已有进行中的知识点生成任务",
                    )
                if any(
                    item.generation_status == KnowledgePointGenerationStatus.DRAFT
                    for item in await _visible_items(session, record_id)
                ):
                    raise CodedHTTPException(
                        code="CANDIDATE_PENDING_REVIEW",
                        status_code=409,
                        detail="已有待确认的知识点候选",
                    )

                input_json = _job_input_json(provider, summary, transcript)
                failed = await _failed_job(session, record_id)
                if failed is not None:
                    previous = cast(dict[str, object], json.loads(failed.input_json))
                    if previous.get("generated_from_summary_id") == summary.id:
                        _requeue_failed(failed, input_json)
                        return failed.id

                now = utcnow()
                job = _new_job(record_id, input_json=input_json, now=now)
                session.add(job)
                await session.flush()
                return job.id
        except IntegrityError:
            raise CodedHTTPException(
                code="GENERATION_IN_PROGRESS",
                status_code=409,
                detail="已有进行中的知识点生成任务",
            ) from None

    @staticmethod
    async def create(
        session: AsyncSession,
        record_id: str,
        body: KnowledgePointWriteRequest,
    ) -> KnowledgePointOut:
        async with session.begin():
            await _get_record(session, record_id)
            item = _new_item(
                record_id,
                name=body.name,
                detail=body.detail,
                tags=body.tags,
                importance=body.importance,
            )
            session.add(item)
            await session.flush()
            await SearchService.upsert_knowledge_point_index(session, item.id)
            return _knowledge_point_out(item)

    @staticmethod
    async def create_from_chat(
        session: AsyncSession,
        *,
        body: KnowledgePointWriteRequest,
        target_record_id: str,
        chat_message_id: str,
    ) -> KnowledgePointOut:
        """对话转知识点（对话转学习资产 V1）：把一条 AI 回答保存为目标记录的知识点。

        无独立事务：调用方（agent 路由编排）的事务包住会话校验与本写入，
        保证知识点、搜索索引、CHAT_MESSAGE 锚点与链接要么同生要么同灭。
        AI 辅助沉淀不代表用户已掌握，不写学习事件（AI 自述不是 Evidence 红线）。
        """
        record = await _get_record(session, target_record_id)
        if record.course_id is None:
            raise CodedHTTPException(
                code="RECORD_COURSE_MISSING",
                status_code=409,
                detail="目标记录尚未归类到课程，无法建立对话溯源",
            )
        item = _new_item(
            target_record_id,
            name=body.name,
            detail=body.detail,
            tags=body.tags,
            importance=body.importance,
        )
        session.add(item)
        await session.flush()
        await SearchService.upsert_knowledge_point_index(session, item.id)
        anchor = await SourceAnchorService.create_chat_message_anchor(
            session,
            course_id=record.course_id,
            chat_message_id=chat_message_id,
            record_id=target_record_id,
        )
        await SourceAnchorService.link_resource(
            session,
            resource_type="KNOWLEDGE_POINT",
            resource_id=item.id,
            source_anchor_id=anchor.id,
            relation_type="PRIMARY",
        )
        return _knowledge_point_out(item)

    @staticmethod
    async def update(
        session: AsyncSession,
        record_id: str,
        item_id: str,
        body: KnowledgePointWriteRequest,
    ) -> KnowledgePointOut:
        async with session.begin():
            await _get_record(session, record_id)
            item = await _editable_item(session, record_id, item_id)
            item.name = body.name
            item.detail = body.detail
            item.tags = _dump_tags(body.tags)
            item.importance = body.importance
            item.updated_at = utcnow()
            await session.flush()
            await SearchService.upsert_knowledge_point_index(session, item.id)
            return _knowledge_point_out(item)

    @staticmethod
    async def delete(session: AsyncSession, record_id: str, item_id: str) -> None:
        async with session.begin():
            await _get_record(session, record_id)
            item = await _editable_item(session, record_id, item_id)
            now = utcnow()
            item.deleted_at = now
            item.updated_at = now

    @staticmethod
    async def confirm(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
        batch_id: str,
    ) -> KnowledgePointReadOut:
        try:
            async with session.begin():
                record = await _get_record(session, record_id)
                draft_rows = await _batch_rows(
                    session, record_id, batch_id, KnowledgePointGenerationStatus.DRAFT
                )
                if not draft_rows:
                    if await _confirm_event(session, batch_id) is None:
                        raise CodedHTTPException(
                            code="KP_BATCH_NOT_FOUND", status_code=404, detail="知识点批次不存在"
                        )
                    return await KnowledgePointService.read(session, data_dir, record_id)
                summary_id = draft_rows[0].generated_from_summary_id
                summary = await session.get(AiSummary, summary_id) if summary_id else None
                course = await session.get(Course, record.course_id) if record.course_id else None
                if (
                    summary is None
                    or summary.deleted_at is not None
                    or summary.status != AiSummaryStatus.CONFIRMED
                    or course is None
                    or course.deleted_at is not None
                    or course.status != CourseStatus.ACTIVE
                ):
                    raise CodedHTTPException(
                        code="KP_BATCH_STALE",
                        status_code=409,
                        detail="总结已换代或课程已归档，请丢弃当前候选后重新生成",
                    )
                now = utcnow()
                for row in draft_rows:
                    row.generation_status = KnowledgePointGenerationStatus.ACTIVE
                    row.updated_at = now
                other_active = list(
                    (
                        await session.scalars(
                            select(KnowledgePoint).where(
                                KnowledgePoint.record_id == record_id,
                                KnowledgePoint.batch_id != batch_id,
                                KnowledgePoint.batch_id.is_not(None),
                                KnowledgePoint.generation_status
                                == KnowledgePointGenerationStatus.ACTIVE,
                                KnowledgePoint.deleted_at.is_(None),
                            )
                        )
                    ).all()
                )
                for row in other_active:
                    row.generation_status = KnowledgePointGenerationStatus.SUPERSEDED
                    row.updated_at = now
                await write_learning_event(
                    session,
                    course_id=cast(str, record.course_id),
                    record_id=record_id,
                    event_type="KNOWLEDGE_CONFIRMED",
                    source_type="KNOWLEDGE_BATCH",
                    source_id=batch_id,
                    idempotency_key=f"knowledge-confirmed:{batch_id}",
                    occurred_at=now,
                    metadata={
                        "batch_id": batch_id,
                        "confirmed_count": len(draft_rows),
                        "generated_from_summary_id": summary_id,
                    },
                )
                # 确认不改检索内容，但显式补齐索引行：候选期间缺行的旧数据确认后同样可搜。
                for row in draft_rows:
                    await SearchService.upsert_knowledge_point_index(session, row.id)
        except IntegrityError:
            # 并发确认时由幂等键唯一约束兜底：另一事务已提交，读取现状返回。
            pass
        return await KnowledgePointService.read(session, data_dir, record_id)

    @staticmethod
    async def discard(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
        batch_id: str,
    ) -> KnowledgePointReadOut:
        async with session.begin():
            await _get_record(session, record_id)
            draft_rows = await _batch_rows(
                session, record_id, batch_id, KnowledgePointGenerationStatus.DRAFT
            )
            if not draft_rows:
                if await _confirm_event(session, batch_id) is not None:
                    raise CodedHTTPException(
                        code="KP_BATCH_ALREADY_CONFIRMED",
                        status_code=409,
                        detail="批次已确认，不能丢弃",
                    )
                raise CodedHTTPException(
                    code="KP_BATCH_NOT_FOUND", status_code=404, detail="知识点批次不存在"
                )
            now = utcnow()
            for row in draft_rows:
                row.deleted_at = now
                row.updated_at = now
        return await KnowledgePointService.read(session, data_dir, record_id)


def _dump_tags(tags: list[str]) -> str:
    return json.dumps(tags, ensure_ascii=False, separators=(",", ":"))


def _new_item(
    record_id: str,
    *,
    name: str,
    detail: str,
    tags: list[str],
    importance: int,
) -> KnowledgePoint:
    return KnowledgePoint(
        id=str(uuid4()),
        record_id=record_id,
        batch_id=None,
        name=name,
        detail=detail,
        tags=_dump_tags(tags),
        importance=importance,
        generated_from_summary_id=None,
        generation_status=KnowledgePointGenerationStatus.ACTIVE,
        source_anchor_id=None,
        created_at=utcnow(),
        updated_at=utcnow(),
        deleted_at=None,
    )


async def _editable_item(
    session: AsyncSession,
    record_id: str,
    item_id: str,
) -> KnowledgePoint:
    item = (
        await session.scalars(
            select(KnowledgePoint).where(
                KnowledgePoint.id == item_id,
                KnowledgePoint.record_id == record_id,
                KnowledgePoint.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if item is None:
        raise CodedHTTPException(
            code="KNOWLEDGE_POINT_NOT_FOUND", status_code=404, detail="知识点不存在或已删除"
        )
    if item.generation_status == KnowledgePointGenerationStatus.SUPERSEDED:
        raise CodedHTTPException(
            code="KP_BATCH_STALE", status_code=409, detail="过时批次的知识点不能编辑或删除"
        )
    return item


async def _batch_rows(
    session: AsyncSession,
    record_id: str,
    batch_id: str,
    status: KnowledgePointGenerationStatus,
) -> list[KnowledgePoint]:
    return list(
        (
            await session.scalars(
                select(KnowledgePoint)
                .where(
                    KnowledgePoint.record_id == record_id,
                    KnowledgePoint.batch_id == batch_id,
                    KnowledgePoint.generation_status == status,
                    KnowledgePoint.deleted_at.is_(None),
                )
                .order_by(KnowledgePoint.created_at)
            )
        ).all()
    )


async def _confirm_event(
    session: AsyncSession,
    batch_id: str,
) -> LearningEvent | None:
    return (
        await session.scalars(
            select(LearningEvent).where(
                LearningEvent.idempotency_key == f"knowledge-confirmed:{batch_id}"
            )
        )
    ).one_or_none()


def _job_input_json(
    provider: LlmProviderConfig,
    summary: AiSummary,
    transcript: Transcript,
) -> str:
    input_mode = (
        KnowledgePointInputMode.SUMMARY_ONLY
        if len(transcript.content) > TRANSCRIPT_LIMIT
        else KnowledgePointInputMode.FULL_TRANSCRIPT
    )
    return json.dumps(
        {
            "provider_fingerprint": llm_provider_fingerprint(provider),
            "generated_from_summary_id": summary.id,
            "transcript_source_version": transcript.source_version,
            "input_mode": input_mode,
        },
        separators=(",", ":"),
    )


def _requeue_failed(job: ProcessingJob, input_json: str) -> None:
    job.input_json = input_json
    job.status = ProcessingJobStatus.PENDING
    job.progress = 0
    job.attempts = 0
    job.next_run_at = None
    job.result_json = None
    job.error_code = None
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    job.updated_at = utcnow()


def _new_job(record_id: str, *, input_json: str, now: datetime) -> ProcessingJob:
    return ProcessingJob(
        id=str(uuid4()),
        record_id=record_id,
        job_type=ProcessingJobType.KNOWLEDGE_EXTRACTION,
        status=ProcessingJobStatus.PENDING,
        progress=0,
        attempts=0,
        max_attempts=1,
        next_run_at=None,
        waiting_reason=None,
        input_json=input_json,
        result_json=None,
        error_code=None,
        error_message=None,
        started_at=None,
        finished_at=None,
        created_at=now,
        updated_at=now,
    )
