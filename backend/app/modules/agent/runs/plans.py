"""批量计划卡与 Run 创建（通用 Agent 第二阶段工单 05，spec 决策 6/8/10~13）。

计划工具（薄工具 ``plan_batch_operations``）→ 本模块公共提交入口：逐项判别校验
与逐项执行前快照固化后按「档位 × 阈值 × 已批准集合」确定性分流——

- 请求批准档：落 OP_BATCH 计划卡（整卡一次确认即批次授权，确认前零业务事实）；
- 帮我批准档：阈值内（同一任务直接业务目标数与写操作数均 ≤10，计入已建/已完成项）
  直建 Run 并投递 AGENT_RUN 触发 job；超阈值仍出计划卡；
- 完全访问档：不受阈值限制，但已批准计划（proposal_id 非空）的 Run 执行中新增
  目标超出已批准集合 → 升回确认（spec 用户故事 23）。

确认路径的应用器同样在本模块：确认事务内建 Run（auth_mode / instruction_text /
proposal_id 固化）＋PLANNED operations（逐项快照随行）＋AGENT_RUN 触发 job；
重复提交同一批目标不新增操作（幂等），重规划则版本递增并延展同一 Run。

依赖方向 agent → library → jobs（触发 job 与执行基础设施），零业务领域分支：
逐项动作的领域写入仍由操作注册表的应用器完成（执行发生在推进 worker）。
"""

import json
from enum import StrEnum
from typing import Any, Literal, cast

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.agent.auth_mode import effective_session_auth_mode
from app.modules.agent.operations.library_item_archive import ARCHIVE_LIBRARY_ITEM_ACTION
from app.modules.agent.operations.library_item_update import UPDATE_LIBRARY_ITEM_ACTION
from app.modules.agent.operations.registry import (
    INSTRUCTION_EXCERPT_MAX_CHARS,
    OperationSpec,
    get_operation,
    should_execute_directly,
)
from app.modules.agent.runs.models import AgentOperation, AgentRun
from app.modules.agent.runs.schemas import (
    AGENT_RUN_PLAN_INVALID,
    AUTO_APPROVE_BATCH_LIMIT,
    RUN_TERMINAL_STATUSES,
    AuthMode,
    BatchPlanAction,
    BatchPlanItemOut,
    BatchPlanItemPayload,
    BatchPlanItemSnapshot,
    BatchPlanOut,
    BatchPlanPayload,
    BatchPlanResult,
    BatchPlanSnapshot,
    OperationAuthorization,
    OperationStatus,
    PlanCorruptError,
    RunStatus,
    parse_plan_out,
    require_plan_out,
)
from app.modules.agent.runs.service import (
    count_run_operations,
    enqueue_trigger,
    find_active_run,
)
from app.modules.agent.runtime import (
    MAX_OPERATION_PROPOSALS_PER_TURN,
    AgentRuntimeContext,
)
from app.modules.library.models import AgentProposal
from app.modules.library.proposals import (
    ProposalService,
    register_applier,
    register_payload_schema,
)
from app.modules.library.schemas import ProposalCreateRequest, ProposalType
from app.shared.errors import CodedHTTPException

# 计划项动作 → 操作注册表动作名（值即注册表 action 与薄工具函数名，零漂移）。
BATCH_PLAN_ACTIONS: dict[BatchPlanAction, str] = {
    BatchPlanAction.UPDATE_LIBRARY_ITEM: UPDATE_LIBRARY_ITEM_ACTION,
    BatchPlanAction.ARCHIVE_LIBRARY_ITEM: ARCHIVE_LIBRARY_ITEM_ACTION,
}

# 计划卡提案的 Run 关联：target_type 固定值（target_id = 被延展的活跃 run，
# 首次计划不带 target）。确认时据此区分「新建 Run」与「重规划延展」。
PLAN_TARGET_TYPE = "agent_run"

type PlanItemTrigger = Literal["USER_CONFIRMED_PROPOSAL", "AUTO_EXECUTED"]


class BatchRoute(StrEnum):
    """批量提交的分流结果（提交路径的确定性判定，执行端零领域分支）。"""

    DIRECT = "DIRECT"  # 校验通过即执行：直建/延展 Run 并投递触发 job
    PLAN_CARD = "PLAN_CARD"  # 落 OP_BATCH 计划卡等整卡确认
    ALREADY_PLANNED = "ALREADY_PLANNED"  # 目标已在活跃 Run 的已批准集合内，不新增


def _plan_payload_invalid(detail: str = "提案载荷不符合该类型的结构要求") -> CodedHTTPException:
    return CodedHTTPException(code="PROPOSAL_PAYLOAD_INVALID", status_code=422, detail=detail)


def _snapshot_stale() -> CodedHTTPException:
    return CodedHTTPException(
        code="OPERATION_SNAPSHOT_STALE",
        status_code=409,
        detail="目标已发生变化，提案已失效，请重新预览确认",
    )


# 计划损坏（run.plan_json 结构非法）的稳定拒绝文案：写入口径（CodedHTTPException）
# 与工具载荷共用同一句；坏计划不得被降级当作空基线继续追加（工单 05 review）。
_PLAN_INVALID_DETAIL = "任务计划数据已损坏，无法在其上继续追加，请重新创建任务"


def _plan_invalid() -> CodedHTTPException:
    return CodedHTTPException(
        code=AGENT_RUN_PLAN_INVALID, status_code=409, detail=_PLAN_INVALID_DETAIL
    )


def parse_plan_payload(proposal: AgentProposal) -> BatchPlanPayload:
    """提案载荷 → 计划载荷（判别校验失败统一 PROPOSAL_PAYLOAD_INVALID）。"""
    try:
        value: object = json.loads(proposal.payload_json)
    except ValueError as exc:
        raise _plan_payload_invalid() from exc
    try:
        return BatchPlanPayload.model_validate(value)
    except ValidationError as exc:
        raise _plan_payload_invalid() from exc


def parse_plan_snapshot(proposal: AgentProposal, payload: BatchPlanPayload) -> BatchPlanSnapshot:
    """提案快照 → 逐项执行前快照（缺失 / 与计划项数不符 = 保守失效，spec 决策 12）。"""
    if proposal.snapshot_json is None:
        raise _snapshot_stale()
    try:
        snapshot = BatchPlanSnapshot.model_validate(json.loads(proposal.snapshot_json))
    except (ValueError, ValidationError) as exc:
        raise _snapshot_stale() from exc
    if len(snapshot.items) != len(payload.items):
        raise _snapshot_stale()
    return snapshot


def _plan_item_params(spec: OperationSpec[Any], item: BatchPlanItemPayload) -> dict[str, Any]:
    """计划项 → 该动作的判别载荷参数（逐项参数的真实执法）。

    字段名与动作载荷 schema 同源：扁平计划项列里属于该动作 schema 的字段即逐项
    参数（None 不落库——模型无法表达显式 null，先例见 registry 提交路径）。
    """
    raw = {
        name: getattr(item, name)
        for name in spec.payload_schema.model_fields
        if getattr(item, name, None) is not None
    }
    try:
        return spec.payload_schema.model_validate(raw).model_dump(mode="json")
    except ValidationError as exc:
        fields = [str(error.get("loc", ("",))[0]) for error in exc.errors() if error.get("loc")]
        shape = "/".join(dict.fromkeys(fields)) if fields else "结构"
        raise _plan_payload_invalid(f"计划项参数不符合动作要求：{shape}") from exc


def resolve_plan_items(
    items: list[BatchPlanItemPayload],
) -> list[tuple[OperationSpec[Any], dict[str, Any]]]:
    """逐项解析（动作装载 + 参数判别校验），顺序与计划项一一对应。"""
    resolved: list[tuple[OperationSpec[Any], dict[str, Any]]] = []
    for item in items:
        action = BATCH_PLAN_ACTIONS[item.action]
        spec = get_operation(action)
        if spec is None:
            raise CodedHTTPException(
                code="OPERATION_NOT_REGISTERED",
                status_code=422,
                detail=f"计划项动作未注册：{action}",
            )
        resolved.append((spec, _plan_item_params(spec, item)))
    return resolved


async def capture_plan_snapshots(
    session: AsyncSession,
    items: list[BatchPlanItemPayload],
    resolved: list[tuple[OperationSpec[Any], dict[str, Any]]],
) -> BatchPlanSnapshot:
    """逐项执行前快照固化（提交 / 直执行共用，调用方事务内）。

    目标不可达（不存在 / 已归档等）由 capture_state 抛稳定错误码：提交路径转
    结构化返回（不落提案、不建 Run），确认路径整体回滚（＝未发生）。
    """
    captured: list[BatchPlanItemSnapshot] = []
    for item, (spec, params) in zip(items, resolved, strict=True):
        state: dict[str, Any] = {}
        if spec.capture_state is not None:
            validated = spec.payload_schema.model_validate(params)
            state = (await spec.capture_state(session, validated)).model_dump(mode="json")
        captured.append(
            BatchPlanItemSnapshot(action=item.action, item_id=item.item_id, state=state)
        )
    return BatchPlanSnapshot(items=captured)


async def verify_plan_snapshots(
    session: AsyncSession,
    resolved: list[tuple[OperationSpec[Any], dict[str, Any]]],
    snapshot: BatchPlanSnapshot,
) -> None:
    """逐项执行前重验（spec 决策 12）：当前态与提交时固化快照不一致即失效。"""
    for (spec, params), captured in zip(resolved, snapshot.items, strict=True):
        if spec.capture_state is None:
            continue
        current = (
            await spec.capture_state(session, spec.payload_schema.model_validate(params))
        ).model_dump(mode="json")
        if current != captured.state:
            raise _snapshot_stale()


def _instruction_excerpt(text: str | None) -> str | None:
    if text is None:
        return None
    return text[:INSTRUCTION_EXCERPT_MAX_CHARS]


def _plan_authorization(
    *,
    payload: BatchPlanPayload,
    session_id: str | None,
    message_id: str | None,
    trigger: PlanItemTrigger,
) -> OperationAuthorization:
    """计划内操作的授权依据（ADR-0026）：Run 固化的档位＋触发指令原文＋消息引用。"""
    return OperationAuthorization(
        auth_mode=payload.auth_mode,
        trigger=trigger,
        instruction_excerpt=_instruction_excerpt(payload.instruction_text),
        session_id=session_id,
        message_id=message_id,
    )


async def create_run(
    session: AsyncSession,
    *,
    session_id: str | None,
    auth_mode: str,
    instruction_text: str | None,
    proposal_id: str | None,
) -> AgentRun:
    """建 Run（spec 决策 3）：授权依据固化（档位 / 触发指令原文 / 批次审批引用）。"""
    now = utcnow()
    run = AgentRun(
        session_id=session_id,
        auth_mode=auth_mode,
        instruction_text=instruction_text,
        proposal_id=proposal_id,
        status=RunStatus.RUNNING.value,
        plan_json=None,
        plan_version=1,
        waiting_reason=None,
        cancel_requested=False,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    await session.flush()
    return run


def run_planned_targets(run: AgentRun) -> set[tuple[str, str]]:
    """已批准计划的 (动作, 目标) 集合（计划投影口径，审计与依赖展示用）。"""
    return {
        (item.action.value, item.item_id)
        for item in parse_plan_out(run.plan_json, run.plan_version).items
    }


async def covered_targets(session: AsyncSession, run: AgentRun) -> dict[tuple[str, str], str]:
    """已覆盖目标（(动作, 目标) → 既有 operation id）：待执行（PLANNED）与已成功
    （SUCCEEDED）的操作目标。失败 / 跳过项不算覆盖——重新预览授权后允许为该目标
    新建操作（冲突解决的唯一路径：旧批准的快照已失效，重试沿用旧快照仍会失效）。
    operation id 供新增项的依赖重映射（依赖已被覆盖的步骤时直接挂到既有操作上）。"""
    covered = {
        OperationStatus.PLANNED.value,
        OperationStatus.SUCCEEDED.value,
    }
    rows = (
        await session.execute(
            select(AgentOperation.action, AgentOperation.target_id, AgentOperation.id).where(
                AgentOperation.run_id == run.id,
                AgentOperation.status.in_(covered),
                AgentOperation.target_id.is_not(None),
            )
        )
    ).all()
    return {
        (cast(str, action), cast(str, target)): cast(str, operation_id)
        for action, target, operation_id in rows
    }


def pending_plan_batch(
    payload: BatchPlanPayload,
    snapshot: BatchPlanSnapshot,
    resolved: list[tuple[OperationSpec[Any], dict[str, Any]]],
    covered: dict[tuple[str, str], str],
) -> tuple[
    BatchPlanPayload,
    BatchPlanSnapshot,
    list[tuple[OperationSpec[Any], dict[str, Any]]],
    list[int],
    dict[int, str],
]:
    """剔除已覆盖项的待执行子批（幂等口径：同一目标不重复建操作、不重做已成功项）。

    返回（子批载荷、子批快照、子批解析、子批在原文中的索引、已覆盖项索引→既有
    operation id）。依赖索引仍按**原始提交顺序**表达：新增项依赖被剔除项时，
    依赖经后者映射到既有 operation id（推进依赖判定同口径）。
    """
    keep = [
        index
        for index, item in enumerate(payload.items)
        if (item.action.value, item.item_id) not in covered
    ]
    preset = {
        index: covered[(item.action.value, item.item_id)]
        for index, item in enumerate(payload.items)
        if (item.action.value, item.item_id) in covered
    }
    subset = payload.model_copy(update={"items": [payload.items[index] for index in keep]})
    return (
        subset,
        BatchPlanSnapshot(
            plan_version=snapshot.plan_version, items=[snapshot.items[index] for index in keep]
        ),
        [resolved[index] for index in keep],
        keep,
        preset,
    )


async def append_plan_operations(
    session: AsyncSession,
    run: AgentRun,
    *,
    payload: BatchPlanPayload,
    snapshot: BatchPlanSnapshot,
    resolved: list[tuple[OperationSpec[Any], dict[str, Any]]],
    authorization: OperationAuthorization,
    proposal_id: str | None,
    submitted_indexes: list[int] | None = None,
    preset_dependencies: dict[int, str] | None = None,
) -> list[BatchPlanItemOut]:
    """计划项 → PLANNED operations（计划顺序即推进顺序）＋ 计划投影写回 run。

    依赖索引按原始提交顺序解析为 operation id（同一次提交内更早的步骤；依赖被
    已覆盖项时经 preset_dependencies 挂到既有操作上）；重规划延展时新批追加在
    既有计划之后，版本随之递增（已批准集合是「对象集合＋参数＋版本」的组合，
    spec 用户故事 23）。

    写入口径严格读既有计划：损坏即拒绝追加（降级为空基线会把新计划写成「只剩
    本批」的残缺集合、索引失真，旧步骤的排序与依赖一并丢失；工单 05 review）。
    """
    now = utcnow()
    try:
        plan = require_plan_out(run.plan_json, run.plan_version)
    except PlanCorruptError as exc:
        raise _plan_invalid() from exc
    base_index = len(plan.items)
    appended: list[BatchPlanItemOut] = []
    dependency_ids: dict[int, str] = dict(preset_dependencies or {})
    indexes = (
        submitted_indexes if submitted_indexes is not None else list(range(len(payload.items)))
    )
    for index, (item, (spec, params)) in enumerate(zip(payload.items, resolved, strict=True)):
        validated = spec.payload_schema.model_validate(params)
        target = spec.target_resolver(validated) if spec.target_resolver is not None else None
        operation = AgentOperation(
            run_id=run.id,
            proposal_id=proposal_id,
            action=spec.action,
            level=spec.level.value,
            target_type=target[0] if target is not None else None,
            target_id=target[1] if target is not None else None,
            payload_json=json.dumps(params, ensure_ascii=False, separators=(",", ":")),
            snapshot_json=json.dumps(
                snapshot.items[index].state, ensure_ascii=False, separators=(",", ":")
            ),
            authorization_json=authorization.model_dump_json(),
            status=OperationStatus.PLANNED.value,
            attempts=1,
            result_json=None,
            error_code=None,
            created_at=now,
            updated_at=now,
            finished_at=None,
        )
        session.add(operation)
        await session.flush()
        dependency_ids[indexes[index]] = operation.id
        appended.append(
            BatchPlanItemOut(
                index=base_index + index,
                action=item.action,
                item_id=item.item_id,
                params=params,
                operation_id=operation.id,
                depends_on=[
                    dependency_ids[dependency]
                    for dependency in item.depends_on
                    if dependency in dependency_ids
                ],
            )
        )
    run.plan_json = BatchPlanOut(
        plan_version=payload.plan_version, items=[*plan.items, *appended]
    ).model_dump_json()
    run.updated_at = now
    return appended


def batch_route(
    *,
    auth_mode: AuthMode,
    active: AgentRun | None,
    items: list[BatchPlanItemPayload],
    resolved: list[tuple[OperationSpec[Any], dict[str, Any]]],
    covered: dict[tuple[str, str], str],
    existing_operation_count: int,
) -> BatchRoute:
    """批量提交分流（spec 决策 10/11，纯判定）：直执行 / 计划卡 / 已在计划内。

    执行中（存在活跃 Run）新增目标一律升回确认：计划的对象集合＋参数＋版本即
    授权范围，超出范围的新目标在完全访问档同样需要重新确认（spec 用户故事 23）；
    帮我批准档阈值只决定「一批全新目标」能否自动建单，不放宽已运行计划的集合。
    等待态 Run 只接受显式唤醒（继续 / 重试），故经工具追加也转计划卡（确认即显式动作）。
    """
    if auth_mode == AuthMode.REQUEST_APPROVAL:
        return BatchRoute.PLAN_CARD
    # 档位不允许自动执行的项（帮我批准档的 L2/L3）恒出计划卡逐项确认。
    if not all(should_execute_directly(auth_mode, spec.level) for spec, _params in resolved):
        return BatchRoute.PLAN_CARD
    if active is None:
        # 全新计划（无活跃 Run）：帮我批准档仍受阈值约束，超阈值出计划卡。
        if auth_mode == AuthMode.AUTO_APPROVE and len(items) > AUTO_APPROVE_BATCH_LIMIT:
            return BatchRoute.PLAN_CARD
        return BatchRoute.DIRECT
    new_items = [item for item in items if (item.action.value, item.item_id) not in covered]
    if not new_items:
        return BatchRoute.ALREADY_PLANNED
    if active.status != RunStatus.RUNNING.value:
        return BatchRoute.PLAN_CARD
    if active.proposal_id is not None or auth_mode == AuthMode.FULL_ACCESS:
        # 执行中目标超出固定计划集合（完全访问档亦然，spec 用户故事 23）。
        return BatchRoute.PLAN_CARD
    if existing_operation_count + len(new_items) > AUTO_APPROVE_BATCH_LIMIT:
        return BatchRoute.PLAN_CARD
    return BatchRoute.DIRECT


def _run_tool_payload(
    run: AgentRun, *, added_item_count: int, detail: str | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ok": True,
        "run": {
            "run_id": run.id,
            "status": run.status,
            "plan_version": run.plan_version,
            "added_item_count": added_item_count,
        },
    }
    if detail is not None:
        body["run"]["detail"] = detail
    return body


async def submit_batch_plan(runtime: AgentRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    """计划工具公共提交入口（工单 05）：校验 → 预算 → 分流 → 执行或落计划卡。

    返回工具 JSON 载荷（模型转述给用户）：
    - 直执行 → {ok: True, run: {run_id, status, plan_version, added_item_count}}；
    - 计划卡 → {ok: True, plan_proposal: {proposal_id, plan_version, item_count}}；
    - 已在计划内 → {ok: True, run: {..., added_item_count: 0, detail}}；
    - 校验失败 → {ok: False, error / missing / detail}（结构化，模型追问或转述）。

    预算口径：一张计划卡 / 一个 Run 计一次操作预算（计划项数由计划规模上限与
    档位阈值各自约束；超每轮上限拒绝不截断，先例见 registry 提交路径）。
    """
    if runtime.budget.operations_created >= MAX_OPERATION_PROPOSALS_PER_TURN:
        return {
            "ok": False,
            "error": "OPERATION_PROPOSAL_LIMIT",
            "detail": f"每轮最多执行 {MAX_OPERATION_PROPOSALS_PER_TURN} 条操作",
        }
    try:
        plan = BatchPlanPayload.model_validate({"items": args.get("items") or []})
    except ValidationError as exc:
        return _validation_tool_payload(exc)
    try:
        resolved = resolve_plan_items(plan.items)
    except CodedHTTPException as exc:
        return {"ok": False, "error": exc.code, "detail": exc.detail}
    runtime.budget.operations_created += 1
    effective_mode = effective_session_auth_mode(runtime.session_id, runtime.auth_mode)
    async with runtime.session_factory() as session, session.begin():
        active = await find_active_run(session, runtime.session_id)
        if active is not None:
            try:
                require_plan_out(active.plan_json, active.plan_version)
            except PlanCorruptError:
                # 活跃任务计划损坏：不追加、也不落新计划卡（确认同样会被拒），
                # 结构化返回原因由模型转述（先例：目标不可达的拒绝）。
                return {
                    "ok": False,
                    "error": AGENT_RUN_PLAN_INVALID,
                    "detail": _PLAN_INVALID_DETAIL,
                }
        existing_count = await count_run_operations(session, active.id) if active else 0
        covered: dict[tuple[str, str], str] = (
            await covered_targets(session, active) if active is not None else {}
        )
        route = batch_route(
            auth_mode=effective_mode,
            active=active,
            items=plan.items,
            resolved=resolved,
            covered=covered,
            existing_operation_count=existing_count,
        )
        if route == BatchRoute.ALREADY_PLANNED:
            assert active is not None
            return _run_tool_payload(active, added_item_count=0, detail="目标已在执行计划中")
        try:
            snapshot = await capture_plan_snapshots(session, plan.items, resolved)
        except CodedHTTPException as exc:
            # 目标不可达：不落提案、不建 Run（结构化返回由模型转述）。
            return {"ok": False, "error": exc.code, "detail": exc.detail}
        payload = plan.model_copy(
            update={
                "plan_version": active.plan_version + 1 if active is not None else 1,
                "auth_mode": effective_mode,
                "instruction_text": runtime.instruction_excerpt,
            }
        )
        # 幂等口径：已覆盖项不重复建操作（直执行与确认路径都只落待执行子批）。
        batch, batch_snapshot, batch_resolved, batch_indexes, preset = pending_plan_batch(
            payload, snapshot, resolved, covered
        )
        if route == BatchRoute.DIRECT:
            if active is None:
                run = await create_run(
                    session,
                    session_id=runtime.session_id,
                    auth_mode=effective_mode.value,
                    instruction_text=runtime.instruction_excerpt,
                    proposal_id=None,
                )
            else:
                run = active
                run.plan_version = payload.plan_version
                run.updated_at = utcnow()
            appended = await append_plan_operations(
                session,
                run,
                payload=batch,
                snapshot=batch_snapshot,
                resolved=batch_resolved,
                authorization=_plan_authorization(
                    payload=payload,
                    session_id=runtime.session_id,
                    message_id=runtime.message_id,
                    trigger="AUTO_EXECUTED",
                ),
                proposal_id=None,
                submitted_indexes=batch_indexes,
                preset_dependencies=preset,
            )
            await enqueue_trigger(session, run.id)
            return _run_tool_payload(run, added_item_count=len(appended))
        proposal = await ProposalService.create_core(
            session,
            ProposalCreateRequest(
                proposal_type=ProposalType.OP_BATCH,
                payload=payload.model_dump(mode="json"),
                session_id=runtime.session_id,
                message_id=runtime.message_id,
                target_type=PLAN_TARGET_TYPE if active is not None else None,
                target_id=active.id if active is not None else None,
            ),
            snapshot_json=snapshot.model_dump_json(),
        )
        return {
            "ok": True,
            "plan_proposal": {
                "proposal_id": proposal.id,
                "plan_version": payload.plan_version,
                "item_count": len(payload.items),
            },
        }


def _validation_tool_payload(exc: ValidationError) -> dict[str, Any]:
    """载荷校验失败 → 结构化工具返回（字段路径 + 条件说明，模型转述追问）。"""
    body: dict[str, Any] = {"ok": False, "error": "PROPOSAL_PAYLOAD_INVALID"}
    fields = [
        ".".join(str(part) for part in error.get("loc", ()))
        for error in exc.errors()
        if error.get("loc")
    ]
    if fields:
        body["missing"] = list(dict.fromkeys(fields))
    detail = next(
        (
            str(error.get("msg", "")).removeprefix("Value error, ")
            for error in exc.errors()
            if not error.get("loc")
        ),
        "",
    )
    if detail:
        body["detail"] = detail
    return body


async def apply_batch_plan(session: AsyncSession, proposal: AgentProposal) -> dict[str, Any]:
    """OP_BATCH 应用器（提案框架契约：调用方确认事务内、不得自行 begin）。

    计划卡确认 = 批次授权（spec 决策 13）：建 Run（auth_mode / instruction_text /
    proposal_id 固化）或按 target 延展已批准计划的活跃 Run（版本递增），逐项
    执行前重验（与单步动作同口径：提交后目标已变 → OPERATION_SNAPSHOT_STALE，
    旧批准作废需重新预览），逐项落 PLANNED operation 并投递 AGENT_RUN 触发 job。
    """
    payload = parse_plan_payload(proposal)
    snapshot = parse_plan_snapshot(proposal, payload)
    resolved = resolve_plan_items(payload.items)
    run = await _target_run(session, proposal, payload)
    # 计划版本以 Run 上生效的版本为准（延展时可能被提升为单调递增版本），
    # 保证 run.plan_json 与「已批准集合」的版本口径一致。
    payload = payload.model_copy(update={"plan_version": run.plan_version})
    # 幂等口径与直执行同源：已覆盖项不重复建操作（同一目标不重做已成功项、
    # 不重复计数）；失败 / 跳过项不算覆盖——重新预览授权后仍会落新操作。
    covered = await covered_targets(session, run)
    batch, batch_snapshot, batch_resolved, batch_indexes, preset = pending_plan_batch(
        payload, snapshot, resolved, covered
    )
    await verify_plan_snapshots(session, batch_resolved, batch_snapshot)
    appended = await append_plan_operations(
        session,
        run,
        payload=batch,
        snapshot=batch_snapshot,
        resolved=batch_resolved,
        authorization=_plan_authorization(
            payload=payload,
            session_id=proposal.session_id,
            message_id=proposal.message_id,
            trigger="USER_CONFIRMED_PROPOSAL",
        ),
        proposal_id=proposal.id,
        submitted_indexes=batch_indexes,
        preset_dependencies=preset,
    )
    await enqueue_trigger(session, run.id)
    return BatchPlanResult(
        run_id=run.id, plan_version=payload.plan_version, item_count=len(appended)
    ).model_dump(mode="json")


async def _target_run(
    session: AsyncSession, proposal: AgentProposal, payload: BatchPlanPayload
) -> AgentRun:
    """确认目标 Run：首次计划新建；重规划（target=agent_run）延展同一 Run。

    无显式 target（提交时尚无活跃 Run）时回落到本会话当前活跃 Run：同一会话里
    先提交的两张计划卡先后确认时延展同一 Run，而不是各建一个 Run 重复执行同一批
    目标（幂等口径在应用器里按已覆盖项收敛）。活跃 Run 已终态则视为新计划新建
    Run（旧 Run 的执行历史不动）。
    """
    run: AgentRun | None = None
    if proposal.target_type == PLAN_TARGET_TYPE and proposal.target_id is not None:
        run = await session.get(AgentRun, proposal.target_id)
    elif proposal.session_id is not None:
        run = await find_active_run(session, proposal.session_id)
    if run is not None and run.status not in {status.value for status in RUN_TERMINAL_STATUSES}:
        # 版本单调递增：多张未确认计划卡可能拿到同一提交时版本，确认时以
        # Run 当前版本为下界（版本是「已批准集合」的组成部分，不能回退）。
        run.plan_version = max(payload.plan_version, run.plan_version + 1)
        if run.status == RunStatus.WAITING_USER.value:
            # 计划卡确认是显式动作：为等待中的任务批准新步骤即继续推进
            # （唤醒只由显式动作触发，spec 决策 7；不自动猜测可否继续）。
            run.status = RunStatus.RUNNING.value
            run.waiting_reason = None
        run.updated_at = utcnow()
        return run
    return await create_run(
        session,
        session_id=proposal.session_id,
        auth_mode=payload.auth_mode.value,
        instruction_text=payload.instruction_text,
        proposal_id=proposal.id,
    )


register_payload_schema(ProposalType.OP_BATCH, BatchPlanPayload)
register_applier(ProposalType.OP_BATCH, apply_batch_plan)
