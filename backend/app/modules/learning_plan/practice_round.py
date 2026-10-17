"""计划练习轮次领域入口：从 02 的 READY 准备结果建卷并投影轮次状态。

建卷提交时重验要求修订、计划正文、来源版本与候选题身份/版本；冻结题面
与判分依据，之后原题修改/删除/移出课程不影响本轮。普通开始优先返回已有
轮次，不自动创建下一轮（重练归 04）。
"""

from typing import cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.jobs.models import ProcessingJob
from app.modules.learning_plan import practice
from app.modules.learning_plan.practice import PreparationResult
from app.modules.learning_plan.practice_models import PracticePreparation, PracticeRequirements
from app.modules.learning_plan.practice_schemas import (
    PracticeRoundOut,
    PracticeRoundSourceOut,
    PracticeRoundStart,
    PracticeStateOut,
    PreparationStatus,
)
from app.modules.quiz import test_service
from app.modules.quiz.frozen import FrozenFace, freeze
from app.modules.quiz.models import Quiz, QuizTest, QuizTestItem
from app.modules.quiz.test_schemas import QuizTestMode, QuizTestStatus
from app.modules.record.models import Record


def _round_conflict(code: str = "PRACTICE_ROUND_CONFLICT"):
    return practice.conflict(code)


async def latest_round(session: AsyncSession, item_id: str) -> QuizTest | None:
    return await session.scalar(
        select(QuizTest)
        .where(QuizTest.plan_item_id == item_id, QuizTest.deleted_at.is_(None))
        .order_by(QuizTest.practice_round_no.desc(), QuizTest.created_at.desc())
        .limit(1)
    )


async def round_out(session: AsyncSession, test: QuizTest) -> PracticeRoundOut:
    """轮次投影：作答/已评分/未评分分开；来源失效按当前事实标注。"""
    rows = (
        await session.execute(
            select(QuizTestItem)
            .where(
                QuizTestItem.test_id == test.id,
                QuizTestItem.deleted_at.is_(None),
            )
            .order_by(QuizTestItem.sequence_no)
        )
    ).all()
    items = [row[0] for row in rows]
    answered = sum(item.answered_at is not None for item in items)
    graded = sum(item.result is not None for item in items)
    requirements = await session.get(PracticeRequirements, test.requirements_id)
    revision = requirements.revision if requirements else 0
    faces = [FrozenFace.model_validate_json(item.frozen_json) for item in items if item.frozen_json]
    frozen_sources = {face.record_id: face.record_title for face in faces}
    alive = set(
        await session.scalars(
            select(Record.id).where(
                Record.id.in_(frozen_sources),
                Record.course_id == test.course_id,
                Record.deleted_at.is_(None),
            )
        )
    )
    return PracticeRoundOut(
        test_id=test.id,
        round_no=cast(int, test.practice_round_no),
        requirements_revision=revision,
        status=test.status,
        entry_path=f"/plan-items/{test.plan_item_id}/practice",
        paper_path=f"/spaces/{test.course_id}/tests/{test.id}",
        total_count=len(items),
        answered_count=answered,
        graded_count=graded,
        unscored_count=answered - graded,
        score=test.score,
        score_denominator=graded if graded else None,
        grading_complete=test.status == QuizTestStatus.COMPLETED.value,
        started_at=test.started_at,
        completed_at=test.completed_at,
        sources=[
            PracticeRoundSourceOut(record_id=record_id, title=title, valid=record_id in alive)
            for record_id, title in frozen_sources.items()
        ],
    )


async def start_round(
    session: AsyncSession, item_id: str, payload: PracticeRoundStart
) -> PracticeRoundOut:
    """开始或继续一轮计划练习；重放同一请求返回同一轮，不重复建卷。"""
    await practice.lock_item(session, item_id)
    item, _plan, goal = await practice.load_context(session, item_id, writable=True)
    existing = await session.scalar(
        select(QuizTest).where(QuizTest.request_id == str(payload.request_id))
    )
    if existing is not None:
        requirements_row = await session.get(PracticeRequirements, existing.requirements_id)
        if (
            existing.plan_item_id != item_id
            or requirements_row is None
            or requirements_row.revision != payload.requirements_revision
        ):
            raise practice.conflict("PRACTICE_REQUEST_CONFLICT")
        return await round_out(session, existing)
    current = await latest_round(session, item_id)
    if current is not None:
        # 普通开始不建新轮：可作答轮直接返回，评分中/已结束轮返回状态。
        return await round_out(session, current)

    req_row = await practice.latest_requirements(session, item_id)
    if req_row is None or req_row.revision != payload.requirements_revision:
        raise practice.conflict()
    preparation = (
        await session.get(PracticePreparation, str(payload.preparation_id))
        if payload.preparation_id is not None
        else (
            await session.scalar(
                select(PracticePreparation)
                .where(PracticePreparation.item_id == item_id)
                .order_by(PracticePreparation.created_at.desc())
                .limit(1)
            )
        )
    )
    if preparation is None or preparation.item_id != item_id:
        raise _round_conflict("PRACTICE_PREPARATION_STALE")
    job = await session.get(ProcessingJob, preparation.job_id)
    result = (
        PreparationResult.model_validate_json(preparation.result_json)
        if preparation.result_json
        else None
    )
    if (
        job is None
        or job.status != "SUCCEEDED"
        or result is None
        or result.outcome != PreparationStatus.READY
        or preparation.requirements_id != req_row.id
    ):
        raise _round_conflict("PRACTICE_PREPARATION_STALE")
    req = practice.requirements_out(req_row)
    if req.plan_content != item.content:
        raise practice.conflict()
    # 建卷提交时重验已确认范围与版本：失效来源不能开新练习。
    await practice.require_confirmed_sources(session, goal.course_id, req)

    quizzes = {
        quiz.id: quiz
        for quiz in await session.scalars(
            select(Quiz).where(Quiz.id.in_([c.quiz_id for c in result.selected]))
        )
    }
    faces: list[tuple[Quiz, str, str]] = []
    for candidate in result.selected:
        quiz = quizzes.get(candidate.quiz_id)
        if (
            quiz is None
            or quiz.deleted_at is not None
            or quiz.generation_status != "ACTIVE"
            or quiz.question_type not in req.question_types
            or quiz.record_id not in req.record_ids
            or practice.quiz_version(quiz) != candidate.version
        ):
            raise _round_conflict("PRACTICE_PREPARATION_STALE")
        faces.append((quiz, candidate.title, candidate.version))

    test = QuizTest(
        id=str(uuid4()),
        course_id=goal.course_id,
        mode=QuizTestMode.PLAN.value,
        status=QuizTestStatus.IN_PROGRESS.value,
        plan_item_id=item_id,
        practice_round_no=1,
        requirements_id=req_row.id,
        request_id=str(payload.request_id),
    )
    session.add(test)
    try:
        await session.flush()
    except IntegrityError:
        # 部分唯一索引兜底真并发建卷：路由层捕获后重查返回同一轮。
        raise _round_conflict() from None
    session.add_all(
        QuizTestItem(
            id=str(uuid4()),
            test_id=test.id,
            quiz_id=quiz.id,
            sequence_no=sequence_no,
            frozen_json=freeze(quiz, title, version),
        )
        for sequence_no, (quiz, title, version) in enumerate(faces, 1)
    )
    await session.flush()
    return await round_out(session, test)


async def attach_round(
    session: AsyncSession, item_id: str, state: PracticeStateOut
) -> PracticeStateOut:
    """练习状态投影附加最近轮次（state 查询共用）。"""
    test = await latest_round(session, item_id)
    state.round = await round_out(session, test) if test is not None else None
    return state


async def _plan_round_guard(session: AsyncSession, test: QuizTest) -> None:
    """计划练习写护栏（quiz 域经 register_plan_round_guard 调用）：复用
    load_context 的计划版本/目标/跳过三态判定，页面与 Agent 同一口径。"""
    await practice.load_context(session, cast(str, test.plan_item_id), writable=True)

test_service.register_plan_round_guard(_plan_round_guard)
