import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.llm import (
    SummaryCallResult,
    SummaryGenerationError,
    SummaryModel,
    call_summary_model,
)
from app.agents.summary import SummaryRuntime, SummaryState
from app.models.base import utcnow
from app.models.course import Course
from app.models.document import AiSummary, ProcessingJob, Transcript
from app.models.record import Record
from app.schemas.document import AiSummaryStatus, ProcessingJobStatus, ProcessingJobType
from app.schemas.record import RecordStatus
from app.schemas.summary import SummaryContent
from app.services.local_config import (
    LlmProviderConfig,
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
)
from app.services.record_invalidation import RecordInvalidationNotifier

PROMPT_VERSION = "summary-v1"


@dataclass(frozen=True)
class _ClaimedSummary:
    job_id: str
    record_id: str
    source_version: int
    transcript: str
    course: Course
    provider: LlmProviderConfig


def build_summary_prompt(
    *,
    transcript: str,
    learning_context: str,
    education_stage: str | None,
    depth: str | None,
) -> str:
    return (
        "请根据以下 Transcript 生成中文学习总结。严格返回指定结构，不添加结构外字段。\n"
        f"学习场景：{learning_context}\n"
        f"教育阶段：{education_stage or '未设置'}\n"
        f"内容深度：{depth or '未设置'}\n"
        "Transcript：\n"
        f"{transcript}"
    )


class SummaryWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        graph: CompiledStateGraph[SummaryState, SummaryRuntime, SummaryState, SummaryState],
        summary_model: SummaryModel,
        record_notifier: RecordInvalidationNotifier,
    ) -> None:
        self._session_factory = session_factory
        self._data_dir = data_dir
        self._graph = graph
        self._summary_model = summary_model
        self._record_notifier = record_notifier
        self._stopped = asyncio.Event()

    def stop(self) -> None:
        self._stopped.set()

    async def recover_interrupted(self) -> None:
        now = utcnow()
        record_ids: list[str] = []
        async with self._session_factory() as session, session.begin():
            jobs = list(
                (
                    await session.scalars(
                        select(ProcessingJob).where(
                            ProcessingJob.job_type == ProcessingJobType.SUMMARY,
                            ProcessingJob.status == ProcessingJobStatus.RUNNING,
                        )
                    )
                ).all()
            )
            for job in jobs:
                job.status = ProcessingJobStatus.FAILED
                job.error_code = "WORKER_INTERRUPTED"
                job.error_message = "总结生成被意外中断"
                job.finished_at = now
                job.updated_at = now
                if job.record_id is not None:
                    record_ids.append(job.record_id)
                    record = await session.get(Record, job.record_id)
                    if record is not None and record.deleted_at is None:
                        record.status = RecordStatus.FAILED
                        record.updated_at = now
        for record_id in record_ids:
            await self._record_notifier.notify(record_id)

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                if await self._process_one():
                    continue
            except Exception:
                logger.error(
                    "summary_worker_unexpected_failure",
                    error_code="INTERNAL_ERROR",
                )
                await self.recover_interrupted()
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=0.25)
            except TimeoutError:
                pass

    async def _process_one(self) -> bool:
        claimed = await self._claim_one()
        if claimed is None:
            return False
        provider = claimed.provider
        await self._record_notifier.notify(claimed.record_id)
        call_result: SummaryCallResult | None = None

        async def generate() -> SummaryContent:
            nonlocal call_result
            call_result = await call_summary_model(
                session_factory=self._session_factory,
                summary_model=self._summary_model,
                provider=provider,
                prompt=build_summary_prompt(
                    transcript=claimed.transcript,
                    learning_context=claimed.course.learning_context,
                    education_stage=claimed.course.education_stage,
                    depth=claimed.course.depth,
                ),
                graph_name="summary",
                graph_node="generate",
                prompt_version=PROMPT_VERSION,
            )
            return call_result.content

        try:
            result = cast(
                SummaryState,
                await self._graph.ainvoke(  # pyright: ignore[reportUnknownMemberType]
                    {
                        "record_id": claimed.record_id,
                        "source_version": claimed.source_version,
                    },
                    {
                        "configurable": {
                            "thread_id": (
                                f"summary-{claimed.record_id}-source-{claimed.source_version}"
                            )
                        }
                    },
                    context=SummaryRuntime(generate=generate),
                ),
            )
            summary = SummaryContent.model_validate(result.get("summary"))
            if call_result is None:
                raise SummaryGenerationError("INTERNAL_ERROR")
        except SummaryGenerationError as exc:
            await self._fail(claimed.job_id, claimed.record_id, exc.code)
        except Exception:
            await self._fail(claimed.job_id, claimed.record_id, "INTERNAL_ERROR")
        else:
            await self._publish(
                claimed.job_id,
                claimed.record_id,
                claimed.source_version,
                provider.model,
                summary,
                call_result,
            )
        return True

    async def _claim_one(self) -> _ClaimedSummary | None:
        provider = await asyncio.to_thread(load_llm_provider, self._data_dir)
        consent_at, consent_current = await asyncio.to_thread(llm_consent, self._data_dir)
        if provider is None or not provider.api_key or not consent_current or consent_at is None:
            return None
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = (
                await session.scalars(
                    select(ProcessingJob)
                    .join(Record, ProcessingJob.record_id == Record.id)
                    .where(
                        ProcessingJob.job_type == ProcessingJobType.SUMMARY,
                        ProcessingJob.status == ProcessingJobStatus.PENDING,
                        Record.status == RecordStatus.SUMMARY_PENDING,
                        Record.deleted_at.is_(None),
                    )
                    .order_by(ProcessingJob.created_at)
                    .limit(1)
                )
            ).one_or_none()
            if job is None or job.record_id is None:
                return None
            record = await session.get(Record, job.record_id)
            transcript = (
                await session.scalars(
                    select(Transcript).where(
                        Transcript.record_id == job.record_id,
                        Transcript.deleted_at.is_(None),
                    )
                )
            ).one_or_none()
            course = (
                await session.get(Course, record.course_id) if record and record.course_id else None
            )
            input_data = cast(dict[str, object], json.loads(job.input_json))
            source_version = input_data.get("transcript_source_version")
            expected_fingerprint = input_data.get("provider_fingerprint")
            if (
                record is None
                or transcript is None
                or course is None
                or course.deleted_at is not None
                or course.status != "ACTIVE"
                or not isinstance(source_version, int)
                or transcript.source_version != source_version
                or expected_fingerprint != llm_provider_fingerprint(provider)
            ):
                job.status = ProcessingJobStatus.CANCELLED
                job.result_json = json.dumps({"reason": "PREREQUISITE_CHANGED"})
                job.finished_at = now
                job.updated_at = now
                return None
            claimed = cast(
                CursorResult[tuple[()]],
                await session.execute(
                    update(ProcessingJob)
                    .where(
                        ProcessingJob.id == job.id,
                        ProcessingJob.status == ProcessingJobStatus.PENDING,
                    )
                    .values(
                        status=ProcessingJobStatus.RUNNING,
                        attempts=ProcessingJob.attempts + 1,
                        started_at=now,
                        updated_at=now,
                    )
                ),
            )
            if claimed.rowcount != 1:
                return None
            record.status = RecordStatus.SUMMARY_PROCESSING
            record.updated_at = now
            return _ClaimedSummary(
                job_id=job.id,
                record_id=job.record_id,
                source_version=source_version,
                transcript=transcript.content,
                course=course,
                provider=provider,
            )

    async def _publish(
        self,
        job_id: str,
        record_id: str,
        source_version: int,
        model: str,
        summary: SummaryContent,
        call_result: SummaryCallResult,
    ) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, job_id)
            record = await session.get(Record, record_id)
            transcript = (
                await session.scalars(
                    select(Transcript).where(
                        Transcript.record_id == record_id,
                        Transcript.deleted_at.is_(None),
                    )
                )
            ).one_or_none()
            course = (
                await session.get(Course, record.course_id) if record and record.course_id else None
            )
            if job is None or job.status != ProcessingJobStatus.RUNNING:
                return
            if (
                record is None
                or record.deleted_at is not None
                or transcript is None
                or transcript.source_version != source_version
                or course is None
                or course.deleted_at is not None
                or course.status != "ACTIVE"
            ):
                job.status = ProcessingJobStatus.CANCELLED
                job.result_json = json.dumps({"reason": "STALE_TRANSCRIPT"})
                job.finished_at = now
                job.updated_at = now
                if record is not None and record.deleted_at is None:
                    record.status = RecordStatus.SUMMARY_PENDING
                    record.updated_at = now
                return
            latest_version = await session.scalar(
                select(func.coalesce(func.max(AiSummary.version_no), 0)).where(
                    AiSummary.record_id == record_id
                )
            )
            version_no = cast(int, latest_version) + 1
            summary_id = str(uuid4())
            session.add(
                AiSummary(
                    id=summary_id,
                    record_id=record_id,
                    version_no=version_no,
                    transcript_source_version=source_version,
                    topic=summary.topic,
                    abstract=summary.abstract,
                    summary_json=json.dumps(
                        {"sections": [section.model_dump() for section in summary.sections]},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    status=AiSummaryStatus.GENERATED,
                    model=model,
                    prompt_version=PROMPT_VERSION,
                    token_usage_json=json.dumps(
                        call_result.token_usage,
                        separators=(",", ":"),
                    ),
                    latency_ms=call_result.latency_ms,
                    user_feedback=None,
                    confirmed_at=None,
                    created_at=now,
                    updated_at=now,
                    deleted_at=None,
                )
            )
            job.status = ProcessingJobStatus.SUCCEEDED
            job.progress = 1
            job.result_json = json.dumps({"summary_id": summary_id})
            job.error_code = None
            job.error_message = None
            job.finished_at = now
            job.updated_at = now
            record.status = RecordStatus.SUMMARY_READY
            record.updated_at = now
        await self._record_notifier.notify(record_id)

    async def _fail(self, job_id: str, record_id: str, error_code: str) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, job_id)
            record = await session.get(Record, record_id)
            if job is None or record is None or job.status != ProcessingJobStatus.RUNNING:
                return
            job.status = ProcessingJobStatus.FAILED
            job.error_code = error_code
            job.error_message = "总结生成失败，请检查 Provider 后重试"
            job.finished_at = now
            job.updated_at = now
            record.status = RecordStatus.FAILED
            record.updated_at = now
        await self._record_notifier.notify(record_id)
