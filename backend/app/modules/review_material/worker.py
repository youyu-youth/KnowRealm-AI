"""复习资料生成执行体描述；任务循环复用 jobs.runner。"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from langchain_core.runnables.config import RunnableConfig
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.types import Command  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.course.models import Course
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
    ReviewMaterialCallResult,
    ReviewMaterialModel,
    StructuredGenerationError,
    call_review_material_model,
)
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus
from app.modules.review_material.graph import (
    REVIEW_DECISION_ADJUST,
    ReviewMaterialRuntime,
    ReviewMaterialState,
)
from app.modules.review_material.models import ReviewMaterial
from app.modules.review_material.schemas import (
    ReviewMaterialContent,
    ReviewMaterialDraft,
    ReviewMaterialStatus,
)
from app.modules.settings.config import (
    LlmProviderConfig,
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
)
from app.modules.summary.models import AiSummary
from app.modules.summary.schemas import AiSummaryStatus
from app.modules.transcript.models import Transcript
from app.shared.events import RecordInvalidationNotifier
from app.shared.prompts import CONTENT_LANGUAGE_INSTRUCTION

PROMPT_VERSION = "review_v2"
ADJUST_PROMPT_VERSION = "review_adjust_v2"
MAP_PROMPT_VERSION = "review_map_v2"
REDUCE_PROMPT_VERSION = "review_reduce_v1"
MODEL_CONTEXT_TOKENS = 128_000
MODEL_INPUT_TOKEN_BUDGET = MODEL_CONTEXT_TOKENS - 16_000 - 4_000
PREREQUISITE_CHANGED = "PREREQUISITE_CHANGED"


def estimate_tokens(text: str) -> int:
    """保守估算中英文混合文本 token 数；非 ASCII 与标点逐字计数。"""
    dense = sum(not char.isascii() or (not char.isalnum() and not char.isspace()) for char in text)
    return dense + (len(text) - dense + 2) // 3


def choose_generation_mode(
    text: str,
    *,
    token_budget: int,
) -> Literal["single", "map_reduce"]:
    return "single" if estimate_tokens(text) <= token_budget else "map_reduce"


@dataclass(frozen=True)
class _ClaimedReviewMaterial(ClaimedJob):
    source_version: int
    transcript: str
    summary: AiSummary
    course: Course
    provider: LlmProviderConfig
    prompt_version: str
    base_material_id: str | None = None
    previous: ReviewMaterialContent | None = None
    feedback: str | None = None


def _summary_text(summary: AiSummary) -> str:
    payload = cast(dict[str, object], json.loads(summary.summary_json))
    sections = payload.get("sections")
    section_lines: list[str] = []
    for raw in cast(list[object], sections) if isinstance(sections, list) else []:
        if isinstance(raw, dict):
            item = cast(dict[str, object], raw)
            section_lines.append(
                f"{item.get('heading', '')}：{'；'.join(cast(list[str], item.get('points', [])))}"
            )
    section_text = "\n".join(section_lines)
    return f"主题：{summary.topic}\n摘要：{summary.abstract}\n{section_text}".strip()


def _previous_text(previous: ReviewMaterialContent) -> str:
    key_list = "\n".join(f"- {item}" for item in previous.key_list)
    return (
        f"考前速记：\n{previous.quick_review}\n"
        f"重点清单：\n{key_list}\n"
        f"大纲：\n{previous.mind_map_markdown}"
    )


def _base_prompt(ctx: _ClaimedReviewMaterial, transcript: str) -> str:
    if ctx.previous is not None:
        head = (
            "请基于全部原文、上一版复习资料与用户反馈，生成修订后的复习资料，"
            "严格返回指定结构，不添加结构外字段。\n"
        )
        revision = (
            f"上一版复习资料：\n{_previous_text(ctx.previous)}\n用户反馈：{ctx.feedback or ''}\n"
        )
    else:
        head = "请基于全部原文生成复习资料，严格返回指定结构，不添加结构外字段。\n"
        revision = ""
    return (
        head + "考前速记使用 Markdown；重点清单条数按内容密度决定；大纲只能使用 Markdown "
        "标题与列表行，不得使用代码块或表格。\n"
        "硬性约束：考前速记与大纲各不超过 5000 字；重点清单 1~50 项、每项 1~80 字；"
        "大纲每一行只能是 Markdown 标题（# 开头）或列表行（-、*、+ 或阿拉伯数字加 . 开头），"
        "禁止中文序号、加粗行、代码块与表格；不得输出结构外字段。\n"
        f"学习场景：{ctx.course.learning_context}\n"
        f"教育阶段：{ctx.course.education_stage or '未设置'}\n"
        f"内容深度：{ctx.course.depth or '未设置'}\n"
        f"已确认总结（仅作辅助）：\n{_summary_text(ctx.summary)}\n"
        + revision
        + f"原文（主要依据，必须完整覆盖）：\n{transcript}\n"
        + CONTENT_LANGUAGE_INSTRUCTION
    )


def _chunk_text(text: str, token_budget: int) -> list[str]:
    if not text:
        return [""]
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        pieces = [
            paragraph[index : index + token_budget]
            for index in range(0, len(paragraph), token_budget)
        ] or [""]
        for piece in pieces:
            candidate = f"{current}\n\n{piece}" if current else piece
            if current and estimate_tokens(candidate) > token_budget:
                chunks.append(current)
                current = piece
            else:
                current = candidate
    if current or not chunks:
        chunks.append(current)
    return chunks


async def preflight(data_dir: Path) -> LlmProviderConfig | None:
    provider = await asyncio.to_thread(load_llm_provider, data_dir)
    consent_at, consent_current = await asyncio.to_thread(llm_consent, data_dir)
    if provider is None or not provider.api_key or consent_at is None or not consent_current:
        return None
    return provider


async def find_candidate(session: AsyncSession, now: datetime) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .join(Record, ProcessingJob.record_id == Record.id)
            .where(
                ProcessingJob.job_type == ProcessingJobType.REVIEW_MATERIAL_GENERATION,
                ProcessingJob.status == ProcessingJobStatus.PENDING,
                Record.deleted_at.is_(None),
            )
            .order_by(ProcessingJob.created_at)
            .limit(1)
        )
    ).one_or_none()


async def validate_claim(
    session: AsyncSession,
    job: ProcessingJob,
    record_id: str,
    provider: LlmProviderConfig | None,
) -> ClaimCheck[_ClaimedReviewMaterial]:
    current_provider = cast(LlmProviderConfig, provider)
    record = await session.get(Record, record_id)
    transcript = (
        await session.scalars(
            select(Transcript).where(
                Transcript.record_id == record_id,
                Transcript.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    course = await session.get(Course, record.course_id) if record and record.course_id else None
    input_data = cast(dict[str, object], json.loads(job.input_json))
    source_version = input_data.get("transcript_source_version")
    summary_id = input_data.get("generated_from_summary_id")
    base_material_id = input_data.get("base_material_id")
    feedback = input_data.get("feedback")
    is_adjust = isinstance(base_material_id, str) and bool(base_material_id)
    base_material: ReviewMaterial | None = None
    if is_adjust:
        base_material = await session.get(ReviewMaterial, cast(str, base_material_id))
    summary = await session.get(AiSummary, summary_id) if isinstance(summary_id, str) else None
    if (
        record is None
        or record.deleted_at is not None
        or record.status != RecordStatus.COMPLETED
        or transcript is None
        or not isinstance(source_version, int)
        or transcript.source_version != source_version
        or course is None
        or course.deleted_at is not None
        or course.status != "ACTIVE"
        or summary is None
        or summary.record_id != record_id
        or summary.deleted_at is not None
        or summary.status != AiSummaryStatus.CONFIRMED
        or input_data.get("provider_fingerprint") != llm_provider_fingerprint(current_provider)
        or (
            is_adjust
            and not (
                isinstance(feedback, str)
                and bool(feedback.strip())
                and base_material is not None
                and base_material.record_id == record_id
                and base_material.deleted_at is None
                and base_material.status != ReviewMaterialStatus.SUPERSEDED
            )
        )
    ):
        return CancelClaim(PREREQUISITE_CHANGED)
    previous: ReviewMaterialContent | None = None
    if base_material is not None:
        previous = ReviewMaterialContent(
            quick_review=base_material.quick_review,
            key_list=cast(list[str], json.loads(base_material.key_list_json)),
            mind_map_markdown=base_material.mind_map_markdown,
        )
    return Ready(
        _ClaimedReviewMaterial(
            job_id=job.id,
            record_id=record_id,
            source_version=source_version,
            transcript=transcript.content,
            summary=summary,
            course=course,
            provider=current_provider,
            prompt_version=ADJUST_PROMPT_VERSION if is_adjust else PROMPT_VERSION,
            base_material_id=cast(str, base_material_id) if is_adjust else None,
            previous=previous,
            feedback=cast(str, feedback) if is_adjust else None,
        )
    )


async def _call(
    ctx: _ClaimedReviewMaterial,
    session_factory: async_sessionmaker[AsyncSession],
    model: ReviewMaterialModel,
    prompt: str,
    prompt_version: str,
) -> ReviewMaterialCallResult:
    try:
        result = await _invoke_model(ctx, session_factory, model, prompt, prompt_version)
        return _normalized(result)
    except StructuredGenerationError as exc:
        if exc.code != "LLM_OUTPUT_INVALID":
            raise
        # json_schema 不可用的供应商（如 DeepSeek）降级 json_mode 后，模型偶发违反
        # schema 约束（自定义校验器规则不进 JSON Schema，模型不可见）；携带真实
        # 校验错误纠偏重试一次，仍失败则按原失败路径记账。
        reason = str(exc.__cause__)[:500] if exc.__cause__ else "输出结构不符合要求"
        corrective = (
            f"{prompt}\n上一次输出未通过结构校验，原因：{reason}。"
            "请修正以上问题，重新输出一个完整且严格符合结构的 JSON 对象。\n"
        )
        result = await _invoke_model(ctx, session_factory, model, corrective, prompt_version)
        return _normalized(result)


def _normalized(result: ReviewMaterialCallResult) -> ReviewMaterialCallResult:
    """服务层按宽松 Draft 校验（key 项不限长）；此处确定性切分归一到严格契约。"""
    content = ReviewMaterialContent.from_draft(cast(ReviewMaterialDraft, result.content))
    return ReviewMaterialCallResult(
        content=content,
        token_usage=result.token_usage,
        latency_ms=result.latency_ms,
    )


async def _invoke_model(
    ctx: _ClaimedReviewMaterial,
    session_factory: async_sessionmaker[AsyncSession],
    model: ReviewMaterialModel,
    prompt: str,
    prompt_version: str,
) -> ReviewMaterialCallResult:
    return await call_review_material_model(
        session_factory=session_factory,
        review_material_model=model,
        provider=ctx.provider,
        prompt=prompt,
        prompt_version=prompt_version,
    )


async def _generate_content(
    ctx: _ClaimedReviewMaterial,
    session_factory: async_sessionmaker[AsyncSession],
    model: ReviewMaterialModel,
) -> tuple[ReviewMaterialContent, dict[str, object], int]:
    full_prompt = _base_prompt(ctx, ctx.transcript)
    if choose_generation_mode(full_prompt, token_budget=MODEL_INPUT_TOKEN_BUDGET) == "single":
        result = await _call(ctx, session_factory, model, full_prompt, ctx.prompt_version)
        return result.content, result.token_usage, result.latency_ms

    calls: list[ReviewMaterialCallResult] = []
    partials: list[str] = []
    map_instruction = "这是原文语义分块。先生成覆盖此分块的三段式复习资料，后续会统一归并。\n"
    map_budget = max(
        1,
        MODEL_INPUT_TOKEN_BUDGET
        - estimate_tokens(map_instruction)
        - estimate_tokens(_base_prompt(ctx, "")),
    )
    for chunk in _chunk_text(ctx.transcript, map_budget):
        prompt = map_instruction + _base_prompt(ctx, chunk)
        result = await _call(ctx, session_factory, model, prompt, MAP_PROMPT_VERSION)
        calls.append(result)
        partials.append(result.content.model_dump_json())

    while len(partials) > 1:
        next_level: list[str] = []
        reduce_instruction = (
            "请把以下分块复习资料无遗漏地归并为一份三段式复习资料，"
            "严格返回指定结构；不得静默丢弃任何分块。\n"
            f"{CONTENT_LANGUAGE_INSTRUCTION}"
        )
        reduce_budget = max(
            1,
            MODEL_INPUT_TOKEN_BUDGET - estimate_tokens(reduce_instruction),
        )
        for group in _chunk_text("\n\n".join(partials), reduce_budget):
            prompt = reduce_instruction + group
            result = await _call(ctx, session_factory, model, prompt, REDUCE_PROMPT_VERSION)
            calls.append(result)
            next_level.append(result.content.model_dump_json())
        if len(next_level) >= len(partials):
            raise StructuredGenerationError("LLM_OUTPUT_INVALID")
        partials = next_level

    content = calls[-1].content
    total_tokens = sum(
        value
        for call in calls
        for key, value in call.token_usage.items()
        if key == "total_tokens" and isinstance(value, int)
    )
    token_usage: dict[str, object] = {"total_tokens": total_tokens} if total_tokens else {}
    return content, token_usage, sum(call.latency_ms for call in calls)


async def execute(
    ctx: _ClaimedReviewMaterial,
    _runtime: RunnerContext,
    session_factory: async_sessionmaker[AsyncSession],
    graph: CompiledStateGraph[
        ReviewMaterialState,
        ReviewMaterialRuntime,
        ReviewMaterialState,
        ReviewMaterialState,
    ],
    model: ReviewMaterialModel,
) -> tuple[ReviewMaterialContent, dict[str, object], int]:
    call_data: tuple[ReviewMaterialContent, dict[str, object], int] | None = None

    async def generate() -> ReviewMaterialContent:
        nonlocal call_data
        call_data = await _generate_content(ctx, session_factory, model)
        return call_data[0]

    result = await _invoke_graph(ctx, generate, graph)
    content = ReviewMaterialContent.model_validate(result.get("review_material"))
    if call_data is None:
        raise StructuredGenerationError("INTERNAL_ERROR")
    return content, call_data[1], call_data[2]


async def _invoke_graph(
    ctx: _ClaimedReviewMaterial,
    generate: "Callable[[], Awaitable[ReviewMaterialContent]]",
    graph: CompiledStateGraph[
        ReviewMaterialState,
        ReviewMaterialRuntime,
        ReviewMaterialState,
        ReviewMaterialState,
    ],
) -> ReviewMaterialState:
    config = RunnableConfig(
        configurable={"thread_id": f"review-material-{ctx.record_id}-source-{ctx.source_version}"}
    )
    context = ReviewMaterialRuntime(generate=generate)
    state_input: ReviewMaterialState = {
        "record_id": ctx.record_id,
        "source_version": ctx.source_version,
    }
    if ctx.base_material_id is None:
        return cast(
            ReviewMaterialState,
            await graph.ainvoke(  # pyright: ignore[reportUnknownMemberType]
                state_input,
                config,
                context=context,
            ),
        )
    snapshot = await graph.aget_state(config)
    if any(task.interrupts for task in snapshot.tasks):
        return cast(
            ReviewMaterialState,
            await graph.ainvoke(  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
                Command(resume=REVIEW_DECISION_ADJUST),
                config,
                context=context,
            ),
        )
    return cast(
        ReviewMaterialState,
        await graph.ainvoke(  # pyright: ignore[reportUnknownMemberType]
            state_input,
            config,
            context=context,
        ),
    )


async def writeback(
    ctx: _ClaimedReviewMaterial,
    result: tuple[ReviewMaterialContent, dict[str, object], int],
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    content, token_usage, latency_ms = result
    now = utcnow()
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, ctx.job_id)
        record = await session.get(Record, ctx.record_id)
        transcript = (
            await session.scalars(
                select(Transcript).where(
                    Transcript.record_id == ctx.record_id,
                    Transcript.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        course = (
            await session.get(Course, record.course_id) if record and record.course_id else None
        )
        summary = await session.get(AiSummary, ctx.summary.id)
        base_material = (
            await session.get(ReviewMaterial, ctx.base_material_id)
            if ctx.base_material_id is not None
            else None
        )
        if job is None or job.status != ProcessingJobStatus.RUNNING:
            return False
        if (
            record is None
            or record.deleted_at is not None
            or record.status != RecordStatus.COMPLETED
            or transcript is None
            or transcript.source_version != ctx.source_version
            or course is None
            or course.deleted_at is not None
            or course.status != "ACTIVE"
            or summary is None
            or summary.deleted_at is not None
            or summary.status != AiSummaryStatus.CONFIRMED
            or (
                ctx.base_material_id is not None
                and (
                    base_material is None
                    or base_material.deleted_at is not None
                    or base_material.status == ReviewMaterialStatus.SUPERSEDED
                )
            )
        ):
            job.status = ProcessingJobStatus.CANCELLED
            job.result_json = json.dumps({"reason": PREREQUISITE_CHANGED})
            job.finished_at = now
            job.updated_at = now
            return True
        latest_version = await session.scalar(
            select(func.coalesce(func.max(ReviewMaterial.version_no), 0)).where(
                ReviewMaterial.record_id == ctx.record_id
            )
        )
        version_no = cast(int, latest_version) + 1
        material_id = str(uuid4())
        session.add(
            ReviewMaterial(
                id=material_id,
                record_id=ctx.record_id,
                version_no=version_no,
                transcript_source_version=ctx.source_version,
                generated_from_summary_id=ctx.summary.id,
                quick_review=content.quick_review,
                key_list_json=json.dumps(
                    content.key_list, ensure_ascii=False, separators=(",", ":")
                ),
                mind_map_markdown=content.mind_map_markdown,
                status=ReviewMaterialStatus.GENERATED,
                model=ctx.provider.model,
                prompt_version=ctx.prompt_version,
                user_feedback=ctx.feedback,
                token_usage_json=json.dumps(token_usage, separators=(",", ":")),
                latency_ms=latency_ms,
                confirmed_at=None,
                created_at=now,
                updated_at=now,
                deleted_at=None,
            )
        )
        if base_material is not None:
            # 反馈调整产生新版本：旧版退场但数据保留
            base_material.status = ReviewMaterialStatus.SUPERSEDED
            base_material.updated_at = now
        job.status = ProcessingJobStatus.SUCCEEDED
        job.progress = 1
        job.result_json = json.dumps({"review_material_id": material_id})
        job.error_code = None
        job.error_message = None
        job.finished_at = now
        job.updated_at = now
    return True


def failure_code(ctx: _ClaimedReviewMaterial, exc: Exception) -> str | None:
    del ctx
    return exc.code if isinstance(exc, StructuredGenerationError) else "INTERNAL_ERROR"


async def apply_failure(
    ctx: _ClaimedReviewMaterial,
    session: AsyncSession,
    job: ProcessingJob,
    record: Record | None,
    error_code: str,
    now: datetime,
) -> bool:
    del session
    if record is None:
        return False
    mark_failed(
        job,
        code=error_code,
        message=(
            "复习资料调整失败，上一版仍可查看"
            if ctx.base_material_id is not None
            else "复习资料生成失败，请检查 Provider 后重试"
        ),
        now=now,
    )
    return True


def review_material_spec(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    graph: CompiledStateGraph[
        ReviewMaterialState,
        ReviewMaterialRuntime,
        ReviewMaterialState,
        ReviewMaterialState,
    ],
    model: ReviewMaterialModel,
    notifier: RecordInvalidationNotifier,
) -> WorkerSpec[
    LlmProviderConfig,
    _ClaimedReviewMaterial,
    tuple[ReviewMaterialContent, dict[str, object], int],
]:
    async def recover() -> None:
        await recover_running_to_failed(
            session_factory,
            notifier,
            ProcessingJobType.REVIEW_MATERIAL_GENERATION,
            "复习资料生成被意外中断",
        )

    def classify(_exc: Exception) -> LoopFailure:
        return LoopFailure(event="review_material_worker_unexpected_failure")

    return WorkerSpec(
        name="review_material_worker",
        job_type=ProcessingJobType.REVIEW_MATERIAL_GENERATION,
        poll_interval=0.25,
        find_candidate=find_candidate,
        validate_claim=validate_claim,
        execute=lambda ctx, runtime: execute(ctx, runtime, session_factory, graph, model),
        writeback=lambda ctx, result: writeback(ctx, result, session_factory),
        failure_code=failure_code,
        apply_failure=apply_failure,
        recover_interrupted=recover,
        classify_loop_error=classify,
        preflight=lambda: preflight(data_dir),
    )
