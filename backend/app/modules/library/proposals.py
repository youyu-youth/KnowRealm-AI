"""agent_proposals 通用提案框架（工单 02）：列表 / 确认 / 拒绝 + 按类型路由应用器。

工单 02 只落框架与端点，零应用器、零生成方——ORGANIZE / RESEARCH_INGEST 的
生成与应用随工单 05 注册，MEMORY 随工单 06 注册（register_applier）。
应用器契约：在调用方事务内执行领域写入、不得自行 begin；抛
CodedHTTPException 表示应用失败（框架在独立小事务落 FAILED + error_code
保留诊断后转 422）。提案创建不改任何业务事实（ADR-0024）。
"""

import json
from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.library.models import AgentProposal
from app.modules.library.schemas import (
    AgentProposalOut,
    MemoryProposalPayload,
    OrganizePayload,
    ProposalCreateRequest,
    ProposalListQuery,
    ProposalStatus,
    ProposalType,
    ResearchIngestPayload,
)
from app.shared.errors import CodedHTTPException

# 应用器注册表：proposal_type → 领域应用函数（05/06 落地时注册）。
ProposalApplier = Callable[[AsyncSession, AgentProposal], Awaitable[object]]
_APPLIERS: dict[ProposalType, ProposalApplier] = {}

# payload 判别校验表：创建侧拒绝任意 SQL/路径/Shell 形状的载荷（ADR-0024）。
_PAYLOAD_SCHEMAS: dict[ProposalType, type[BaseModel]] = {
    ProposalType.ORGANIZE: OrganizePayload,
    ProposalType.RESEARCH_INGEST: ResearchIngestPayload,
    # MEMORY 的应用器随工单 06 在 learner 域注册（learner/routes 导入即注册）。
    ProposalType.MEMORY: MemoryProposalPayload,
}


def register_payload_schema(proposal_type: ProposalType, schema: type[BaseModel]) -> None:
    """注册提案类型的判别 payload schema（工单 02：操作提案随 operations 包导入注册）。

    依赖方向：library 不依赖 agent 域，操作类型的 schema 类定义在 agent/operations、
    经本函数反向注册（同 register_applier 的先例）。重复注册以最后一次为准。"""
    _PAYLOAD_SCHEMAS[proposal_type] = schema


def register_applier(proposal_type: ProposalType, applier: ProposalApplier) -> None:
    _APPLIERS[proposal_type] = applier


def clear_appliers() -> dict[ProposalType, ProposalApplier]:
    """清空注册表并返回原内容（测试隔离用：恢复时传回 register）。"""
    snapshot = dict(_APPLIERS)
    _APPLIERS.clear()
    return snapshot


def restore_appliers(snapshot: dict[ProposalType, ProposalApplier]) -> None:
    _APPLIERS.update(snapshot)


def _proposal_out(proposal: AgentProposal) -> AgentProposalOut:
    out = AgentProposalOut.model_validate(proposal)
    try:
        out.payload = _as_dict(proposal.payload_json)
    except ValueError:
        out.payload = {}
    if proposal.snapshot_json:
        try:
            out.snapshot = _as_dict(proposal.snapshot_json)
        except ValueError:
            out.snapshot = None
    if proposal.evidence_refs_json:
        try:
            out.evidence_refs = json.loads(proposal.evidence_refs_json)
        except ValueError:
            out.evidence_refs = None
    if proposal.result_json:
        try:
            out.result = _as_dict(proposal.result_json)
        except ValueError:
            out.result = None
    return out


def _as_dict(raw: str) -> dict[str, Any]:
    value: object = json.loads(raw)
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


class ProposalService:
    @staticmethod
    async def list_proposals(
        session: AsyncSession, query: ProposalListQuery
    ) -> list[AgentProposalOut]:
        stmt = select(AgentProposal).order_by(AgentProposal.created_at.desc())
        if query.status is not None:
            stmt = stmt.where(AgentProposal.status == query.status.value)
        if query.proposal_type is not None:
            stmt = stmt.where(AgentProposal.proposal_type == query.proposal_type.value)
        if query.session_id is not None:
            stmt = stmt.where(AgentProposal.session_id == query.session_id)
        proposals = list((await session.scalars(stmt)).all())
        return [_proposal_out(p) for p in proposals]

    @staticmethod
    async def confirm(session: AsyncSession, proposal_id: str) -> AgentProposalOut:
        """确认并应用：原子抢占执行权后，应用器写入与 APPLIED 同事务；失败独立落 FAILED 后 422。

        执行权由一条带终态守卫的 UPDATE 抢占（WHERE status IN (PENDING, FAILED)）：
        rowcount=1 才执行应用器，=0 说明提案不存在或已被处理（404 / 409）。不能
        先 SELECT 检查再执行——pysqlite 驱动的 SELECT 不开启事务（SQLAlchemy
        方言文档明载），两个并发确认会各自读到 PENDING、双双执行应用器产生重复
        业务事实；UPDATE 的写写串行保证同一提案只有一个请求获得执行权。FAILED
        提案可再次确认（工单 05：失败留稳定错误码可重试）——APPLIED / REJECTED
        是终局，重复确认 409。

        应用器返回值是类型化结果投影（操作回执，工单 02：课程创建 →
        {course_id}），同事务写进 result_json、经输出契约 result 字段透出。
        """
        try:
            async with session.begin():
                claimed = await session.execute(
                    update(AgentProposal)
                    .where(
                        AgentProposal.id == proposal_id,
                        AgentProposal.status.in_(
                            [ProposalStatus.PENDING.value, ProposalStatus.FAILED.value]
                        ),
                    )
                    .values(
                        status=ProposalStatus.APPLIED.value,
                        error_code=None,
                        decided_at=utcnow(),
                    )
                )
                if not isinstance(claimed, CursorResult) or claimed.rowcount != 1:
                    # 不存在 → 404；存在但已是终态或正被并发请求处理 → 409。
                    await ProposalService._get(session, proposal_id)
                    raise CodedHTTPException(
                        code="PROPOSAL_ALREADY_DECIDED",
                        status_code=409,
                        detail="提案已处理，不能重复确认",
                    )
                proposal = await ProposalService._get(session, proposal_id)
                try:
                    proposal_type = ProposalType(proposal.proposal_type)
                except ValueError:
                    proposal_type = None
                applier = _APPLIERS.get(proposal_type) if proposal_type is not None else None
                if applier is None:
                    raise CodedHTTPException(
                        code="PROPOSAL_NO_APPLIER",
                        status_code=422,
                        detail="该提案类型尚未注册应用器",
                    )
                result = await applier(session, proposal)
                if isinstance(result, dict):
                    proposal.result_json = json.dumps(result, ensure_ascii=False)
        except CodedHTTPException as exc:
            if exc.code in ("PROPOSAL_NOT_FOUND", "PROPOSAL_ALREADY_DECIDED"):
                raise
            # 应用失败：主事务回滚（抢占与应用器部分写入一起消失），独立小事务保留 FAILED 诊断。
            await ProposalService._mark_failed(session, proposal_id, exc.code)
            raise CodedHTTPException(
                code="PROPOSAL_APPLY_FAILED",
                status_code=422,
                detail=f"提案应用失败：{exc.code}",
                params={"errorCode": exc.code},
            ) from exc
        except Exception as exc:
            # 应用器非编码异常（bug / 环境故障）：原子回滚＝未发生；同样落 FAILED +
            # INTERNAL 稳定错误码（诊断不断链、FAILED 可重试），对调用方仍是 422。
            await ProposalService._mark_failed(session, proposal_id, "INTERNAL")
            raise CodedHTTPException(
                code="PROPOSAL_APPLY_FAILED",
                status_code=422,
                detail="提案应用失败：INTERNAL",
                params={"errorCode": "INTERNAL"},
            ) from exc
        refreshed = await ProposalService._get(session, proposal_id)
        return _proposal_out(refreshed)

    @staticmethod
    async def create(session: AsyncSession, body: ProposalCreateRequest) -> AgentProposalOut:
        """通用提案创建（工单 05）：payload 按 proposal_type 判别校验后落库，
        创建不改任何业务事实。尚未注册 payload schema 的类型（MEMORY）拒绝。"""
        async with session.begin():
            return await ProposalService.create_core(session, body)

    @staticmethod
    async def create_core(
        session: AsyncSession,
        body: ProposalCreateRequest,
        *,
        snapshot_json: str | None = None,
    ) -> AgentProposalOut:
        """提案创建事务内核心（工单 03，create_core 先例）：调用方拥有事务边界，
        便于操作提交路径在同一事务固化执行前快照（目标读取与提案创建原子）。

        snapshot_json 是已按动作快照 schema 判别校验后的序列化结果，形状执法
        在操作注册表侧（agent/operations），本框架不感知具体形状。"""
        schema = _PAYLOAD_SCHEMAS.get(body.proposal_type)
        if schema is None:
            raise CodedHTTPException(
                code="PROPOSAL_PAYLOAD_INVALID",
                status_code=422,
                detail="该提案类型暂不支持创建",
            )
        try:
            validated = schema.model_validate(body.payload)
        except ValidationError as exc:
            raise CodedHTTPException(
                code="PROPOSAL_PAYLOAD_INVALID",
                status_code=422,
                detail="提案载荷不符合该类型的结构要求",
            ) from exc
        # 落库的是判别校验后的清洗载荷：未知键不持久化，存储层与 schema 形状
        # 一致（ADR-0024 禁任意 SQL/路径/Shell 形状）；mode="json" 保证
        # payload_json TEXT 列恒为可序列化 JSON（date 等按 ISO 字符串下行）。
        cleaned_payload = validated.model_dump(mode="json")
        proposal = AgentProposal(
            id=str(uuid4()),
            proposal_type=body.proposal_type.value,
            status=ProposalStatus.PENDING.value,
            session_id=body.session_id,
            message_id=body.message_id,
            target_type=body.target_type,
            target_id=body.target_id,
            payload_json=json.dumps(cleaned_payload, ensure_ascii=False),
            snapshot_json=snapshot_json,
            created_at=utcnow(),
        )
        session.add(proposal)
        await session.flush()
        return _proposal_out(proposal)

    @staticmethod
    async def reject(session: AsyncSession, proposal_id: str) -> AgentProposalOut:
        """拒绝：只改提案状态，不改任何业务事实。

        执行权由带终态守卫的条件 UPDATE 抢占（confirm 先例）：先读后写在并发
        确认下会覆盖对方结果——读到 PENDING → 对方已 APPLIED → 本方写 REJECTED
        覆盖回执。rowcount=0 说明提案不存在（404）或已被处理（409）。
        """
        async with session.begin():
            claimed = await session.execute(
                update(AgentProposal)
                .where(
                    AgentProposal.id == proposal_id,
                    AgentProposal.status.in_(
                        [ProposalStatus.PENDING.value, ProposalStatus.FAILED.value]
                    ),
                )
                .values(status=ProposalStatus.REJECTED.value, decided_at=utcnow())
            )
            if not isinstance(claimed, CursorResult) or claimed.rowcount != 1:
                await ProposalService._get(session, proposal_id)
                raise CodedHTTPException(
                    code="PROPOSAL_ALREADY_DECIDED",
                    status_code=409,
                    detail="提案已处理，不能重复拒绝",
                )
        refreshed = await ProposalService._get(session, proposal_id)
        return _proposal_out(refreshed)

    @staticmethod
    async def discard_session_plan_drafts(session: AsyncSession, chat_session_id: str) -> None:
        """弃置会话内待确认的计划草案提案（spec「确认卡关闭即弃」，用户故事 11）。

        新用户消息 = 话题翻篇：本会话 PENDING / FAILED 的 OP_PLAN_CONFIRM 提案
        批量置 REJECTED 终态（计划业务表零写入不变，草案经重新生成即可恢复）。
        仅草案类提案随话题弃置；其余操作提案（课程创建等用户发起的动作）跨
        消息保留待确认。调用方事务内执行（_mark_failed 先例）；与确认并发的
        竞态由 PENDING / FAILED 条件守卫消除（已 APPLIED 的行不受影响）。
        """
        await session.execute(
            update(AgentProposal)
            .where(
                AgentProposal.session_id == chat_session_id,
                AgentProposal.proposal_type == ProposalType.OP_PLAN_CONFIRM.value,
                AgentProposal.status.in_(
                    [ProposalStatus.PENDING.value, ProposalStatus.FAILED.value]
                ),
            )
            .values(status=ProposalStatus.REJECTED.value, decided_at=utcnow())
        )

    @staticmethod
    async def _mark_failed(session: AsyncSession, proposal_id: str, error_code: str) -> None:
        """失败回写：条件 UPDATE 抢占（终态守卫）。

        与确认 / 重试并发的先读后写竞态在此消除：提案已被并发请求置 APPLIED
        时 rowcount=0 静默不覆盖（APPLIED 事实优先，本方事务早已回滚＝未发生）。
        """
        async with session.begin():
            await session.execute(
                update(AgentProposal)
                .where(
                    AgentProposal.id == proposal_id,
                    AgentProposal.status.in_(
                        [ProposalStatus.PENDING.value, ProposalStatus.FAILED.value]
                    ),
                )
                .values(
                    status=ProposalStatus.FAILED.value,
                    error_code=error_code,
                    decided_at=utcnow(),
                )
            )

    @staticmethod
    async def _get(session: AsyncSession, proposal_id: str) -> AgentProposal:
        proposal = await session.get(AgentProposal, proposal_id)
        if proposal is None:
            raise CodedHTTPException(
                code="PROPOSAL_NOT_FOUND", status_code=404, detail="提案不存在"
            )
        return proposal
