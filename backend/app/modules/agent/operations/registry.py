"""操作注册表与公共提案入口（通用 Agent 第一阶段工单 02）：最小公共执行机制。

术语（spec 决策 3）：动作（action）= 模型可调用的工具语义；操作（Operation）
= 一次受控执行的事实记录（回执）。注册表以稳定动作标识声明提案类型、操作
级别、判别 payload schema、类型化结果投影与应用器；写工具是薄壳（docstring
面向模型、参数 schema 由注册项 payload schema 派生，校验执法在提案创建时）——
公共执行流程零领域专属分支，新写动作 = 一个注册项 + 一个薄工具。
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.runs.service import record_confirmed_operation
from app.modules.agent.runtime import (
    MAX_OPERATION_PROPOSALS_PER_TURN,
    AgentRuntimeContext,
)
from app.modules.library.models import AgentProposal
from app.modules.library.proposals import ProposalService, register_applier, register_payload_schema
from app.modules.library.schemas import ProposalCreateRequest, ProposalType

# 应用器契约（提案框架 library.proposals.ProposalApplier 的操作侧收窄）：在调用方
# 确认事务内执行领域写入、不得自行 begin；返回值是类型化结果投影（操作回执，
# 经类型参数与 result_schema 静态绑定，APPLIED 时由注册表适配器校验并转 dict
# 同事务写进 result_json）。
type OperationApplier[R: BaseModel] = Callable[[AsyncSession, AgentProposal], Awaitable[R]]


class OperationLevel(StrEnum):
    """操作级别（设计-4 §6 授权映射表的分级词汇）：声明写操作的风险层级。

    第一阶段仅"请求批准"档（spec 决策 1），级别仅声明、不参与执行分支；
    第二阶段三档授权按级别决定"落提案等确认"还是"校验通过即执行"。
    """

    L0 = "L0"  # 读取／检索／导航查询（纯只读工具，不经本注册表）
    L1 = "L1"  # 单对象创建与可逆修改
    L2 = "L2"  # 批量创建／移动／归档／跨课程整理
    L3 = "L3"  # 删除、覆盖正文等破坏性操作


@dataclass(frozen=True)
class OperationSpec[R: BaseModel]:
    """单个写操作的声明式注册项（课程创建为首个接入动作，文本记录随后复用）。"""

    action: str  # 动作标识（= 薄工具函数名，流式分发按名识别）
    proposal_type: ProposalType  # 提案类型（提案框架判别键）
    level: OperationLevel  # 操作级别（设计-4 §6，第二阶段授权按级分流）
    payload_schema: type[BaseModel]  # 判别 payload schema（未知键拒绝）
    result_schema: type[R]  # 类型化结果投影（操作回执形状，spec 决策 8）
    applier: OperationApplier[R]  # 确认事务内的应用器（返回结果投影）


_OPERATIONS: dict[str, OperationSpec[Any]] = {}


def register_operation(spec: OperationSpec[Any]) -> None:
    """注册操作项；payload schema 与应用器同步注册进既有提案框架。

    应用器经投影适配器包装：返回值先按 result_schema 校验再转 dict 交给提案
    框架（框架只识别 dict 结果，投影形状漂移在此显式失败而非被静默丢弃）。
    执行成功后同事务回接写 operation 行（spec 决策 4：执行事实唯一源）——
    run_id 空的单步操作、payload 投影、result 回填、authorization_json
    授权依据；应用器异常时整个确认事务回滚，operation 不落（未发生）。
    """

    async def scoped_applier(session: AsyncSession, proposal: AgentProposal) -> dict[str, Any]:
        result = spec.result_schema.model_validate(await spec.applier(session, proposal))
        result_dict = result.model_dump()
        await record_confirmed_operation(
            session,
            proposal=proposal,
            action=spec.action,
            level=spec.level.value,
            result_dict=result_dict,
        )
        return result_dict

    _OPERATIONS[spec.action] = spec
    register_payload_schema(spec.proposal_type, spec.payload_schema)
    register_applier(spec.proposal_type, scoped_applier)


def get_operation(action: str) -> OperationSpec[Any] | None:
    return _OPERATIONS.get(action)


def lenient_tool_args_schema(payload_schema: type[BaseModel]) -> type[BaseModel]:
    """由注册项 payload schema 派生薄工具的宽松参数 schema（spec 决策 3/9）。

    字段集与类型逐一同源派生（annotation | None、默认 None、保留字段描述），
    不声明必填——缺失项仍由 payload schema 在提案创建时执法并结构化返回，
    langchain 层不做硬拦截；未知键拒绝对齐载荷纪律（ADR-0024）。
    """
    field_defs: dict[str, Any] = {}
    for name, field in payload_schema.model_fields.items():
        annotation = field.annotation
        # 声明字段的 annotation 恒非 None（pydantic 类型标注可选仅为泛型宽容）。
        assert annotation is not None
        field_defs[name] = (annotation | None, Field(default=None, description=field.description))
    return create_model(
        f"{payload_schema.__name__}ToolArgs",
        __module__=payload_schema.__module__,
        __config__=ConfigDict(extra="forbid"),
        **field_defs,
    )


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
