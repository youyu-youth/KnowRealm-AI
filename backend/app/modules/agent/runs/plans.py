"""批量计划卡与 Run 创建（通用 Agent 第二阶段工单 05，spec 决策 6/8/10~13）。

计划工具（薄工具 ``plan_batch_operations``）→ 本模块公共提交入口：逐项判别校验
与逐项执行前快照固化后按「档位 × 阈值 × 已批准集合」确定性分流——

- 请求批准档：落 OP_BATCH 计划卡（整卡一次确认即批次授权，确认前零业务事实）；
- 帮我批准档：阈值内（本会话直接业务目标数与写操作数累计 ≤10，计入已建 / 已完成
  项，拆调用 / 分段 / 重启不重置）直建 Run 并投递 AGENT_RUN 触发 job；超阈值仍出
  计划卡；
- 完全访问档：不受阈值限制，但已批准计划（proposal_id 非空）的 Run 执行中新增
  目标超出已批准集合 → 升回确认（spec 用户故事 23）。

确认路径的应用器同样在本模块：确认事务内建 Run（auth_mode / instruction_text /
proposal_id 固化）＋PLANNED operations（逐项快照随行）＋AGENT_RUN 触发 job；
重复提交同一批目标不新增操作（幂等），重规划则版本递增并延展同一 Run。

依赖方向 agent → library → jobs（触发 job 与执行基础设施），零业务领域分支：
逐项动作的领域写入仍由操作注册表的应用器完成（执行发生在推进 worker）。
"""

import json
from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, cast

from pydantic import ValidationError
from pydantic_core import ErrorDetails
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.agent.auth_mode import effective_session_auth_mode
from app.modules.agent.operations.course_create import CREATE_COURSE_ACTION
from app.modules.agent.operations.goal_create import CREATE_GOAL_ACTION
from app.modules.agent.operations.library_item_archive import ARCHIVE_LIBRARY_ITEM_ACTION
from app.modules.agent.operations.library_item_ingest import INGEST_LIBRARY_ITEM_ACTION
from app.modules.agent.operations.library_item_update import UPDATE_LIBRARY_ITEM_ACTION
from app.modules.agent.operations.local_document_ingest import INGEST_LOCAL_DOCUMENT_ACTION
from app.modules.agent.operations.plan_draft import GENERATE_PLAN_DRAFT_ACTION
from app.modules.agent.operations.registry import (
    INSTRUCTION_EXCERPT_MAX_CHARS,
    OperationSpec,
    get_operation,
    should_execute_directly,
)
from app.modules.agent.operations.shared_ref import ADD_SHARED_REF_ACTION
from app.modules.agent.operations.text_record_add import ADD_TEXT_RECORD_ACTION
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
    StepOutputRef,
    params_output_refs,
    parse_plan_out,
    require_plan_out,
)
from app.modules.agent.runs.service import (
    count_session_operations,
    enqueue_trigger,
    find_active_run,
)
from app.modules.agent.runtime import (
    CHAT_TURN_CANCELLED,
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
# 工单 06 起纳入创建类动作（建课 / URL 导入）：导入步骤提交后台解析 job，Run
# 推进到该步成功后转 WAITING_JOB（spec M2 执行闭环）。工单 07 起纳入多资料
# 建课编排动作面：四类来源导入（URL / 本地文档 / 粘贴文本）＋库内资料挂课
# （改归属或共享引用）＋建目标＋计划草案产出（末步，草案确认是 Run 外闸门）。
BATCH_PLAN_ACTIONS: dict[BatchPlanAction, str] = {
    BatchPlanAction.UPDATE_LIBRARY_ITEM: UPDATE_LIBRARY_ITEM_ACTION,
    BatchPlanAction.ARCHIVE_LIBRARY_ITEM: ARCHIVE_LIBRARY_ITEM_ACTION,
    BatchPlanAction.CREATE_COURSE: CREATE_COURSE_ACTION,
    BatchPlanAction.INGEST_LIBRARY_ITEM: INGEST_LIBRARY_ITEM_ACTION,
    BatchPlanAction.INGEST_LOCAL_DOCUMENT: INGEST_LOCAL_DOCUMENT_ACTION,
    BatchPlanAction.ADD_TEXT_RECORD: ADD_TEXT_RECORD_ACTION,
    BatchPlanAction.ADD_SHARED_REF: ADD_SHARED_REF_ACTION,
    BatchPlanAction.CREATE_GOAL: CREATE_GOAL_ACTION,
    BatchPlanAction.GENERATE_PLAN_DRAFT: GENERATE_PLAN_DRAFT_ACTION,
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


def _only_deferred_errors(exc: ValidationError, ref_names: Collection[str]) -> bool:
    """校验失败是否全部「因引用而放行」：①model 级条件校验（如 update 的
    「至少一个修改字段」——错误无字段路径）；②引用字段自身的 missing 错误
    （工单 07：必填引用消费方如 create_goal / add_text_record 的 course_id，
    剔除后缺失属预期——引用字段执行时注入终值，自身即构成创建 / 修改意图）。
    其余字段级校验（类型 / 枚举 / 长度）不放行。"""
    if not ref_names:
        return False
    errors = exc.errors()
    if not errors:
        return False

    def _deferred(error: ErrorDetails) -> bool:
        loc = error.get("loc")
        if not loc:
            return True
        return str(loc[0]) in ref_names and error.get("type") == "missing"

    return all(_deferred(error) for error in errors)


def _concrete_payload(
    spec: OperationSpec[Any],
    params: dict[str, Any],
    ref_names: Collection[str],
) -> Any:
    """剔除引用字段后的动作载荷实例（快照 / 重验 / 定位共用）。

    仅因引用而放行的校验失败（:func:`_only_deferred_errors`）以
    model_construct 构造——修改类含引用项的快照读取不受「至少一个修改字段」
    等条件校验拦截（引用即修改意图，工单 06 review 口径）。
    """
    concrete = {k: v for k, v in params.items() if k not in ref_names}
    try:
        return spec.payload_schema.model_validate(concrete)
    except ValidationError as exc:
        if _only_deferred_errors(exc, ref_names):
            return spec.payload_schema.model_construct(**concrete)
        raise


def _plan_item_params(spec: OperationSpec[Any], item: BatchPlanItemPayload) -> dict[str, Any]:
    """计划项 → 该动作的判别载荷参数（逐项参数的真实执法）。

    字段名与动作载荷 schema 同源：扁平计划项列里属于该动作 schema 的字段即逐项
    参数（None 不落库——模型无法表达显式 null，先例见 registry 提交路径）。
    输出引用字段（StepOutputRef）执行时才解析为终值：判别校验只覆盖已知终值
    字段、引用原样保留进操作载荷（推进 worker 解析后回填）；引用字段若为该
    动作必填项，missing 属预期放行（执行路径的 payload 判别承担类型执法）。
    """
    raw = {
        name: getattr(item, name)
        for name in spec.payload_schema.model_fields
        if getattr(item, name, None) is not None
    }
    deferred = {name: value for name, value in raw.items() if isinstance(value, StepOutputRef)}
    try:
        params = spec.payload_schema.model_validate(
            {k: v for k, v in raw.items() if k not in deferred}
        ).model_dump(mode="json")
    except ValidationError as exc:
        if not _only_deferred_errors(exc, deferred.keys()):
            fields = [str(error.get("loc", ("",))[0]) for error in exc.errors() if error.get("loc")]
            detail_parts = [
                str(error.get("msg", "")).removeprefix("Value error, ")
                for error in exc.errors()
                if not error.get("loc")
            ]
            shape = "/".join(dict.fromkeys(fields)) if fields else "结构"
            detail = f"计划项参数不符合动作要求：{shape}"
            if detail_parts:
                detail = f"{detail}（{'；'.join(detail_parts)}）"
            raise _plan_payload_invalid(detail) from exc
        # 因引用放行（missing / model 级条件校验）：具体值直接投影，引用字段由
        # update 补回；枚举等类型转换交执行路径的 payload 判别（model_construct
        # 实例的 dump 会对 str 枚举值告警，故不经实例）。
        params = {k: v for k, v in raw.items() if k not in deferred}
    params.update({name: ref.model_dump(mode="json") for name, ref in deferred.items()})
    return params


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


def _skip_item_snapshot(item: BatchPlanItemPayload, params: dict[str, Any]) -> bool:
    """该项是否跳过提交期快照：创建类（item_id 空）且参数含输出引用——引用
    定位的对象（新建课程 / 新建目标）在同批前序步骤产出，提交与确认时还不
    存在、capture 无从读取（照常执行会误拒整张卡）；推进 worker 解析引用后
    现固化兜底（空快照判定），状态依赖由应用器与存储层校验兜底。

    修改类（item_id 非空）不跳过：剔除引用字段后照常固化目标快照（对象版本
    绑定与 Undo 补偿不因引用降级，工单 06 review 口径）。
    """
    return item.item_id is None and bool(params_output_refs(params))


async def capture_plan_snapshots(
    session: AsyncSession,
    items: list[BatchPlanItemPayload],
    resolved: list[tuple[OperationSpec[Any], dict[str, Any]]],
) -> BatchPlanSnapshot:
    """逐项执行前快照固化（提交 / 直执行共用，调用方事务内）。

    目标不可达（不存在 / 已归档等）由 capture_state 抛稳定错误码：提交路径转
    结构化返回（不落提案、不建 Run），确认路径整体回滚（＝未发生）。参数含
    输出引用的**修改类**项（目标 item 既有，引用的只是 course_id 等参数字段）
    剔除引用字段后照常固化目标快照；创建类（capture_state 为 None，或创建类
    含引用按 :func:`_skip_item_snapshot` 跳过）恒无快照。
    """
    captured: list[BatchPlanItemSnapshot] = []
    for item, (spec, params) in zip(items, resolved, strict=True):
        state: dict[str, Any] = {}
        if spec.capture_state is not None and not _skip_item_snapshot(item, params):
            validated = _concrete_payload(spec, params, params_output_refs(params))
            state = (await spec.capture_state(session, validated)).model_dump(mode="json")
        captured.append(
            BatchPlanItemSnapshot(action=item.action, item_id=item.item_id, state=state)
        )
    return BatchPlanSnapshot(items=captured)


async def verify_plan_snapshots(
    session: AsyncSession,
    resolved: list[tuple[OperationSpec[Any], dict[str, Any]]],
    snapshot: BatchPlanSnapshot,
    items: list[BatchPlanItemPayload] | None = None,
) -> None:
    """逐项执行前重验（spec 决策 12）：当前态与提交时固化快照不一致即失效。

    含输出引用的修改类项同口径重验（剔除引用字段后读取比对——引用字段值
    执行时才注入，不参与目标状态读取）；创建类（capture_state 为 None，或
    创建类含引用无提交期快照——引用对象尚未产出，比对无意义）跳过。"""
    for index, ((spec, params), captured) in enumerate(zip(resolved, snapshot.items, strict=True)):
        if spec.capture_state is None:
            continue
        if items is not None and _skip_item_snapshot(items[index], params):
            continue
        current = (
            await spec.capture_state(
                session, _concrete_payload(spec, params, params_output_refs(params))
            )
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


def run_planned_targets(run: AgentRun) -> set[tuple[str, str | None]]:
    """已批准计划的 (动作, 目标) 集合（计划投影口径，审计与依赖展示用；
    创建类步骤目标为空——无既有目标）。"""
    return {
        (item.action.value, item.item_id)
        for item in parse_plan_out(run.plan_json, run.plan_version).items
    }


@dataclass(frozen=True)
class LiveStep:
    """同一 (动作, 目标) 的既有活步骤：待执行（PLANNED）优先，否则最近一次已成功
    （SUCCEEDED）。params 承载「已批准集合」里的参数部分（spec 决策 13），用于判定
    本次提交是重复覆盖还是参数变更。"""

    operation_id: str
    params: dict[str, Any]
    status: str


def _stored_params(payload_json: str) -> dict[str, Any]:
    """既有操作载荷参数（坏值＝空：与任何新参数都不同 → 走变更路径，不静默丢弃）。"""
    try:
        value: object = json.loads(payload_json)
    except ValueError:
        return {}
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


async def covered_targets(session: AsyncSession, run: AgentRun) -> dict[tuple[str, str], LiveStep]:
    """每个 (动作, 目标) 的既有活步骤（待执行优先，否则最近一次已成功）。

    失败 / 跳过项不算活步骤——重新预览授权后允许为该目标新建操作（冲突解决的唯一
    路径：旧批准的快照已失效，重试沿用旧快照仍会失效）。参数一致的项＝已覆盖（不
    重复建操作、不重做已成功项）；参数不一致＝重新确认过的变更，按活步骤状态就地
    改写（待执行）或追加新步骤（已成功）——不能只看 (动作, 目标) 就把变更丢弃
    （spec 用户故事 23「改参数后重新确认」，工单 05 review）。
    """
    covered = {
        OperationStatus.PLANNED.value,
        OperationStatus.SUCCEEDED.value,
    }
    rows = (
        await session.execute(
            select(
                AgentOperation.action,
                AgentOperation.target_id,
                AgentOperation.id,
                AgentOperation.payload_json,
                AgentOperation.status,
            )
            .where(
                AgentOperation.run_id == run.id,
                AgentOperation.status.in_(covered),
                AgentOperation.target_id.is_not(None),
            )
            .order_by(AgentOperation.created_at, AgentOperation.id)
        )
    ).all()
    steps: dict[tuple[str, str], LiveStep] = {}
    for action, target, operation_id, payload_json, status in rows:
        key = (cast(str, action), cast(str, target))
        previous = steps.get(key)
        if previous is not None and previous.status == OperationStatus.PLANNED.value:
            continue  # 待执行步骤优先（同一目标至多一条），更晚的已成功历史不覆盖它
        steps[key] = LiveStep(
            operation_id=cast(str, operation_id),
            params=_stored_params(cast(str, payload_json)),
            status=cast(str, status),
        )
    return steps


def _covered_unchanged(
    item: BatchPlanItemPayload,
    params: dict[str, Any],
    covered: dict[tuple[str, str], LiveStep],
) -> bool:
    """该项是否已被既有活步骤以**相同参数**覆盖（「已在计划中」判定）。

    参数变更不算「已在计划中」——它是本次重新确认的修改，按档位与固定计划约束处理。
    创建类步骤（item_id 空）无既有目标，恒未被覆盖。
    """
    if item.item_id is None:
        return False
    step = covered.get((item.action.value, item.item_id))
    return step is not None and step.params == params


def pending_plan_batch(
    payload: BatchPlanPayload,
    snapshot: BatchPlanSnapshot,
    resolved: list[tuple[OperationSpec[Any], dict[str, Any]]],
    covered: dict[tuple[str, str], LiveStep],
) -> tuple[
    BatchPlanPayload,
    BatchPlanSnapshot,
    list[tuple[OperationSpec[Any], dict[str, Any]]],
    list[int],
    dict[int, str],
    dict[int, str],
]:
    """待执行子批与既有活步骤的分类（幂等口径＋参数变更口径）。

    逐项分类（spec 决策 13：已批准集合＝对象集合＋参数＋版本）：
    - 无活步骤 → 待执行子批（新建操作）；
    - 活步骤参数一致 → 已覆盖（不重复建操作、不重做已成功项），依赖经 preset 映射
      到既有 operation id；
    - 活步骤参数不一致 → 本次重新确认的变更（spec 用户故事 23）：待执行（PLANNED）
      的就地改写（replaced，未执行＝无历史要保，身份与计划位置不变）；已成功
      （SUCCEEDED）的作为新步骤追加（不改写已执行的历史行）。

    返回（子批载荷、子批快照、子批解析、子批在原文中的索引、已覆盖项索引→既有
    operation id、参数变更项索引→既有 operation id）。依赖索引仍按**原始提交顺序**
    表达：新增项依赖被剔除项时，依赖经后者映射到既有 operation id（推进依赖判定
    同口径）。
    """
    keep: list[int] = []
    preset: dict[int, str] = {}
    replaced: dict[int, str] = {}
    for index, item in enumerate(payload.items):
        step: LiveStep | None = (
            covered.get((item.action.value, item.item_id)) if item.item_id is not None else None
        )
        if step is None:
            keep.append(index)
        elif step.params == resolved[index][1]:
            preset[index] = step.operation_id
        elif step.status == OperationStatus.PLANNED.value:
            keep.append(index)
            replaced[index] = step.operation_id
        else:
            keep.append(index)
    subset = payload.model_copy(update={"items": [payload.items[index] for index in keep]})
    return (
        subset,
        BatchPlanSnapshot(
            plan_version=snapshot.plan_version, items=[snapshot.items[index] for index in keep]
        ),
        [resolved[index] for index in keep],
        keep,
        preset,
        replaced,
    )


def _remap_step_refs(params: dict[str, Any], index_map: dict[int, int]) -> dict[str, Any]:
    """追加批次的输出引用坐标换算：引用 step 是本批局部索引，写入操作载荷与
    计划投影前换算为 Run 全局步骤编号（解析器 _resolve_step_refs 按全局编号取
    结果）。结构校验保证引用只指向本批更早项，映射必全（keep / preset / replaced
    三类覆盖全部索引）。"""
    remapped = dict(params)
    for name, ref in params_output_refs(params).items():
        remapped[name] = StepOutputRef(step=index_map[ref.step], field=ref.field).model_dump(
            mode="json"
        )
    return remapped


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
    replaced_operation_ids: dict[int, str] | None = None,
) -> list[BatchPlanItemOut]:
    """计划项 → PLANNED operations（计划顺序即推进顺序）＋ 计划投影写回 run。

    依赖索引按原始提交顺序解析为 operation id（同一次提交内更早的步骤；依赖被
    已覆盖项时经 preset_dependencies 挂到既有操作上）；输出引用的 step 同源换算
    为全局编号（已覆盖 / 就地改写项挂到既有条目的编号）；重规划延展时新批追加在
    既有计划之后，版本随之递增（已批准集合是「对象集合＋参数＋版本」的组合，
    spec 用户故事 23）。

    参数变更项（replaced_operation_ids：原始提交索引 → 既有待执行 operation id）
    就地改写该步骤的载荷 / 快照 / 授权依据：未执行＝无历史要保，身份与计划位置
    不变（依赖它的步骤不受影响），计划条目参数同步更新；已成功步骤的变更不走此
    路径（由调用方分类后作为新条目追加）。返回值含新建与就地改写两类条目（调用方
    以条数呈现本次实际生效的项）。

    写入口径严格读既有计划：损坏即拒绝追加（降级为空基线会把新计划写成「只剩
    本批」的残缺集合、索引失真，旧步骤的排序与依赖一并丢失；工单 05 review）。
    """
    now = utcnow()
    try:
        plan = require_plan_out(run.plan_json, run.plan_version)
    except PlanCorruptError as exc:
        raise _plan_invalid() from exc
    entry_by_operation = {entry.operation_id: entry for entry in plan.items}
    base_index = len(plan.items)
    # 原始提交索引 → Run 全局步骤编号：追加批次的引用 step 是本批局部索引，
    # 先建已覆盖（preset）部分的映射，keep 项在循环内按序登记。
    index_map: dict[int, int] = {
        original: entry_by_operation[operation_id].index
        for original, operation_id in (preset_dependencies or {}).items()
    }
    appended: list[BatchPlanItemOut] = []
    new_entries: list[BatchPlanItemOut] = []
    updated_params: dict[str, dict[str, Any]] = {}
    replacements = replaced_operation_ids or {}
    dependency_ids: dict[int, str] = dict(preset_dependencies or {})
    indexes = (
        submitted_indexes if submitted_indexes is not None else list(range(len(payload.items)))
    )
    for index, (item, (spec, params)) in enumerate(zip(payload.items, resolved, strict=True)):
        params = _remap_step_refs(params, index_map)
        existing_id = replacements.get(indexes[index])
        if existing_id is not None:
            index_map[indexes[index]] = entry_by_operation[existing_id].index
            operation = await session.get(AgentOperation, existing_id)
            assert operation is not None
            operation.payload_json = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
            operation.snapshot_json = json.dumps(
                snapshot.items[index].state, ensure_ascii=False, separators=(",", ":")
            )
            operation.authorization_json = authorization.model_dump_json()
            operation.proposal_id = proposal_id
            operation.updated_at = now
            dependency_ids[indexes[index]] = operation.id
            updated_params[operation.id] = params
            appended.append(entry_by_operation[operation.id].model_copy(update={"params": params}))
            continue
        # 目标定位只消费既有目标字段（具体值）：引用字段（值未定）不参与定位，
        # 剔除后判别再喂 resolver——含引用参数的修改类步骤（如归类到新建课程）
        # 提交时也能正常建 operation（引用注入在推进 worker，工单 06）。创建类
        # 步骤（item_id 空）无既有目标可定位，恒不 resolve（工单 07：create_goal
        # 的 resolver 消费 course_id，引用时值未定、model_construct 也不含该键）。
        target = None
        if spec.target_resolver is not None and item.item_id is not None:
            target = spec.target_resolver(
                _concrete_payload(spec, params, params_output_refs(params))
            )
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
        index_map[indexes[index]] = base_index + index
        entry = BatchPlanItemOut(
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
        new_entries.append(entry)
        appended.append(entry)
    items = [
        entry.model_copy(update={"params": updated_params[entry.operation_id]})
        if entry.operation_id in updated_params
        else entry
        for entry in plan.items
    ]
    run.plan_json = BatchPlanOut(
        plan_version=payload.plan_version, items=[*items, *new_entries]
    ).model_dump_json()
    run.updated_at = now
    return appended


def batch_route(
    *,
    auth_mode: AuthMode,
    active: AgentRun | None,
    items: list[BatchPlanItemPayload],
    resolved: list[tuple[OperationSpec[Any], dict[str, Any]]],
    covered: dict[tuple[str, str], LiveStep],
    session_operation_count: int,
) -> BatchRoute:
    """批量提交分流（spec 决策 10/11，纯判定）：直执行 / 计划卡 / 已在计划内。

    执行中（存在活跃 Run）需要动作的项一律升回确认：计划的对象集合＋参数＋版本即
    授权范围，超出范围的新目标与**参数变更**在完全访问档同样需要重新确认
    （spec 用户故事 23「改参数后重新确认」）；帮我批准档阈值只决定「一批全新或
    变更目标」能否自动生效，不放宽已运行计划的集合。等待态 Run 只接受显式唤醒
    （继续 / 重试），故经工具追加也转计划卡（确认即显式动作）。

    阈值计数为**会话累计**（`session_operation_count` 含已结束 Run 与已完成项）：
    首批完成、Run 落终态后不重置（spec 决策 11：计入已完成项，拆调用 / 分段 /
    重启不重置）；全新计划（无活跃 Run）同样先扣已用额度再判。
    """
    if auth_mode == AuthMode.REQUEST_APPROVAL:
        return BatchRoute.PLAN_CARD
    # 档位不允许自动执行的项（帮我批准档的 L2/L3）恒出计划卡逐项确认。
    if not all(should_execute_directly(auth_mode, spec.level) for spec, _params in resolved):
        return BatchRoute.PLAN_CARD
    if active is None:
        # 全新计划（无活跃 Run）：帮我批准档仍受阈值约束，超阈值出计划卡。
        if (
            auth_mode == AuthMode.AUTO_APPROVE
            and session_operation_count + len(items) > AUTO_APPROVE_BATCH_LIMIT
        ):
            return BatchRoute.PLAN_CARD
        return BatchRoute.DIRECT
    actionable = [
        item
        for item, (_spec, params) in zip(items, resolved, strict=True)
        if not _covered_unchanged(item, params, covered)
    ]
    if not actionable:
        return BatchRoute.ALREADY_PLANNED
    if active.status != RunStatus.RUNNING.value:
        return BatchRoute.PLAN_CARD
    if active.proposal_id is not None or auth_mode == AuthMode.FULL_ACCESS:
        # 执行中目标超出固定计划集合（完全访问档亦然，spec 用户故事 23）。
        return BatchRoute.PLAN_CARD
    if session_operation_count + len(actionable) > AUTO_APPROVE_BATCH_LIMIT:
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
        # 业务提交处最终校验（ChatTurn 规格 §2/§14）：持久取消先落库或执行
        # 身份失配 → 不建 Run、不落计划卡（取消后禁止新增副作用）。
        if not await runtime.turn_write_allowed(session):
            return {"ok": False, "error": CHAT_TURN_CANCELLED}
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
        # 阈值计数为会话累计：首批完成（Run 终态）后不重置（spec 决策 11）。
        session_count = await count_session_operations(session, runtime.session_id)
        covered: dict[tuple[str, str], LiveStep] = (
            await covered_targets(session, active) if active is not None else {}
        )
        route = batch_route(
            auth_mode=effective_mode,
            active=active,
            items=plan.items,
            resolved=resolved,
            covered=covered,
            session_operation_count=session_count,
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
        # 幂等口径：已覆盖项（参数一致）不重复建操作；参数变更项就地改写既有待执行
        # 步骤（直执行与确认路径都只落待执行子批）。
        (
            batch,
            batch_snapshot,
            batch_resolved,
            batch_indexes,
            preset,
            replaced,
        ) = pending_plan_batch(payload, snapshot, resolved, covered)
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
                replaced_operation_ids=replaced,
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
    # 幂等口径与直执行同源：参数一致的已覆盖项不重复建操作（同一目标不重做已成功项、
    # 不重复计数）；参数变更项就地改写待执行步骤或作为新步骤追加（spec 用户故事 23
    # 「改参数后重新确认」）；失败 / 跳过项不算覆盖——重新预览授权后仍会落新操作。
    covered = await covered_targets(session, run)
    (
        batch,
        batch_snapshot,
        batch_resolved,
        batch_indexes,
        preset,
        replaced,
    ) = pending_plan_batch(payload, snapshot, resolved, covered)
    await verify_plan_snapshots(session, batch_resolved, batch_snapshot, batch.items)
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
        replaced_operation_ids=replaced,
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
