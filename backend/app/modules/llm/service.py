import json
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol, cast
from uuid import uuid4

import openai
from langchain_core.exceptions import OutputParserException
from langchain_openai import ChatOpenAI
from loguru import logger
from pydantic import BaseModel, SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.course_brain.schemas import CourseBrainExtractionBatch
from app.modules.knowledge_point.schemas import KnowledgePointBatch
from app.modules.learning_plan.schemas import PlanDraft, PlanSuggestions
from app.modules.library.schemas import OrganizeSuggestionBatch
from app.modules.llm.models import LlmCallLog
from app.modules.quiz.schemas import QuizBatch, ShortAnswerGrade
from app.modules.review_material.schemas import ReviewMaterialContent, ReviewMaterialDraft
from app.modules.settings.config import LlmProviderConfig
from app.modules.summary.schemas import SummaryContent
from app.modules.todo.schemas import TodoBatch


@dataclass(frozen=True)
class StructuredModelResult:
    output: object
    token_usage: dict[str, object]


SummaryModelResult = StructuredModelResult


@dataclass(frozen=True)
class SummaryCallResult:
    content: SummaryContent
    token_usage: dict[str, object]
    latency_ms: int


@dataclass(frozen=True)
class KnowledgePointCallResult:
    content: KnowledgePointBatch
    token_usage: dict[str, object]
    latency_ms: int


@dataclass(frozen=True)
class QuizCallResult:
    content: QuizBatch
    token_usage: dict[str, object]
    latency_ms: int


@dataclass(frozen=True)
class QuizGradingCallResult:
    content: ShortAnswerGrade
    token_usage: dict[str, object]
    latency_ms: int


@dataclass(frozen=True)
class TodoCallResult:
    content: TodoBatch
    token_usage: dict[str, object]
    latency_ms: int


@dataclass(frozen=True)
class ReviewMaterialCallResult:
    content: ReviewMaterialContent
    token_usage: dict[str, object]
    latency_ms: int


@dataclass(frozen=True)
class CourseBrainCallResult:
    content: CourseBrainExtractionBatch
    token_usage: dict[str, object]
    latency_ms: int


@dataclass(frozen=True)
class PlanDraftCallResult:
    content: PlanDraft
    token_usage: dict[str, object]
    latency_ms: int


@dataclass(frozen=True)
class PlanSuggestionsCallResult:
    content: PlanSuggestions
    token_usage: dict[str, object]
    latency_ms: int


class StructuredModel(Protocol):
    async def generate(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> StructuredModelResult: ...


SummaryModel = StructuredModel
KnowledgePointModel = StructuredModel
QuizModel = StructuredModel
QuizGradingModel = StructuredModel
TodoModel = StructuredModel
ReviewMaterialModel = StructuredModel
ReviewMaterialModelResult = StructuredModelResult
CourseBrainModel = StructuredModel
PlanDraftModel = StructuredModel
PlanSuggestionsModel = StructuredModel


class StructuredGenerationError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


SummaryGenerationError = StructuredGenerationError


def is_json_schema_rejection(error: openai.BadRequestError) -> bool:
    detail = f"{error} {error.response.text}".lower()
    return (error.param or "").startswith("response_format") or any(
        field in detail for field in ("response_format", "json_schema")
    )


def json_mode_prompt(prompt: str, schema: type[BaseModel]) -> str:
    return (
        prompt
        + "\n必须只返回一个符合以下 JSON Schema 的 JSON 对象，不要输出其他内容：\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )


class _OpenAiCompatibleStructuredModel:
    def __init__(self, output_schema: type[BaseModel]) -> None:
        self._output_schema = output_schema

    async def generate(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> StructuredModelResult:
        http_client = openai.DefaultAsyncHttpxClient(trust_env=False)
        try:
            llm = ChatOpenAI(
                model=model,
                base_url=base_url,
                api_key=SecretStr(api_key),
                timeout=90,
                max_retries=0,
                http_async_client=http_client,
            )
            structured = llm.with_structured_output(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                self._output_schema,
                method="json_schema",
                include_raw=True,
                strict=True,
            )
            try:
                raw_response = cast(dict[str, object], await structured.ainvoke(prompt))
            except openai.BadRequestError as exc:
                if not is_json_schema_rejection(exc):
                    raise
                raw_response = await self._generate_json_mode(llm, prompt)
            output = raw_response.get("parsed")
            parsing_error = raw_response.get("parsing_error")
            raw_message = raw_response.get("raw")
            usage = getattr(raw_message, "usage_metadata", None)
            if output is None and parsing_error is not None:
                # include_raw 会吞掉 JSON 解析/schema 违规的真实错误；上抛让
                # _call_structured_model 按"输出无效"归类（而非误导性的 None 校验）。
                raise cast(BaseException, parsing_error)
            return StructuredModelResult(
                output=output,
                token_usage=cast(dict[str, object], usage) if isinstance(usage, dict) else {},
            )
        finally:
            await http_client.aclose()

    async def _generate_json_mode(
        self,
        llm: ChatOpenAI,
        prompt: str,
    ) -> dict[str, object]:
        structured = llm.with_structured_output(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            self._output_schema,
            method="json_mode",
            include_raw=True,
            max_tokens=8192,
        )
        # json_object 端点依赖提示词携带结构；8192 为推理模型（思考与正文同计费）留足输出空间
        json_prompt = json_mode_prompt(prompt, self._output_schema)
        return cast(dict[str, object], await structured.ainvoke(json_prompt))


class OpenAiCompatibleSummaryModel(_OpenAiCompatibleStructuredModel):
    def __init__(self) -> None:
        super().__init__(SummaryContent)


class OpenAiCompatibleKnowledgePointModel(_OpenAiCompatibleStructuredModel):
    def __init__(self) -> None:
        super().__init__(KnowledgePointBatch)


class OpenAiCompatibleQuizModel(_OpenAiCompatibleStructuredModel):
    def __init__(self) -> None:
        super().__init__(QuizBatch)


class OpenAiCompatibleQuizGradingModel(_OpenAiCompatibleStructuredModel):
    def __init__(self) -> None:
        super().__init__(ShortAnswerGrade)


class OpenAiCompatibleTodoModel(_OpenAiCompatibleStructuredModel):
    def __init__(self) -> None:
        super().__init__(TodoBatch)


class OpenAiCompatibleReviewMaterialModel(_OpenAiCompatibleStructuredModel):
    def __init__(self) -> None:
        # 校验用宽松 Draft（key 项不限长，flash 级模型无法按提示控制每项字数）；
        # worker._call 调 from_draft 切分归一到严格 ReviewMaterialContent。
        super().__init__(ReviewMaterialDraft)


class OpenAiCompatibleCourseBrainModel(_OpenAiCompatibleStructuredModel):
    def __init__(self) -> None:
        super().__init__(CourseBrainExtractionBatch)


class OpenAiCompatibleOrganizeModel(_OpenAiCompatibleStructuredModel):
    def __init__(self) -> None:
        super().__init__(OrganizeSuggestionBatch)


class OpenAiCompatiblePlanDraftModel(_OpenAiCompatibleStructuredModel):
    """学习计划草案生成（第三阶段工单 02）：阶段 / 项序 / 时长 / 理由。"""

    def __init__(self) -> None:
        super().__init__(PlanDraft)


class OpenAiCompatiblePlanSuggestionsModel(_OpenAiCompatibleStructuredModel):
    """纯目标起点（无资料）的建议与资料缺口生成（工单 02，spec 用户故事 8）。"""

    def __init__(self) -> None:
        super().__init__(PlanSuggestions)


def build_chat_model(
    provider: LlmProviderConfig,
    http_client: openai.DefaultAsyncHttpxClient,
) -> ChatOpenAI:
    """自由聊天流式模型：供应商卡自选 OpenAI 兼容端点，stream_usage 让末块带用量。"""
    return ChatOpenAI(
        model=provider.model,
        base_url=provider.base_url,
        api_key=SecretStr(provider.api_key),
        timeout=90,
        max_retries=0,
        http_async_client=http_client,
        stream_usage=True,
    )


@dataclass(frozen=True)
class _StructuredCallResult:
    content: BaseModel
    token_usage: dict[str, object]
    latency_ms: int


async def write_llm_call_log(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    graph_name: str,
    graph_node: str,
    model: str,
    prompt_version: str,
    token_usage: dict[str, object],
    latency_ms: int,
    retrieval_count: int | None = None,
    error_code: str | None = None,
) -> None:
    """llm_call_logs 统一埋点（只记元数据，不落 prompt 与输出正文）。

    retrieval_count：本轮资料检索命中数（未检索=None，检索了=命中合计）。
    埋点失败不得影响主流程：吞掉并记 error code。
    """
    try:
        async with session_factory() as session, session.begin():
            session.add(
                LlmCallLog(
                    request_id=str(uuid4()),
                    graph_name=graph_name,
                    graph_node=graph_node,
                    model=model,
                    prompt_version=prompt_version,
                    embedding_model=None,
                    token_usage_json=json.dumps(token_usage, separators=(",", ":")),
                    latency_ms=latency_ms,
                    retrieval_count=retrieval_count,
                    evidence_count=None,
                    interrupt_count=0,
                    error_code=error_code,
                    created_at=utcnow(),
                )
            )
    except Exception:
        logger.error("llm_call_log_failed", error_code="LLM_CALL_LOG_FAILED")


async def _call_structured_model(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    structured_model: StructuredModel,
    provider: LlmProviderConfig,
    prompt: str,
    graph_name: str,
    graph_node: str,
    prompt_version: str,
    output_schema: type[BaseModel],
    invalid_output_code: str,
) -> _StructuredCallResult:
    started = perf_counter()
    token_usage: dict[str, object] = {}
    error_code: str | None = None
    content: BaseModel | None = None
    failure: StructuredGenerationError | None = None
    try:
        result = await structured_model.generate(
            base_url=provider.base_url,
            api_key=provider.api_key,
            model=provider.model,
            prompt=prompt,
        )
        token_usage = result.token_usage
        content = output_schema.model_validate(result.output)
    except (ValidationError, OutputParserException) as exc:
        error_code = invalid_output_code
        failure = StructuredGenerationError(error_code)
        failure.__cause__ = exc
    except Exception as exc:
        error_code = "PROVIDER_REQUEST_FAILED"
        failure = StructuredGenerationError(error_code)
        failure.__cause__ = exc
    latency_ms = max(0, round((perf_counter() - started) * 1000))
    await write_llm_call_log(
        session_factory=session_factory,
        graph_name=graph_name,
        graph_node=graph_node,
        model=provider.model,
        prompt_version=prompt_version,
        token_usage=token_usage,
        latency_ms=latency_ms,
        error_code=error_code,
    )
    if failure is not None:
        # 结构化失败此前全程无日志（错误码只进 DB）；真实校验错误内联进消息，
        # loguru 默认 sink 不渲染 extra kwargs，只记事件名会再次丢失原因。
        detail = str(failure.__cause__)[:300] if failure.__cause__ is not None else ""
        logger.warning(
            f"structured_generation_failed graph={graph_name} node={graph_node} "
            f"error={error_code} detail={detail}"
        )
        raise failure
    if content is None:
        raise StructuredGenerationError(invalid_output_code)
    return _StructuredCallResult(content, token_usage, latency_ms)


async def call_summary_model(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    summary_model: SummaryModel,
    provider: LlmProviderConfig,
    prompt: str,
    graph_name: str,
    graph_node: str,
    prompt_version: str,
) -> SummaryCallResult:
    result = await _call_structured_model(
        session_factory=session_factory,
        structured_model=summary_model,
        provider=provider,
        prompt=prompt,
        graph_name=graph_name,
        graph_node=graph_node,
        prompt_version=prompt_version,
        output_schema=SummaryContent,
        invalid_output_code="INVALID_STRUCTURED_OUTPUT",
    )
    return SummaryCallResult(
        content=cast(SummaryContent, result.content),
        token_usage=result.token_usage,
        latency_ms=result.latency_ms,
    )


async def call_knowledge_point_model(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    knowledge_point_model: KnowledgePointModel,
    provider: LlmProviderConfig,
    prompt: str,
    prompt_version: str,
) -> KnowledgePointCallResult:
    result = await _call_structured_model(
        session_factory=session_factory,
        structured_model=knowledge_point_model,
        provider=provider,
        prompt=prompt,
        graph_name="knowledge-points",
        graph_node="generate",
        prompt_version=prompt_version,
        output_schema=KnowledgePointBatch,
        invalid_output_code="LLM_OUTPUT_INVALID",
    )
    return KnowledgePointCallResult(
        content=cast(KnowledgePointBatch, result.content),
        token_usage=result.token_usage,
        latency_ms=result.latency_ms,
    )


async def call_quiz_model(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    quiz_model: QuizModel,
    provider: LlmProviderConfig,
    prompt: str,
    prompt_version: str,
) -> QuizCallResult:
    result = await _call_structured_model(
        session_factory=session_factory,
        structured_model=quiz_model,
        provider=provider,
        prompt=prompt,
        graph_name="quiz",
        graph_node="generate",
        prompt_version=prompt_version,
        output_schema=QuizBatch,
        invalid_output_code="LLM_OUTPUT_INVALID",
    )
    return QuizCallResult(
        content=cast(QuizBatch, result.content),
        token_usage=result.token_usage,
        latency_ms=result.latency_ms,
    )


async def call_quiz_grading_model(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    quiz_grading_model: QuizGradingModel,
    provider: LlmProviderConfig,
    prompt: str,
    prompt_version: str,
) -> QuizGradingCallResult:
    result = await _call_structured_model(
        session_factory=session_factory,
        structured_model=quiz_grading_model,
        provider=provider,
        prompt=prompt,
        graph_name="quiz",
        graph_node="grade",
        prompt_version=prompt_version,
        output_schema=ShortAnswerGrade,
        invalid_output_code="LLM_OUTPUT_INVALID",
    )
    return QuizGradingCallResult(
        content=cast(ShortAnswerGrade, result.content),
        token_usage=result.token_usage,
        latency_ms=result.latency_ms,
    )


async def call_todo_model(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    todo_model: TodoModel,
    provider: LlmProviderConfig,
    prompt: str,
    prompt_version: str,
) -> TodoCallResult:
    result = await _call_structured_model(
        session_factory=session_factory,
        structured_model=todo_model,
        provider=provider,
        prompt=prompt,
        graph_name="todo",
        graph_node="generate",
        prompt_version=prompt_version,
        output_schema=TodoBatch,
        invalid_output_code="LLM_OUTPUT_INVALID",
    )
    return TodoCallResult(
        content=cast(TodoBatch, result.content),
        token_usage=result.token_usage,
        latency_ms=result.latency_ms,
    )


async def call_review_material_model(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    review_material_model: ReviewMaterialModel,
    provider: LlmProviderConfig,
    prompt: str,
    prompt_version: str,
) -> ReviewMaterialCallResult:
    result = await _call_structured_model(
        session_factory=session_factory,
        structured_model=review_material_model,
        provider=provider,
        prompt=prompt,
        graph_name="review-material",
        graph_node="generate",
        prompt_version=prompt_version,
        output_schema=ReviewMaterialDraft,
        invalid_output_code="LLM_OUTPUT_INVALID",
    )
    return ReviewMaterialCallResult(
        # 实际为 ReviewMaterialDraft 实例；调用方（worker._call）确定性归一后使用
        content=cast(ReviewMaterialContent, result.content),
        token_usage=result.token_usage,
        latency_ms=result.latency_ms,
    )


async def call_course_brain_model(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    course_brain_model: CourseBrainModel,
    provider: LlmProviderConfig,
    prompt: str,
    prompt_version: str,
) -> CourseBrainCallResult:
    result = await _call_structured_model(
        session_factory=session_factory,
        structured_model=course_brain_model,
        provider=provider,
        prompt=prompt,
        graph_name="course-brain",
        graph_node="extract",
        prompt_version=prompt_version,
        output_schema=CourseBrainExtractionBatch,
        invalid_output_code="INVALID_STRUCTURED_OUTPUT",
    )
    return CourseBrainCallResult(
        content=cast(CourseBrainExtractionBatch, result.content),
        token_usage=result.token_usage,
        latency_ms=result.latency_ms,
    )


async def call_organize_model(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    organize_model: StructuredModel,
    provider: LlmProviderConfig,
    prompt: str,
    prompt_version: str,
) -> OrganizeSuggestionBatch:
    """AI 整理建议生成（工单 05）：结构化输出 = 每条目可选标题/课程建议。"""
    result = await _call_structured_model(
        session_factory=session_factory,
        structured_model=organize_model,
        provider=provider,
        prompt=prompt,
        graph_name="library-organize",
        graph_node="propose",
        prompt_version=prompt_version,
        output_schema=OrganizeSuggestionBatch,
        invalid_output_code="LLM_OUTPUT_INVALID",
    )
    return cast(OrganizeSuggestionBatch, result.content)


async def call_plan_draft_model(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    plan_draft_model: PlanDraftModel,
    provider: LlmProviderConfig,
    prompt: str,
    prompt_version: str,
) -> PlanDraftCallResult:
    """学习计划草案生成（第三阶段工单 02）：结构化输出 = 阶段 + 逐项参数。

    日期不进 LLM 契约——排期由 learning_plan.scheduling 确定性铺排。"""
    result = await _call_structured_model(
        session_factory=session_factory,
        structured_model=plan_draft_model,
        provider=provider,
        prompt=prompt,
        graph_name="learning-plan",
        graph_node="generate",
        prompt_version=prompt_version,
        output_schema=PlanDraft,
        invalid_output_code="LLM_OUTPUT_INVALID",
    )
    return PlanDraftCallResult(
        content=cast(PlanDraft, result.content),
        token_usage=result.token_usage,
        latency_ms=result.latency_ms,
    )


async def call_plan_suggestions_model(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    plan_suggestions_model: PlanSuggestionsModel,
    provider: LlmProviderConfig,
    prompt: str,
    prompt_version: str,
) -> PlanSuggestionsCallResult:
    """无资料路径建议生成（工单 02）：建议学习内容 + 资料缺口清单。"""
    result = await _call_structured_model(
        session_factory=session_factory,
        structured_model=plan_suggestions_model,
        provider=provider,
        prompt=prompt,
        graph_name="learning-plan",
        graph_node="suggest",
        prompt_version=prompt_version,
        output_schema=PlanSuggestions,
        invalid_output_code="LLM_OUTPUT_INVALID",
    )
    return PlanSuggestionsCallResult(
        content=cast(PlanSuggestions, result.content),
        token_usage=result.token_usage,
        latency_ms=result.latency_ms,
    )
