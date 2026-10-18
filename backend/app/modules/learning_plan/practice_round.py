"""计划练习轮次领域入口：从 02 的 READY 准备结果建卷并投影轮次状态。

建卷提交时重验要求修订、计划正文、来源版本与候选题身份/版本；冻结题面
与判分依据，之后原题修改/删除/移出课程不影响本轮。普通开始优先返回已有
轮次；明确重练时先校验准备结果，再在同一事务内安全切换轮次。
"""

import json
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.jobs.models import ProcessingJob
from app.modules.learning_plan import practice
from app.modules.learning_plan.practice import PreparationResult
from app.modules.learning_plan.practice_models import (
    PracticePreparation,
    PracticeRequirements,
    PracticeRoundRequest,
)
from app.modules.learning_plan.practice_schemas import (
    PracticeGradingRetry,
    PracticePrepareRequest,
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
    scores = [item.score for item in items if item.score is not None]
    job = await session.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.job_type == "QUIZ_GRADING",
            func.json_extract(ProcessingJob.input_json, "$.test_id") == test.id,
        )
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    )
    errors = {
        str(item.sequence_no): str(json.loads(item.ai_grade_json)["error_code"])
        for item in items
        if item.result is None
        and item.ai_grade_json
        and json.loads(item.ai_grade_json).get("error_code")
    }
    try:
        await practice.load_context(session, cast(str, test.plan_item_id), writable=True)
        writable = True
    except practice.CodedHTTPException:
        writable = False
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
        score=sum(scores) / len(scores) if scores else None,
        score_denominator=graded if graded else None,
        grading_complete=test.status == QuizTestStatus.COMPLETED.value and graded == len(items),
        started_at=test.started_at,
        completed_at=test.completed_at,
        version=await round_version(session, test),
        requirements=practice.requirements_out(requirements) if requirements else None,
        grading_job_id=job.id if job else None,
        grading_job_status=job.status if job else None,
        error_code=job.error_code if job else None,
        grading_errors=errors,
        retry_available=writable
        and answered > graded
        and test.status in ("COMPLETED", "GRADING_FAILED"),
        reused_count=await reused_count(session, test),
        sources=[
            PracticeRoundSourceOut(record_id=record_id, title=title, valid=record_id in alive)
            for record_id, title in frozen_sources.items()
        ],
    )


async def start_round(
    session: AsyncSession, item_id: str, payload: PracticeRoundStart
) -> PracticeRoundOut:
    await practice.lock_item(session, item_id)
    await practice.load_context(session, item_id, writable=True)
    replay = await session.get(PracticeRoundRequest, str(payload.request_id))
    if replay:
        test = await session.get(QuizTest, replay.test_id)
        if (
            test is None
            or test.plan_item_id != item_id
            or replay.payload_json != payload.model_dump_json()
        ):
            raise practice.conflict("PRACTICE_REQUEST_CONFLICT")
        return await round_out(session, test)
    result = await _start_round(session, item_id, payload)
    session.add(
        PracticeRoundRequest(
            request_id=str(payload.request_id),
            test_id=result.test_id,
            payload_json=payload.model_dump_json(),
        )
    )
    await session.flush()
    return result


async def _start_round(
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
            or (
                payload.preparation_id is not None
                and existing.preparation_id != str(payload.preparation_id)
            )
        ):
            raise practice.conflict("PRACTICE_REQUEST_CONFLICT")
        return await round_out(session, existing)
    current = await latest_round(session, item_id)
    preparation = (
        await session.get(PracticePreparation, str(payload.preparation_id))
        if payload.preparation_id
        else None
    )
    job = await session.get(ProcessingJob, preparation.job_id) if preparation else None
    request_data = json.loads(job.input_json).get("request") if job else None
    request = PracticePrepareRequest.model_validate(request_data) if request_data else None
    restarting = request is not None and request.expected_round_id is not None
    if preparation is not None and preparation.item_id != item_id:
        raise practice.conflict("PRACTICE_REQUEST_CONFLICT")
    if current is not None and not restarting:
        # 普通开始不建新轮：可作答轮直接返回，评分中/已结束轮返回状态。
        return await round_out(session, current)
    if restarting:
        assert request is not None
        consumed = await session.scalar(
            select(QuizTest).where(QuizTest.preparation_id == str(payload.preparation_id))
        )
        if consumed:
            req = await session.get(PracticeRequirements, consumed.requirements_id)
            if req is None or req.revision != payload.requirements_revision:
                raise practice.conflict("PRACTICE_REQUEST_CONFLICT")
            return await round_out(session, consumed)
        await validate_repractice(session, item_id, request)
        if preparation is not None and preparation.authority == "AGENT":
            await practice.require_preparation_authority(session, preparation.job_id)

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
    if (
        len(result.selected) != req.question_count
        or len({c.quiz_id for c in result.selected}) != req.question_count
    ):
        raise _round_conflict("PRACTICE_PREPARATION_STALE")

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

    if restarting and current is not None and current.status == QuizTestStatus.IN_PROGRESS.value:
        current.status = QuizTestStatus.ABANDONED.value
        current.updated_at = utcnow()
        await session.flush()
    test = QuizTest(
        id=str(uuid4()),
        course_id=goal.course_id,
        mode=QuizTestMode.PLAN.value,
        status=QuizTestStatus.IN_PROGRESS.value,
        plan_item_id=item_id,
        practice_round_no=cast(int, current.practice_round_no) + 1 if current else 1,
        requirements_id=req_row.id,
        request_id=str(payload.request_id),
        preparation_id=preparation.id,
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
    tests = await session.scalars(
        select(QuizTest)
        .where(QuizTest.plan_item_id == item_id, QuizTest.deleted_at.is_(None))
        .order_by(QuizTest.practice_round_no.desc())
    )
    state.rounds = [await round_out(session, test) for test in tests]
    state.round = state.rounds[0] if state.rounds else None
    return state


async def _plan_round_guard(session: AsyncSession, test: QuizTest) -> None:
    """计划练习写护栏（quiz 域经 register_plan_round_guard 调用）：复用
    load_context 的计划版本/目标/跳过三态判定，页面与 Agent 同一口径。"""
    await practice.lock_item(session, cast(str, test.plan_item_id))
    await session.refresh(test)
    await practice.load_context(session, cast(str, test.plan_item_id), writable=True)


test_service.register_plan_round_guard(_plan_round_guard)


async def validate_repractice(
    session: AsyncSession, item_id: str, payload: PracticePrepareRequest
) -> None:
    current = await latest_round(session, item_id)
    if (
        current is None
        or current.id != str(payload.expected_round_id)
        or await round_version(session, current) != payload.expected_round_version
    ):
        raise practice.conflict("PRACTICE_PREPARATION_STALE")
    if current.status == QuizTestStatus.IN_PROGRESS.value and not payload.abandon_confirmed:
        raise practice.conflict("PRACTICE_CONFIRMATION_REQUIRED")


async def round_version(session: AsyncSession, test: QuizTest) -> str:
    """只冻结可作答进度；已交卷旧轮的晚到评分不使重练基线过期。"""
    answers = list(
        await session.execute(
            select(QuizTestItem.id, QuizTestItem.user_answer_json)
            .where(QuizTestItem.test_id == test.id, QuizTestItem.deleted_at.is_(None))
            .order_by(QuizTestItem.sequence_no)
        )
    )
    return sha256(
        json.dumps([test.id, test.status == "IN_PROGRESS", [list(row) for row in answers]]).encode()
    ).hexdigest()


async def used_quiz_ids(
    session: AsyncSession, item_id: str, *, before_round: int | None = None
) -> set[str]:
    query = (
        select(QuizTestItem.frozen_json)
        .join(QuizTest, QuizTest.id == QuizTestItem.test_id)
        .where(
            QuizTest.plan_item_id == item_id,
            QuizTest.deleted_at.is_(None),
            QuizTestItem.deleted_at.is_(None),
        )
    )
    if before_round is not None:
        query = query.where(QuizTest.practice_round_no < before_round)
    return {
        FrozenFace.model_validate_json(face).quiz_id
        for face in await session.scalars(query)
        if face
    }


async def reused_count(session: AsyncSession, test: QuizTest) -> int:
    used = await used_quiz_ids(
        session, cast(str, test.plan_item_id), before_round=test.practice_round_no
    )
    faces = await session.scalars(
        select(QuizTestItem.frozen_json).where(
            QuizTestItem.test_id == test.id, QuizTestItem.deleted_at.is_(None)
        )
    )
    return sum(FrozenFace.model_validate_json(face).quiz_id in used for face in faces if face)


async def retry_grading(
    session: AsyncSession, data_dir: Path, item_id: str, test_id: str, payload: PracticeGradingRetry
) -> PracticeRoundOut:
    await practice.lock_item(session, item_id)
    await practice.load_context(session, item_id, writable=True)
    test = await session.get(QuizTest, test_id, populate_existing=True)
    if test is None or test.plan_item_id != item_id or test.deleted_at is not None:
        raise practice.conflict("PRACTICE_ROUND_CONFLICT")
    job_id = await test_service.retry_plan_grading(
        session, data_dir, test_id, str(payload.request_id)
    )
    out = await round_out(session, test)
    if job_id is not None:
        job = await session.get(ProcessingJob, job_id)
        assert job is not None
        out.grading_job_id, out.grading_job_status = job.id, job.status
        out.error_code = job.error_code
    return out
