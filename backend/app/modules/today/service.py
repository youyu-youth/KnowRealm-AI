from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, cast

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.base import utcnow
from app.modules.agent.models import ChatMessage, ChatSession
from app.modules.agent.schemas import ChatRole
from app.modules.course.models import Course
from app.modules.learning_plan.models import (
    LearningGoal,
    LearningPlan,
    LearningPlanItem,
)
from app.modules.learning_plan.scheduling import local_today
from app.modules.learning_plan.schemas import (
    GoalStatus,
    PlanItemStatus,
    PlanItemType,
    PlanStatus,
)
from app.modules.quiz.models import Quiz
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus
from app.modules.summary.models import AiSummary
from app.modules.today.schemas import (
    TodayCompletedItemOut,
    TodayPlanItemOut,
    TodayProgressCourseOut,
    TodayProgressOut,
    TodayStatsOut,
    TodaySummaryTodoOut,
    TodayTrendPointOut,
)


def local_day_bounds(day: date) -> tuple[datetime, datetime]:
    # 分别转换本地零点，保留夏令时切换日的 23/25 小时边界。
    return (
        datetime.combine(day, time.min).astimezone(UTC),
        datetime.combine(day + timedelta(days=1), time.min).astimezone(UTC),
    )


def _due_plan_conditions(day: date) -> tuple[ColumnElement[bool], ...]:
    return (
        LearningPlanItem.status == PlanItemStatus.PENDING,
        LearningPlanItem.scheduled_date <= day.isoformat(),
        LearningPlan.status == PlanStatus.ACTIVE,
        LearningGoal.status == GoalStatus.ACTIVE,
    )


def _plan_item_out(
    item: LearningPlanItem, plan: LearningPlan, goal: LearningGoal, course_name: str
) -> TodayPlanItemOut:
    return TodayPlanItemOut(
        item_id=item.id,
        plan_id=plan.id,
        course_id=goal.course_id,
        course_name=course_name,
        goal_id=goal.id,
        goal_title=goal.title,
        action_type=PlanItemType(item.action_type),
        content=item.content,
        estimated_minutes=item.estimated_minutes,
        scheduled_date=date.fromisoformat(item.scheduled_date),
        user_locked=item.user_locked,
    )


class TodayService:
    @staticmethod
    async def list_pending_summaries(
        session: AsyncSession,
    ) -> list[TodaySummaryTodoOut]:
        rows = (
            await session.execute(
                select(Record, Course.name)
                .join(Course, Record.course_id == Course.id)
                .where(
                    Record.status == RecordStatus.SUMMARY_READY,
                    Record.deleted_at.is_(None),
                    Course.deleted_at.is_(None),
                )
                .order_by(Record.updated_at.desc())
            )
        ).all()
        return [
            TodaySummaryTodoOut(
                record_id=record.id,
                title=record.title,
                course_id=cast(str, record.course_id),
                course_name=course_name,
                ready_at=record.updated_at,
            )
            for record, course_name in rows
        ]

    @staticmethod
    async def list_due_plan_items(
        session: AsyncSession,
    ) -> list[TodayPlanItemOut]:
        """今日待学的计划项（跨空间，spec 用户故事 18）：排期日 ≤ 今天且
        PENDING 的项，仅统计 ACTIVE 目标名下 ACTIVE 计划版本（历史版本与其
        项是只读进度、不再催办）；SKIPPED 是用户主动放弃、不算待学。课程软删
        随空间不可见（查询期过滤，与目标/计划查询同口径）。排序 = 排期日、
        空间名、项序（逾期在前，同日内同空间项聚在一起）。
        """
        rows = (
            await session.execute(
                select(LearningPlanItem, LearningPlan, LearningGoal, Course.name)
                .join(LearningPlan, LearningPlan.id == LearningPlanItem.plan_id)
                .join(LearningGoal, LearningGoal.id == LearningPlan.goal_id)
                .join(Course, Course.id == LearningGoal.course_id)
                .where(
                    *_due_plan_conditions(local_today()),
                    Course.deleted_at.is_(None),
                )
                .order_by(
                    LearningPlanItem.scheduled_date,
                    Course.name,
                    LearningPlanItem.priority,
                )
            )
        ).all()
        return [
            _plan_item_out(item, plan, goal, course_name) for item, plan, goal, course_name in rows
        ]

    @staticmethod
    async def progress(
        session: AsyncSession,
        *,
        course_id: str | None = None,
        order: Literal["date", "duration"] = "date",
        offset: int = 0,
        limit: int = 20,
    ) -> TodayProgressOut:
        day = local_today()
        start, end = local_day_bounds(day)
        # 单条 SELECT 固定 SQLite 读取快照，汇总/课程并集/分页不会跨事务漂移。
        rows = (
            await session.execute(
                select(LearningPlanItem, LearningPlan, LearningGoal, Course.name)
                .join(LearningPlan, LearningPlan.id == LearningPlanItem.plan_id)
                .join(LearningGoal, LearningGoal.id == LearningPlan.goal_id)
                .join(Course, Course.id == LearningGoal.course_id)
                .where(
                    Course.deleted_at.is_(None),
                    or_(
                        and_(*_due_plan_conditions(day)),
                        and_(
                            LearningPlanItem.status == PlanItemStatus.DONE,
                            LearningPlanItem.completed_at >= start,
                            LearningPlanItem.completed_at < end,
                        ),
                    ),
                )
            )
        ).all()
        courses = {goal.course_id: name for _item, _plan, goal, name in rows}
        pending: list[LearningPlanItem] = []
        completed: list[TodayCompletedItemOut] = []
        for item, plan, goal, name in rows:
            if course_id is not None and goal.course_id != course_id:
                continue
            if item.status == PlanItemStatus.PENDING:
                pending.append(item)
            else:
                assert item.completed_at is not None  # 查询日界限已排除 NULL
                completed.append(
                    TodayCompletedItemOut(
                        **_plan_item_out(item, plan, goal, name).model_dump(),
                        plan_version=plan.plan_version,
                        completed_at=item.completed_at,
                    )
                )
        completed.sort(key=lambda item: (item.completed_at, item.item_id), reverse=True)
        if order == "duration":
            completed.sort(
                key=lambda item: (
                    item.estimated_minutes is None,
                    -(item.estimated_minutes or 0),
                )
            )
        known = [item.estimated_minutes for item in pending if item.estimated_minutes is not None]
        return TodayProgressOut(
            date=day,
            day_start=start,
            day_end=end,
            completed_count=len(completed),
            pending_count=len(pending),
            overdue_count=sum(item.scheduled_date < day.isoformat() for item in pending),
            remaining_estimated_minutes=sum(known) if known or not pending else None,
            unestimated_count=len(pending) - len(known),
            courses=[
                TodayProgressCourseOut(course_id=key, course_name=name)
                for key, name in sorted(courses.items(), key=lambda pair: (pair[1], pair[0]))
            ],
            completed_items=completed[offset : offset + limit],
            offset=offset,
            limit=limit,
        )

    @staticmethod
    async def stats(session: AsyncSession) -> TodayStatsOut:
        # 双重软删过滤：record 域指标 JOIN records（删记录/课程即回落，不依赖子表级联），
        # 子表自身 deleted_at 按 data-layer 规则同样过滤。
        total_learning_ms = cast(
            "int",
            await session.scalar(
                select(func.coalesce(func.sum(Record.duration_ms), 0)).where(
                    Record.deleted_at.is_(None)
                )
            ),
        )
        record_count = cast(
            "int",
            await session.scalar(
                select(func.count()).select_from(Record).where(Record.deleted_at.is_(None))
            ),
        )
        course_count = cast(
            "int",
            await session.scalar(
                select(func.count()).select_from(Course).where(Course.deleted_at.is_(None))
            ),
        )
        ai_summary_count = cast(
            "int",
            await session.scalar(
                select(func.count())
                .select_from(AiSummary)
                .join(Record, AiSummary.record_id == Record.id)
                .where(AiSummary.deleted_at.is_(None), Record.deleted_at.is_(None))
            ),
        )
        quiz_generated_count = cast(
            "int",
            await session.scalar(
                select(func.count())
                .select_from(Quiz)
                .join(Record, Quiz.record_id == Record.id)
                .where(Quiz.deleted_at.is_(None), Record.deleted_at.is_(None))
            ),
        )
        quiz_answered_count = cast(
            "int",
            await session.scalar(
                select(func.count())
                .select_from(Quiz)
                .join(Record, Quiz.record_id == Record.id)
                .where(
                    Quiz.deleted_at.is_(None),
                    Quiz.answered_at.is_not(None),
                    Record.deleted_at.is_(None),
                )
            ),
        )
        chat_turn_count = cast(
            "int",
            await session.scalar(
                select(func.count())
                .select_from(ChatMessage)
                .join(ChatSession, ChatMessage.session_id == ChatSession.id)
                .where(ChatMessage.role == ChatRole.USER, ChatSession.deleted_at.is_(None))
            ),
        )
        return TodayStatsOut(
            total_learning_ms=total_learning_ms,
            record_count=record_count,
            course_count=course_count,
            ai_summary_count=ai_summary_count,
            quiz_generated_count=quiz_generated_count,
            quiz_answered_count=quiz_answered_count,
            chat_turn_count=chat_turn_count,
        )

    @staticmethod
    async def stats_trend(
        session: AsyncSession,
        days: int,
    ) -> list[TodayTrendPointOut]:
        # 捕获日 = date(created_at)（UTC 存储）；缺天后端补零，序列连续无空洞。
        # 计划项完成贡献第二源（工单 04）：DONE 项的预估时长按 date(completed_at)
        # 归日（同 UTC 口径）；完成不进学习证据链，时长统计只认完成时间戳。
        today = utcnow().date()
        start = today - timedelta(days=days - 1)
        rows = (
            await session.execute(
                select(
                    func.date(Record.created_at),
                    func.coalesce(func.sum(Record.duration_ms), 0),
                )
                .where(
                    Record.deleted_at.is_(None),
                    func.date(Record.created_at) >= start.isoformat(),
                )
                .group_by(func.date(Record.created_at))
            )
        ).all()
        totals_by_day = {str(day): int(total) for day, total in rows}
        plan_rows = (
            await session.execute(
                select(
                    func.date(LearningPlanItem.completed_at),
                    func.coalesce(func.sum(LearningPlanItem.estimated_minutes), 0),
                )
                .join(LearningPlan, LearningPlan.id == LearningPlanItem.plan_id)
                .join(LearningGoal, LearningGoal.id == LearningPlan.goal_id)
                .join(Course, Course.id == LearningGoal.course_id)
                .where(
                    LearningPlanItem.status == PlanItemStatus.DONE,
                    LearningPlanItem.completed_at.is_not(None),
                    Course.deleted_at.is_(None),
                    func.date(LearningPlanItem.completed_at) >= start.isoformat(),
                )
                .group_by(func.date(LearningPlanItem.completed_at))
            )
        ).all()
        for day, minutes in plan_rows:
            # 历史版本里的 DONE 项也是真实发生的学习（completed_at 每次完成只写
            # 一次），跨版本求和即逐日学习事实；课程软删即回落（同记录口径）。
            totals_by_day[str(day)] = totals_by_day.get(str(day), 0) + int(minutes) * 60_000
        points: list[TodayTrendPointOut] = []
        for offset in range(days):
            day = (start + timedelta(days=offset)).isoformat()
            points.append(TodayTrendPointOut(date=day, total_ms=totals_by_day.get(day, 0)))
        return points
