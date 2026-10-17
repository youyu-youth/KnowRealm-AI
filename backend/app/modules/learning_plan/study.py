"""计划资料学习领域能力；页面与 Agent 共用可见性及生命周期约束。"""

from typing import cast

from sqlalchemy import Select, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.course.models import Course
from app.modules.learning_plan.models import LearningGoal, LearningPlan, LearningPlanItem
from app.modules.learning_plan.service import PlanItemService, PlanService, item_out
from app.modules.learning_plan.study_schemas import (
    RecordStudyOut,
    RecordStudyStart,
    RecordStudyTabUpdate,
    StudySourceOut,
)
from app.modules.library.shared_refs import shared_alive_record_ids
from app.modules.record.models import Record
from app.modules.record.schemas import RecordContentTab
from app.modules.today.resume_models import LearningResumeEntry
from app.shared.errors import CodedHTTPException


def unavailable(code: str = "PLAN_STUDY_UNAVAILABLE") -> CodedHTTPException:
    return CodedHTTPException(
        code=code, status_code=409, detail="计划项、资料或本次访问已变化，请返回计划项刷新后重试"
    )


async def context(
    session: AsyncSession, item_id: str, *, writable: bool = False
) -> tuple[LearningPlanItem, LearningPlan, LearningGoal]:
    item = await session.get(LearningPlanItem, item_id)
    found = await PlanService.get_with_goal(session, item.plan_id) if item else None
    if item is None or found is None:
        raise CodedHTTPException(
            code="PLAN_ITEM_NOT_FOUND", status_code=404, detail="计划项不存在或课程已删除"
        )
    plan, goal = found
    if item.action_type != "STUDY_RECORD":
        raise unavailable()
    if writable:
        PlanItemService.require_active_plan(plan)
        if goal.status != "ACTIVE" or item.status == "SKIPPED":
            raise unavailable()
    return item, plan, goal


def visible_records(course_id: str) -> Select[tuple[Record]]:
    return (
        select(Record)
        .outerjoin(Course, Course.id == Record.course_id)
        .where(
            Record.deleted_at.is_(None),
            or_(Record.course_id.is_(None), Course.deleted_at.is_(None)),
            or_(Record.course_id == course_id, Record.id.in_(shared_alive_record_ids(course_id))),
        )
    )


async def source(session: AsyncSession, course_id: str, record_id: str | None) -> Record | None:
    if record_id is None:
        return None
    return await session.scalar(visible_records(course_id).where(Record.id == record_id))


async def require_source(session: AsyncSession, course_id: str, record_id: str) -> Record:
    record = await source(session, course_id, record_id)
    if record is None:
        raise unavailable("PLAN_STUDY_SOURCE_INVALID")
    return record


def source_out(record: Record, course_id: str) -> StudySourceOut:
    return StudySourceOut(
        record_id=record.id, title=record.title, read_only=record.course_id != course_id
    )


async def state(session: AsyncSession, item_id: str, *, q: str = "") -> RecordStudyOut:
    item, plan, goal = await context(session, item_id)
    linked = await source(session, goal.course_id, item.record_id)
    rows = list(
        await session.scalars(
            visible_records(goal.course_id)
            .where(Record.title.contains(q.strip(), autoescape=True))
            .order_by(Record.created_at.desc(), Record.id)
            .limit(51)
        )
    )
    tab = item.study_tab
    if linked and tab in ("quiz", "review", "todo") and linked.status != "COMPLETED":
        tab = "summary"
    return RecordStudyOut(
        item=item_out(item),
        course_id=goal.course_id,
        goal_id=goal.id,
        plan_id=plan.id,
        editable=plan.status == "ACTIVE" and goal.status == "ACTIVE" and item.status != "SKIPPED",
        source_status="AVAILABLE"
        if linked
        else ("UNAVAILABLE" if item.record_id or item.study_record_id else "MISSING"),
        source=source_out(linked, goal.course_id) if linked else None,
        sources=[source_out(record, goal.course_id) for record in rows[:50]],
        sources_truncated=len(rows) > 50,
        visit_id=item.study_visit_id,
        started_at=item.study_started_at,
        # 表 CHECK 限定枚举，旧数据默认 summary。
        tab=cast(RecordContentTab, tab),
        entry_path=f"/plan-items/{item.id}/study",
    )


async def lock_item(session: AsyncSession, item_id: str) -> None:
    # 首条语句取得 SQLite 写锁，启动、页签及关联修改不能用旧读快照覆盖彼此。
    await session.execute(
        update(LearningPlanItem)
        .where(LearningPlanItem.id == item_id)
        .values(id=LearningPlanItem.id)
    )


async def start(session: AsyncSession, item_id: str, body: RecordStudyStart) -> RecordStudyOut:
    await lock_item(session, item_id)
    item, _plan, goal = await context(session, item_id, writable=True)
    if item.record_id != str(body.record_id):
        raise unavailable("PLAN_STUDY_SOURCE_INVALID")
    await require_source(session, goal.course_id, str(body.record_id))
    if item.study_visit_id != str(body.request_id):
        if item.study_visit_id is None:
            # 仅在明确启动时借用记录已有页签；普通访问不反写本项事实。
            saved_tab = await session.scalar(
                select(LearningResumeEntry.record_tab).where(
                    LearningResumeEntry.kind == "RECORD",
                    LearningResumeEntry.target_id == item.record_id,
                )
            )
            item.study_tab = saved_tab or "summary"
        item.study_visit_id = str(body.request_id)
        item.study_record_id = item.record_id
        item.study_started_at = utcnow()
    await session.flush()
    return await state(session, item_id)


async def save_tab(
    session: AsyncSession, item_id: str, body: RecordStudyTabUpdate
) -> RecordStudyOut:
    await lock_item(session, item_id)
    item, _plan, goal = await context(session, item_id, writable=True)
    if (
        item.study_visit_id != str(body.visit_id)
        or item.study_record_id != str(body.record_id)
        or item.record_id != str(body.record_id)
    ):
        raise unavailable("PLAN_STUDY_VISIT_STALE")
    record = await require_source(session, goal.course_id, str(body.record_id))
    item.study_tab = (
        "summary"
        if body.tab in ("quiz", "review", "todo") and record.status != "COMPLETED"
        else body.tab
    )
    await session.flush()
    return await state(session, item_id)
