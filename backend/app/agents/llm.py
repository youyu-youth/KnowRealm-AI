import json
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol, cast
from uuid import uuid4

import openai
from langchain_openai import ChatOpenAI
from loguru import logger
from pydantic import SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.base import utcnow
from app.models.document import LlmCallLog
from app.schemas.summary import SummaryContent
from app.services.local_config import LlmProviderConfig


@dataclass(frozen=True)
class SummaryModelResult:
    output: object
    token_usage: dict[str, object]


@dataclass(frozen=True)
class SummaryCallResult:
    content: SummaryContent
    token_usage: dict[str, object]
    latency_ms: int


class SummaryModel(Protocol):
    async def generate(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> SummaryModelResult: ...


class SummaryGenerationError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class OpenAiCompatibleSummaryModel:
    async def generate(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> SummaryModelResult:
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
                SummaryContent,
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
            return SummaryModelResult(
                output=output,
                token_usage=cast(dict[str, object], usage) if isinstance(usage, dict) else {},
            )
        finally:
            await http_client.aclose()

    @staticmethod
    async def _generate_json_mode(
        llm: ChatOpenAI,
        prompt: str,
    ) -> dict[str, object]:
        structured = llm.with_structured_output(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            SummaryContent,
            method="json_mode",
            include_raw=True,
            max_tokens=8192,
        )
        schema_text = json.dumps(SummaryContent.model_json_schema(), ensure_ascii=False)
        # json_object 端点依赖提示词携带结构；8192 为推理模型（思考与正文同计费）留足输出空间
        json_prompt = (
            prompt
            + "\n必须只返回一个符合以下 JSON Schema 的 JSON 对象，不要输出其他内容：\n"
            + schema_text
        )
        return cast(dict[str, object], await structured.ainvoke(json_prompt))


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
    request_id = str(uuid4())
    started = perf_counter()
    token_usage: dict[str, object] = {}
    error_code: str | None = None
    content: SummaryContent | None = None
    failure: SummaryGenerationError | None = None
    try:
        result = await summary_model.generate(
            base_url=provider.base_url,
            api_key=provider.api_key,
            model=provider.model,
            prompt=prompt,
        )
        token_usage = result.token_usage
        content = SummaryContent.model_validate(result.output)
    except ValidationError as exc:
        error_code = "INVALID_STRUCTURED_OUTPUT"
        failure = SummaryGenerationError(error_code)
        failure.__cause__ = exc
    except Exception as exc:
        error_code = "PROVIDER_REQUEST_FAILED"
        failure = SummaryGenerationError(error_code)
        failure.__cause__ = exc
    latency_ms = max(0, round((perf_counter() - started) * 1000))
    try:
        async with session_factory() as session, session.begin():
            session.add(
                LlmCallLog(
                    request_id=request_id,
                    graph_name=graph_name,
                    graph_node=graph_node,
                    model=provider.model,
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
    if failure is not None:
        raise failure
    if content is None:
        raise SummaryGenerationError("INVALID_STRUCTURED_OUTPUT")
    return SummaryCallResult(content=content, token_usage=token_usage, latency_ms=latency_ms)
