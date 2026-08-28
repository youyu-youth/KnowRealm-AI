import json
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol, cast
from uuid import uuid4

import openai
from langchain_openai import ChatOpenAI
from loguru import logger
from pydantic import BaseModel, SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.base import utcnow
from app.models.document import LlmCallLog
from app.schemas.knowledge_point import KnowledgePointBatch
from app.schemas.quiz import QuizBatch
from app.schemas.summary import SummaryContent
from app.schemas.todo import TodoBatch
from app.services.local_config import LlmProviderConfig


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
class TodoCallResult:
    content: TodoBatch
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
TodoModel = StructuredModel


class StructuredGenerationError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


SummaryGenerationError = StructuredGenerationError


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
            except openai.BadRequestError:
                # 端点不支持 json_schema（如 DeepSeek 只接受 json_object）。
                # 400 拒绝请求不计费，此降级不构成额外的付费重试。
                raw_response = await self._generate_json_mode(llm, prompt)
            output = raw_response.get("parsed")
            raw_message = raw_response.get("raw")
            usage = getattr(raw_message, "usage_metadata", None)
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
        schema_text = json.dumps(self._output_schema.model_json_schema(), ensure_ascii=False)
        # json_object 端点依赖提示词携带结构；8192 为推理模型（思考与正文同计费）留足输出空间
        json_prompt = (
            prompt
            + "\n必须只返回一个符合以下 JSON Schema 的 JSON 对象，不要输出其他内容：\n"
            + schema_text
        )
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


class OpenAiCompatibleTodoModel(_OpenAiCompatibleStructuredModel):
    def __init__(self) -> None:
        super().__init__(TodoBatch)


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
    error_code: str | None = None,
) -> None:
    """llm_call_logs 统一埋点（只记元数据，不落 prompt 与输出正文）。

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
                    retrieval_count=None,
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
    except ValidationError as exc:
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
