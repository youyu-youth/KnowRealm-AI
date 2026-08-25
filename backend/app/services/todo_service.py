import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
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
from app.services.local_config import LlmProviderConfig, llm_consent, load_llm_provider


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
        return TodoReadOut(items=output, action_required=TodoAction.NONE)

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
            # 重复置同态直接返回现状（幂等）；状态变化才写 updated_at。
            if TodoStatus(item.status) != body.status:
                item.status = body.status
                item.updated_at = utcnow()
                await session.flush()
            return _todo_out(item)
