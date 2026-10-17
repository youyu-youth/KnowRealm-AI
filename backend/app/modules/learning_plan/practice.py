"""练习要求与准备领域入口。页面和受控 Agent 共用；题集不是可作答试卷。"""

import json
import unicodedata
from collections.abc import Awaitable, Callable
from hashlib import sha256
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.learning_plan.models import LearningGoal, LearningPlan, LearningPlanItem
from app.modules.learning_plan.practice_models import PracticePreparation, PracticeRequirements
from app.modules.learning_plan.practice_schemas import (
    PracticeMatchReason,
    PracticePreparationOut,
    PracticePrepareRequest,
    PracticeRequirementsOut,
    PracticeRequirementsUpdate,
    PracticeSourceOut,
    PracticeStateOut,
    PreparationStatus,
)
from app.modules.learning_plan.service import PlanService
from app.modules.quiz.models import Quiz
from app.modules.record.models import Record
from app.shared.errors import CodedHTTPException

type PreparationAuthorizer = Callable[[AsyncSession, str], Awaitable[None]]
_preparation_authorizer: PreparationAuthorizer | None = None


def register_preparation_authorizer(authorizer: PreparationAuthorizer) -> None:
    global _preparation_authorizer
    _preparation_authorizer = authorizer


async def require_preparation_authority(session: AsyncSession, job_id: str) -> None:
    if _preparation_authorizer is None:
        raise conflict("OPERATION_APPROVAL_REQUIRED")
    await _preparation_authorizer(session, job_id)


def conflict(code: str = "PRACTICE_REQUIREMENTS_STALE") -> CodedHTTPException:
    return CodedHTTPException(
        code=code, status_code=409, detail="练习要求、来源或执行状态已变化，请刷新后重新确认"
    )


async def load_context(
    session: AsyncSession, item_id: str, *, writable: bool = False
) -> tuple[LearningPlanItem, LearningPlan, LearningGoal]:
    item = await session.get(LearningPlanItem, item_id)
    found = await PlanService.get_with_goal(session, item.plan_id) if item else None
    if item is None or found is None:
        raise CodedHTTPException(
            code="PLAN_ITEM_NOT_FOUND", status_code=404, detail="计划项不存在或课程已删除"
        )
    plan, goal = found
    if item.action_type != "PRACTICE_QUIZ":
        raise conflict("PRACTICE_ITEM_UNAVAILABLE")
    if writable and (
        plan.status != "ACTIVE" or goal.status != "ACTIVE" or item.status == "SKIPPED"
    ):
        raise conflict("PRACTICE_ITEM_UNAVAILABLE")
    return item, plan, goal


async def lock_item(session: AsyncSession, item_id: str) -> None:
    # SQLite SELECT 不取得写锁；先串行化，保证修订、取消与最终提交使用同一事实。
    await session.execute(
        update(LearningPlanItem)
        .where(LearningPlanItem.id == item_id)
        .values(id=LearningPlanItem.id)
    )


async def latest_requirements(session: AsyncSession, item_id: str) -> PracticeRequirements | None:
    return await session.scalar(
        select(PracticeRequirements)
        .where(PracticeRequirements.item_id == item_id)
        .order_by(PracticeRequirements.revision.desc())
        .limit(1)
    )


def requirements_out(row: PracticeRequirements) -> PracticeRequirementsOut:
    payload = PracticeRequirementsUpdate.model_validate_json(row.content_json)
    return PracticeRequirementsOut(
        id=row.id,
        revision=row.revision,
        confirmed_at=row.confirmed_at,
        **payload.model_dump(exclude={"expected_revision"}, mode="json"),
    )


async def require_sources(session: AsyncSession, course_id: str, record_ids: list[str]) -> None:
    owned = set(
        await session.scalars(
            select(Record.id).where(
                Record.id.in_(record_ids),
                Record.course_id == course_id,
                Record.deleted_at.is_(None),
            )
        )
    )
    if owned != set(record_ids):
        raise conflict("PRACTICE_SOURCE_INVALID")


async def require_confirmed_sources(
    session: AsyncSession, course_id: str, req: PracticeRequirementsOut
) -> None:
    await require_sources(session, course_id, req.record_ids)
    if await source_versions(session, req.record_ids) != req.source_versions:
        raise conflict("PRACTICE_SOURCE_INVALID")


async def confirm_requirements(
    session: AsyncSession, item_id: str, payload: PracticeRequirementsUpdate
) -> PracticeRequirementsOut:
    await lock_item(session, item_id)
    item, _plan, goal = await load_context(session, item_id, writable=True)
    latest = await latest_requirements(session, item_id)
    if (
        payload.expected_revision != (latest.revision if latest else 0)
        or payload.plan_content != item.content
    ):
        raise conflict()
    await require_sources(session, goal.course_id, [str(value) for value in payload.record_ids])
    versions = await source_versions(session, [str(value) for value in payload.record_ids])
    if payload.source_versions != versions:
        raise conflict("PRACTICE_SOURCE_INVALID")
    row = PracticeRequirements(
        item_id=item_id,
        revision=payload.expected_revision + 1,
        content_json=payload.model_dump_json(),
    )
    session.add(row)
    await session.flush()
    return requirements_out(row)


class Candidate(BaseModel):
    quiz_id: str
    record_id: str
    title: str
    question_type: str
    stem: str
    options: list[str]
    version: str
    match_reason: PracticeMatchReason | None = None


def quiz_version(quiz: Quiz) -> str:
    return sha256(
        json.dumps(
            [
                quiz.id,
                quiz.record_id,
                quiz.question_type,
                quiz.stem,
                quiz.options_json,
                quiz.correct_answer_json,
                quiz.explanation,
                quiz.concept_id,
                str(quiz.updated_at),
            ],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


async def source_versions(session: AsyncSession, record_ids: list[str]) -> dict[str, str]:
    records = list(await session.scalars(select(Record).where(Record.id.in_(record_ids))))
    quizzes = list(
        await session.scalars(select(Quiz).where(Quiz.record_id.in_(record_ids)).order_by(Quiz.id))
    )
    return {
        record.id: sha256(
            json.dumps(
                [
                    str(record.updated_at),
                    record.course_id,
                    str(record.deleted_at),
                    [
                        (quiz_version(quiz), quiz.generation_status, str(quiz.deleted_at))
                        for quiz in quizzes
                        if quiz.record_id == record.id
                    ],
                ]
            ).encode()
        ).hexdigest()
        for record in records
    }


async def candidates(
    session: AsyncSession, course_id: str, req: PracticeRequirementsOut
) -> list[Candidate]:
    rows = (
        await session.execute(
            select(Quiz, Record.title)
            .join(Record, Record.id == Quiz.record_id)
            .where(
                Record.course_id == course_id,
                Record.deleted_at.is_(None),
                Quiz.deleted_at.is_(None),
                Quiz.generation_status == "ACTIVE",
                Quiz.question_type.in_(req.question_types),
            )
            .order_by(Quiz.created_at, Quiz.id)
        )
    ).all()
    # 已确认范围优先，防止同题副本在其他资料中抢走本范围的候选。
    rows = sorted(rows, key=lambda row: row[0].record_id not in req.record_ids)
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    result: list[Candidate] = []
    for quiz, title in rows:
        options = json.loads(quiz.options_json)
        key = (
            quiz.question_type,
            normalized(quiz.stem),
            tuple(normalized(option) for option in options),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(
            Candidate(
                quiz_id=quiz.id,
                record_id=quiz.record_id,
                title=title,
                question_type=quiz.question_type,
                stem=quiz.stem,
                options=options,
                version=quiz_version(quiz),
            )
        )
    return result


class PreparationResult(BaseModel):
    candidate_fingerprint: str
    source_versions: dict[str, str]
    provider_fingerprint: str | None = None
    outcome: PreparationStatus
    eligible_count: int
    related_count: int
    examined_count: int
    total_candidates: int
    course_scan_complete: bool
    sources: list[PracticeSourceOut]
    suggestions: list[PracticeSourceOut]
    selected: list[Candidate] = Field(default_factory=list[Candidate])


def candidate_fingerprint(pool: list[Candidate]) -> str:
    return sha256(
        json.dumps([(candidate.quiz_id, candidate.version) for candidate in pool]).encode()
    ).hexdigest()


async def prepare(
    session: AsyncSession, item_id: str, payload: PracticePrepareRequest, *, authority: str
) -> PracticePreparationOut:
    await lock_item(session, item_id)
    item, _plan, goal = await load_context(session, item_id, writable=True)
    existing = await session.scalar(
        select(PracticePreparation).where(PracticePreparation.request_id == str(payload.request_id))
    )
    if existing:
        req = await session.get(PracticeRequirements, existing.requirements_id)
        if (
            existing.item_id != item_id
            or req is None
            or req.revision != payload.requirements_revision
        ):
            raise conflict("PRACTICE_REQUEST_CONFLICT")
        return await preparation_out(session, existing)
    req_row = await latest_requirements(session, item_id)
    if req_row is None or req_row.revision != payload.requirements_revision:
        raise conflict()
    req = requirements_out(req_row)
    if req.plan_content != item.content:
        raise conflict()
    await require_confirmed_sources(session, goal.course_id, req)
    active = await session.scalar(
        select(ProcessingJob.id).where(
            ProcessingJob.job_type == ProcessingJobType.PRACTICE_PREPARE,
            func.json_extract(ProcessingJob.input_json, "$.item_id") == item_id,
            ProcessingJob.status.in_(["PENDING", "RUNNING"]),
        )
    )
    if active:
        raise conflict("PRACTICE_REQUEST_CONFLICT")
    job_id = str(uuid4())
    job = ProcessingJob(
        id=job_id,
        job_type=ProcessingJobType.PRACTICE_PREPARE,
        status=ProcessingJobStatus.PENDING,
        max_attempts=1,
        input_json=json.dumps({"item_id": item_id}),
    )
    session.add(job)
    await session.flush()
    row = PracticePreparation(
        item_id=item_id,
        requirements_id=req_row.id,
        request_id=str(payload.request_id),
        job_id=job_id,
        authority=authority,
    )
    session.add(row)
    await session.flush()
    return await preparation_out(session, row)


async def preparation_out(
    session: AsyncSession, row: PracticePreparation
) -> PracticePreparationOut:
    # 同一 SELECT 读取状态与结果，避免恰逢 Worker 完成时返回“成功＋旧检查点”。
    row, job, req_row = (
        await session.execute(
            select(PracticePreparation, ProcessingJob, PracticeRequirements)
            .join(ProcessingJob, ProcessingJob.id == PracticePreparation.job_id)
            .join(
                PracticeRequirements, PracticeRequirements.id == PracticePreparation.requirements_id
            )
            .where(PracticePreparation.id == row.id)
            .execution_options(populate_existing=True)
        )
    ).one()
    req = requirements_out(req_row)
    result = PreparationResult.model_validate_json(row.result_json) if row.result_json else None
    return PracticePreparationOut(
        id=row.id,
        item_id=row.item_id,
        entry_path=f"/plan-items/{row.item_id}/practice",
        job_id=job.id,
        requirements_revision=req.revision,
        status=job.status,
        outcome=result.outcome if result else None,
        target_count=req.question_count,
        eligible_count=result.eligible_count if result else 0,
        related_count=result.related_count if result else 0,
        selected_count=len(result.selected) if result else 0,
        examined_count=result.examined_count if result else 0,
        total_candidates=result.total_candidates if result else 0,
        course_scan_complete=result.course_scan_complete if result else False,
        error_code=job.error_code,
        sources=result.sources if result else [],
        suggestions=result.suggestions if result else [],
    )


async def state(session: AsyncSession, item_id: str) -> PracticeStateOut:
    item, plan, goal = await load_context(session, item_id)
    latest = await latest_requirements(session, item_id)
    req = requirements_out(latest) if latest else None
    sources = (
        await session.execute(
            select(Record.id, Record.title, func.count(Quiz.id))
            .outerjoin(
                Quiz,
                (Quiz.record_id == Record.id)
                & Quiz.deleted_at.is_(None)
                & (Quiz.generation_status == "ACTIVE"),
            )
            .where(Record.course_id == goal.course_id, Record.deleted_at.is_(None))
            .group_by(Record.id)
            .order_by(Record.created_at)
        )
    ).all()
    preparations = list(
        await session.scalars(
            select(PracticePreparation)
            .where(PracticePreparation.item_id == item_id)
            .order_by(PracticePreparation.created_at.desc())
            .limit(10)
        )
    )
    versions = await source_versions(session, [row[0] for row in sources])
    from app.modules.learning_plan.practice_round import attach_round

    return await attach_round(
        session,
        item_id,
        PracticeStateOut(
            item_id=item.id,
            course_id=goal.course_id,
            plan_id=plan.id,
            plan_content=item.content,
            editable=plan.status == "ACTIVE"
            and goal.status == "ACTIVE"
            and item.status != "SKIPPED",
            requirements_stale=req is not None and req.plan_content != item.content,
            requirements=req,
            preparations=[await preparation_out(session, row) for row in preparations],
            sources=[
                PracticeSourceOut(
                    record_id=id_, title=title, eligible_count=count, version=versions[id_]
                )
                for id_, title, count in sources
            ],
        ),
    )


async def cancel(
    session: AsyncSession, item_id: str, preparation_id: str
) -> PracticePreparationOut:
    await lock_item(session, item_id)
    await load_context(session, item_id)
    row = await session.get(PracticePreparation, preparation_id)
    if row is None or row.item_id != item_id:
        raise conflict("PRACTICE_REQUEST_CONFLICT")
    job = await session.get(ProcessingJob, row.job_id)
    assert job is not None
    if job.status in ("PENDING", "RUNNING"):
        job.status = ProcessingJobStatus.CANCELLED
        job.finished_at = job.updated_at = utcnow()
        job.error_code = None
    return await preparation_out(session, row)
