"""操作注册表与公共提交入口（通用 Agent 第二阶段工单 02）：分流与直执行。

术语（spec 决策 3）：动作（action）= 模型可调用的工具语义；操作（Operation）
= 一次受控执行的事实记录（回执）。注册表以稳定动作标识声明提案类型、操作
级别、判别 payload schema、类型化结果投影与应用器；写工具是薄壳（docstring
面向模型、参数 schema 由注册项 payload schema 派生，校验执法在提交时）——
公共执行流程零领域专属分支，新写动作 = 一个注册项 + 一个薄工具。

提交路径按授权档位确定性分流（spec 决策 10，执行端执法——提示词与工具
描述不随档位改变）：默认档落提案等确认（现状零变化）；AUTO_APPROVE 下
L1 直执行、L3 恒落提案；FULL_ACCESS 下 L1/L3 均直执行。直执行单事务写
operation＋业务结果，失败独立小事务落 FAILED＋稳定错误码（提案
_mark_failed 先例）。
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.agent.auth_mode import effective_session_auth_mode
from app.modules.agent.runs.schemas import AuthMode, OperationAuthorization
from app.modules.agent.runs.service import record_confirmed_operation, record_direct_execution
from app.modules.agent.runtime import (
    MAX_OPERATION_PROPOSALS_PER_TURN,
    AgentRuntimeContext,
)
from app.modules.library.models import AgentProposal
from app.modules.library.proposals import ProposalService, register_applier, register_payload_schema
from app.modules.library.schemas import ProposalCreateRequest, ProposalType
from app.shared.errors import CodedHTTPException

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


def operation_payload_dict(proposal: AgentProposal) -> dict[str, Any]:
    """解析提案载荷 JSON（应用器共用）：非 dict 形状返回空 dict 由 schema 校验兜底。"""
    try:
        value: object = json.loads(proposal.payload_json)
    except ValueError:
        return {}
    # 元素类型静态未知（载荷源自 json.loads 的运行时收窄，与 proposals._as_dict 同口径）。
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


# 触发指令摘录上限：authorization_json 的授权依据素材（spec 用户故事 7：
# 回执可追溯「当时档位、触发指令原文、时间」，截断防超长指令全文入库）。
INSTRUCTION_EXCERPT_MAX_CHARS = 200


def should_execute_directly(auth_mode: AuthMode, level: OperationLevel) -> bool:
    """提交路径分流（spec 决策 10，纯函数）：True＝校验通过即执行，False＝落提案。

    - REQUEST_APPROVAL：一切写操作落提案等确认（与第一阶段零行为变更）；
    - AUTO_APPROVE：L1 直执行；L2（批量走计划卡）与 L3（删除类恒逐项确认）落提案；
    - FULL_ACCESS：除禁止项外全自动（禁止项任何档位不暴露，不在注册面）。

    后续票新动作按注册表 level 声明自动继承本分流，零执行端改动。
    """
    if auth_mode == AuthMode.REQUEST_APPROVAL:
        return False
    if auth_mode == AuthMode.AUTO_APPROVE:
        return level == OperationLevel.L1
    return True


def _direct_authorization(
    runtime: AgentRuntimeContext, auth_mode: AuthMode
) -> OperationAuthorization:
    """直执行回执的授权依据（ADR-0026）：执行时生效档＋触发指令摘录＋消息引用。"""
    excerpt = runtime.instruction_excerpt
    if excerpt is not None and len(excerpt) > INSTRUCTION_EXCERPT_MAX_CHARS:
        excerpt = excerpt[:INSTRUCTION_EXCERPT_MAX_CHARS]
    return OperationAuthorization(
        auth_mode=auth_mode,
        trigger="AUTO_EXECUTED",
        instruction_excerpt=excerpt,
        session_id=runtime.session_id,
        message_id=runtime.message_id,
    )


async def _execute_operation_directly(
    runtime: AgentRuntimeContext,
    spec: OperationSpec[Any],
    validated: BaseModel,
    auth_mode: AuthMode,
) -> dict[str, Any]:
    """自动档直执行（spec 决策 11）：单事务写 operation＋业务结果。

    auth_mode 是本次提交的生效档（会话覆盖与本轮起点取更严格者），
    授权依据与回执载荷如实记录执行时实际生效档。成功：应用器领域写入与
    operation 行（SUCCEEDED＋result 回填＋授权依据）同一事务原子提交；
    失败：业务事务整体回滚（＝未发生），独立小事务落 FAILED operation＋
    稳定错误码（_mark_failed 先例，诊断不断链）。返回工具 JSON 载荷：
    成功 {ok, executed}；失败 {ok: False, error}（模型转述原因）。
    """
    payload_json = validated.model_dump_json()
    authorization = _direct_authorization(runtime, auth_mode)
    # 应用器契约是 (session, proposal) 且只消费 payload_json（course_create /
    # text_record_add 均然），构造未落库的 transient 提案实例喂给应用器——
    # 领域应用器零改动、提案路径与直执行路径复用同一执行核心。
    transient = AgentProposal(
        id=str(uuid4()),
        proposal_type=spec.proposal_type.value,
        status="PENDING",
        payload_json=payload_json,
        created_at=utcnow(),
    )
    async with runtime.session_factory() as session:
        try:
            async with session.begin():
                result = spec.result_schema.model_validate(await spec.applier(session, transient))
                operation = await record_direct_execution(
                    session,
                    action=spec.action,
                    level=spec.level.value,
                    payload_json=payload_json,
                    authorization=authorization,
                    result_dict=result.model_dump(),
                )
        except CodedHTTPException as exc:
            async with session.begin():
                await record_direct_execution(
                    session,
                    action=spec.action,
                    level=spec.level.value,
                    payload_json=payload_json,
                    authorization=authorization,
                    result_dict=None,
                    error_code=exc.code,
                )
            return {"ok": False, "error": exc.code, "executed": None}
        except Exception:
            # 非编码异常（bug / 环境故障）：原子回滚＝未发生，落 INTERNAL 稳定
            # 错误码（先例：提案框架非编码异常路径）。
            async with session.begin():
                await record_direct_execution(
                    session,
                    action=spec.action,
                    level=spec.level.value,
                    payload_json=payload_json,
                    authorization=authorization,
                    result_dict=None,
                    error_code="INTERNAL",
                )
            return {"ok": False, "error": "INTERNAL", "executed": None}
    return {
        "ok": True,
        "executed": {
            "operation_id": operation.id,
            "action": spec.action,
            "level": spec.level.value,
            "auth_mode": auth_mode.value,
            "payload": validated.model_dump(),
            "result": result.model_dump(),
        },
    }


async def submit_operation(
    runtime: AgentRuntimeContext, action: str, args: dict[str, Any]
) -> dict[str, Any]:
    """操作类写工具的公共提交入口（spec 决策 10）：校验 → 每轮上限执法 →
    按当轮授权档位分流（默认档落提案＝现状零变化，自动档直执行）。

    返回工具 JSON 载荷：
    - 校验失败 → {ok: False, missing: [...], detail?}（模型转述追问缺失项）；
    - 超每轮上限 → {ok: False, error: OPERATION_PROPOSAL_LIMIT}（拒绝不截断）；
    - 落提案 → {ok: True, proposals: [{proposal_id, action, payload, status}]}；
    - 直执行 → {ok: True, executed: {...}} 或 {ok: False, error}（见直执行）。
    """
    spec = get_operation(action)
    if spec is None:
        return {"ok": False, "error": "OPERATION_NOT_REGISTERED", "proposals": []}
    if runtime.budget.operations_created >= MAX_OPERATION_PROPOSALS_PER_TURN:
        return {
            "ok": False,
            "error": "OPERATION_PROPOSAL_LIMIT",
            "detail": f"每轮最多执行 {MAX_OPERATION_PROPOSALS_PER_TURN} 条操作",
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
    runtime.budget.operations_created += 1
    # 生效档＝会话覆盖与本轮起点档取更严格者（spec 用户故事 6）：流式生成
    # 中途降档经注册表即时约束本轮后续提交；升档自下一轮（请求携带新档）放宽。
    effective_mode = effective_session_auth_mode(runtime.session_id, runtime.auth_mode)
    if should_execute_directly(effective_mode, spec.level):
        return await _execute_operation_directly(runtime, spec, validated, effective_mode)
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
