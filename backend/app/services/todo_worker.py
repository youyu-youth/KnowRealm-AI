import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.llm import StructuredGenerationError, TodoModel, call_todo_model
from app.models.base import utcnow
from app.models.course import Course
from app.models.document import AiSummary, ProcessingJob, TodoItem
from app.models.record import Record
from app.schemas.course import CourseStatus
from app.schemas.document import AiSummaryStatus, ProcessingJobStatus, ProcessingJobType
from app.schemas.summary import SummaryContent
from app.schemas.todo import TodoBatch, TodoGenerationStatus, TodoSource, TodoStatus
from app.services.local_config import (
    LlmProviderConfig,
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
)
from app.services.record_invalidation import RecordInvalidationNotifier

PROMPT_VERSION = "todo_v1"


@dataclass(frozen=True)
class _ClaimedTodoJob:
    job_id: str
    record_id: str
    summary_id: str
    summary: SummaryContent
    course: Course
    provider: LlmProviderConfig


def _summary_content(summary: AiSummary) -> SummaryContent:
    payload = cast(dict[str, object], json.loads(summary.summary_json))
    return SummaryContent.model_validate(
        {"topic": summary.topic, "abstract": summary.abstract, "sections": payload.get("sections")}
    )


def build_todo_prompt(claimed: _ClaimedTodoJob) -> str:
    sections = "\n".join(
        f"{section.heading}：" + "；".join(section.points) for section in claimed.summary.sections
    )
    return (
        "请根据以下课程上下文和已确认总结生成中文 Todo 建议。"
        "严格返回指定结构，不添加结构外字段。\n"
        f"学习场景：{claimed.course.learning_context}\n"
        f"教育阶段：{claimed.course.education_stage or '未设置'}\n"
        f"内容深度：{claimed.course.depth or '未设置'}\n"
        "已确认总结：\n"
        f"主题：{claimed.summary.topic}\n"
        f"摘要：{claimed.summary.abstract}\n{sections}\n"
        "生成 3 至 8 条具体、可执行且只基于总结内容的待办建议。"
    )


def _source_is_current(
    record: Record | None, course: Course | None, summary: AiSummary | None, *, record_id: str
) -> bool:
    return bool(
        record is not None
        and record.deleted_at is None
        and course is not None
        and course.deleted_at is None
        and course.status == CourseStatus.ACTIVE
        and summary is not None
        and summary.record_id == record_id
        and summary.deleted_at is None
        and summary.status == AiSummaryStatus.CONFIRMED
    )


class TodoWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        model: TodoModel,
        record_notifier: RecordInvalidationNotifier,
    ) -> None:
        self._session_factory = session_factory
        self._data_dir = data_dir
        self._model = model
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
                            ProcessingJob.job_type == ProcessingJobType.TODO_GENERATION,
                            ProcessingJob.status == ProcessingJobStatus.RUNNING,
                        )
                    )
                ).all()
            )
            for job in jobs:
                job.status = ProcessingJobStatus.FAILED
                job.error_code = "WORKER_INTERRUPTED"
                job.error_message = "Todo 生成被意外中断"
                job.finished_at = now
                job.updated_at = now
                if job.record_id:
                    record_ids.append(job.record_id)
        for record_id in record_ids:
            await self._record_notifier.notify(record_id)

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                if await self._process_one():
                    continue
            except Exception:
                logger.exception("todo_worker_unexpected_failure", error_code="INTERNAL_ERROR")
                await self.recover_interrupted()
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=0.25)
            except TimeoutError:
                pass

    async def _process_one(self) -> bool:
        claimed = await self._claim_one()
        if claimed is None:
            return False
        await self._record_notifier.notify(claimed.record_id)
        try:
            result = await call_todo_model(
                session_factory=self._session_factory,
                todo_model=self._model,
                provider=claimed.provider,
                prompt=build_todo_prompt(claimed),
                prompt_version=PROMPT_VERSION,
            )
        except StructuredGenerationError as exc:
            await self._fail(claimed, exc.code)
        except Exception:
            await self._fail(claimed, "INTERNAL_ERROR")
        else:
            await self._publish(claimed, result.content)
        return True

    async def _claim_one(self) -> _ClaimedTodoJob | None:
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
                        ProcessingJob.job_type == ProcessingJobType.TODO_GENERATION,
                        ProcessingJob.status == ProcessingJobStatus.PENDING,
                        Record.deleted_at.is_(None),
                    )
                    .order_by(ProcessingJob.created_at)
                    .limit(1)
                )
            ).one_or_none()
            if job is None or job.record_id is None:
                return None
            record = await session.get(Record, job.record_id)
            input_data = cast(dict[str, object], json.loads(job.input_json))
            summary_id = input_data.get("generated_from_summary_id")
            summary = (
                await session.get(AiSummary, summary_id) if isinstance(summary_id, str) else None
            )
            course = (
                await session.get(Course, record.course_id) if record and record.course_id else None
            )
            if not _source_is_current(
                record, course, summary, record_id=job.record_id
            ) or input_data.get("provider_fingerprint") != llm_provider_fingerprint(provider):
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
            return _ClaimedTodoJob(
                job.id,
                job.record_id,
                cast(AiSummary, summary).id,
                _summary_content(cast(AiSummary, summary)),
                cast(Course, course),
                provider,
            )

    async def _publish(self, claimed: _ClaimedTodoJob, content: TodoBatch) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, claimed.job_id)
            record = await session.get(Record, claimed.record_id)
            summary = await session.get(AiSummary, claimed.summary_id)
            course = (
                await session.get(Course, record.course_id) if record and record.course_id else None
            )
            if job is None or job.status != ProcessingJobStatus.RUNNING:
                return
            if not _source_is_current(record, course, summary, record_id=claimed.record_id):
                job.status = ProcessingJobStatus.CANCELLED
                job.result_json = json.dumps({"reason": "PREREQUISITE_CHANGED"})
                job.finished_at = now
                job.updated_at = now
                return
            max_order = await session.scalar(
                select(func.max(TodoItem.sort_order)).where(TodoItem.record_id == claimed.record_id)
            )
            start = (max_order if max_order is not None else -1) + 1
            for offset, candidate in enumerate(content.items):
                session.add(
                    TodoItem(
                        id=str(uuid4()),
                        record_id=claimed.record_id,
                        batch_id=claimed.job_id,
                        content=candidate.content,
                        status=TodoStatus.TODO,
                        source=TodoSource.AI,
                        generated_from_summary_id=claimed.summary_id,
                        generation_status=TodoGenerationStatus.DRAFT,
                        sort_order=start + offset,
                        created_at=now,
                        updated_at=now,
                        deleted_at=None,
                    )
                )
            job.status = ProcessingJobStatus.SUCCEEDED
            job.progress = 1
            job.result_json = json.dumps(
                {
                    "model": claimed.provider.model,
                    "prompt_version": PROMPT_VERSION,
                    "todo_count": len(content.items),
                },
                separators=(",", ":"),
            )
            job.error_code = None
            job.error_message = None
            job.finished_at = now
            job.updated_at = now
        await self._record_notifier.notify(claimed.record_id)

    async def _fail(self, claimed: _ClaimedTodoJob, error_code: str) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, claimed.job_id)
            if job is None or job.status != ProcessingJobStatus.RUNNING:
                return
            job.status = ProcessingJobStatus.FAILED
            job.error_code = error_code
            job.error_message = "Todo 生成失败，请重试"
            job.finished_at = now
            job.updated_at = now
        await self._record_notifier.notify(claimed.record_id)
