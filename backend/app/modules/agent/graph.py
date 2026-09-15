"""deepagents 骨架装配与流式生成路径：AgentConfig 变体、图工厂与 SSE 结构化事件分发。"""

import json
from collections.abc import AsyncGenerator, Sequence
from contextvars import Token
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, cast

import openai
from deepagents import (
    create_deep_agent,  # pyright: ignore[reportMissingTypeStubs, reportUnknownVariableType]
)
from deepagents.backends.protocol import (  # pyright: ignore[reportMissingTypeStubs]
    BackendProtocol,
)
from langchain.agents.middleware.types import (  # pyright: ignore[reportMissingTypeStubs]
    AgentMiddleware,
    AgentState,
    InputAgentState,
    OutputAgentState,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessageChunk,
    AnyMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.checkpoint.base import BaseCheckpointSaver  # pyright: ignore[reportMissingTypeStubs]
from langgraph.graph.state import (  # pyright: ignore[reportMissingTypeStubs]
    CompiledStateGraph,
)
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.agent.context import MountedMaterial
from app.modules.agent.middleware.skeleton import (
    ExcludeDeepAgentToolsMiddleware,
    NoopSummarizationMiddleware,
)
from app.modules.agent.tools.search_library import (
    LibrarySearchContext,
    bind_library_context,
    reset_library_context,
    search_library,
)
from app.modules.agent.tools.search_transcript import (
    SearchTranscriptContext,
    bind_search_context,
    reset_search_context,
    search_transcript,
)
from app.modules.agent.tools.web_search import (
    bind_web_search,
    reset_web_search,
    web_search,
)
from app.modules.llm.service import build_chat_model, write_llm_call_log
from app.modules.search.web_search import SearchProvider
from app.modules.settings.config import LlmProviderConfig

CHAT_PROMPT_VERSION = "chat-concept-v6"
CHAT_RECURSION_LIMIT = 25


@dataclass
class ChatStreamOutcome:
    """流式生成的用量回传（llm_call_logs 与 assistant 行落库共用）。"""

    token_usage: dict[str, object] = field(default_factory=dict[str, object])


@dataclass(frozen=True)
class ChatTokenEvent:
    """流式文本增量。"""

    text: str


@dataclass(frozen=True)
class ChatToolCallEvent:
    """工具调用开始：SSE 载荷 {tool, query}。"""

    tool: str
    query: str


@dataclass(frozen=True)
class ChatToolResultEvent:
    """工具调用结束：SSE 载荷 {tool, hits, ok}（执行失败 ok=False）。"""

    tool: str
    hits: int
    ok: bool


ChatStreamEvent = ChatTokenEvent | ChatToolCallEvent | ChatToolResultEvent


# ---------------------------------------------------------------------------
# deepagents 骨架装配层：严格空骨架，模型可见面（工具列表 / 提示组装）与
# create_agent 时代一致；能力扩展经 AgentConfig 逐项开启（ADR-0018）。
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentConfig:
    """chat 系 agent 的 deepagents 装配配置；新变体（Tutor 等）= 新增常量实例。

    扩展点（按后续工单逐项开启；启用内置工具须同步调整 middleware/skeleton 的
    DEEPAGENT_TOOL_NAMES）：
    - tools：追加工具（检索等），与 deepagents 内置工具并存；
    - subagents：子代理规格，非空时 task 工具才有意义；
    - skills：技能源（SKILL.md 渐进加载，需配合 backend 提供文件）；
    - backend：文件后端（虚拟文件上下文 / 大输出落盘等能力的前提）；
    - middleware：附加中间件（错误归一、超时等横切能力）。
    """

    tools: tuple[Any, ...] = ()
    subagents: tuple[Any, ...] = ()
    skills: tuple[str, ...] | None = None
    backend: BackendProtocol | None = None
    middleware: tuple[AgentMiddleware[Any, Any, Any], ...] = ()  # pyright: ignore[reportMissingTypeStubs]


CHAT_AGENT_CONFIG = AgentConfig()
# 挂载变体：带 search_transcript 检索工具；自由聊天维持空配置（ADR-0018 变体=常量）。
MOUNTED_CHAT_AGENT_CONFIG = AgentConfig(tools=(search_transcript,))
# 课程 / 全部范围变体（B2）：带 search_library 跨记录检索工具（与 search_transcript 互斥）。
LIBRARY_CHAT_AGENT_CONFIG = AgentConfig(tools=(search_library,))


def _resolve_agent_config(*, mounted: bool, library: bool, web_search_enabled: bool) -> AgentConfig:
    """按「scope × web_search」组合出当轮装配（B2）：既有变体维持常量，
    web_search 生效时在其基础上追加工具（frozen dataclass 实例化）。
    mounted 与 library 互斥（RECORD 挂 search_transcript，COURSE/ALL 挂
    search_library），同时为真按 library 优先（调用方不会产生该组合）。"""
    if library:
        config = LIBRARY_CHAT_AGENT_CONFIG
    elif mounted:
        config = MOUNTED_CHAT_AGENT_CONFIG
    else:
        config = CHAT_AGENT_CONFIG
    if web_search_enabled:
        config = AgentConfig(tools=(*config.tools, web_search))
    return config


def build_agent(
    config: AgentConfig,
    model: BaseChatModel,
    checkpointer: BaseCheckpointSaver[str],
    *,
    system_prompt: SystemMessage | None,
) -> CompiledStateGraph[AgentState[Any], Any, InputAgentState, OutputAgentState[Any]]:
    """按配置装配 deep agent。

    system_prompt 必须经参数注入：deepagents 会把组装结果（哪怕空串）传给
    create_agent 的 system_prompt 参数，输入 messages 里的 SystemMessage 会被
    覆盖丢弃（已实测 0.7.13），混入消息不生效。
    """
    return create_deep_agent(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        model=model,
        tools=list(config.tools),
        system_prompt=system_prompt,
        subagents=list(config.subagents) or None,
        skills=list(config.skills) if config.skills is not None else None,
        backend=config.backend,
        middleware=[
            ExcludeDeepAgentToolsMiddleware(),
            NoopSummarizationMiddleware(),
            *config.middleware,
        ],
        checkpointer=checkpointer,
    )


def build_chat_agent(
    model: BaseChatModel,
    checkpointer: BaseCheckpointSaver[str],
    *,
    system_prompt: SystemMessage | None,
    config: AgentConfig = CHAT_AGENT_CONFIG,
) -> CompiledStateGraph[AgentState[Any], Any, InputAgentState, OutputAgentState[Any]]:
    """chat agent 装配：config 决定能力面（自由聊天空配置 / 挂载变体带检索工具），
    复用 lifespan 的 checkpointer。"""
    return build_agent(config, model, checkpointer, system_prompt=system_prompt)


def chat_thread_id(session_id: str) -> str:
    """checkpoint 线程命名；每轮发送前清空，checkpoint 只承载当轮运行态。"""
    return f"chat-{session_id}"


def _accumulate_usage(total: dict[str, object], usage: object) -> None:
    """把单次模型调用的 usage_metadata 累加进总量（工具循环 = 多次调用求和）。"""
    if not isinstance(usage, dict):
        return
    chunk_usage = cast(dict[str, object], usage)
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = chunk_usage.get(key)
        if isinstance(value, int):
            current = total.get(key)
            total[key] = (current if isinstance(current, int) else 0) + value


@dataclass
class _ToolCallDraft:
    """一次工具调用的流式拼装：名称取首个非空片段，args 逐片累加。"""

    name: str = ""
    args: str = ""
    emitted: bool = False


def _consume_tool_call_fragments(
    drafts: dict[int, _ToolCallDraft], chunk: AIMessageChunk
) -> list[ChatToolCallEvent]:
    """消费 tool_call_chunks 增量：args 严格 JSON 解析成功（拼装完整）才上报 query。

    不能读 ``AIMessageChunk.tool_calls``：它对未闭合的 args 做部分解析（实测
    1.6.3 会把 ``{"query": "傅里叶`` 解析成截断 query），会导致检索词提前上报。
    """
    events: list[ChatToolCallEvent] = []
    for fragment in chunk.tool_call_chunks:
        index = fragment.get("index")
        if not isinstance(index, int):
            continue
        draft = drafts.setdefault(index, _ToolCallDraft())
        name = fragment.get("name")
        if not draft.name and isinstance(name, str) and name:
            draft.name = name
        args_fragment = fragment.get("args")
        if isinstance(args_fragment, str) and args_fragment:
            draft.args += args_fragment
        if draft.emitted or not draft.name or not draft.args:
            continue
        try:
            parsed = json.loads(draft.args)
        except ValueError:
            continue
        if not isinstance(parsed, dict):
            continue
        query = cast(dict[str, object], parsed).get("query")
        if not isinstance(query, str) or not query:
            continue
        draft.emitted = True
        events.append(ChatToolCallEvent(tool=draft.name, query=query))
    return events


def _tool_result_event(message: ToolMessage) -> ChatToolResultEvent:
    """ToolMessage → {tool, hits, ok}；错误态 ok=False，命中数从工具 JSON 载荷读取。

    web_search 失败走「错误 JSON 载荷」路径（模型可据此说明、流不中断）：
    ToolMessage status 仍为 success，由载荷内 ok=false 标记失败（B1）。
    """
    if message.status == "error":
        return ChatToolResultEvent(tool=message.name or "", hits=0, ok=False)
    hits = 0
    ok = True
    if isinstance(message.content, str):
        try:
            payload = json.loads(message.content)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            value = cast(dict[str, object], payload).get("hits")
            if isinstance(value, list):
                hits = len(cast(list[object], value))
            ok_value = cast(dict[str, object], payload).get("ok")
            if isinstance(ok_value, bool):
                ok = ok_value
    return ChatToolResultEvent(tool=message.name or "", hits=hits, ok=ok)


async def stream_chat_reply(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    checkpointer: BaseCheckpointSaver[str],
    provider: LlmProviderConfig,
    context_messages: Sequence[AnyMessage],
    session_id: str,
    outcome: ChatStreamOutcome,
    mounted: MountedMaterial | None = None,
    library: LibrarySearchContext | None = None,
    web_search: SearchProvider | None = None,
) -> AsyncGenerator[ChatStreamEvent, None]:
    """工厂层流式生成路径：建模型 → 清残留 → astream 分发结构化流事件 → 统一埋点。

    - 每轮从 chat_messages 重建喂入：轮初清掉上轮/崩溃残留，checkpoint 只承载当轮运行态；
    - 挂载会话（mounted）注入检索工具与运行期上下文；课程 / 全部范围会话（library）
    注入 search_library 与范围上下文（与 mounted 互斥）；web_search 非 None 时挂载
      联网工具并绑定凭据（每请求组合装配）；自由聊天空配置；
    - 事件分发：AIMessageChunk 文本 → token、tool_call_chunks 拼全 → tool_call、
      ToolMessage → tool_result；token 用量跨工具循环累加；
    - 正常完成埋点（graph_name=chat，仅元数据）并在返回前清理本轮 checkpoint；
    - 中断（GeneratorExit，客户端断开/用户停止）不落埋点直接终止；
    - 其他异常埋点后重新抛出，由调用方转 error 事件。
    """
    thread_id = chat_thread_id(session_id)
    await checkpointer.adelete_thread(thread_id)
    http_client = openai.DefaultAsyncHttpxClient(trust_env=False)
    started = perf_counter()
    # 业务 system 提示经 build_chat_agent 参数注入（deepagents 下混入 messages 会被丢弃），
    # 其余消息（轮次窗口 + 当前提问）照常作为对话历史喂入。
    system_prompt = next((m for m in context_messages if isinstance(m, SystemMessage)), None)
    input_messages = [m for m in context_messages if not isinstance(m, SystemMessage)]
    # 挂载会话：绑定检索工具上下文（record_id 与 transcript 成对，见 MountedMaterial）；
    # 课程 / 全部范围：绑定跨记录检索范围（scope 与 course_id，见 LibrarySearchContext）；
    # web_search 生效：绑定联网搜索凭据（无 key 时调用方已强制不传）。
    search_token: Token[SearchTranscriptContext | None] | None = None
    if mounted is not None:
        search_token = bind_search_context(
            SearchTranscriptContext(
                record_id=mounted.record_id,
                transcript=mounted.transcript,
                session_factory=session_factory,
            )
        )
    library_token: Token[LibrarySearchContext | None] | None = None
    if library is not None:
        library_token = bind_library_context(
            LibrarySearchContext(
                scope=library.scope,
                course_id=library.course_id,
                session_factory=library.session_factory,
            )
        )
    web_token: Token[SearchProvider | None] | None = None
    if web_search is not None:
        web_token = bind_web_search(web_search)
    try:
        agent = build_chat_agent(
            build_chat_model(provider, http_client),
            checkpointer,
            system_prompt=system_prompt,
            config=_resolve_agent_config(
                mounted=search_token is not None,
                library=library_token is not None,
                web_search_enabled=web_token is not None,
            ),
        )
        tool_call_drafts: dict[int, _ToolCallDraft] = {}
        async for chunk, _metadata in agent.astream(  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            {"messages": input_messages},  # pyright: ignore[reportArgumentType, reportUnknownArgumentType]
            config={
                "configurable": {"thread_id": thread_id},
                "recursion_limit": CHAT_RECURSION_LIMIT,
            },
            stream_mode="messages",
        ):
            if isinstance(chunk, AIMessageChunk):
                _accumulate_usage(outcome.token_usage, getattr(chunk, "usage_metadata", None))
                text = chunk.content if isinstance(chunk.content, str) else ""
                if text:
                    yield ChatTokenEvent(text=text)
                if chunk.tool_call_chunks:
                    for event in _consume_tool_call_fragments(tool_call_drafts, chunk):
                        yield event
            elif isinstance(chunk, ToolMessage):
                # 本轮工具执行完毕：拼装草稿在下一次模型调用前清空。
                tool_call_drafts = {}
                yield _tool_result_event(chunk)
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
        if search_token is not None:
            reset_search_context(search_token)
        if library_token is not None:
            reset_library_context(library_token)
        if web_token is not None:
            reset_web_search(web_token)
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
