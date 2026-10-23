"""委派登记、状态与受控结果：所有状态提交共享根写锁。"""

import json
from typing import Any, cast
from uuid import uuid4

from langchain_core.messages import SystemMessage, messages_to_dict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.agent.context import ContextRow, RecordContext, build_context_messages
from app.modules.agent.context_budget.models import ChatContextInput, ChatModelRequest
from app.modules.agent.context_budget.schemas import ModelRequestStatus
from app.modules.agent.delegations.models import AgentDelegation
from app.modules.agent.delegations.schemas import KnowledgeResult, KnowledgeTask
from app.modules.agent.runtime import AgentRuntimeContext
from app.modules.agent.schemas import AgentId, ChatRole, ChatScope
from app.modules.agent.turns.effects import current_tool_call_identity, effect_args_fingerprint
from app.modules.agent.turns.models import ChatTurn, ChatTurnEvent, ChatTurnWait
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.shared.errors import CodedHTTPException

TERMINAL = frozenset({"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"})


def thread_id(execution_id: str) -> str:
    return f"agent-delegation-{execution_id}"


def conflict(detail: str) -> CodedHTTPException:
    return CodedHTTPException(code="CHAT_TURN_RESUME_CONFLICT", status_code=409, detail=detail)


async def emit_state(session: AsyncSession, child: AgentDelegation) -> None:
    """调用者已取得根锁并校验执行身份；结果与终态事件在同一事务提交。"""
    root = await session.get(ChatTurn, child.turn_id)
    assert root is not None
    root.last_seq += 1
    root.updated_at = utcnow()
    session.add(
        ChatTurnEvent(
            turn_id=root.id,
            seq=root.last_seq,
            attempt=root.attempt,
            output_revision=root.output_revision,
            type="commentary",
            payload_json=json.dumps(
                {
                    "execution_id": child.id,
                    "agent_id": child.agent_id,
                    "execution_attempt": child.attempt,
                    "status": child.status,
                    "error_code": child.error_code,
                },
                ensure_ascii=False,
            ),
        )
    )


async def register(runtime: AgentRuntimeContext, task: KnowledgeTask) -> ChatTurnWait:
    identity = current_tool_call_identity()
    if (
        runtime.turn_id is None
        or identity is None
        or runtime.execution_id is not None
        or runtime.agent_id != AgentId.GENERAL
        or runtime.scope == ChatScope.FREE
    ):
        raise conflict("当前范围不允许委派本地知识任务")
    fingerprint = effect_args_fingerprint(task.model_dump())
    async with runtime.session_factory() as session, session.begin():
        if not await runtime.turn_write_allowed(session):
            raise conflict("原轮次已停止或执行身份失效")
        child = await session.scalar(
            select(AgentDelegation).where(
                AgentDelegation.turn_id == runtime.turn_id,
                AgentDelegation.namespace == identity.namespace,
                AgentDelegation.logical_call_id == identity.logical_call_id,
            )
        )
        if child is not None:
            if child.args_fingerprint != fingerprint:
                raise conflict("同一委派身份的任务参数不一致")
            wait = await session.scalar(
                select(ChatTurnWait).where(
                    ChatTurnWait.turn_id == runtime.turn_id,
                    ChatTurnWait.target_id == child.job_id,
                    ChatTurnWait.namespace == identity.namespace,
                    ChatTurnWait.logical_call_id == identity.logical_call_id,
                )
            )
            assert wait is not None
            return wait
        count = await session.scalar(
            select(func.count())
            .select_from(AgentDelegation)
            .where(AgentDelegation.turn_id == runtime.turn_id)
        )
        if count is not None and count >= 2:
            raise conflict("本轮最多委派两个知识任务")
        bound = await session.get(ChatContextInput, runtime.turn_id)
        root = await session.get(ChatTurn, runtime.turn_id)
        if bound is None or root is None or runtime.context_policy is None:
            raise conflict("缺少原轮次输入或预算快照")
        execution_id, job_id = str(uuid4()), str(uuid4())
        from app.modules.agent.message_service import session_context

        material = await session_context(
            runtime.session_factory,
            runtime.session_id,
            input_messages=[],
            context_turn_id=runtime.turn_id,
            memory_allowed=False,
        )
        # 复用独立入口的 knowledge 提示构造，只冻结明确任务和范围，不带父历史/记忆。
        messages = build_context_messages(
            [ContextRow(id=execution_id, role=ChatRole.USER, content=task.task)],
            library=material.library,
            record=RecordContext(transcript=material.transcript or "")
            if runtime.record_id
            else None,
            mode=runtime.mode,
            agent_id=AgentId.KNOWLEDGE,
        )
        system = messages[0]
        assert isinstance(system, SystemMessage)
        system.content = (
            f"{system.content}\n本任务独立拥有六次工具调用，父子合计最多十八次，"
            "委派只计入父任务；本任务与其他子任务不挤占各自的六次额度。"
            "优先用一至两次检索取得证据，必要时在剩余额度内补查；"
            "每项用一个主题的短关键词，多个主题用 query 列表，不拼成长查询；"
            "未命中时删减关键词，只保留核心主题补查，不要继续堆叠同义词。"
            "基于已有有效证据回答，证据仍不足时在 KnowledgeReport.gaps 中明确缺口。"
        )
        frozen = {
            "contract_version": 1,
            "task_id": execution_id,
            "task": task.task,
            "scope": str(runtime.scope),
            "mode": str(runtime.mode),
            "course_id": runtime.course_id,
            "record_id": runtime.record_id,
            "library_item_id": runtime.library_item_id,
            "messages": messages_to_dict(messages),
            "rules_json": bound.rules_json,
            "segment": bound.segment,
            "policy_json": bound.policy_json,
            "execution": {
                key: value
                for key, value in json.loads(root.execution_json).items()
                if key
                in {
                    "graph_version",
                    "context_policy_version",
                    "budget_policy_version",
                    "provider_base_url",
                    "provider_model",
                    "provider_fingerprint",
                    "outbound_consent_required",
                }
            },
        }
        job = ProcessingJob(
            id=job_id,
            job_type=ProcessingJobType.CHAT_TURN,
            status=ProcessingJobStatus.PENDING,
            input_json=json.dumps({"delegation_id": execution_id}),
        )
        session.add(job)
        await session.flush()
        child = AgentDelegation(
            id=execution_id,
            turn_id=runtime.turn_id,
            job_id=job_id,
            namespace=identity.namespace,
            logical_call_id=identity.logical_call_id,
            args_fingerprint=fingerprint,
            input_json=json.dumps(frozen, ensure_ascii=False),
        )
        session.add(child)
        await session.flush()
        wait = ChatTurnWait(
            id=str(uuid4()),
            turn_id=runtime.turn_id,
            namespace=identity.namespace,
            logical_call_id=identity.logical_call_id,
            target_type="JOB",
            target_id=job_id,
        )
        session.add(wait)
        await emit_state(session, child)
        await session.flush()
        return wait


async def job_delegation(session: AsyncSession, wait: ChatTurnWait) -> AgentDelegation | None:
    return await session.scalar(
        select(AgentDelegation).where(
            AgentDelegation.turn_id == wait.turn_id,
            AgentDelegation.job_id == wait.target_id,
        )
    )


async def unresolved_requests(session: AsyncSession, child: AgentDelegation) -> list[str]:
    rows = (
        await session.scalars(
            select(ChatModelRequest).where(
                ChatModelRequest.turn_id == child.turn_id,
                ChatModelRequest.execution_id == child.id,
            )
        )
    ).all()
    superseded = {
        row.retry_of for row in rows if row.retry_of and row.status != ModelRequestStatus.BLOCKED
    }
    return [
        row.id
        for row in rows
        if row.status == ModelRequestStatus.STARTED and row.id not in superseded
    ]


async def commit_result(runtime: AgentRuntimeContext, result: KnowledgeResult) -> bool:
    async with runtime.session_factory() as session, session.begin():
        if not await runtime.turn_write_allowed(session):
            return False
        child = await session.get(AgentDelegation, runtime.execution_id)
        assert child is not None and result.task_id == child.id
        from app.modules.agent.context_budget.retrieval import validate_evidence
        from app.modules.agent.context_budget.schemas import ContextRules
        from app.modules.agent.message_service import validate_sendable_chat
        from app.modules.agent.models import ChatSession

        chat = await session.get(ChatSession, runtime.session_id)
        if chat is None:
            return False
        await validate_sendable_chat(session, chat)
        frozen = json.loads(child.input_json)
        await validate_evidence(
            session,
            chat,
            [citation.model_dump(mode="json") for citation in result.citations],
            rules=ContextRules.model_validate_json(frozen["rules_json"]),
        )
        child.status, child.result_json = result.status, result.model_dump_json()
        child.error_code, child.updated_at = result.error_code, utcnow()
        child.finished_at = utcnow() if result.status in TERMINAL else None
        await emit_state(session, child)
        return True


async def cancel_children(session: AsyncSession, turn_id: str, reason: str) -> None:
    children = (
        await session.scalars(
            select(AgentDelegation).where(
                AgentDelegation.turn_id == turn_id,
                AgentDelegation.status.not_in(TERMINAL),
            )
        )
    ).all()
    for child in children:
        child.cancel_requested = True
        child.status, child.finished_at, child.updated_at = "CANCELLED", utcnow(), utcnow()
        child.result_json = KnowledgeResult(
            task_id=child.id,
            status="CANCELLED",
            gaps=[reason],
            error_code="CHAT_TURN_CANCELLED",
        ).model_dump_json()
        job = await session.get(ProcessingJob, child.job_id)
        if job is not None:
            job.status, job.finished_at, job.updated_at = (
                ProcessingJobStatus.CANCELLED,
                utcnow(),
                utcnow(),
            )
        await emit_state(session, child)


def result_payload(child: AgentDelegation) -> dict[str, Any] | None:
    if child.status not in TERMINAL or child.result_json is None:
        return None
    result = KnowledgeResult.model_validate_json(child.result_json)
    if result.task_id != child.id or result.status != child.status:
        raise conflict("知识报告与原子任务身份或状态不一致")
    return result.model_dump(mode="json")


async def validate_report(
    session: AsyncSession,
    session_id: str,
    value: object,
    *,
    logical_call_id: str | None = None,
) -> None:
    """模型投影必须来自该分支的原持久报告，不能借用兄弟引用或改写结论。"""
    if isinstance(value, dict):
        body = cast(dict[str, object], value)
        if (
            body.get("ok") is False
            and isinstance(body.get("error"), str)
            and body.keys() <= {"ok", "error", "message", "retryable", "tool_budget"}
        ):
            return
    try:
        report = KnowledgeResult.model_validate(value)
    except ValueError:
        raise conflict("知识报告契约不合法") from None
    child = await session.scalar(
        select(AgentDelegation)
        .join(ChatTurn, ChatTurn.id == AgentDelegation.turn_id)
        .where(AgentDelegation.id == report.task_id, ChatTurn.session_id == session_id)
    )
    if (
        child is None
        or (logical_call_id is not None and child.logical_call_id != logical_call_id)
        or result_payload(child) != report.model_dump(mode="json")
    ):
        raise conflict("知识报告与原委派分支不一致")
