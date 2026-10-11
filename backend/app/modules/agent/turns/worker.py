"""CHAT_TURN 执行 worker（切换会话不中断任务，票 01/02）。

复用 WorkerSpec／JobRunner（ADR-0012）：双执行槽各自一个 runner 实例，数据库
条件领取（``_preempt`` rowcount==1）天然防双领取；轮次是执行与观察的事实源：

- 领取闸门（validate_claim）：受理身份失配 / 已取消 / 已非 QUEUED 即作废；
  领取即换执行身份（claim_token）并 attempt+1，迟到旧执行不能落事件或终态；
- 事件持久化：token 短批处理，非 token 事件即时落；同事务推进 last_seq 后
  才广播（通知只降延迟，订阅端超时补拉兜底）；
- 取消落实：观察器独立轮询 cancel_requested（不依赖下一条 token），置位即
  取消在途生成并按执行身份条件收口 CANCELLED（部分输出已持久，保留展示）；
  完成提交与取消裁决同事务串行——取消先提交则拒绝完成提交（不写最终消息与
  done 事件），按取回收口，迟到输出不得转回完成；
- 失败收口：单槽故障只收口对应轮次与 job（apply_failure 条件更新）；
  on_loop_failure 禁全局恢复（双槽会误伤兄弟槽在途轮次），只做针对性收口
  （job 已终态时仍按轮次事实补齐收口，重试恢复可写后不永久占用会话）；
- 安全续跑（票 02，规格 §8/§10/§12）：attempt>1 即续跑——先重验恢复条件
  （图版本 / 原供应商身份 / 记忆外发 / 联网），不满足落 WAITING_USER
  （释放执行槽、保留内容，等用户处理后 resume）；checkpoint 三入口（首次 /
  续跑 astream(None) / 图已完成仅补写）；模型节点重放先发 revision 事件
  （output_revision+1，未完成 segment 被替换，旧片段保留）；checkpoint 缺失
  时按持久事实分流（无副作用且无输出＝从头执行，否则保守等待）；终态收口
  后清理 checkpoint（业务先落盘，双库可对账）；预算跨恢复累计重建。

- 启动对账经 ChatTurnRecovery 一次性闸门：RUNNING → QUEUED 自动续跑（安全
  能力齐备后开放，票 02）；遗留 INTERRUPTED 保留内容，由用户显式 resume。
"""

import asyncio
import contextlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, cast
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver  # pyright: ignore[reportMissingTypeStubs]
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.agent import message_service
from app.modules.agent.auth_mode import clamp_resume_auth_mode
from app.modules.agent.citations import parse_citation_reply, parse_library_citation_reply
from app.modules.agent.context import ChatContextTooLargeError
from app.modules.agent.graph import (
    CHAT_PROMPT_VERSION,
    CHAT_RESEARCH_PROMPT_VERSION,
    ChatCommentaryEvent,
    ChatMemoryProposalEvent,
    ChatOperationExecutionEvent,
    ChatOperationProposalEvent,
    ChatResearchProposalEvent,
    ChatRevisionEvent,
    ChatStreamOutcome,
    ChatTokenEvent,
    ChatToolCallEvent,
    ChatToolResultEvent,
    TurnCheckpointMissingError,
)
from app.modules.agent.message_service import (
    SessionPromptContext,
    load_library_materials,
    session_context,
)
from app.modules.agent.middleware.cancel_guard import TurnCancelledError
from app.modules.agent.models import ChatMessage
from app.modules.agent.operations.registry import budget_counted_effect_tool_names
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runtime import (
    BUDGET_COUNTED_TOOL_NAMES,
    AgentRuntimeContext,
    ToolCallBudget,
)
from app.modules.agent.schemas import ChatMode, ChatPageSnapshot, ChatRole, ChatScope
from app.modules.agent.turns.background import park_turn, reconcile_waits
from app.modules.agent.turns.effects import count_turn_effects
from app.modules.agent.turns.models import ChatTurn
from app.modules.agent.turns.runtime import (
    ActiveTurnRegistry,
    ChatTurnRecovery,
    TurnEventBroadcaster,
)
from app.modules.agent.turns.schemas import (
    ChatTurnEventType,
    ChatTurnStatus,
    ChatTurnWaitingKind,
)
from app.modules.agent.turns.service import (
    CHAT_TURN_JOB_TYPE,
    ChatTurnService,
    TurnCompletionOutcome,
    list_turn_events,
    load_execution,
    parse_timezone,
    resume_blocked_reason,
)
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.runner import (
    CancelClaim,
    ClaimCheck,
    ClaimedJob,
    LoopFailure,
    Ready,
    RunnerContext,
    WaitingClaim,
    WorkerSpec,
    mark_failed,
)
from app.modules.jobs.schemas import ProcessingJobStatus
from app.modules.search.integrations.tavily import TavilySearchClient
from app.modules.search.web_search import SearchProvider
from app.modules.settings.config import (
    LlmProviderConfig,
    agent_default_auth_mode,
    load_llm_provider,
    load_web_search_config,
)
from app.shared.errors import CodedHTTPException
from app.shared.events import RecordInvalidationNotifier

# 取消观察器轮询间隔：不依赖下一条 token 的持久取消落实时延上界。
CANCEL_POLL_INTERVAL_SECONDS = 0.4
# token 增量短批处理窗口（规格 §5：可批处理，但须先提交后通知）。
TOKEN_FLUSH_INTERVAL_SECONDS = 0.25
TOKEN_FLUSH_BATCH_SIZE = 64
# astream 取消注入下偶发不返回（负载相关死锁先例）：aclose 超时保护。
ACLOSE_TIMEOUT_SECONDS = 5.0

# 通用执行失败码沿用旧流式路径口径（前端翻译与埋点连续）。
CHAT_STREAM_FAILED = "CHAT_STREAM_FAILED"


@dataclass(frozen=True)
class _ClaimedTurn(ClaimedJob):
    turn_id: str
    claim_token: str


class _TurnCancelled(Exception):
    """生成被持久取消终止（观察器 / 取消闸门 / 完成提交被取消裁决拒绝；非失败路径）。"""


class _ClaimLost(Exception):
    """执行身份失配（迟到执行）：静默停止消费与收尾。"""


def turn_thread_id(turn_id: str) -> str:
    """每轮独立 checkpoint 身份（规格 §8）：chat-turn-{turn_id}。"""
    return f"chat-turn-{turn_id}"


async def find_candidate(session: AsyncSession, now: datetime) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.job_type == CHAT_TURN_JOB_TYPE.value,
                ProcessingJob.status == ProcessingJobStatus.PENDING,
                (ProcessingJob.next_run_at.is_(None) | (ProcessingJob.next_run_at <= now)),
            )
            .order_by(ProcessingJob.created_at)
            .limit(1)
        )
    ).one_or_none()


async def validate_claim(
    session: AsyncSession,
    job: ProcessingJob,
    _record_id: str,
    _preflight: None,
) -> ClaimCheck[_ClaimedTurn]:
    """领取闸门（纯读校验，无副作用）。

    双执行槽会在同一候选 job 上竞争：``_preempt`` 条件 UPDATE 只有一个槽胜出，
    落败槽的领取事务同样提交——因此这里不得改写轮次（否则落败者会覆盖胜出者
    的执行身份，导致轮次永久 RUNNING）。轮次状态推进一律放在 ``on_preempted``
    （仅胜出槽到达）。RUNNING＝兄弟槽在途执行：WaitingClaim 让出调度窗口
    （write_waiting_reason=False，零 job 写入），胜出者写回后候选自然消失。
    """
    try:
        data: object = json.loads(job.input_json)
    except ValueError:
        return CancelClaim("turn_missing")
    turn_id = cast(dict[str, object], data).get("turn_id") if isinstance(data, dict) else None
    if not isinstance(turn_id, str):
        return CancelClaim("turn_missing")
    turn = await session.get(ChatTurn, turn_id)
    if turn is None:
        return CancelClaim("turn_missing")
    if turn.status == ChatTurnStatus.RUNNING.value:
        return WaitingClaim("turn_busy")
    if turn.status != ChatTurnStatus.QUEUED.value:
        return CancelClaim("turn_not_queued")
    return Ready(_ClaimedTurn(job_id=job.id, record_id="", turn_id=turn_id, claim_token=""))


async def claim_turn(
    session: AsyncSession,
    job: ProcessingJob,
    ctx: _ClaimedTurn,
    now: datetime,
) -> _ClaimedTurn:
    """胜出槽专属（``_preempt`` rowcount==1 后）：轮次翻 RUNNING 并换执行身份。

    排队期取消在此落实（cancel API 直收口 QUEUED 之外的兜底路径）；轮次已
    不可执行时收口 job 并交还原 ctx（execute 的身份核对会静默跳过）。
    """
    turn = await session.get(ChatTurn, ctx.turn_id)
    if turn is None:
        close_job(job, ProcessingJobStatus.CANCELLED, now)
        return ctx
    if bool(turn.cancel_requested):
        turn.status = ChatTurnStatus.CANCELLED.value
        turn.finished_at = now
        turn.updated_at = now
        close_job(job, ProcessingJobStatus.CANCELLED, now)
        return ctx
    if turn.status != ChatTurnStatus.QUEUED.value:
        close_job(job, ProcessingJobStatus.CANCELLED, now)
        return ctx
    claim_token = str(uuid4())
    turn.status = ChatTurnStatus.RUNNING.value
    turn.claim_token = claim_token
    turn.attempt += 1
    # 续跑（attempt>1）推进正文版本（票 02，规格 §10）：模型节点重放的增量
    # 属新 output_revision，未完成 segment 被替换而非拼接。
    if turn.attempt > 1:
        turn.output_revision += 1
    turn.started_at = turn.started_at or now
    turn.updated_at = now
    return _ClaimedTurn(
        job_id=ctx.job_id, record_id=ctx.record_id, turn_id=ctx.turn_id, claim_token=claim_token
    )


def failure_code(_ctx: _ClaimedTurn, exc: Exception) -> str:
    if isinstance(exc, ChatContextTooLargeError):
        return "CHAT_CONTEXT_TOO_LARGE"
    if isinstance(exc, CodedHTTPException):
        return exc.code
    return CHAT_STREAM_FAILED


def classify_loop_error(_exc: Exception) -> LoopFailure:
    return LoopFailure(event="chat_turn_worker_unexpected_failure", error_code=CHAT_STREAM_FAILED)


async def apply_failure(
    ctx: _ClaimedTurn,
    session: AsyncSession,
    job: ProcessingJob,
    _record: Any,
    code: str,
    now: datetime,
) -> bool:
    """执行失败收口：job FAILED + 轮次按执行身份条件翻 FAILED（唯一终态）。"""
    mark_failed(job, code=code, message="回答生成失败", now=now)
    turn = await session.get(ChatTurn, ctx.turn_id)
    if (
        turn is not None
        and turn.status == ChatTurnStatus.RUNNING.value
        and turn.claim_token == ctx.claim_token
    ):
        turn.status = ChatTurnStatus.FAILED.value
        turn.error_code = code
        turn.error_message = "回答生成失败"
        turn.finished_at = now
        turn.updated_at = now
    return True


@dataclass
class _StreamState:
    """执行侧内存聚合：与持久事件同源派生，仅供收尾（最终正文 / done 载荷）使用。"""

    segments: dict[str, str] = field(default_factory=dict[str, str])
    commentary_ids: set[str] = field(default_factory=set[str])
    # checkpoint 展示恢复与工具节点重放可能返回同一对象，按业务身份合并。
    memory_proposals: dict[str, dict[str, object]] = field(
        default_factory=dict[str, dict[str, object]]
    )
    research_proposals: dict[str, dict[str, str]] = field(default_factory=dict[str, dict[str, str]])
    operation_proposals: dict[str, dict[str, object]] = field(
        default_factory=dict[str, dict[str, object]]
    )
    executed_operations: dict[str, dict[str, object]] = field(
        default_factory=dict[str, dict[str, object]]
    )

    @property
    def joined_text(self) -> str:
        return "".join(
            text
            for segment_id, text in self.segments.items()
            if segment_id not in self.commentary_ids
        )


class _TurnExecutor:
    """单轮生成的执行体：消费流 → 持久事件 → 收尾终态。"""

    def __init__(
        self,
        *,
        ctx: _ClaimedTurn,
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        checkpointer: BaseCheckpointSaver[str],
        broadcaster: TurnEventBroadcaster,
        stopped: asyncio.Event | None = None,
    ) -> None:
        self._ctx = ctx
        self._session_factory = session_factory
        self._data_dir = data_dir
        self._checkpointer = checkpointer
        self._broadcaster = broadcaster
        self._buffer: list[dict[str, Any]] = []
        self._last_flush = perf_counter()
        self._state = _StreamState()
        self._cancel_event = asyncio.Event()
        # 停机联动：runner 循环 stopped 置位即停止生成（不写终态——重启对账
        # 把 RUNNING 翻 INTERRUPTED，保留内容）。
        self._shutdown_event = stopped if stopped is not None else asyncio.Event()

    async def run(self) -> None:
        """抛 _TurnCancelled＝取消落实；_ClaimLost＝迟到执行；正常返回＝已收尾。"""
        turn = await self._load_turn()
        if turn is None:
            return
        is_resume = turn.attempt > 1
        execution = load_execution(turn)
        provider = await asyncio.to_thread(load_llm_provider, self._data_dir)
        if provider is None or not provider.api_key:
            if is_resume:
                # 续跑遇原供应商不可用：保留输出等待（规格 §12），不静默换服务。
                await self._wait(
                    ChatTurnWaitingKind.PROVIDER_UNAVAILABLE, "原 AI 服务配置当前不可用"
                )
                return
            # 受理后配置被清空：收口失败，不静默换供应商（规格 §12）。
            await self._fail("LLM_PROVIDER_UNCONFIGURED", "AI 服务配置已失效，请重新配置后再试")
            return
        if is_resume:
            blocked = await self._resume_blocked_reason(execution, provider)
            if blocked is not None:
                await self._wait(blocked[0], blocked[1])
                return
        try:
            await self._drive(turn, execution, provider, resume=is_resume)
        except TurnCheckpointMissingError:
            # checkpoint 缺失：按持久事实分流（规格 §8）——无副作用且无已保存
            # 输出＝领取前中断，可从头执行；否则安全边界无法确定，保守等待。
            effect_count, last_seq = await self._turn_facts()
            if effect_count == 0 and last_seq == 0:
                await self._drive(turn, execution, provider, resume=False)
            else:
                await self._wait(
                    ChatTurnWaitingKind.CHECKPOINT_MISSING,
                    "执行状态缺失且已有已提交内容，无法安全继续",
                )

    async def _drive(
        self,
        turn: ChatTurn,
        execution: dict[str, Any],
        provider: LlmProviderConfig,
        *,
        resume: bool,
    ) -> None:
        """构建上下文与流并驱动执行到收尾（首次 / 续跑两形态共用）。"""
        session_id = turn.session_id
        user_content = await self._user_content(turn.user_message_id)
        web_search_provider = await self._resolve_web_search(bool(execution.get("web_search")))
        page = self._page_snapshot(execution.get("page"))
        user_timezone = parse_timezone(execution.get("user_timezone"))
        prompt_context = await session_context(
            self._session_factory,
            session_id,
            web_search=web_search_provider is not None,
            memory_allowed=bool(execution.get("memory_injection_allowed")),
            page=page,
            user_timezone=user_timezone,
        )
        context_messages: list[Any] = list(prompt_context.messages)
        resume_replaces: str | None = None
        if resume:
            # 续跑：原 system 提示与已注入记忆用首次执行固化的快照（规格 §10——
            # 已进入上下文的材料保持原快照，不随会话 / 配置漂移重建）。
            snapshot_prompt = execution.get("system_prompt")
            if isinstance(snapshot_prompt, str) and snapshot_prompt:
                context_messages = [
                    SystemMessage(content=snapshot_prompt),
                    HumanMessage(content=user_content or ""),
                ]
            # 替换边界由流在 checkpoint 验证通过后发（ChatRevisionEvent）——不在
            # 此预发，避免 checkpoint 缺失分流被 revision 事件污染 last_seq。
            resume_replaces = await self._pending_segment()
        else:
            await self._persist_execution_snapshot(turn, execution, prompt_context)
        budget = await self._restore_budget(resume)
        turn_mode = AuthMode(str(execution.get("auth_mode") or AuthMode.REQUEST_APPROVAL))
        if turn.attempt > 1:
            # 恢复档收紧（ChatTurn 规格 §11/T13）：重启后会话临时高权限失效——
            # 覆盖缺席时与当前全局默认取更严格者，高权限写回落提案等显式重新
            # 授权；同进程 resume 覆盖仍在则 clamp 原样放行（升降档交提交点）。
            current_default = AuthMode(
                await asyncio.to_thread(agent_default_auth_mode, self._data_dir)
            )
            turn_mode = clamp_resume_auth_mode(session_id, turn_mode, current_default)
        runtime = AgentRuntimeContext(
            session_factory=self._session_factory,
            session_id=session_id,
            scope=prompt_context.scope,
            mode=prompt_context.mode,
            course_id=prompt_context.course_id,
            record_id=prompt_context.record_id,
            library_item_id=prompt_context.library_item_id,
            web_search_provider=web_search_provider,
            llm_provider=provider,
            page=prompt_context.page,
            auth_mode=turn_mode,
            instruction_excerpt=user_content,
            message_id=turn.user_message_id,
            user_timezone=user_timezone,
            budget=budget,
            turn_id=self._ctx.turn_id,
            turn_claim_token=self._ctx.claim_token,
        )
        outcome = ChatStreamOutcome()
        stream = message_service.stream_chat_reply(
            checkpointer=self._checkpointer,
            provider=provider,
            context_messages=context_messages,
            runtime=runtime,
            outcome=outcome,
            prompt_version=(
                CHAT_RESEARCH_PROMPT_VERSION
                if prompt_context.mode == ChatMode.RESEARCH
                else CHAT_PROMPT_VERSION
            ),
            thread_id=turn_thread_id(self._ctx.turn_id),
            cancel_check=self._cancel_event.is_set,
            resume=resume,
            resume_replaces=resume_replaces,
        )
        watcher = asyncio.create_task(self._watch_stop())
        flusher = asyncio.create_task(self._flush_loop())
        consume = asyncio.create_task(self._consume(stream))
        cancel_waiter = asyncio.create_task(self._cancel_event.wait())
        shutdown_waiter = asyncio.create_task(self._shutdown_event.wait())
        try:
            done, _pending = await asyncio.wait(
                {consume, cancel_waiter, shutdown_waiter},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            watcher.cancel()
            flusher.cancel()
        if consume not in done:
            # 取消 / 停机先到：落实停止（不等待下一条 token），部分输出尽力持久。
            consume.cancel()
            try:
                await asyncio.wait_for(consume, ACLOSE_TIMEOUT_SECONDS * 2)
            except (TimeoutError, BaseException):
                # astream 取消注入下偶发不返回（先例）：放弃等待，迟到落事件会被
                # 执行身份条件更新拒绝。
                pass
            with contextlib.suppress(Exception):
                await asyncio.wait_for(stream.aclose(), ACLOSE_TIMEOUT_SECONDS)
            cancel_waiter.cancel()
            shutdown_waiter.cancel()
            with contextlib.suppress(_ClaimLost):
                await self._flush_buffer(force=True)
            if shutdown_waiter in done or self._shutdown_event.is_set():
                # 停机不写终态：保留 RUNNING 交启动对账翻 QUEUED 续跑（票 02）。
                return
            raise _TurnCancelled
        cancel_waiter.cancel()
        shutdown_waiter.cancel()
        try:
            await consume  # 传播执行异常（含持久化失败与 _ClaimLost）
        except TurnCancelledError:
            # 取消闸门命中（模型前 / 工具前）：已落事件保留，按取消收口。
            with contextlib.suppress(_ClaimLost):
                await self._flush_buffer(force=True)
            raise _TurnCancelled from None
        if outcome.background_interrupts:
            async with self._session_factory() as session, session.begin():
                parked = await park_turn(
                    session, self._ctx.turn_id, self._ctx.claim_token, outcome.background_interrupts
                )
            if not parked:
                raise _TurnCancelled
            self._broadcaster.publish(self._ctx.turn_id)
            return
        await self._finalize(session_id, prompt_context, execution, outcome, provider, resume)

    async def _load_turn(self) -> ChatTurn | None:
        async with self._session_factory() as session:
            turn = await session.get(ChatTurn, self._ctx.turn_id)
            if (
                turn is None
                or turn.claim_token != self._ctx.claim_token
                or turn.status != ChatTurnStatus.RUNNING.value
            ):
                return None
            return turn

    async def _resume_blocked_reason(
        self, execution: dict[str, Any], provider: LlmProviderConfig
    ) -> tuple[ChatTurnWaitingKind, str] | None:
        """续跑前置重验（规格 §11/§12）：与 resume 端点共用 service 实现。"""
        return await resume_blocked_reason(self._data_dir, execution, provider)

    async def _turn_facts(self) -> tuple[int, int]:
        """轮次持久事实：已登记副作用数与已保存事件游标（checkpoint 缺失分流）。"""
        async with self._session_factory() as session:
            effect_count = await count_turn_effects(session, self._ctx.turn_id)
            last_seq = await session.scalar(
                select(ChatTurn.last_seq).where(ChatTurn.id == self._ctx.turn_id)
            )
        return effect_count, int(last_seq or 0)

    async def _pending_segment(self) -> str | None:
        """中断时仍未完成的正文 segment（空＝中断发生在正文边界外）。"""
        async with self._session_factory() as session:
            events = await list_turn_events(session, self._ctx.turn_id)
        pending: str | None = None
        for row in events:
            if row.type == ChatTurnEventType.TOKEN.value:
                pending = row.segment_id
            elif row.type in (
                ChatTurnEventType.TOOL_CALL.value,
                ChatTurnEventType.TOOL_RESULT.value,
                ChatTurnEventType.COMMENTARY.value,
                ChatTurnEventType.REVISION.value,
            ):
                pending = None
        return pending

    async def _persist_execution_snapshot(
        self, turn: ChatTurn, execution: dict[str, Any], prompt_context: SessionPromptContext
    ) -> None:
        """首次执行起固化恢复上下文（规格 §10）：原 system 提示与已注入记忆。

        已固化不覆盖（checkpoint 缺失后从头重跑的二次固化保持原快照）。
        """
        if "system_prompt" in execution:
            return
        system_prompt = next(
            (m for m in prompt_context.messages if isinstance(m, SystemMessage)), None
        )
        execution = {
            **execution,
            "system_prompt": system_prompt.content if system_prompt is not None else None,
            "injected_memories": list(prompt_context.learner_memories),
        }
        async with self._session_factory() as session, session.begin():
            row = await session.get(ChatTurn, self._ctx.turn_id)
            if row is None or row.claim_token != self._ctx.claim_token:
                return
            row.execution_json = json.dumps(execution, ensure_ascii=False, separators=(",", ":"))
            row.updated_at = utcnow()

    async def _restore_budget(self, resume: bool) -> ToolCallBudget:
        """预算跨恢复累计重建（规格 §10）：calls_used 从事件、operations 从
        效果行；操作口径只数递增入口的行（记忆 / 入库逐项不消耗操作预算）。"""
        if not resume:
            return ToolCallBudget()
        async with self._session_factory() as session:
            events = await list_turn_events(session, self._ctx.turn_id)
            operations = await count_turn_effects(
                session,
                self._ctx.turn_id,
                tool_names=budget_counted_effect_tool_names(),
            )
        calls = 0
        for row in events:
            if row.type != ChatTurnEventType.TOOL_CALL.value:
                continue
            try:
                payload: object = json.loads(row.payload_json)
            except ValueError:
                continue
            if not isinstance(payload, dict):
                continue
            tool = cast(dict[str, object], payload).get("tool")
            if isinstance(tool, str) and tool in BUDGET_COUNTED_TOOL_NAMES:
                calls += 1
        return ToolCallBudget(calls_used=calls, operations_created=operations)

    async def _wait(self, kind: ChatTurnWaitingKind, detail: str) -> None:
        """真正等待（规格 §7）：释放执行槽、保留内容与已提交事实，等用户处理。"""
        landed = await ChatTurnService.finalize_waiting(
            session_factory=self._session_factory,
            turn_id=self._ctx.turn_id,
            claim_token=self._ctx.claim_token,
            kind=kind,
            detail=detail,
        )
        if landed:
            self._broadcaster.publish(self._ctx.turn_id)

    async def _user_content(self, message_id: str) -> str | None:
        async with self._session_factory() as session:
            row = await session.get(ChatMessage, message_id)
            return row.content if row is not None else None

    async def _resolve_web_search(self, requested: bool) -> SearchProvider | None:
        if not requested:
            return None
        config = await asyncio.to_thread(load_web_search_config, self._data_dir)
        return TavilySearchClient(config.api_key) if config is not None else None

    def _page_snapshot(self, raw: Any) -> ChatPageSnapshot | None:
        if not isinstance(raw, dict):
            return None
        try:
            return ChatPageSnapshot.model_validate(raw)
        except Exception:
            return None

    async def _watch_stop(self) -> None:
        """独立轮询持久取消标记与停机事件：排队 / 生成 / 工具调用期间均可控制。"""
        while not self._cancel_event.is_set():
            if self._shutdown_event.is_set():
                return
            async with self._session_factory() as session:
                turn = await session.get(ChatTurn, self._ctx.turn_id)
                if turn is not None and bool(turn.cancel_requested):
                    self._cancel_event.set()
                    return
            await asyncio.sleep(CANCEL_POLL_INTERVAL_SECONDS)

    async def _flush_loop(self) -> None:
        """周期性冲刷 token 批缓冲：模型慢（分片间隔 > 批窗口）时输出仍及时可见。"""
        while True:
            await asyncio.sleep(TOKEN_FLUSH_INTERVAL_SECONDS)
            with contextlib.suppress(_ClaimLost):
                await self._flush_buffer(force=True)

    async def _consume(self, stream: Any) -> None:
        """消费流事件：映射为持久事件行（token 批处理），同事务提交后广播。"""
        async for event in stream:
            if isinstance(event, ChatRevisionEvent):
                # 续跑替换边界（图流在 checkpoint 验证通过后首发）：先落
                # revision 事件再落重放 token，投影端据此替换未完成段。
                self._buffer.append(
                    {
                        "type": ChatTurnEventType.REVISION.value,
                        "payload": {"replaces_segment": event.replaces_segment},
                    }
                )
                await self._flush_buffer(force=True)
            elif isinstance(event, ChatTokenEvent):
                self._state.segments[event.segment_id] = (
                    self._state.segments.get(event.segment_id, "") + event.text
                )
                self._buffer.append(
                    {
                        "type": ChatTurnEventType.TOKEN.value,
                        "segment_id": event.segment_id,
                        "payload": {"text": event.text},
                    }
                )
                await self._flush_buffer(force=False)
            elif isinstance(event, ChatCommentaryEvent):
                self._state.commentary_ids.add(event.segment_id)
                await self._flush_buffer(force=True)
                self._buffer.append(
                    {
                        "type": ChatTurnEventType.COMMENTARY.value,
                        "segment_id": event.segment_id,
                        "payload": {"text": event.text},
                    }
                )
                await self._flush_buffer(force=True)
            elif isinstance(event, ChatToolCallEvent):
                # 工具调用前的正文段定性为评注（先例 capture_commentary）：片段级
                # tool_call 早于 updates 分支的完整评注事件，先按已积累文本落
                # 评注事件，迟到的完整评注经投影 upsert 覆盖文本。
                preamble = self._state.segments.get(event.segment_id, "")
                if event.segment_id and event.segment_id not in self._state.commentary_ids:
                    self._state.commentary_ids.add(event.segment_id)
                    if preamble:
                        self._buffer.append(
                            {
                                "type": ChatTurnEventType.COMMENTARY.value,
                                "segment_id": event.segment_id,
                                "payload": {"text": preamble},
                            }
                        )
                await self._flush_buffer(force=True)
                self._buffer.append(
                    {
                        "type": ChatTurnEventType.TOOL_CALL.value,
                        "tool_call_id": event.tool_call_id,
                        "segment_id": event.segment_id,
                        "payload": {
                            "tool": event.tool,
                            "query": event.query,
                            "tool_call_id": event.tool_call_id,
                        },
                    }
                )
                await self._flush_buffer(force=True)
            elif isinstance(event, ChatToolResultEvent):
                self._buffer.append(
                    {
                        "type": ChatTurnEventType.TOOL_RESULT.value,
                        "tool_call_id": event.tool_call_id,
                        "payload": {
                            "tool": event.tool,
                            "hits": event.hits,
                            "ok": event.ok,
                            "tool_call_id": event.tool_call_id,
                            "awaiting_confirmation": event.awaiting_confirmation,
                        },
                    }
                )
                await self._flush_buffer(force=True)
            elif isinstance(event, ChatMemoryProposalEvent):
                self._state.memory_proposals[event.proposal_id] = {
                    "proposal_id": event.proposal_id,
                    "items": event.items,
                }
            elif isinstance(event, ChatResearchProposalEvent):
                self._state.research_proposals.update(
                    (entry["proposal_id"], entry) for entry in event.proposals
                )
            elif isinstance(event, ChatOperationProposalEvent):
                self._state.operation_proposals.update(
                    (cast(str, entry["proposal_id"]), entry) for entry in event.proposals
                )
            elif isinstance(event, ChatOperationExecutionEvent):
                self._state.executed_operations.update(
                    (cast(str, entry["operation_id"]), entry) for entry in event.executions
                )
        await self._flush_buffer(force=True)

    async def _flush_buffer(self, *, force: bool) -> None:
        now = perf_counter()
        if not self._buffer:
            self._last_flush = now
            return
        if not force:
            if (
                len(self._buffer) < TOKEN_FLUSH_BATCH_SIZE
                and now - self._last_flush < TOKEN_FLUSH_INTERVAL_SECONDS
            ):
                return
        rows = self._buffer
        self._buffer = []
        self._last_flush = now
        landed = await ChatTurnService.append_events(
            session_factory=self._session_factory,
            turn_id=self._ctx.turn_id,
            claim_token=self._ctx.claim_token,
            rows=rows,
        )
        if landed is None:
            # 执行身份失配（迟到执行）：停止消费；终态收尾的条件更新同样失配跳过。
            raise _ClaimLost
        self._broadcaster.publish(self._ctx.turn_id)

    async def _finalize(
        self,
        session_id: str,
        prompt_context: SessionPromptContext,
        execution: dict[str, Any],
        outcome: ChatStreamOutcome,
        provider: LlmProviderConfig,
        resume: bool,
    ) -> None:
        content = outcome.final_text if outcome.final_text is not None else self._state.joined_text
        if not content:
            await self._fail("EMPTY_REPLY", "回答为空，请重试")
            return
        citations: list[dict[str, int | str]] = []
        if prompt_context.should_parse_citations:
            if prompt_context.library is not None:
                scope_id = (
                    prompt_context.library_item_id
                    if prompt_context.scope == ChatScope.LIBRARY_ITEM
                    else prompt_context.course_id
                )
                records, items = await load_library_materials(
                    self._session_factory, prompt_context.scope, scope_id
                )
                parsed = parse_library_citation_reply(content, records, items)
            else:
                parsed = parse_citation_reply(
                    content,
                    transcript=prompt_context.transcript or "",
                    record_id=prompt_context.record_id or "",
                )
            content = parsed.content
            citations = parsed.citations
        if not content:
            await self._fail("EMPTY_REPLY", "回答为空，请重试")
            return
        assistant_id = str(uuid4())
        executed_anchor_ids = [
            entry["operation_id"]
            for entry in self._state.executed_operations.values()
            if isinstance(entry.get("operation_id"), str)
        ]
        # 本轮注入记忆（续跑用首次执行快照，规格 §10；缺省回退当次上下文）。
        injected_memories = execution.get("injected_memories")
        memory_used = (
            [item for item in cast(list[object], injected_memories) if isinstance(item, str)]
            if isinstance(injected_memories, list)
            else list(prompt_context.learner_memories)
        )
        assistant_row = ChatMessage(
            id=assistant_id,
            session_id=session_id,
            role=ChatRole.ASSISTANT,
            content=content,
            citations_json=json.dumps(citations, separators=(",", ":")) if citations else None,
            model=provider.model,
            token_usage_json=json.dumps(outcome.token_usage, separators=(",", ":"))
            if outcome.token_usage
            else None,
            executed_operations_json=json.dumps(executed_anchor_ids, separators=(",", ":"))
            if executed_anchor_ids
            else None,
            created_at=utcnow(),
        )
        done_payload: dict[str, Any] = {
            "message_id": assistant_id,
            "content": content,
            "memory_used": memory_used,
        }
        if self._state.memory_proposals:
            done_payload["memory_proposals"] = list(self._state.memory_proposals.values())
        if self._state.research_proposals:
            done_payload["research_proposals"] = list(self._state.research_proposals.values())
        if self._state.operation_proposals:
            done_payload["operation_proposals"] = list(self._state.operation_proposals.values())
        if self._state.executed_operations:
            done_payload["executed_operations"] = list(self._state.executed_operations.values())
        completion = await ChatTurnService.finalize_completed(
            session_factory=self._session_factory,
            turn_id=self._ctx.turn_id,
            claim_token=self._ctx.claim_token,
            assistant_row=assistant_row,
            done_payload=done_payload,
            citations=citations,
        )
        if completion == TurnCompletionOutcome.COMPLETED:
            # 业务终态已提交：清理本 thread checkpoint（票 02 生命周期——先业务
            # 后 checkpoint，崩溃窗口只留孤儿由启动对账兜底清理）。
            await self._checkpointer.adelete_thread(turn_thread_id(self._ctx.turn_id))
            self._broadcaster.publish(self._ctx.turn_id)
        elif completion == TurnCompletionOutcome.CANCELLED:
            # 取消先提交：完成提交被拒（最终消息与 done 事件未落库，部分输出
            # 保留），复用取回收口路径写 CANCELLED。
            raise _TurnCancelled

    async def _fail(self, code: str, message: str) -> None:
        landed = await ChatTurnService.finalize_terminal(
            session_factory=self._session_factory,
            turn_id=self._ctx.turn_id,
            claim_token=self._ctx.claim_token,
            status=ChatTurnStatus.FAILED,
            error_code=code,
            error_message=message,
        )
        if landed:
            await self._checkpointer.adelete_thread(turn_thread_id(self._ctx.turn_id))
            self._broadcaster.publish(self._ctx.turn_id)


async def execute(
    ctx: _ClaimedTurn,
    runtime: RunnerContext,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    checkpointer: BaseCheckpointSaver[str],
    broadcaster: TurnEventBroadcaster,
    active: ActiveTurnRegistry,
) -> bool:
    """执行一轮生成：取消落实或完成后交 writeback 关 job（取消／失配也返回 True）。"""
    active.register(ctx.turn_id)
    try:
        executor = _TurnExecutor(
            ctx=ctx,
            session_factory=session_factory,
            data_dir=data_dir,
            checkpointer=checkpointer,
            broadcaster=broadcaster,
            stopped=runtime.stopped,
        )
        try:
            await executor.run()
        except _TurnCancelled:
            landed = await ChatTurnService.finalize_terminal(
                session_factory=session_factory,
                turn_id=ctx.turn_id,
                claim_token=ctx.claim_token,
                status=ChatTurnStatus.CANCELLED,
            )
            if landed:
                # 取消终态已提交：checkpoint 随之清理（不再续跑）。
                await checkpointer.adelete_thread(turn_thread_id(ctx.turn_id))
                broadcaster.publish(ctx.turn_id)
        except _ClaimLost:
            logger.warning("chat_turn_claim_lost", turn_id=ctx.turn_id)
        return True
    finally:
        active.unregister(ctx.turn_id)


def close_job(job: ProcessingJob, status: ProcessingJobStatus, now: datetime) -> None:
    """job 终态收口三元组（状态 / finished_at / updated_at）共享助手。"""
    job.status = status
    job.finished_at = now
    job.updated_at = now


async def writeback(
    ctx: _ClaimedTurn,
    _result: bool,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    """轮次已终态（完成 / 取消 / 失败收口 / 失配）：job 条件翻 SUCCEEDED。"""
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, ctx.job_id)
        if job is None or job.status != ProcessingJobStatus.RUNNING:
            return False
        close_job(job, ProcessingJobStatus.SUCCEEDED, utcnow())
        await session.flush()
        turn = await session.get(ChatTurn, ctx.turn_id)
        if turn is not None and turn.status == ChatTurnStatus.QUEUED.value:
            from app.modules.agent.turns.service import ensure_turn_job

            await ensure_turn_job(session, ctx.turn_id, utcnow())
    return True


def chat_turn_spec(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    checkpointer: BaseCheckpointSaver[str],
    broadcaster: TurnEventBroadcaster,
    active: ActiveTurnRegistry,
    notifier: RecordInvalidationNotifier,
    recovery: ChatTurnRecovery,
) -> WorkerSpec[None, _ClaimedTurn, bool]:
    """双执行槽各建一个实例：last-claim 钩子只收口本槽最后一次领取的 job。"""
    last_claim: list[_ClaimedTurn | None] = [None]
    last_reconcile = 0.0

    async def find_with_reconciliation(
        session: AsyncSession, now: datetime
    ) -> ProcessingJob | None:
        nonlocal last_reconcile
        if perf_counter() - last_reconcile >= 2.0:
            await reconcile_waits(session)
            last_reconcile = perf_counter()
        return await find_candidate(session, now)

    async def targeted_closure(claim: _ClaimedTurn) -> bool:
        # 双槽禁全局恢复（兄弟槽在途轮次会被误翻 INTERRUPTED）：只针对性收口
        # 本槽最后一次领取。job 已终态时仍按轮次事实继续收口（job 先落 FAILED、
        # 轮次收口暂时失败的重试路径），轮次收口复用 finalize_terminal（同条件
        # 守卫）；任一事务暂时写失败整体不生效，重试恢复可写后必须完成收口，
        # 不能永久占用会话（规格 §6）。
        now = utcnow()
        async with session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, claim.job_id)
            if job is not None and job.status == ProcessingJobStatus.RUNNING:
                mark_failed(job, code=CHAT_STREAM_FAILED, message="回答生成执行异常", now=now)
        await ChatTurnService.finalize_terminal(
            session_factory=session_factory,
            turn_id=claim.turn_id,
            claim_token=claim.claim_token,
            status=ChatTurnStatus.FAILED,
            error_code=CHAT_STREAM_FAILED,
            error_message="回答生成执行异常",
        )
        return True

    async def retry_closure(claim: _ClaimedTurn, attempt: int = 0) -> None:
        # 写库暂时不可写时保留故障身份并退避重试针对性收口（规格 §6）；
        # 两次仍失败则留待启动对账 / 用户停止兜底。
        try:
            await targeted_closure(claim)
        except Exception:
            logger.error("chat_turn_targeted_closure_failed", job_id=claim.job_id, attempt=attempt)
            if attempt < 2:
                await asyncio.sleep(2.0 * (attempt + 1))
                await retry_closure(claim, attempt + 1)

    async def on_loop_failure(error_code: str) -> None:
        claim = last_claim[0]
        logger.error(
            "chat_turn_loop_failure",
            job_id=claim.job_id if claim else None,
            error_code=error_code,
        )
        if claim is None:
            return
        await retry_closure(claim)

    async def recover() -> None:
        await recovery.run_once(
            lambda: ChatTurnService.startup_recover(session_factory, notifier, checkpointer)
        )

    async def tracked_execute(ctx: _ClaimedTurn, runtime: RunnerContext) -> bool:
        last_claim[0] = ctx
        # 异常路径保留 last_claim：apply_failure 自身失败时 on_loop_failure
        # 仍能定位本槽最后领取做针对性收口（条件更新失配即安全跳过）。
        return await execute(
            ctx,
            runtime,
            session_factory=session_factory,
            data_dir=data_dir,
            checkpointer=checkpointer,
            broadcaster=broadcaster,
            active=active,
        )

    async def tracked_writeback(ctx: _ClaimedTurn, result: bool) -> bool:
        last_claim[0] = ctx
        landed = await writeback(ctx, result, session_factory=session_factory)
        # 写回成功才清（失败时保留供 on_loop_failure 针对性收口）。
        if landed:
            last_claim[0] = None
        return landed

    return WorkerSpec(
        name="chat_turn_worker",
        job_type=CHAT_TURN_JOB_TYPE,
        poll_interval=0.25,
        write_waiting_reason=False,
        find_candidate=find_with_reconciliation,
        validate_claim=validate_claim,
        on_preempted=claim_turn,
        execute=tracked_execute,
        writeback=tracked_writeback,
        failure_code=failure_code,
        apply_failure=apply_failure,
        recover_interrupted=recover,
        classify_loop_error=classify_loop_error,
        on_loop_failure=on_loop_failure,
    )
