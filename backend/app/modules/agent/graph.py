"""deepagents 骨架装配与流式生成路径：AgentConfig 变体、图工厂与 SSE 结构化事件分发。"""

import json
from collections.abc import AsyncGenerator, Sequence
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

from app.modules.agent.middleware.skeleton import (
    ExcludeDeepAgentToolsMiddleware,
    NoopSummarizationMiddleware,
)
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.schemas import ChatMode, ChatScope
from app.modules.agent.tools.add_text_record import (
    ADD_TEXT_RECORD_TOOL_NAME,
    add_text_record_to_course,
)
from app.modules.agent.tools.archive_course import (
    ARCHIVE_COURSE_TOOL_NAME,
    RESTORE_COURSE_TOOL_NAME,
    archive_course,
    restore_course,
)
from app.modules.agent.tools.archive_library_item import (
    ARCHIVE_LIBRARY_ITEM_TOOL_NAME,
    RESTORE_LIBRARY_ITEM_TOOL_NAME,
    archive_library_item,
    restore_library_item,
)
from app.modules.agent.tools.create_course import (
    CREATE_COURSE_TOOL_NAME,
    create_course,
)
from app.modules.agent.tools.delete_course import (
    DELETE_COURSE_TOOL_NAME,
    delete_course,
)
from app.modules.agent.tools.list_course_records import list_course_records
from app.modules.agent.tools.list_library_items import list_library_items
from app.modules.agent.tools.move_record_course import (
    MOVE_RECORD_COURSE_TOOL_NAME,
    move_record_course,
)
from app.modules.agent.tools.plan_batch_operations import plan_batch_operations
from app.modules.agent.tools.propose_ingest import (
    PROPOSE_INGEST_TOOL_NAME,
    propose_ingest,
)
from app.modules.agent.tools.propose_memory import (
    PROPOSE_MEMORY_TOOL_NAME,
    propose_memory,
)
from app.modules.agent.tools.search_courses import search_courses
from app.modules.agent.tools.search_library import search_library
from app.modules.agent.tools.soft_delete_record import (
    SOFT_DELETE_RECORD_TOOL_NAME,
    soft_delete_record,
)
from app.modules.agent.tools.update_course import (
    UPDATE_COURSE_TOOL_NAME,
    update_course,
)
from app.modules.agent.tools.update_library_item import (
    UPDATE_LIBRARY_ITEM_TOOL_NAME,
    update_library_item,
)
from app.modules.agent.tools.web_search import web_search
from app.modules.llm.service import build_chat_model, write_llm_call_log
from app.modules.settings.config import LlmProviderConfig

CHAT_PROMPT_VERSION = "chat-library-scope-v16"
# 研究会话独立 prompt 版本（研究会话 V1）：研究语义进版本串；评测黄金集回归随
# 此版本触发。工单 01 起两版随模型可见面变化同步 bump（工单 04：删除与跨课
# 迁移三工具；工单 05：批量整理计划工具与批量指引；插队票 08：对象枚举工具
# 指引）。
CHAT_RESEARCH_PROMPT_VERSION = "chat-research-scope-v17"
CHAT_RECURSION_LIMIT = 25
# 计入 llm_call_logs.retrieval_count 的资料检索工具（web_search 是外网检索，不混入）。
RETRIEVAL_TOOL_NAMES = frozenset({"search_library"})
# 操作工具族（工单 02 起）：成功返回经操作提案事件进 done 载荷（确认卡）。
# 工单 03 追加修改与归档动作（六动作）、工单 04 追加删除与跨课迁移（三动作），
# 动作名 = 注册项 action = 工具函数名。
OPERATION_TOOL_NAMES = frozenset(
    {
        CREATE_COURSE_TOOL_NAME,
        ADD_TEXT_RECORD_TOOL_NAME,
        UPDATE_COURSE_TOOL_NAME,
        ARCHIVE_COURSE_TOOL_NAME,
        RESTORE_COURSE_TOOL_NAME,
        UPDATE_LIBRARY_ITEM_TOOL_NAME,
        ARCHIVE_LIBRARY_ITEM_TOOL_NAME,
        RESTORE_LIBRARY_ITEM_TOOL_NAME,
        SOFT_DELETE_RECORD_TOOL_NAME,
        DELETE_COURSE_TOOL_NAME,
        MOVE_RECORD_COURSE_TOOL_NAME,
    }
)
# 挂载检索工具的范围（工单 04：五档中 FREE 外统一挂 search_library；工单 01
# 起从 message_service 收敛到装配层，页面快照不改变挂载矩阵）。
RETRIEVAL_SCOPES = frozenset(
    {
        ChatScope.RECORD,
        ChatScope.LIBRARY_ITEM,
        ChatScope.COURSE,
        ChatScope.ALL,
    }
)


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


@dataclass(frozen=True)
class ChatMemoryProposalEvent:
    """记忆提案已创建（propose_memory 成功返回）：done 载荷透传前端确认卡。"""

    proposal_id: str
    items: list[str]


@dataclass(frozen=True)
class ChatResearchProposalEvent:
    """入库提案已创建（propose_ingest 成功返回）：done 载荷透传前端确认卡，
    每项 {proposal_id, url, title}。"""

    proposals: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class ChatOperationProposalEvent:
    """操作提案已创建（操作工具成功返回，工单 02）：done 载荷透传前端确认卡，
    每项 {proposal_id, action, payload}（payload 为判别校验后的清洗载荷，
    确认卡据此预览完整参数）。"""

    proposals: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class ChatOperationExecutionEvent:
    """操作直执行回执（操作工具成功返回，第二阶段工单 02）：done 载荷透传
    前端回执卡，每项含 operation_id / action / level / auth_mode / payload /
    result（自动档免确认执行，授权依据经操作历史可追溯）。"""

    executions: tuple[dict[str, object], ...]


ChatStreamEvent = (
    ChatTokenEvent
    | ChatToolCallEvent
    | ChatToolResultEvent
    | ChatMemoryProposalEvent
    | ChatResearchProposalEvent
    | ChatOperationProposalEvent
    | ChatOperationExecutionEvent
)


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
# 检索挂载变体（工单 04）：五档范围会话（RECORD / LIBRARY_ITEM / COURSE / ALL）
# 统一挂 search_library（作用域由统一 Agent 运行时上下文承载，工单 01 起）；
# 自由聊天空配置。
LIBRARY_CHAT_AGENT_CONFIG = AgentConfig(tools=(search_library,))


def _resolve_agent_config(
    *, retrieval: bool, web_search_enabled: bool, research: bool = False
) -> AgentConfig:
    """按「检索挂载 × web_search × 研究」组合出当轮装配：变体维持常量，
    web_search 生效时追加工具（frozen dataclass 实例化）；search_courses 与
    propose_memory 恒挂载（工单 01 操作工具组：课程查询在全部会话类型可用，
    先例=记忆提案工具）；propose_ingest 仅研究会话挂载（研究会话 V1）。"""
    config = LIBRARY_CHAT_AGENT_CONFIG if retrieval else CHAT_AGENT_CONFIG
    if web_search_enabled:
        config = AgentConfig(tools=(*config.tools, web_search))
    # 恒挂载段（操作工具组）：search_courses 课程查询 + list_course_records /
    # list_library_items 对象枚举（插队票 08：只读查询工具，无 operation 事实、
    # 不进 OPERATION_TOOL_NAMES）+ propose_memory 记忆提案
    # + create_course 课程创建提案 + add_text_record_to_course 文本记录添加提案
    # （工单 02/03，spec 决策 12：写工具恒挂载全部会话类型，目标解析与会话范围
    # 解耦）+ 修改与归档动作组（工单 03：update/archive/restore_course 与
    # update/archive/restore_library_item，L1 级）+ 删除与迁移动作组（工单 04：
    # soft_delete_record / delete_course（L3 恒确认）与 move_record_course（L2），
    # 按注册表 level 声明自动继承档位分流）+ 批量整理计划工具（工单 05：一次
    # 提交多条整理目标，出计划卡或直建 Run 由后端档位与阈值判定——计划卡经既有
    # 提案查询就地呈现，不进 done 载荷，故不入 OPERATION_TOOL_NAMES）。
    config = AgentConfig(
        tools=(
            *config.tools,
            search_courses,
            list_course_records,
            list_library_items,
            propose_memory,
            create_course,
            add_text_record_to_course,
            update_course,
            archive_course,
            restore_course,
            update_library_item,
            archive_library_item,
            restore_library_item,
            soft_delete_record,
            delete_course,
            move_record_course,
            plan_batch_operations,
        )
    )
    if research:
        config = AgentConfig(tools=(*config.tools, propose_ingest))
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
    命中数兼容各工具载荷键（search_library 的 evidence_hits〔工单 04〕、
    web_search 的 hits、search_courses 的 courses〔工单 01〕）。
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
            body = cast(dict[str, object], payload)
            for key in ("evidence_hits", "hits", "courses"):
                value = body.get(key)
                if isinstance(value, list):
                    hits = len(cast(list[object], value))
                    break
            ok_value = body.get("ok")
            if isinstance(ok_value, bool):
                ok = ok_value
    return ChatToolResultEvent(tool=message.name or "", hits=hits, ok=ok)


def _memory_proposal_event(message: ToolMessage) -> ChatMemoryProposalEvent | None:
    """propose_memory 的成功返回 → 提案事件（载荷 JSON：{ok, proposal_id, items}）。"""
    if not isinstance(message.content, str):
        return None
    try:
        value: object = json.loads(message.content)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    payload = cast(dict[str, object], value)
    proposal_id = payload.get("proposal_id")
    items = payload.get("items")
    if payload.get("ok") is not True or not isinstance(proposal_id, str):
        return None
    if not isinstance(items, list):
        return None
    names = cast(list[object], items)
    return ChatMemoryProposalEvent(
        proposal_id=proposal_id,
        items=[item for item in names if isinstance(item, str)],
    )


def _research_proposal_event(message: ToolMessage) -> ChatResearchProposalEvent | None:
    """propose_ingest 的成功返回 → 提案事件（载荷 JSON：{ok, proposals: [...]}）。

    每项收窄为 {proposal_id, url, title} 三键：形状不符的条目丢弃（与前端
    done 载荷防御性收窄同一口径）。
    """
    if not isinstance(message.content, str):
        return None
    try:
        value: object = json.loads(message.content)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    payload = cast(dict[str, object], value)
    raw_proposals = payload.get("proposals")
    if payload.get("ok") is not True or not isinstance(raw_proposals, list):
        return None
    proposals: list[dict[str, str]] = []
    for item in cast(list[object], raw_proposals):
        if not isinstance(item, dict):
            continue
        entry = cast(dict[str, object], item)
        proposal_id = entry.get("proposal_id")
        url = entry.get("url")
        title = entry.get("title")
        if not (isinstance(proposal_id, str) and isinstance(url, str) and isinstance(title, str)):
            continue
        proposals.append({"proposal_id": proposal_id, "url": url, "title": title})
    if not proposals:
        return None
    return ChatResearchProposalEvent(proposals=tuple(proposals))


def _operation_proposal_event(message: ToolMessage) -> ChatOperationProposalEvent | None:
    """操作工具的成功返回 → 操作提案事件（载荷 JSON：{ok, proposals: [...]}）。

    每项收窄为 {proposal_id, action, payload} 三键：形状不符的条目丢弃（与
    前端 done 载荷防御性收窄同一口径）。
    """
    if not isinstance(message.content, str):
        return None
    try:
        value: object = json.loads(message.content)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    payload = cast(dict[str, object], value)
    raw_proposals = payload.get("proposals")
    if payload.get("ok") is not True or not isinstance(raw_proposals, list):
        return None
    proposals: list[dict[str, object]] = []
    for item in cast(list[object], raw_proposals):
        if not isinstance(item, dict):
            continue
        entry = cast(dict[str, object], item)
        proposal_id = entry.get("proposal_id")
        action = entry.get("action")
        item_payload = entry.get("payload")
        if not (
            isinstance(proposal_id, str)
            and isinstance(action, str)
            and isinstance(item_payload, dict)
        ):
            continue
        proposals.append({"proposal_id": proposal_id, "action": action, "payload": item_payload})
    if not proposals:
        return None
    return ChatOperationProposalEvent(proposals=tuple(proposals))


def _operation_execution_event(message: ToolMessage) -> ChatOperationExecutionEvent | None:
    """操作工具的直执行返回 → 执行回执事件（载荷 JSON：{ok, executed: {...}}，
    工单 02 自动档）。executed 六键全为标量/JSON 形状才透传（与提案事件同一
    防御性收窄口径）。"""

    if not isinstance(message.content, str):
        return None
    try:
        value: object = json.loads(message.content)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    payload = cast(dict[str, object], value)
    executed = payload.get("executed")
    if payload.get("ok") is not True or not isinstance(executed, dict):
        return None
    entry = cast(dict[str, object], executed)
    operation_id = entry.get("operation_id")
    action = entry.get("action")
    level = entry.get("level")
    auth_mode = entry.get("auth_mode")
    item_payload = entry.get("payload")
    result = entry.get("result")
    if not (
        isinstance(operation_id, str)
        and isinstance(action, str)
        and isinstance(level, str)
        and isinstance(auth_mode, str)
        and isinstance(item_payload, dict)
        and isinstance(result, dict)
    ):
        return None
    return ChatOperationExecutionEvent(
        executions=(
            {
                "operation_id": operation_id,
                "action": action,
                "level": level,
                "auth_mode": auth_mode,
                "payload": item_payload,
                "result": result,
            },
        )
    )


async def stream_chat_reply(
    *,
    checkpointer: BaseCheckpointSaver[str],
    provider: LlmProviderConfig,
    context_messages: Sequence[AnyMessage],
    runtime: AgentRuntimeContext,
    outcome: ChatStreamOutcome,
    prompt_version: str = CHAT_PROMPT_VERSION,
) -> AsyncGenerator[ChatStreamEvent, None]:
    """工厂层流式生成路径：建模型 → 清残留 → astream 分发结构化流事件 → 统一埋点。

    - 每轮从 chat_messages 重建喂入：轮初清掉上轮/崩溃残留，checkpoint 只承载当轮运行态；
    - 统一 Agent 运行时上下文（工单 01）承载全部工具运行期状态并单对绑定/重置：
      范围会话（scope ∈ RETRIEVAL_SCOPES）注入 search_library，web_search_provider
      非 None 时挂载联网工具，mode=RESEARCH 追加挂载 propose_ingest，search_courses
      / propose_memory / create_course 恒挂载（装配组合见 _resolve_agent_config）；
    - 事件分发：AIMessageChunk 文本 → token、tool_call_chunks 拼全 → tool_call、
      ToolMessage → tool_result；token 用量跨工具循环累加；
    - 正常完成埋点（graph_name=chat，仅元数据，prompt_version 随会话模式取
      普通/研究两版）并在返回前清理本轮 checkpoint；
    - 中断（GeneratorExit，客户端断开/用户停止）不落埋点直接终止；
    - 其他异常埋点后重新抛出，由调用方转 error 事件。
    """
    thread_id = chat_thread_id(runtime.session_id)
    await checkpointer.adelete_thread(thread_id)
    http_client = openai.DefaultAsyncHttpxClient(trust_env=False)
    started = perf_counter()
    # 业务 system 提示经 build_chat_agent 参数注入（deepagents 下混入 messages 会被丢弃），
    # 其余消息（轮次窗口 + 当前提问）照常作为对话历史喂入。
    system_prompt = next((m for m in context_messages if isinstance(m, SystemMessage)), None)
    input_messages = [m for m in context_messages if not isinstance(m, SystemMessage)]
    runtime_token = bind_agent_runtime_context(runtime)
    # 检索归因（CB-08）：本轮资料检索命中合计（None=未检索，0=检索无命中）。
    retrieval_count: int | None = None
    try:
        agent = build_chat_agent(
            build_chat_model(provider, http_client),
            checkpointer,
            system_prompt=system_prompt,
            config=_resolve_agent_config(
                retrieval=runtime.scope in RETRIEVAL_SCOPES,
                web_search_enabled=runtime.web_search_provider is not None,
                research=runtime.mode == ChatMode.RESEARCH,
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
                result_event = _tool_result_event(chunk)
                if result_event.tool in RETRIEVAL_TOOL_NAMES:
                    retrieval_count = (retrieval_count or 0) + result_event.hits
                if not result_event.ok:
                    logger.warning("chat_tool_failed", tool=result_event.tool)
                yield result_event
                if chunk.name == PROPOSE_MEMORY_TOOL_NAME:
                    proposal_event = _memory_proposal_event(chunk)
                    if proposal_event is not None:
                        yield proposal_event
                if chunk.name == PROPOSE_INGEST_TOOL_NAME:
                    research_event = _research_proposal_event(chunk)
                    if research_event is not None:
                        yield research_event
                if chunk.name in OPERATION_TOOL_NAMES:
                    operation_event = _operation_proposal_event(chunk)
                    if operation_event is not None:
                        yield operation_event
                    execution_event = _operation_execution_event(chunk)
                    if execution_event is not None:
                        yield execution_event
    except GeneratorExit:
        # 客户端断开 / 用户停止：半截回答不落库、不落埋点，直接终止。
        raise
    except Exception:
        logger.error("chat_stream_failed", error_code="CHAT_STREAM_FAILED")
        await write_llm_call_log(
            session_factory=runtime.session_factory,
            graph_name="chat",
            graph_node="generate",
            model=provider.model,
            prompt_version=prompt_version,
            token_usage=outcome.token_usage,
            latency_ms=max(0, round((perf_counter() - started) * 1000)),
            retrieval_count=retrieval_count,
            error_code="CHAT_STREAM_FAILED",
        )
        raise
    finally:
        try:
            reset_agent_runtime_context(runtime_token)
        except ValueError:
            # SSE 中断（aclose）时生成器 finalization 可能跨执行 context 运行，
            # reset 校验 token 来源失败；原 context 已随任务销毁，无绑定泄漏
            # （既有 memory/ingest 绑定先例，工单 01 收敛为单对）。
            pass
        await http_client.aclose()
    await write_llm_call_log(
        session_factory=runtime.session_factory,
        graph_name="chat",
        graph_node="generate",
        model=provider.model,
        prompt_version=prompt_version,
        token_usage=outcome.token_usage,
        latency_ms=max(0, round((perf_counter() - started) * 1000)),
        retrieval_count=retrieval_count,
        error_code=None,
    )
    await checkpointer.adelete_thread(thread_id)
