"""执行事实查询与清理契约（spec 决策 2/3/21/22）＋批量计划卡契约（工单 05）。

枚举值与迁移 0030 的 CHECK 逐一对应；终态集合供清理守卫与查询过滤复用。
计划卡契约（BatchPlan*）是 OP_BATCH 提案载荷 / 快照 / 结果投影与 run.plan_json
的形状声明：载荷承载对象集合＋逐项参数＋计划版本（spec 决策 13），逐项参数
的真实执法在操作注册表的判别 schema（本模块只声明计划层结构）。
"""

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_serializer,
    model_validator,
)


def _iso_utc(value: datetime) -> str:
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _iso_utc_opt(value: datetime | None) -> str | None:
    return None if value is None else _iso_utc(value)


class AuthMode(StrEnum):
    """授权档位（ADR-0026；档位执行分流随 02 票落地，本票为授权事实的记录词汇）。"""

    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    AUTO_APPROVE = "AUTO_APPROVE"
    FULL_ACCESS = "FULL_ACCESS"


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    WAITING_USER = "WAITING_USER"
    WAITING_JOB = "WAITING_JOB"  # 第三阶段预留，本阶段无写入者
    COMPLETED = "COMPLETED"
    PARTIAL_COMPLETED = "PARTIAL_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class OperationStatus(StrEnum):
    PLANNED = "PLANNED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class ActivityType(StrEnum):
    AUTH_MODE_SWITCH = "AUTH_MODE_SWITCH"


class ActivityScope(StrEnum):
    GLOBAL = "GLOBAL"
    SESSION = "SESSION"


# 终态集合（清理守卫：仅终态可清理；提案审批事实永不删，spec 决策 21）。
RUN_TERMINAL_STATUSES = (
    RunStatus.COMPLETED,
    RunStatus.PARTIAL_COMPLETED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
)
OPERATION_TERMINAL_STATUSES = (
    OperationStatus.SUCCEEDED,
    OperationStatus.FAILED,
    OperationStatus.SKIPPED,
    OperationStatus.CANCELLED,
)

# 推进遇阻时转 WAITING_USER 等用户处理的错误码（spec 决策 7/8：冲突与需确认
# 保留任务等用户，其余单项失败按独立项继续）：
# - OPERATION_SNAPSHOT_STALE：目标在执行前发生变化（冲突，用户处理后继续）；
# - OPERATION_APPROVAL_REQUIRED：每步重检授权发现该操作已不能由固化档位自动
#   执行（需确认档位/重新授权）。
WAITABLE_OPERATION_ERROR_CODES = frozenset(
    {"OPERATION_SNAPSHOT_STALE", "OPERATION_APPROVAL_REQUIRED"}
)

# 依赖项未成功时置 SKIPPED 的错误码（依赖阻塞，spec 决策 8）。
OPERATION_DEPENDENCY_FAILED = "OPERATION_DEPENDENCY_FAILED"

# run.plan_json 结构损坏时的稳定错误码（工单 05 review）：损坏计划让推进顺序与
# 依赖判定静默失效——执行 / 写入路径必须显式失败，不得降级为空计划继续。
AGENT_RUN_PLAN_INVALID = "AGENT_RUN_PLAN_INVALID"

# 批量计划规模上限（单张计划卡项数上限；AUTO_APPROVE 的自动执行阈值见下）。
MAX_BATCH_PLAN_ITEMS = 50

# 「帮我批准」档同一任务的自动执行阈值（spec 决策 11 / Q9）：直接业务目标数
# 与写操作数均不超过 10；计入已完成项，拆工具调用 / 分段执行 / 重启不重置。
AUTO_APPROVE_BATCH_LIMIT = 10

# 计划项参数结构（action / depends_on）与逐项动作参数的边界见 plans.py。
_UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class BatchPlanAction(StrEnum):
    """计划项动作（值 = 操作注册表动作名，spec 决策 14：L2 批量归类 / 归档
    编排既有 L1 动作，不另立动作类型）。

    白名单枚举本阶段只含资料条目两类批量动作；新批量能力 = 扩展本枚举 ＋
    在 plans.BATCH_PLAN_ACTIONS 建立到注册表动作的映射 ＋ 逐项参数列补字段。
    """

    UPDATE_LIBRARY_ITEM = "update_library_item"
    ARCHIVE_LIBRARY_ITEM = "archive_library_item"


class BatchPlanItemPayload(BaseModel):
    """计划项（对象集合的逐项条目，spec 决策 13）。

    逐项参数以扁平列声明（update 动作消费 title / course_id，archive 动作只消费
    item_id）：可复用的无缝形状是「各动作参数 schema 字段的并集」，真实执法在
    提交/确认时按动作判别 schema 校验（registry），本层只做计划结构校验。
    """

    model_config = ConfigDict(extra="forbid")

    action: BatchPlanAction = Field(description="计划项动作")
    item_id: str = Field(
        pattern=_UUID_PATTERN, description="目标资料条目 id（经 search_library 消歧后取得）"
    )
    title: str | None = Field(
        default=None, min_length=1, description="条目新标题（归类动作不使用）"
    )
    course_id: str | None = Field(
        default=None, pattern=_UUID_PATTERN, description="归类目标课程 id（改标题不需要）"
    )
    depends_on: list[int] = Field(
        default_factory=list[int],
        description="依赖项在本计划内的索引（0 起、必须小于自身索引）；依赖项未成功则本项跳过",
    )


class BatchPlanPayload(BaseModel):
    """OP_BATCH 提案判别载荷（spec 决策 13）：对象集合＋逐项参数＋计划版本。

    plan_version / auth_mode / instruction_text 由提交路径注入（模型只能提供
    items）：版本在提交时按活跃 run 计算（重规划递增），档位与触发指令原文是
    Run 固化的授权依据素材（确认时随 run 落库）。
    """

    model_config = ConfigDict(extra="forbid")

    items: list[BatchPlanItemPayload] = Field(min_length=1, max_length=MAX_BATCH_PLAN_ITEMS)
    plan_version: int = Field(default=1, ge=1, description="计划版本（提交路径注入）")
    auth_mode: AuthMode = Field(default=AuthMode.REQUEST_APPROVAL, description="提交时生效档位")
    instruction_text: str | None = Field(
        default=None, description="触发指令原文（提交路径注入，Run 固化）"
    )

    @model_validator(mode="after")
    def _validate_plan_structure(self) -> "BatchPlanPayload":
        seen: set[tuple[str, str]] = set()
        for index, item in enumerate(self.items):
            for dependency in item.depends_on:
                if dependency < 0 or dependency >= index:
                    raise ValueError("依赖项索引必须是本计划内更早的步骤")
            key = (item.action.value, item.item_id)
            if key in seen:
                raise ValueError("同一计划内同一动作的同一目标不能重复")
            seen.add(key)
        return self


class BatchPlanItemSnapshot(BaseModel):
    """逐项执行前快照（spec 决策 12 的一份三用：确认卡预览 / 执行前重验 /
    Undo 补偿数据）：提交时同事务读取的目标当前态。"""

    model_config = ConfigDict(extra="forbid")

    action: BatchPlanAction
    item_id: str
    state: dict[str, Any] = Field(description="该动作 capture_state 的类型化快照投影")


class BatchPlanSnapshot(BaseModel):
    """OP_BATCH 提案快照：逐项快照按计划顺序对齐（索引一一对应）。"""

    model_config = ConfigDict(extra="forbid")

    plan_version: int = 1
    items: list[BatchPlanItemSnapshot] = Field(default_factory=list[BatchPlanItemSnapshot])


class BatchPlanItemOut(BaseModel):
    """run.plan_json 的计划项投影：逐项参数＋已建 operation 引用＋依赖的
    operation id（推进 worker 依赖判定与前端逐项呈现共用）。"""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    action: BatchPlanAction
    item_id: str
    params: dict[str, Any] = Field(default_factory=dict[str, Any])
    operation_id: str
    depends_on: list[str] = Field(default_factory=list[str])


class BatchPlanOut(BaseModel):
    """run.plan_json 的形状：计划版本＋逐项条目（已获批的对象集合，执行中
    重规划新增目标即超出本集合 → 升回确认，spec 用户故事 23）。"""

    model_config = ConfigDict(extra="forbid")

    plan_version: int = Field(ge=1)
    items: list[BatchPlanItemOut] = Field(default_factory=list[BatchPlanItemOut])


class PlanCorruptError(Exception):
    """run.plan_json 结构损坏（非法 JSON 或不符合 BatchPlanOut 形状）。

    执行 / 写入路径必须显式失败：损坏计划会让推进顺序与依赖判定静默失效，
    继续推进＝在失去依赖约束的对象集合上写业务事实；读取 / 展示路径
    （parse_plan_out）沿用降级口径，不阻断查询。
    """


def require_plan_out(plan_json: str | None, plan_version: int) -> BatchPlanOut:
    """执行 / 写入口径：坏值抛 PlanCorruptError（plan_json 为空＝尚无计划，合法）。"""
    if plan_json is None:
        return BatchPlanOut(plan_version=plan_version, items=[])
    try:
        return BatchPlanOut.model_validate(json.loads(plan_json))
    except (ValueError, ValidationError) as exc:
        raise PlanCorruptError(plan_version) from exc


def parse_plan_out(plan_json: str | None, plan_version: int) -> BatchPlanOut:
    """读取 / 展示口径：坏值降级为空计划（不阻断查询与呈现）。"""
    try:
        return require_plan_out(plan_json, plan_version)
    except PlanCorruptError:
        return BatchPlanOut(plan_version=plan_version, items=[])


def plan_dependencies(plan: BatchPlanOut) -> dict[str, list[str]]:
    """操作 id → 依赖的操作 id 列表（推进与重试的依赖判定口径）。"""
    return {item.operation_id: list(item.depends_on) for item in plan.items}


class BatchPlanResult(BaseModel):
    """OP_BATCH 结果投影（提案 result_json，回执卡）：本次计划落到哪个 Run。"""

    run_id: str
    plan_version: int
    item_count: int


class OperationAuthorization(BaseModel):
    """operation.authorization_json 的形状（ADR-0026 授权依据）。

    确认路径：档位恒 REQUEST_APPROVAL、trigger=USER_CONFIRMED_PROPOSAL、
    指令摘录为空（提案框架未携带触发指令原文）；直执行（工单 02）沿同列
    回填 trigger=AUTO_EXECUTED、当轮档位与触发指令摘录。单步无 run 时
    本列是授权事实的唯一载体。UI 显式撤销（工单 06）trigger=USER_UNDO
    ——按钮点击即用户授权直接建补偿 operation，不经提案档位。
    """

    model_config = ConfigDict(extra="forbid")

    auth_mode: AuthMode = AuthMode.REQUEST_APPROVAL
    trigger: Literal["USER_CONFIRMED_PROPOSAL", "AUTO_EXECUTED", "USER_UNDO"] = (
        "USER_CONFIRMED_PROPOSAL"
    )
    instruction_excerpt: str | None = None
    session_id: str | None = None
    message_id: str | None = None


class UndoOperationPayload(BaseModel):
    """OP_UNDO 提案判别载荷（工单 06，spec 决策 19）：撤销目标的原 operation id。

    经 Agent 的 undo 工具在默认档落提案（走三档授权）；operation_id 由模型
    从此前的执行回执（operation_id 键）取得。快照＝提交时原操作目标的当前
    态（确认卡预览用；确认时撤销前重验由补偿器执法）。"""

    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(
        pattern=_UUID_PATTERN,
        description="要撤销的操作 id（此前操作回执中的 operation_id）",
    )


class AgentOperationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str | None
    proposal_id: str | None
    action: str
    level: str
    target_type: str | None
    target_id: str | None
    payload: dict[str, Any] = {}
    snapshot: dict[str, Any] | None = None
    authorization: dict[str, Any] | None = None
    status: str
    attempts: int
    attempts_history: list[dict[str, Any]] | None = None
    result: dict[str, Any] | None = None
    error_code: str | None
    undoable: bool = False
    undo_reason: str | None = None
    undo_of: str | None
    undone_by: str | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None

    @field_serializer("created_at", "updated_at")
    def _ser(self, value: datetime) -> str:
        return _iso_utc(value)

    @field_serializer("finished_at")
    def _ser_opt(self, value: datetime | None) -> str | None:
        return _iso_utc_opt(value)


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str | None
    auth_mode: AuthMode
    instruction_text: str | None
    proposal_id: str | None
    status: str
    plan: dict[str, Any] | None = None
    plan_version: int
    waiting_reason: str | None
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None

    @field_serializer("created_at", "updated_at")
    def _ser(self, value: datetime) -> str:
        return _iso_utc(value)

    @field_serializer("finished_at")
    def _ser_opt(self, value: datetime | None) -> str | None:
        return _iso_utc_opt(value)


class AgentRunDetailOut(AgentRunOut):
    operations: list[AgentOperationOut] = []


class AgentActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    activity_type: ActivityType
    from_mode: AuthMode
    to_mode: AuthMode
    scope: ActivityScope
    session_id: str | None
    created_at: datetime

    @field_serializer("created_at")
    def _ser(self, value: datetime) -> str:
        return _iso_utc(value)


class RunListQuery(BaseModel):
    status: RunStatus | None = None
    session_id: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class OperationListQuery(BaseModel):
    status: OperationStatus | None = None
    session_id: str | None = Field(
        default=None, description="按触发会话过滤（授权依据列 JSON 投影）"
    )
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ActivityListQuery(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class PurgeResultOut(BaseModel):
    runs_deleted: int
    operations_deleted: int


class RunUndoItemOut(BaseModel):
    """批次撤销的逐项结果（工单 06：单项补偿失败不谎报整体成功）。"""

    model_config = ConfigDict(extra="forbid")

    operation_id: str
    action: str
    status: str
    error_code: str | None = None
    compensation_id: str | None = None


class RunUndoResultOut(BaseModel):
    """run 级批次 Undo 回执：按依赖逆序补偿、逐项结果如实呈现。"""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    undone_count: int
    failed_count: int
    items: list[RunUndoItemOut] = Field(default_factory=list[RunUndoItemOut])


# ---------------------------------------------------------------------------
# 授权档位 API 契约（工单 02：设置页全局默认档 + 会话切换审计）


class AgentAuthModeOut(BaseModel):
    """当前全局默认授权档（settings.json 偏离项，缺省 REQUEST_APPROVAL）。"""

    model_config = ConfigDict(extra="forbid")

    auth_mode: AuthMode


class AgentAuthModeSwitch(BaseModel):
    """全局默认档切换请求：只声明目标档，from 由后端自读 settings.json
    （审计链权威口径——客户端缓存过期时不上报失真的 from）。"""

    model_config = ConfigDict(extra="forbid")

    to_mode: AuthMode


class AgentAuthModeSessionSwitch(BaseModel):
    """会话内临时切档的审计行（会话档位本身是前端按会话内存，不落库）。
    from 由客户端上报：会话生效档（覆盖 ?? 全局默认）在后端无从得知。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=36)
    from_mode: AuthMode
    to_mode: AuthMode
