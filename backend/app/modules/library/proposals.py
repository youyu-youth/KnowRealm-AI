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
from sqlalchemy import select
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
    if proposal.evidence_refs_json:
        try:
            out.evidence_refs = json.loads(proposal.evidence_refs_json)
        except ValueError:
            out.evidence_refs = None
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
        proposals = list((await session.scalars(stmt)).all())
        return [_proposal_out(p) for p in proposals]

    @staticmethod
    async def confirm(session: AsyncSession, proposal_id: str) -> AgentProposalOut:
        """确认并应用：应用器写入与 APPLIED 同事务；失败独立落 FAILED 后 422。

        FAILED 提案可再次确认（工单 05：失败留稳定错误码可重试）——
        APPLIED / REJECTED 是终局，重复确认 409。
        """
        try:
            async with session.begin():
                proposal = await ProposalService._get(session, proposal_id)
                decided = (ProposalStatus.PENDING.value, ProposalStatus.FAILED.value)
                if proposal.status not in decided:
                    raise CodedHTTPException(
                        code="PROPOSAL_ALREADY_DECIDED",
                        status_code=409,
                        detail="提案已处理，不能重复确认",
                    )
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
                await applier(session, proposal)
                proposal.status = ProposalStatus.APPLIED.value
                proposal.error_code = None
                proposal.decided_at = utcnow()
        except CodedHTTPException as exc:
            if exc.code in ("PROPOSAL_NOT_FOUND", "PROPOSAL_ALREADY_DECIDED"):
                raise
            # 应用失败：主事务回滚（应用器部分写入消失），独立小事务保留 FAILED 诊断。
            await ProposalService._mark_failed(session, proposal_id, exc.code)
            raise CodedHTTPException(
                code="PROPOSAL_APPLY_FAILED",
                status_code=422,
                detail=f"提案应用失败：{exc.code}",
                params={"errorCode": exc.code},
            ) from exc
        refreshed = await ProposalService._get(session, proposal_id)
        return _proposal_out(refreshed)

    @staticmethod
    async def create(session: AsyncSession, body: ProposalCreateRequest) -> AgentProposalOut:
        """通用提案创建（工单 05）：payload 按 proposal_type 判别校验后落库，
        创建不改任何业务事实。尚未注册 payload schema 的类型（MEMORY）拒绝。"""
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
        # 落库的是判别校验后的清洗载荷（model_dump）：未知键不持久化，
        # 存储层与 schema 形状一致（ADR-0024 禁任意 SQL/路径/Shell 形状）。
        cleaned_payload = validated.model_dump()
        async with session.begin():
            proposal = AgentProposal(
                id=str(uuid4()),
                proposal_type=body.proposal_type.value,
                status=ProposalStatus.PENDING.value,
                session_id=body.session_id,
                message_id=body.message_id,
                target_type=body.target_type,
                target_id=body.target_id,
                payload_json=json.dumps(cleaned_payload, ensure_ascii=False),
                created_at=utcnow(),
            )
            session.add(proposal)
            await session.flush()
            return _proposal_out(proposal)

    @staticmethod
    async def reject(session: AsyncSession, proposal_id: str) -> AgentProposalOut:
        """拒绝：只改提案状态，不改任何业务事实。"""
        async with session.begin():
            proposal = await ProposalService._get(session, proposal_id)
            if proposal.status not in (ProposalStatus.PENDING, ProposalStatus.FAILED):
                raise CodedHTTPException(
                    code="PROPOSAL_ALREADY_DECIDED",
                    status_code=409,
                    detail="提案已处理，不能重复拒绝",
                )
            proposal.status = ProposalStatus.REJECTED.value
            proposal.decided_at = utcnow()
        return _proposal_out(proposal)

    @staticmethod
    async def _mark_failed(session: AsyncSession, proposal_id: str, error_code: str) -> None:
        async with session.begin():
            proposal = await session.get(AgentProposal, proposal_id)
            if proposal is not None and proposal.status in (
                ProposalStatus.PENDING.value,
                ProposalStatus.FAILED.value,
            ):
                proposal.status = ProposalStatus.FAILED.value
                proposal.error_code = error_code
                proposal.decided_at = utcnow()

    @staticmethod
    async def _get(session: AsyncSession, proposal_id: str) -> AgentProposal:
        proposal = await session.get(AgentProposal, proposal_id)
        if proposal is None:
            raise CodedHTTPException(
                code="PROPOSAL_NOT_FOUND", status_code=404, detail="提案不存在"
            )
        return proposal
