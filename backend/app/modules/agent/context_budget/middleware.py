import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, cast

import openai
from langchain.agents.middleware.types import (  # pyright: ignore[reportMissingTypeStubs]
    AgentMiddleware,
    ModelRequest,
)
from langchain_core.messages import SystemMessage, messages_to_dict
from sqlalchemy import and_, or_, select

from app.modules.agent.context_budget.compaction import compact
from app.modules.agent.context_budget.models import ChatModelRequest
from app.modules.agent.context_budget.outputs import project_outputs
from app.modules.agent.context_budget.pins import inject_pins, select_pinned_material, turn_pins
from app.modules.agent.context_budget.policy import estimate_input, request_usage
from app.modules.agent.context_budget.retrieval import (
    validate_read_results,
    validate_summary_messages,
)
from app.modules.agent.context_budget.schemas import (
    ContextPolicy,
    ModelRequestStatus,
)
from app.modules.agent.middleware.cancel_guard import TurnCancelledError
from app.modules.agent.runtime import AgentRuntimeContext
from app.modules.llm.service import chat_output_parameters
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
        await validate_summary_messages(
            self.runtime.session_factory, self.runtime.session_id, request.messages
        )
        request = request.override(
            messages=await validate_read_results(
                self.runtime.session_factory, self.runtime.session_id, request.messages
            )
        )
        # 原始请求跨 checkpoint 恢复不变，摘要只改变本次模型可见投影。
        estimate = estimate_input(
            self.policy,
            ([request.system_message] if request.system_message else []) + request.messages,
            request.tools,
        )
        request_identity = estimate.input_fingerprint
        if self.runtime.execution_id is not None:
            # 子图没有父会话固定项或摘要，完整输入不容纳时由原准入拒绝。
            return await self._invoke(request, handler, request_identity=request_identity)
        if estimate.input_tokens >= estimate.usable_budget * 0.8:
            request = request.override(
                messages=await project_outputs(self.runtime, request.messages)
            )
        pins_json, segment = await turn_pins(self.runtime)
        system, pin_system, _, overflow = await select_pinned_material(
            self.runtime,
            self.policy,
            pins_json,
            segment,
            request.system_message,
            request.messages,
            request.tools,
        )
        request = request.override(system_message=system)
        if overflow:
            return await self._invoke(
                request,
                handler,
                request_identity=request_identity,
                pin_system=pin_system,
            )
        messages = await compact(
            self.runtime,
            self.policy,
            request.messages,
            request.system_message,
            request.tools,
            request.model,
            self._check_outbound,
        )
        request = request.override(messages=messages)
        try:
            return await self._invoke(
                request,
                handler,
                request_identity=request_identity,
                pin_system=pin_system,
            )
        except openai.BadRequestError as exc:
            code = exc.code or ""
            raw_body = cast(object, exc.body)
            body = cast(dict[str, object], raw_body) if isinstance(raw_body, dict) else {}
            message = str(body.get("message", "")).lower()
            if code not in ("context_length_exceeded", "max_context_length_exceeded") and not (
                message.startswith("range of input length should be [1,")
                or ("maximum context length" in message and "tokens" in message)
            ):
                raise
            # 只重试当前模型请求；handler 不执行已提交的工具节点。
            messages = await compact(
                self.runtime,
                self.policy,
                request.messages,
                request.system_message,
                request.tools,
                request.model,
                self._check_outbound,
                force=True,
            )
            if messages == request.messages:
                raise
            return await self._invoke(
                request.override(messages=messages),
                handler,
                request_identity=request_identity,
                retry_of=request_identity,
                pin_system=pin_system,
            )

    async def _invoke(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[Any]],
        *,
        request_identity: str,
        retry_of: str | None = None,
        pin_system: SystemMessage | None = None,
    ) -> Any:
        await self._check_outbound()
        await validate_summary_messages(
            self.runtime.session_factory, self.runtime.session_id, request.messages
        )
        request = request.override(
            messages=await validate_read_results(
                self.runtime.session_factory, self.runtime.session_id, request.messages
            )
        )
        if self.runtime.execution_id is not None:
            system, pins, overflow = request.system_message, [], False
        else:
            pins_json, segment = await turn_pins(self.runtime)
            system, pins, overflow = await inject_pins(
                self.runtime.session_factory,
                self.runtime.session_id,
                pins_json,
                segment,
                pin_system,
                request.messages,
                request.tools,
                self.policy,
            )
        request = request.override(system_message=system)
        messages = ([request.system_message] if request.system_message else []) + request.messages
        estimate = estimate_input(self.policy, messages, request.tools)
        if overflow:
            estimate.error_code = "CONTEXT_PINS_TOO_LARGE"
        request = request.override(
            model_settings={
                **request.model_settings,
                **chat_output_parameters(self.policy.base_url, estimate.output_reserve),
            }
        )
        messages_json = json.dumps(messages_to_dict(request.messages), ensure_ascii=False)
        row = ChatModelRequest(
            turn_id=self.runtime.turn_id,
            execution_id=self.runtime.execution_id,
            execution_attempt=self.runtime.execution_attempt,
            decision_id=self.runtime.decision_id,
            status=ModelRequestStatus.BLOCKED
            if estimate.error_code
            else ModelRequestStatus.STARTED,
            input_fingerprint=estimate.input_fingerprint,
            estimate_json=estimate.model_dump_json(),
            error_code=estimate.error_code,
            messages_json=messages_json,
            retry_of=retry_of or self.runtime.retry_request_id,
            pins_json=json.dumps(
                [pin.model_dump(mode="json") for pin in pins or []], ensure_ascii=False
            ),
        )
        async with self.runtime.session_factory() as session, session.begin():
            if not await self.runtime.turn_write_allowed(session):
                raise TurnCancelledError
            if self.runtime.execution_id is not None:
                from app.modules.agent.delegations.models import AgentDelegation
                from app.modules.agent.delegations.service import unresolved_requests
                from app.modules.agent.delegations.worker import DelegationUncertain

                child = await session.get(AgentDelegation, self.runtime.execution_id)
                assert child is not None
                unknown = await unresolved_requests(session, child)
                if unknown and unknown != [self.runtime.retry_request_id]:
                    raise DelegationUncertain
                completed = await session.scalar(
                    select(ChatModelRequest.id)
                    .where(
                        ChatModelRequest.turn_id == self.runtime.turn_id,
                        ChatModelRequest.execution_id == self.runtime.execution_id,
                        ChatModelRequest.execution_attempt < self.runtime.execution_attempt,
                        # 兄弟消费可改变额度提示和工具集合，恢复仍是同一条冻结消息链。
                        ChatModelRequest.messages_json == messages_json,
                        ChatModelRequest.status == ModelRequestStatus.COMPLETED,
                    )
                    .limit(1)
                )
                if completed is not None:
                    raise CodedHTTPException(
                        code="CHAT_TURN_RESUME_UNSAFE",
                        status_code=409,
                        detail="原模型请求已完成但图节点结果未保存，不能安全重发，请停止后新任务",
                    )
            if await session.scalar(
                select(ChatModelRequest.id)
                .where(
                    ChatModelRequest.turn_id == self.runtime.turn_id,
                    ChatModelRequest.execution_id == self.runtime.execution_id,
                    ChatModelRequest.decision_id.is_(None),
                    or_(
                        ChatModelRequest.retry_of == request_identity,
                        # 旧版已准入重试仍按恢复后的实际输入识别，不补发请求。
                        and_(
                            ChatModelRequest.retry_of.is_not(None),
                            ChatModelRequest.input_fingerprint == estimate.input_fingerprint,
                        ),
                    ),
                )
                .limit(1)
            ):
                raise CodedHTTPException(
                    code="MODEL_INPUT_BUDGET_EXCEEDED",
                    status_code=409,
                    detail="该请求的超限重试已用尽",
                )
            session.add(row)
        self.runtime.retry_request_id = None
        if estimate.error_code:
            raise CodedHTTPException(
                code=estimate.error_code,
                status_code=409,
                detail="完整模型输入超过可用预算，请缩短提问、调整材料或模型能力配置",
            )
        try:
            response = await handler(request)
        except (openai.APIConnectionError, openai.APITimeoutError):
            if self.runtime.execution_id is not None:
                from app.modules.agent.delegations.worker import DelegationUncertain

                raise DelegationUncertain from None
            await self._finish(row.id, ModelRequestStatus.FAILED, None, "CHAT_STREAM_FAILED")
            raise
        except Exception:
            await self._finish(
                row.id,
                ModelRequestStatus.FAILED,
                None,
                "MODEL_INPUT_BUDGET_EXCEEDED" if retry_of else None,
            )
            raise
        usage = next(
            (
                message.usage_metadata
                for message in reversed(response.result)
                if getattr(message, "usage_metadata", None) is not None
            ),
            None,
        )
        await self._finish(row.id, ModelRequestStatus.COMPLETED, request_usage(usage))
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

    async def _finish(
        self,
        request_id: str,
        status: ModelRequestStatus,
        usage: object,
        error_code: str | None = None,
    ) -> None:
        await self._check_outbound()
        async with self.runtime.session_factory() as session, session.begin():
            if not await self.runtime.turn_write_allowed(session):
                raise TurnCancelledError
            row = await session.get(ChatModelRequest, request_id)
            if row is not None:
                if (
                    row.turn_id != self.runtime.turn_id
                    or row.execution_id != self.runtime.execution_id
                ):
                    raise TurnCancelledError
                row.status = status
                row.error_code = (
                    error_code or "CHAT_STREAM_FAILED"
                    if status == ModelRequestStatus.FAILED
                    else None
                )
                row.usage_json = json.dumps(usage) if usage is not None else None
