import asyncio
import json
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models.course import Course
from app.models.document import AiSummary, ProcessingJob, TodoItem
from app.models.record import Record
from app.schemas.course import CourseStatus
from app.schemas.document import AiSummaryStatus, ProcessingJobStatus, ProcessingJobType
from app.schemas.todo import (
    TodoAction,
    TodoBlockedReason,
    TodoGenerationStatus,
    TodoOut,
    TodoReadOut,
    TodoSource,
    TodoStatus,
    TodoToggleRequest,
    TodoWriteRequest,
)
from app.services.local_config import (
    LlmProviderConfig,
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
)


def _todo_out(item: TodoItem) -> TodoOut:
    return TodoOut(
        id=item.id,
        record_id=item.record_id,
        batch_id=item.batch_id,
        content=item.content,
        status=TodoStatus(item.status),
        source=TodoSource(item.source),
        generated_from_summary_id=item.generated_from_summary_id,
        generation_status=(
            TodoGenerationStatus(item.generation_status)
            if item.generation_status is not None
            else None
        ),
        sort_order=item.sort_order,
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
        raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
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
        (
            await session.scalars(
                select(AiSummary.id)
                .where(
                    AiSummary.record_id == record_id,
                    AiSummary.status == AiSummaryStatus.SUPERSEDED,
                    AiSummary.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).first()
    ) is not None


async def _active_job(session: AsyncSession, record_id: str) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.record_id == record_id,
                ProcessingJob.job_type == ProcessingJobType.TODO_GENERATION,
                ProcessingJob.status.in_(
                    (ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING)
                ),
            )
            .order_by(ProcessingJob.created_at.desc())
            .limit(1)
        )
    ).one_or_none()


async def _failed_job(
    session: AsyncSession, record_id: str, summary_id: str
) -> ProcessingJob | None:
    jobs = (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.record_id == record_id,
                ProcessingJob.job_type == ProcessingJobType.TODO_GENERATION,
                ProcessingJob.status == ProcessingJobStatus.FAILED,
            )
            .order_by(ProcessingJob.created_at.desc())
        )
    ).all()
    return next(
        (
            job
            for job in jobs
            if json.loads(job.input_json).get("generated_from_summary_id") == summary_id
        ),
        None,
    )


async def _visible_items(
    session: AsyncSession,
    record_id: str,
    *,
    include_superseded: bool = False,
) -> list[TodoItem]:
    # 手工项与被接管项的 generation_status 为 NULL，始终可见；AI 批次行按状态过滤。
    statuses: tuple[TodoGenerationStatus, ...] = (
        (
            TodoGenerationStatus.DRAFT,
            TodoGenerationStatus.ACTIVE,
            TodoGenerationStatus.SUPERSEDED,
        )
        if include_superseded
        else (TodoGenerationStatus.DRAFT, TodoGenerationStatus.ACTIVE)
    )
    return list(
        (
            await session.scalars(
                select(TodoItem)
                .where(
                    TodoItem.record_id == record_id,
                    TodoItem.deleted_at.is_(None),
                    or_(
                        TodoItem.generation_status.is_(None),
                        TodoItem.generation_status.in_(statuses),
                    ),
                )
                .order_by(TodoItem.sort_order)
            )
        ).all()
    )


async def _editable_item(session: AsyncSession, record_id: str, todo_id: str) -> TodoItem:
    item = (
        await session.scalars(
            select(TodoItem).where(
                TodoItem.id == todo_id,
                TodoItem.record_id == record_id,
                TodoItem.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="待办不存在或已删除")
    return item


class TodoService:
    @staticmethod
    async def read(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
        *,
        include_superseded: bool = False,
    ) -> TodoReadOut:
        record = await _get_record(session, record_id)
        items = await _visible_items(session, record_id, include_superseded=include_superseded)
        output = [_todo_out(item) for item in items]
        active = await _active_job(session, record_id)
        if active is not None:
            return TodoReadOut(
                items=output,
                action_required=TodoAction.NONE,
                active_job_id=active.id,
            )

        course = await session.get(Course, record.course_id) if record.course_id else None
        if course is None or course.deleted_at is not None or course.status != CourseStatus.ACTIVE:
            return TodoReadOut(
                items=output,
                action_required=TodoAction.NONE,
                blocked_reason=TodoBlockedReason.COURSE_ARCHIVED,
            )
        summary = await _confirmed_summary(session, record_id)
        if summary is None:
            blocked = (
                TodoBlockedReason.SUMMARY_SUPERSEDED
                if await _superseded_summary_exists(session, record_id)
                else TodoBlockedReason.SUMMARY_NOT_CONFIRMED
            )
            return TodoReadOut(
                items=output,
                action_required=TodoAction.NONE,
                blocked_reason=blocked,
            )
        draft = next(
            (item for item in items if item.generation_status == TodoGenerationStatus.DRAFT),
            None,
        )
        if draft is not None and draft.batch_id is not None:
            if draft.generated_from_summary_id != summary.id:
                return TodoReadOut(
                    items=output,
                    action_required=TodoAction.NONE,
                    blocked_reason=TodoBlockedReason.SUMMARY_SUPERSEDED,
                )
            return TodoReadOut(items=output, action_required=TodoAction.ADOPT)
        provider, consent_current = await _provider_state(data_dir)
        if provider is None or not provider.api_key:
            return TodoReadOut(
                items=output,
                action_required=TodoAction.NONE,
                blocked_reason=TodoBlockedReason.PROVIDER_NOT_CONFIGURED,
            )
        if not consent_current:
            return TodoReadOut(
                items=output,
                action_required=TodoAction.NONE,
                blocked_reason=TodoBlockedReason.CONSENT_REQUIRED,
            )
        failed = await _failed_job(session, record_id, summary.id)
        return TodoReadOut(
            items=output,
            action_required=TodoAction.RETRY if failed is not None else TodoAction.GENERATE,
        )

    @staticmethod
    async def submit(session: AsyncSession, data_dir: Path, record_id: str) -> str:
        provider, consent_current = await _provider_state(data_dir)
        if provider is None or not provider.api_key:
            raise HTTPException(status_code=409, detail="请先配置 LLM Provider")
        if not consent_current:
            raise HTTPException(status_code=409, detail="请先同意外部 AI 处理")
        try:
            async with session.begin():
                record = await _get_record(session, record_id)
                course = await session.get(Course, record.course_id) if record.course_id else None
                if (
                    course is None
                    or course.deleted_at is not None
                    or course.status != CourseStatus.ACTIVE
                ):
                    raise HTTPException(status_code=409, detail="归档课程不能生成 Todo")
                summary = await _confirmed_summary(session, record_id)
                if summary is None:
                    raise HTTPException(status_code=409, detail="请先确认当前总结")
                if await _active_job(session, record_id) is not None:
                    raise HTTPException(status_code=409, detail="已有进行中的 Todo 生成任务")
                if any(
                    item.generation_status == TodoGenerationStatus.DRAFT
                    for item in await _visible_items(session, record_id)
                ):
                    raise HTTPException(status_code=409, detail="已有待审阅的 Todo 候选")
                input_json = json.dumps(
                    {
                        "provider_fingerprint": llm_provider_fingerprint(provider),
                        "generated_from_summary_id": summary.id,
                    },
                    separators=(",", ":"),
                )
                failed = await _failed_job(session, record_id, summary.id)
                if failed is not None:
                    _requeue_failed(failed, input_json)
                    return failed.id
                now = utcnow()
                job = ProcessingJob(
                    id=str(uuid4()),
                    record_id=record_id,
                    job_type=ProcessingJobType.TODO_GENERATION,
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
                session.add(job)
                await session.flush()
                return job.id
        except IntegrityError:
            raise HTTPException(status_code=409, detail="已有进行中的 Todo 生成任务") from None

    @staticmethod
    async def create(session: AsyncSession, record_id: str, body: TodoWriteRequest) -> TodoOut:
        async with session.begin():
            await _get_record(session, record_id)
            # 追加尾部：取该记录全部行（含软删）的最大 sort_order + 1，保证递增无重号。
            max_order = await session.scalar(
                select(func.max(TodoItem.sort_order)).where(TodoItem.record_id == record_id)
            )
            now = utcnow()
            item = TodoItem(
                id=str(uuid4()),
                record_id=record_id,
                batch_id=None,
                content=body.content,
                status=TodoStatus.TODO,
                source=TodoSource.MANUAL,
                generated_from_summary_id=None,
                generation_status=None,
                sort_order=(max_order if max_order is not None else -1) + 1,
                created_at=now,
                updated_at=now,
                deleted_at=None,
            )
            session.add(item)
            await session.flush()
            return _todo_out(item)

    @staticmethod
    async def update(
        session: AsyncSession,
        record_id: str,
        todo_id: str,
        body: TodoWriteRequest,
    ) -> TodoOut:
        async with session.begin():
            await _get_record(session, record_id)
            item = await _editable_item(session, record_id, todo_id)
            item.content = body.content
            if (
                item.generation_status == TodoGenerationStatus.ACTIVE
                and item.source == TodoSource.AI
            ):
                item.generation_status = None
            item.updated_at = utcnow()
            await session.flush()
            return _todo_out(item)

    @staticmethod
    async def delete(session: AsyncSession, record_id: str, todo_id: str) -> None:
        async with session.begin():
            await _get_record(session, record_id)
            item = await _editable_item(session, record_id, todo_id)
            now = utcnow()
            item.deleted_at = now
            item.updated_at = now

    @staticmethod
    async def toggle(
        session: AsyncSession,
        record_id: str,
        todo_id: str,
        body: TodoToggleRequest,
    ) -> TodoOut:
        async with session.begin():
            await _get_record(session, record_id)
            item = await _editable_item(session, record_id, todo_id)
            if item.generation_status == TodoGenerationStatus.DRAFT:
                raise HTTPException(status_code=409, detail="候选待办不能勾选完成")
            # 重复置同态直接返回现状（幂等）；状态变化才写 updated_at。
            if TodoStatus(item.status) != body.status:
                item.status = body.status
                if (
                    item.generation_status == TodoGenerationStatus.ACTIVE
                    and item.source == TodoSource.AI
                ):
                    item.generation_status = None
                item.updated_at = utcnow()
                await session.flush()
            return _todo_out(item)

    @staticmethod
    async def discard(
        session: AsyncSession, data_dir: Path, record_id: str, batch_id: str
    ) -> TodoReadOut:
        async with session.begin():
            await _get_record(session, record_id)
            rows = await _batch_rows(session, record_id, batch_id, TodoGenerationStatus.DRAFT)
            if not rows:
                if await _batch_rows(session, record_id, batch_id, TodoGenerationStatus.ACTIVE):
                    raise HTTPException(status_code=409, detail="批次已采纳，不能丢弃")
                raise HTTPException(status_code=404, detail="Todo 批次不存在")
            now = utcnow()
            for row in rows:
                row.deleted_at = now
                row.updated_at = now
        return await TodoService.read(session, data_dir, record_id)

    @staticmethod
    async def adopt(
        session: AsyncSession, data_dir: Path, record_id: str, batch_id: str
    ) -> TodoReadOut:
        async with session.begin():
            record = await _get_record(session, record_id)
            rows = await _batch_rows(session, record_id, batch_id, TodoGenerationStatus.DRAFT)
            if not rows:
                if await _batch_rows(session, record_id, batch_id, TodoGenerationStatus.ACTIVE):
                    return await TodoService.read(session, data_dir, record_id)
                if await _batch_rows(session, record_id, batch_id, TodoGenerationStatus.SUPERSEDED):
                    raise HTTPException(status_code=409, detail="Todo 批次已被新批次替代")
                raise HTTPException(status_code=404, detail="Todo 批次不存在")
            summary = await session.get(AiSummary, rows[0].generated_from_summary_id)
            if (
                summary is None
                or summary.deleted_at is not None
                or summary.status != AiSummaryStatus.CONFIRMED
            ):
                raise TodoAdoptionBlocked(
                    TodoBlockedReason.SUMMARY_SUPERSEDED,
                    "总结已换代，请丢弃当前候选后重新生成",
                )
            course = await session.get(Course, record.course_id) if record.course_id else None
            if (
                course is None
                or course.deleted_at is not None
                or course.status != CourseStatus.ACTIVE
            ):
                raise TodoAdoptionBlocked(
                    TodoBlockedReason.COURSE_ARCHIVED, "课程已归档，不能采纳 Todo 候选"
                )
            now = utcnow()
            await session.execute(
                update(TodoItem)
                .where(
                    TodoItem.record_id == record_id,
                    TodoItem.batch_id != batch_id,
                    TodoItem.generation_status == TodoGenerationStatus.ACTIVE,
                    TodoItem.deleted_at.is_(None),
                )
                .values(generation_status=TodoGenerationStatus.SUPERSEDED, updated_at=now)
            )
            await session.execute(
                update(TodoItem)
                .where(
                    TodoItem.record_id == record_id,
                    TodoItem.batch_id == batch_id,
                    TodoItem.generation_status == TodoGenerationStatus.DRAFT,
                    TodoItem.deleted_at.is_(None),
                )
                .values(generation_status=TodoGenerationStatus.ACTIVE, updated_at=now)
            )
        return await TodoService.read(session, data_dir, record_id)


class TodoAdoptionBlocked(Exception):
    def __init__(self, blocked_reason: TodoBlockedReason, detail: str) -> None:
        super().__init__(detail)
        self.blocked_reason = blocked_reason
        self.detail = detail


async def _batch_rows(
    session: AsyncSession,
    record_id: str,
    batch_id: str,
    status: TodoGenerationStatus,
) -> list[TodoItem]:
    return list(
        (
            await session.scalars(
                select(TodoItem)
                .where(
                    TodoItem.record_id == record_id,
                    TodoItem.batch_id == batch_id,
                    TodoItem.generation_status == status,
                    TodoItem.deleted_at.is_(None),
                )
                .order_by(TodoItem.sort_order)
            )
        ).all()
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
