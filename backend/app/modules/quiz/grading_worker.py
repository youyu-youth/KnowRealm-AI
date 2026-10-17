"""模拟测试简答评分执行体描述（任务循环骨架见 job_runner.py，ADR-0012）。

一卷一评分 job、逐题调 LLM；单题评分失败不阻塞整卷（错误码入 ai_grade_json、
排除出分母、不落 QUIZ_ANSWERED），崩溃由恢复钩子翻 GRADING_FAILED 供重新评分。
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.course.models import Course
from app.modules.course.schemas import CourseStatus
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.runner import (
    CancelClaim,
    ClaimCheck,
    ClaimedJob,
    LoopFailure,
    Ready,
    RunnerContext,
    WorkerSpec,
    mark_failed,
    recover_running_to_failed,
)
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.llm.service import (
    QuizGradingModel,
    StructuredGenerationError,
    call_quiz_grading_model,
)
from app.modules.quiz.frozen import FrozenFace, face_of
from app.modules.quiz.models import Quiz, QuizTest, QuizTestItem
from app.modules.quiz.schemas import QuizQuestionType, ShortAnswerGrade
from app.modules.quiz.test_schemas import QuizTestItemResult, QuizTestStatus
from app.modules.quiz.test_service import finalize_completed_test, record_test_answer_event
from app.modules.quiz.worker import preflight
from app.modules.record.models import Record
from app.modules.settings.config import LlmProviderConfig, llm_provider_fingerprint
from app.shared.events import RecordInvalidationNotifier
from app.shared.prompts import CONTENT_LANGUAGE_INSTRUCTION

PROMPT_VERSION = "quiz_grading_v1"
PREREQUISITE_CHANGED = "PREREQUISITE_CHANGED"


@dataclass(frozen=True)
class _ClaimedGradingJob(ClaimedJob):
    """课程级任务：record_id 坐标位承载 test_id（评分 job 无 record 主体）。"""

    test_id: str
    provider: LlmProviderConfig


def build_grading_prompt(*, stem: str, reference: str, answer: str) -> str:
    return (
        "请评阅以下简答题作答，严格返回指定结构，不添加结构外字段。\n"
        f"题目：{stem}\n"
        f"参考答案：{reference}\n"
        f"学生作答：{answer}\n"
        "评分要求：\n"
        "- verdict：CORRECT（核心要点覆盖）/ PARTIAL（部分覆盖）/ WRONG（未覆盖或错误）\n"
        "- score：0 到 1 的小数，与 verdict 一致（WRONG 为 0，PARTIAL 介于 0 与 1，"
        "CORRECT 大于 0）\n"
        "- confidence：0 到 1 的小数，表示对本题评分的把握\n"
        "- rationale：一到两句评分依据，说明覆盖或缺失的要点\n"
        "- 只依据参考答案评阅，不引入题目之外的知识\n"
        f"{CONTENT_LANGUAGE_INSTRUCTION}"
    )


async def find_candidate(session: AsyncSession, now: datetime) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.job_type == ProcessingJobType.QUIZ_GRADING,
                ProcessingJob.status == ProcessingJobStatus.PENDING,
            )
            .order_by(ProcessingJob.created_at)
            .limit(1)
        )
    ).one_or_none()


async def validate_claim(
    session: AsyncSession,
    job: ProcessingJob,
    _record_id: str,
    provider: LlmProviderConfig | None,
) -> ClaimCheck[_ClaimedGradingJob]:
    """领取闸门（第三道）：卷面/课程/供应商指纹任一失效即静默取消，卷面翻 GRADING_FAILED。"""
    current_provider = cast(LlmProviderConfig, provider)  # preflight 通过时必非 None
    input_data = cast(dict[str, object], json.loads(job.input_json))
    test_id = input_data.get("test_id")
    if not isinstance(test_id, str):
        return CancelClaim(PREREQUISITE_CHANGED)
    test = await session.get(QuizTest, test_id)
    course = await session.get(Course, test.course_id) if test is not None else None
    if (
        test is None
        or test.deleted_at is not None
        or course is None
        or course.deleted_at is not None
        or course.status != CourseStatus.ACTIVE
        or test.status != QuizTestStatus.GRADING
        or input_data.get("provider_fingerprint") != llm_provider_fingerprint(current_provider)
    ):
        if test is not None and test.status == QuizTestStatus.GRADING:
            test.status = QuizTestStatus.GRADING_FAILED
            test.updated_at = utcnow()
        return CancelClaim(PREREQUISITE_CHANGED)
    return Ready(
        _ClaimedGradingJob(
            job_id=job.id,
            record_id=test_id,
            test_id=test_id,
            provider=current_provider,
        )
    )


async def execute(
    ctx: _ClaimedGradingJob,
    _runtime: RunnerContext,
    session_factory: async_sessionmaker[AsyncSession],
    model: QuizGradingModel,
) -> dict[str, object]:
    """逐题评分待评简答（result 为 NULL 即未评成功者，重评自然跳过已评题）。

    题面与参考答案取轮次事实（计划练习=冻结副本，普通测试=原题行）。"""
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(QuizTestItem, Quiz)
                .outerjoin(Quiz, Quiz.id == QuizTestItem.quiz_id)
                .where(
                    QuizTestItem.test_id == ctx.test_id,
                    QuizTestItem.deleted_at.is_(None),
                    QuizTestItem.result.is_(None),
                )
                .order_by(QuizTestItem.sequence_no)
            )
        ).all()
    targets: list[tuple[str, str, FrozenFace]] = []
    for item, quiz in rows:
        face = face_of(item, quiz)
        if face.question_type == QuizQuestionType.SHORT_ANSWER.value:
            targets.append((item.id, cast(str, item.user_answer_json), face))
    graded = 0
    failed = 0
    for item_id, user_answer_json, face in targets:
        try:
            call = await call_quiz_grading_model(
                session_factory=session_factory,
                quiz_grading_model=model,
                provider=ctx.provider,
                prompt=build_grading_prompt(
                    stem=face.stem,
                    reference=cast(str, json.loads(face.correct_answer)),
                    answer=cast(str, json.loads(user_answer_json)),
                ),
                prompt_version=PROMPT_VERSION,
            )
        except StructuredGenerationError as exc:
            failed += 1
            await _land_item_grade(session_factory, ctx.test_id, item_id, face, None, exc.code)
            continue
        graded += 1
        await _land_item_grade(session_factory, ctx.test_id, item_id, face, call.content, None)
    return {"graded": graded, "failed": failed}


async def _land_item_grade(
    session_factory: async_sessionmaker[AsyncSession],
    test_id: str,
    item_id: str,
    face: FrozenFace,
    grade: ShortAnswerGrade | None,
    error_code: str | None,
) -> None:
    """单题评分落库（一题一事务，崩溃后已落题不重评）。

    成功：result/score/ai_grade_json + QUIZ_ANSWERED 事件（幂等键）；
    失败：仅 ai_grade_json 记错误码，result/score 留 NULL、不落事件。
    """
    now = utcnow()
    async with session_factory() as session, session.begin():
        item = await session.get(QuizTestItem, item_id)
        if item is None or item.result is not None:
            return
        if grade is not None:
            verdict = QuizTestItemResult(grade.verdict)
            item.result = verdict.value
            item.score = grade.score
            item.ai_grade_json = json.dumps(
                {
                    "verdict": grade.verdict,
                    "score": grade.score,
                    "confidence": grade.confidence,
                    "rationale": grade.rationale,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            test = await session.get(QuizTest, test_id)
            if test is not None:
                # 事件代表作答行为：评分落行在评分时刻，occurred_at 取作答时刻
                # （交卷闸门要求全部作答，answered_at 必非空）。
                await record_test_answer_event(
                    session,
                    test,
                    item,
                    face,
                    verdict,
                    grade.score,
                    occurred_at=cast(datetime, item.answered_at),
                    created_at=now,
                )
        else:
            item.ai_grade_json = json.dumps({"error_code": error_code}, separators=(",", ":"))
        item.updated_at = now


async def writeback(
    ctx: _ClaimedGradingJob,
    summary: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    now = utcnow()
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, ctx.job_id)
        if job is None or job.status != ProcessingJobStatus.RUNNING:
            return False
        test = await session.get(QuizTest, ctx.test_id)
        if test is not None and test.status == QuizTestStatus.GRADING:
            await finalize_completed_test(session, test, now)
        job.status = ProcessingJobStatus.SUCCEEDED
        job.progress = 1
        job.result_json = json.dumps(summary, separators=(",", ":"))
        job.error_code = None
        job.error_message = None
        job.finished_at = now
        job.updated_at = now
    return True


def failure_code(ctx: _ClaimedGradingJob, exc: Exception) -> str | None:
    del ctx
    if isinstance(exc, StructuredGenerationError):
        return exc.code
    return "INTERNAL_ERROR"


async def _flip_test_to_grading_failed(session: AsyncSession, test_id: str, now: datetime) -> None:
    test = await session.get(QuizTest, test_id)
    if test is not None and test.status == QuizTestStatus.GRADING:
        test.status = QuizTestStatus.GRADING_FAILED
        test.updated_at = now


async def apply_failure(
    ctx: _ClaimedGradingJob,
    session: AsyncSession,
    job: ProcessingJob,
    _record: Record | None,
    error_code: str,
    now: datetime,
) -> bool:
    del _record
    mark_failed(job, code=error_code, message="简答评分失败，请重新评分", now=now)
    await _flip_test_to_grading_failed(session, ctx.test_id, now)
    return True


async def _recover_test(session: AsyncSession, job: ProcessingJob, now: datetime) -> None:
    input_data = cast(dict[str, object], json.loads(job.input_json))
    test_id = input_data.get("test_id")
    if isinstance(test_id, str):
        await _flip_test_to_grading_failed(session, test_id, now)


def quiz_grading_spec(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    model: QuizGradingModel,
    record_notifier: RecordInvalidationNotifier,
) -> WorkerSpec[LlmProviderConfig, _ClaimedGradingJob, dict[str, object]]:
    async def recover() -> None:
        await recover_running_to_failed(
            session_factory,
            record_notifier,
            ProcessingJobType.QUIZ_GRADING,
            "简答评分被意外中断",
            on_job_recovered=_recover_test,
        )

    def classify(_exc: Exception) -> LoopFailure:
        return LoopFailure(event="quiz_grading_worker_unexpected_failure")

    return WorkerSpec(
        name="quiz_grading_worker",
        job_type=ProcessingJobType.QUIZ_GRADING,
        poll_interval=0.25,
        find_candidate=find_candidate,
        validate_claim=validate_claim,
        execute=lambda ctx, runtime: execute(ctx, runtime, session_factory, model),
        writeback=lambda ctx, summary: writeback(ctx, summary, session_factory),
        failure_code=failure_code,
        apply_failure=apply_failure,
        recover_interrupted=recover,
        classify_loop_error=classify,
        preflight=lambda: preflight(data_dir),
    )
