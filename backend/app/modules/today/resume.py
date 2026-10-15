from typing import cast
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.agent.session_service import ChatSessionService
from app.modules.course.models import Course
from app.modules.quiz.models import QuizTest, QuizTestItem
from app.modules.record.service import RecordService
from app.modules.today.resume_models import LearningResumeEntry
from app.modules.today.resume_schemas import (
    LearningResumeOut,
    LearningResumeUpdate,
    RecordResumeTab,
    ResumeKind,
)
from app.shared.errors import CodedHTTPException

RESUME_HISTORY_LIMIT = 30


class LearningResumeService:
    @staticmethod
    async def resolve(
        session: AsyncSession, entry: LearningResumeEntry
    ) -> LearningResumeOut | None:
        kind = ResumeKind(entry.kind)
        course_id: str | None = None
        tab: RecordResumeTab | None = None
        answered: int | None = None
        total: int | None = None
        if kind == ResumeKind.RECORD:
            record = await RecordService.get(session, entry.target_id)
            if record is None:
                return None
            title, course_id = record.title, record.course_id
            # 旧 Tab 在当前记录状态不可用时，恢复到始终可达的总结页。
            stored_tab = entry.record_tab or "summary"
            if stored_tab in ("quiz", "review", "todo") and record.status != "COMPLETED":
                stored_tab = "summary"
            # 写入口 Schema 与表 CHECK 共同限定 Tab；ORM 字符串在此收窄。
            tab = cast(RecordResumeTab, stored_tab)
            href = f"/records/{record.id}"
            if tab != "summary":
                href += f"?tab={tab}"
        elif kind == ResumeKind.QUIZ_TEST:
            test = await session.get(QuizTest, entry.target_id)
            if test is None or test.deleted_at is not None or test.status != "IN_PROGRESS":
                return None
            course = await session.get(Course, test.course_id)
            if course is None or course.deleted_at is not None or course.status != "ACTIVE":
                return None
            course_id, title = course.id, None
            counts = (
                await session.execute(
                    select(func.count(QuizTestItem.id), func.count(QuizTestItem.answered_at)).where(
                        QuizTestItem.test_id == test.id, QuizTestItem.deleted_at.is_(None)
                    )
                )
            ).one()
            total, answered = int(counts[0]), int(counts[1])
            href = f"/spaces/{course.id}/tests/{test.id}"
        else:
            chat = await ChatSessionService.get_out(session, entry.target_id)
            if (
                chat is None
                or chat.record_deleted
                or chat.course_deleted
                or chat.library_item_deleted
            ):
                return None
            title, course_id = chat.title, chat.course_id
            href = f"/chat/{chat.id}"
        course = await session.get(Course, course_id) if course_id else None
        return LearningResumeOut(
            kind=kind,
            target_id=entry.target_id,
            title=title,
            course_id=course_id,
            course_name=course.name if course and course.deleted_at is None else None,
            record_tab=tab,
            visited_at=entry.updated_at,
            answered_count=answered,
            total_count=total,
            href=href,
        )

    @staticmethod
    async def list_recent(
        session: AsyncSession, *, exclude_session_id: str | None = None
    ) -> list[LearningResumeOut]:
        entries = await session.scalars(
            select(LearningResumeEntry).order_by(
                LearningResumeEntry.updated_at.desc(), LearningResumeEntry.id.desc()
            )
        )
        result: list[LearningResumeOut] = []
        for entry in entries:
            if entry.kind == ResumeKind.CHAT_SESSION and entry.target_id == exclude_session_id:
                continue
            resolved = await LearningResumeService.resolve(session, entry)
            if resolved is not None:
                result.append(resolved)
        return result

    @staticmethod
    async def visit(session: AsyncSession, body: LearningResumeUpdate) -> None:
        async with session.begin():
            now = utcnow()
            candidate = LearningResumeEntry(
                kind=body.kind,
                target_id=str(body.target_id),
                record_tab=body.record_tab,
                updated_at=now,
            )
            if await LearningResumeService.resolve(session, candidate) is None:
                codes = {
                    ResumeKind.RECORD: "RECORD_NOT_FOUND",
                    ResumeKind.QUIZ_TEST: "QUIZ_TEST_NOT_IN_PROGRESS",
                    ResumeKind.CHAT_SESSION: "CHAT_SESSION_NOT_FOUND",
                }
                raise CodedHTTPException(
                    code=codes[body.kind],
                    status_code=409 if body.kind == ResumeKind.QUIZ_TEST else 404,
                    detail="目标当前不可继续学习",
                )
            await session.execute(
                insert(LearningResumeEntry)
                .values(
                    id=str(uuid4()),
                    kind=body.kind,
                    target_id=str(body.target_id),
                    record_tab=body.record_tab,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=["kind", "target_id"],
                    set_={"record_tab": body.record_tab, "updated_at": now},
                )
            )
            retained = (
                select(LearningResumeEntry.id)
                .order_by(LearningResumeEntry.updated_at.desc(), LearningResumeEntry.id.desc())
                .limit(RESUME_HISTORY_LIMIT)
            )
            await session.execute(
                delete(LearningResumeEntry).where(LearningResumeEntry.id.not_in(retained))
            )

    @staticmethod
    async def remove(
        session: AsyncSession, *, kind: ResumeKind | None = None, target_id: str | None = None
    ) -> None:
        async with session.begin():
            statement = delete(LearningResumeEntry)
            if kind is not None:
                statement = statement.where(
                    LearningResumeEntry.kind == kind, LearningResumeEntry.target_id == target_id
                )
            await session.execute(statement)
