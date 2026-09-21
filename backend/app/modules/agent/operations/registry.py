"""操作注册表与公共提案入口（通用 Agent 第一阶段工单 02）：最小公共执行机制。

术语（spec 决策 3）：动作（action）= 模型可调用的工具语义；操作（Operation）
= 一次受控执行的事实记录（回执）。注册表以稳定动作标识声明提案类型、判别
payload schema 与应用器（结果投影随应用器返回）；写工具是薄壳（docstring
面向模型、参数面与注册项 payload schema 同源，校验执法在提案创建时）——
公共执行流程零领域专属分支，新写动作 = 一个注册项 + 一个薄工具。
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.runtime import (
    MAX_OPERATION_PROPOSALS_PER_TURN,
    AgentRuntimeContext,
)
from app.modules.library.models import AgentProposal
from app.modules.library.proposals import ProposalService, register_applier, register_payload_schema
from app.modules.library.schemas import ProposalCreateRequest, ProposalType

# 应用器契约（对齐 library.proposals.ProposalApplier）：在调用方确认事务内
# 执行领域写入、不得自行 begin；返回值即结果投影（操作回执，APPLIED 时由
# 提案框架同事务写进 result_json）。
OperationApplier = Callable[[AsyncSession, AgentProposal], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class OperationSpec:
    """单个写操作的声明式注册项（课程创建为首个接入动作，文本记录随后复用）。"""

    action: str  # 动作标识（= 薄工具函数名，流式分发按名识别）
    proposal_type: ProposalType  # 提案类型（提案框架判别键）
    payload_schema: type[BaseModel]  # 判别 payload schema（未知键拒绝）
    applier: OperationApplier  # 确认事务内的应用器（返回结果投影）


_OPERATIONS: dict[str, OperationSpec] = {}


def register_operation(spec: OperationSpec) -> None:
    """注册操作项；payload schema 与应用器同步注册进既有提案框架。"""
    _OPERATIONS[spec.action] = spec
    register_payload_schema(spec.proposal_type, spec.payload_schema)
    register_applier(spec.proposal_type, spec.applier)


def get_operation(action: str) -> OperationSpec | None:
    return _OPERATIONS.get(action)


def _missing_fields(exc: ValidationError) -> tuple[list[str], str]:
    """ValidationError →（缺失字段名列表, 可转述说明）。

    字段级错误取 loc 首段；模型级条件校验（如「学业场景必须选择教育阶段」）
    无字段锚点，进说明文本由模型转述给用户。
    """
    fields: list[str] = []
    detail = ""
    for error in exc.errors():
        loc = error.get("loc", ())
        if loc:
            field = str(loc[0])
            if field not in fields:
                fields.append(field)
        elif not detail:
            detail = str(error.get("msg", "")).removeprefix("Value error, ")
    return fields, detail


async def submit_operation_proposal(
    runtime: AgentRuntimeContext, action: str, args: dict[str, Any]
) -> dict[str, Any]:
    """操作类写工具的公共提案入口：注册项 schema 校验 → 每轮上限执法 → 创建
    PENDING 提案（创建不改任何业务事实，ADR-0024）。

    返回工具 JSON 载荷（对齐 propose_ingest 先例形状）：
    - 校验失败 → {ok: False, missing: [...], detail?}（模型转述追问缺失项）；
    - 超每轮上限 → {ok: False, error: OPERATION_PROPOSAL_LIMIT}（拒绝不截断）；
    - 成功 → {ok: True, proposals: [{proposal_id, action, payload, status}]}。
    """
    spec = get_operation(action)
    if spec is None:
        return {"ok": False, "error": "OPERATION_NOT_REGISTERED", "proposals": []}
    if runtime.budget.operations_created >= MAX_OPERATION_PROPOSALS_PER_TURN:
        return {
            "ok": False,
            "error": "OPERATION_PROPOSAL_LIMIT",
            "detail": f"每轮最多创建 {MAX_OPERATION_PROPOSALS_PER_TURN} 条操作提案",
            "proposals": [],
        }
    try:
        validated = spec.payload_schema.model_validate(args)
    except ValidationError as exc:
        fields, detail = _missing_fields(exc)
        body: dict[str, Any] = {"ok": False, "missing": fields, "proposals": []}
        if detail:
            body["detail"] = detail
        return body
    cleaned_payload = validated.model_dump()
    async with runtime.session_factory() as session:
        proposal = await ProposalService.create(
            session,
            ProposalCreateRequest(
                proposal_type=spec.proposal_type,
                payload=cleaned_payload,
                session_id=runtime.session_id,
            ),
        )
    runtime.budget.operations_created += 1
    return {
        "ok": True,
        "proposals": [
            {
                "proposal_id": proposal.id,
                "action": action,
                "payload": cleaned_payload,
                "status": proposal.status.value,
            }
        ],
    }


def operation_payload_dict(proposal: AgentProposal) -> dict[str, Any]:
    """解析提案载荷 JSON（应用器共用）：非 dict 形状返回空 dict 由 schema 校验兜底。"""
    try:
        value: object = json.loads(proposal.payload_json)
    except ValueError:
        return {}
    # 元素类型静态未知（载荷源自 json.loads 的运行时收窄，与 proposals._as_dict 同口径）。
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}
