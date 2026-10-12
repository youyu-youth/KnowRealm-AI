import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain.agents.middleware.types import (  # pyright: ignore[reportMissingTypeStubs]
    AgentMiddleware,
    ModelRequest,
)

from app.modules.agent.context_budget.models import ChatModelRequest
from app.modules.agent.context_budget.policy import estimate_input
from app.modules.agent.context_budget.schemas import ContextPolicy
from app.modules.agent.middleware.cancel_guard import TurnCancelledError
from app.modules.agent.runtime import AgentRuntimeContext
from app.modules.settings.config import (
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
    memory_outbound_enabled,
)
from app.shared.errors import CodedHTTPException


class InputBudgetMiddleware(AgentMiddleware[Any, Any, Any]):  # pyright: ignore[reportMissingTypeStubs]
    """最后一层模型 wrap：不裁消息，准入与失败请求均有持久记录。"""

    def __init__(self, runtime: AgentRuntimeContext, policy: ContextPolicy) -> None:
        self.runtime = runtime
        self.policy = policy

    async def awrap_model_call(  # pyright: ignore[reportMissingTypeStubs]
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Awaitable[Any]]
    ) -> Any:
        await self._check_outbound()
        messages = ([request.system_message] if request.system_message else []) + request.messages
        estimate = estimate_input(self.policy, messages, request.tools)
        request = request.override(
            model_settings={**request.model_settings, "max_tokens": estimate.output_reserve}
        )
        row = ChatModelRequest(
            turn_id=self.runtime.turn_id,
            status="BLOCKED" if estimate.error_code else "STARTED",
            input_fingerprint=estimate.input_fingerprint,
            estimate_json=estimate.model_dump_json(),
            error_code=estimate.error_code,
        )
        async with self.runtime.session_factory() as session, session.begin():
            if not await self.runtime.turn_write_allowed(session):
                raise TurnCancelledError
            session.add(row)
        if estimate.error_code:
            raise CodedHTTPException(
                code=estimate.error_code,
                status_code=409,
                detail="完整模型输入超过可用预算，请缩短提问、调整材料或模型能力配置",
            )
        try:
            response = await handler(request)
        except Exception:
            await self._finish(row.id, "FAILED", None)
            raise
        usage = next(
            (
                message.usage_metadata
                for message in reversed(response.result)
                if getattr(message, "usage_metadata", None) is not None
            ),
            None,
        )
        if isinstance(usage, dict):
            usage = {
                key: value
                for key, value in cast(dict[str, object], usage).items()
                if key in ("input_tokens", "output_tokens", "total_tokens")
                and isinstance(value, int)
            } or None
        await self._finish(row.id, "COMPLETED", usage)
        return response

    async def _check_outbound(self) -> None:
        if self.runtime.data_dir is None:
            return
        provider = await asyncio.to_thread(load_llm_provider, self.runtime.data_dir)
        if (
            provider is None
            or not provider.api_key
            or provider.base_url != self.policy.base_url
            or provider.model != self.policy.model
            or llm_provider_fingerprint(provider) != self.runtime.provider_fingerprint
        ):
            raise CodedHTTPException(
                code="CHAT_TURN_RESUME_CONDITION_UNMET",
                status_code=409,
                detail="原轮次 AI 服务或凭据已变更，请恢复原配置或重新提问",
            )
        _, consent = await asyncio.to_thread(llm_consent, self.runtime.data_dir)
        if (self.runtime.outbound_consent_required and not consent) or (
            self.runtime.memory_injected
            and (
                not consent
                or not await asyncio.to_thread(memory_outbound_enabled, self.runtime.data_dir)
            )
        ):
            raise CodedHTTPException(
                code="AI_CONSENT_REQUIRED",
                status_code=409,
                detail="AI 或记忆外发同意已失效，请恢复同意后重新提问",
            )

    async def _finish(self, request_id: str, status: str, usage: object) -> None:
        async with self.runtime.session_factory() as session, session.begin():
            if not await self.runtime.turn_write_allowed(session):
                raise TurnCancelledError
            row = await session.get(ChatModelRequest, request_id)
            if row is not None:
                row.status = status
                row.error_code = "CHAT_STREAM_FAILED" if status == "FAILED" else None
                row.usage_json = json.dumps(usage) if usage is not None else None
