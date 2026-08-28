"""自由聊天 agent：上下文组装（每轮从 chat_messages 显式重建）与流式生成路径。"""

from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, cast

import openai
from langchain.agents import (
    create_agent,  # pyright: ignore[reportUnknownVariableType]
)
from langchain.agents.middleware.types import (  # pyright: ignore[reportMissingTypeStubs]
    AgentState,
    InputAgentState,
    OutputAgentState,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    HumanMessage,
    SystemMessage,
)
from langgraph.checkpoint.base import BaseCheckpointSaver  # pyright: ignore[reportMissingTypeStubs]
from langgraph.graph.state import (  # pyright: ignore[reportMissingTypeStubs]
    CompiledStateGraph,
)
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.llm import build_chat_model, write_llm_call_log
from app.schemas.chat import ChatRole
from app.services.local_config import LlmProviderConfig

# 部署级语义常量（当前后端不读 .env、无 pydantic-settings；配置体系统一后迁移）。
CHAT_CONTEXT_CHAR_BUDGET = 60000
CHAT_CONTEXT_MAX_TURNS = 10
CHAT_PROMPT_VERSION = "chat-free-v1"
CHAT_RECURSION_LIMIT = 25


@dataclass(frozen=True)
class ContextRow:
    """chat_messages 行喂入上下文组装的最小投影（id 用作喂入消息的稳定 ID）。"""

    id: str
    role: ChatRole
    content: str


@dataclass
class ChatStreamOutcome:
    """流式生成的用量回传（llm_call_logs 与 assistant 行落库共用）。"""

    token_usage: dict[str, object] = field(default_factory=dict[str, object])


@dataclass(frozen=True)
class _Turn:
    user: ContextRow
    assistant: ContextRow


def _split_turns(
    rows: Sequence[ContextRow],
) -> tuple[ContextRow | None, list[_Turn], ContextRow | None]:
    """拆出 SYSTEM 快照、成功完成的轮次，以及末尾未获回复的 user（无则 None）。

    1 轮 = 一条成功完成的 user→assistant 往返；中断轮不计入轮次窗口（spec #39）。
    """
    system_row = next((item for item in rows if item.role == ChatRole.SYSTEM), None)
    turns: list[_Turn] = []
    trailing_user: ContextRow | None = None
    for item in rows:
        if item.role in (ChatRole.SYSTEM, ChatRole.TOOL):
            continue
        if item.role == ChatRole.USER:
            trailing_user = item
        elif item.role == ChatRole.ASSISTANT and trailing_user is not None:
            turns.append(_Turn(user=trailing_user, assistant=item))
            trailing_user = None
    return system_row, turns, trailing_user


def _turns_chars(
    system_row: ContextRow | None, turns: Sequence[_Turn], trailing: ContextRow | None
) -> int:
    total = len(system_row.content) if system_row is not None else 0
    for turn in turns:
        total += len(turn.user.content) + len(turn.assistant.content)
    if trailing is not None:
        total += len(trailing.content)
    return total


def build_context_messages(
    rows: Sequence[ContextRow],
    *,
    budget: int = CHAT_CONTEXT_CHAR_BUDGET,
) -> list[AnyMessage]:
    """把会话全部消息行组装为喂入 LLM 的上下文。

    - SYSTEM 快照（会话创建时落库的角色注入）恒在且在最前；
    - 只保留最近 CHAT_CONTEXT_MAX_TURNS 个完成轮，末尾未获回复的 user（当前提问）额外附加；
    - 超出字符预算时从最旧完成轮继续丢弃，当前提问永不丢弃。
    """
    system_row, turns, trailing_user = _split_turns(rows)
    turns = turns[-CHAT_CONTEXT_MAX_TURNS:]
    while turns and _turns_chars(system_row, turns, trailing_user) > budget:
        turns = turns[1:]
    messages: list[AnyMessage] = []
    if system_row is not None:
        messages.append(SystemMessage(content=system_row.content, id=system_row.id))
    for turn in turns:
        messages.append(HumanMessage(content=turn.user.content, id=turn.user.id))
        messages.append(AIMessage(content=turn.assistant.content, id=turn.assistant.id))
    if trailing_user is not None:
        messages.append(HumanMessage(content=trailing_user.content, id=trailing_user.id))
    return messages


def build_chat_agent(
    model: BaseChatModel,
    checkpointer: BaseCheckpointSaver[str],
) -> CompiledStateGraph[AgentState[Any], Any, InputAgentState, OutputAgentState[Any]]:
    """自由聊天 agent：工具集为空（检索工具为后续工单），复用 lifespan 的 checkpointer。"""
    return create_agent(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        model=model,
        tools=[],
        checkpointer=checkpointer,
    )


def chat_thread_id(session_id: str) -> str:
    """checkpoint 线程命名；每轮发送前清空，checkpoint 只承载当轮运行态。"""
    return f"chat-{session_id}"


async def stream_chat_reply(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    checkpointer: BaseCheckpointSaver[str],
    provider: LlmProviderConfig,
    context_messages: Sequence[AnyMessage],
    session_id: str,
    outcome: ChatStreamOutcome,
) -> AsyncGenerator[str, None]:
    """工厂层流式生成路径：建模型 → 清残留 → astream 逐 token → 统一埋点。

    - 每轮从 chat_messages 重建喂入：轮初清掉上轮/崩溃残留，checkpoint 只承载当轮运行态；
    - 正常完成埋点（graph_name=chat，仅元数据）并在返回前清理本轮 checkpoint；
    - 中断（GeneratorExit，客户端断开/用户停止）不落埋点直接终止；
    - 其他异常埋点后重新抛出，由调用方转 error 事件。
    """
    thread_id = chat_thread_id(session_id)
    await checkpointer.adelete_thread(thread_id)
    http_client = openai.DefaultAsyncHttpxClient(trust_env=False)
    started = perf_counter()
    try:
        agent = build_chat_agent(build_chat_model(provider, http_client), checkpointer)
        async for chunk, _metadata in agent.astream(  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            {"messages": list(context_messages)},  # pyright: ignore[reportArgumentType, reportUnknownArgumentType]
            config={
                "configurable": {"thread_id": thread_id},
                "recursion_limit": CHAT_RECURSION_LIMIT,
            },
            stream_mode="messages",
        ):
            if not isinstance(chunk, AIMessageChunk):
                continue
            chunk_usage = getattr(chunk, "usage_metadata", None)
            if isinstance(chunk_usage, dict):
                outcome.token_usage = cast(dict[str, object], chunk_usage)
            text = chunk.content if isinstance(chunk.content, str) else ""
            if not text:
                continue
            yield text
    except GeneratorExit:
        # 客户端断开 / 用户停止：半截回答不落库、不落埋点，直接终止。
        raise
    except Exception:
        logger.error("chat_stream_failed", error_code="CHAT_STREAM_FAILED")
        await write_llm_call_log(
            session_factory=session_factory,
            graph_name="chat",
            graph_node="generate",
            model=provider.model,
            prompt_version=CHAT_PROMPT_VERSION,
            token_usage=outcome.token_usage,
            latency_ms=max(0, round((perf_counter() - started) * 1000)),
            error_code="CHAT_STREAM_FAILED",
        )
        raise
    finally:
        await http_client.aclose()
    await write_llm_call_log(
        session_factory=session_factory,
        graph_name="chat",
        graph_node="generate",
        model=provider.model,
        prompt_version=CHAT_PROMPT_VERSION,
        token_usage=outcome.token_usage,
        latency_ms=max(0, round((perf_counter() - started) * 1000)),
        error_code=None,
    )
    await checkpointer.adelete_thread(thread_id)
